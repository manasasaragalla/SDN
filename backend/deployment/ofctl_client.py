"""Deployment client for Ryu's ryu.app.ofctl_rest REST API (see
docs/adr-002-topology-source-and-deployment.md for why this app was
chosen over a bespoke Ryu controller app).

Uses only the standard library (urllib) -- no extra HTTP dependency for
what is a handful of small JSON POSTs/GETs.

Important environment note this module encodes a fix for: Mininet's
OVSSwitch leaves the bridge's OpenFlow protocol list unset by default,
which risks not landing on OpenFlow13 (which ofctl_rest's OXM-style match
fields like ipv4_src/arp_spa require). testbed/topology/diamond.py pins
protocols="OpenFlow13" explicitly for exactly this reason -- verified
empirically: without it, POSTed flows silently vanish (200 OK, but never
appear in a subsequent flow-table read); with it, they install and are
readable back immediately.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from backend.models.deployment import DeploymentResult
from backend.models.flow import FlowRule

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
REQUEST_TIMEOUT_S = 10
MAX_TRANSPORT_RETRIES = 2  # bounded, deterministic -- never retries forever
RETRY_DELAY_S = 0.5

# A real problem this fixes, found running the Phase 13 evaluation harness
# (evaluation/run_evaluation.py) for dozens of sequential real deploy/
# delete/measure cycles in one session: an occasional single REST call to
# Ryu's ofctl_rest stalls past REQUEST_TIMEOUT_S even though Ryu and OVS
# are both observably healthy immediately before and after -- a transient
# transport hiccup under sustained load, not a real rejection. Previously
# this raised an uncaught TimeoutError straight out of urllib, crashing
# the whole process (and, in the evaluation harness, losing every real
# run already completed in that session). A bounded retry on a transport-
# level failure (never on an HTTP-level error response, which is a real
# rejection and is returned as-is) is the minimal fix: still fails loudly
# and honestly (as a real DeploymentResult error, not silently) if the
# retries are exhausted, but survives a one-off stall instead of losing
# an entire evaluation sweep to it.

_TRANSPORT_ERRORS = (TimeoutError, urllib.error.URLError, ConnectionError, OSError)


def _post_json(url: str, payload: dict, max_retries: int = MAX_TRANSPORT_RETRIES) -> tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")
        except _TRANSPORT_ERRORS as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(RETRY_DELAY_S)
    return 0, f"transport error after {max_retries + 1} attempt(s): {last_exc}"


def _get_json(url: str, max_retries: int = MAX_TRANSPORT_RETRIES) -> tuple[int, dict]:
    req = urllib.request.Request(url, method="GET")
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, {}
        except _TRANSPORT_ERRORS as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(RETRY_DELAY_S)
    return 0, {}


def add_flow(rule: FlowRule, base_url: str = DEFAULT_BASE_URL) -> bool:
    status, _ = _post_json(f"{base_url}/stats/flowentry/add", rule.to_ofctl_payload())
    return status == 200


def delete_flow(rule: FlowRule, base_url: str = DEFAULT_BASE_URL) -> bool:
    status, _ = _post_json(f"{base_url}/stats/flowentry/delete", rule.to_ofctl_payload())
    return status == 200


def get_flows(dpid: int, base_url: str = DEFAULT_BASE_URL) -> list[dict]:
    status, data = _get_json(f"{base_url}/stats/flow/{dpid}")
    if status != 200:
        return []
    return data.get(str(dpid), [])


def _rule_is_present(rule: FlowRule, installed_flows: list[dict]) -> bool:
    """Ryu's flow-read reports OF1.3 fields under short names (dl_type,
    nw_src, nw_dst, arp_spa, arp_tpa, ...) that don't exactly match the
    OXM names ofctl_rest's *write* API accepts (eth_type, ipv4_src, ...).
    Compare the complete normalized match, priority, and ordered action
    list rather than accepting a partially matching flow-table entry."""
    field_aliases = {
        "eth_type": "dl_type",
        "ipv4_src": "nw_src",
        "ipv4_dst": "nw_dst",
        "arp_spa": "arp_spa",
        "arp_tpa": "arp_tpa",
    }
    expected_actions: list[str] = []
    for action in rule.actions:
        if action.get("type") == "OUTPUT" and "port" in action:
            expected_actions.append(f"OUTPUT:{action['port']}")
        elif action.get("type") == "SET_QUEUE" and "queue_id" in action:
            expected_actions.append(f"SET_QUEUE:{action['queue_id']}")
        else:
            return False

    if not expected_actions:
        return False

    for flow in installed_flows:
        try:
            if int(flow.get("priority")) != rule.priority:
                continue
        except (TypeError, ValueError):
            continue

        flow_match = flow.get("match", {})
        expected_match = {
            field_aliases.get(key, key): value
            for key, value in rule.match.items()
        }
        if flow_match == expected_match:
            flow_actions = flow.get("actions", [])
            if flow_actions == expected_actions:
                return True
    return False


def deploy_rules(rules: list[FlowRule], base_url: str = DEFAULT_BASE_URL) -> DeploymentResult:
    """Deploys rules and verifies each one is actually present in the
    switch's flow table afterwards -- Step 6 of the brief explicitly
    requires not trusting a 200 response alone."""
    errors: list[str] = []
    accepted = 0
    for rule in rules:
        if add_flow(rule, base_url):
            accepted += 1
        else:
            errors.append(f"POST rejected for rule: {rule.label or rule.match}")

    # Re-read each distinct dpid's flow table once and check every rule
    # against it, rather than one GET per rule.
    flows_by_dpid: dict[int, list[dict]] = {}
    verified = 0
    for rule in rules:
        if rule.dpid not in flows_by_dpid:
            flows_by_dpid[rule.dpid] = get_flows(rule.dpid, base_url)
        if _rule_is_present(rule, flows_by_dpid[rule.dpid]):
            verified += 1
        else:
            errors.append(f"rule not found in flow table after deploy: {rule.label or rule.match} @ dpid={rule.dpid}")

    return DeploymentResult(
        requested_count=len(rules),
        accepted_count=accepted,
        verified_count=verified,
        errors=errors,
    )


def delete_rules(rules: list[FlowRule], base_url: str = DEFAULT_BASE_URL) -> None:
    for rule in rules:
        delete_flow(rule, base_url)
