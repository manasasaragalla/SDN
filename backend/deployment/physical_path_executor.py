"""Operation-scoped deployment for exact physical-path flow rules."""

from __future__ import annotations

import secrets

from backend.deployment import ofctl_client
from backend.models.deployment import (
    PhysicalCleanupResult,
    PhysicalCleanupState,
    PhysicalDeploymentResult,
    PhysicalDeploymentState,
)
from backend.models.flow import MAX_COOKIE, FlowRule

COOKIE_MASK = MAX_COOKIE
COOKIE_ALLOCATION_ATTEMPTS = 16
_FIELD_ALIASES = {
    "eth_type": "dl_type",
    "ipv4_src": "nw_src",
    "ipv4_dst": "nw_dst",
}
_OWNED_OPERATIONS: dict[int, tuple[int, ...]] = {}


def deploy_physical_path_rules(
    rules: list[FlowRule],
    base_url: str = ofctl_client.DEFAULT_BASE_URL,
) -> PhysicalDeploymentResult:
    """Install and verify rules under one cookie, without retrying ambiguous POSTs."""
    if not rules:
        raise ValueError("At least one physical-path flow rule is required")
    if any(not isinstance(rule, FlowRule) for rule in rules):
        raise ValueError("rules must contain only FlowRule models")
    if any(rule.cookie is not None for rule in rules):
        raise ValueError("Physical-path rules must not already have a cookie")

    dpids = tuple(sorted({rule.dpid for rule in rules}))
    existing_flows: dict[int, list[dict]] = {}
    preflight_errors: list[str] = []
    for dpid in dpids:
        status, flows, error = _read_flows(dpid, base_url)
        if status != 200:
            preflight_errors.append(
                f"Could not inspect DPID {dpid} before deployment: {error}"
            )
        else:
            existing_flows[dpid] = flows

    if preflight_errors:
        return PhysicalDeploymentResult(
            operation_cookie=None,
            dpids=dpids,
            requested_count=len(rules),
            accepted_count=0,
            verified_count=0,
            state=PhysicalDeploymentState.FAILED,
            errors=preflight_errors,
        )

    operation_cookie = _allocate_cookie(existing_flows, dpids)
    _OWNED_OPERATIONS[operation_cookie] = dpids
    owned_rules = [
        rule.model_copy(update={"cookie": operation_cookie}) for rule in rules
    ]
    accepted_count = 0
    post_statuses: list[tuple[int, str]] = []
    errors: list[str] = []
    for rule in owned_rules:
        status, response = _post_flow(
            f"{base_url}/stats/flowentry/add",
            rule.to_ofctl_payload(),
        )
        post_statuses.append((status, response))
        if status == 200:
            accepted_count += 1
        elif status == 0:
            errors.append(
                f"Ambiguous add response for {rule.label or rule.match}: {response}"
            )
        else:
            errors.append(
                f"Add rejected for {rule.label or rule.match}: HTTP {status} {response}"
            )

    flows_by_dpid: dict[int, list[dict]] = {}
    read_errors: list[str] = []
    for dpid in dpids:
        status, flows, error = _read_flows(dpid, base_url)
        if status == 200:
            flows_by_dpid[dpid] = flows
        else:
            read_errors.append(f"Could not verify DPID {dpid}: {error}")
    errors.extend(read_errors)

    verified_count = 0
    reconciled_count = 0
    unresolved_ambiguous = False
    for rule, (post_status, _) in zip(owned_rules, post_statuses, strict=True):
        flows = flows_by_dpid.get(rule.dpid)
        if flows is None:
            if post_status == 0:
                unresolved_ambiguous = True
            continue
        if _owned_rule_is_present(rule, flows):
            verified_count += 1
            if post_status == 0:
                reconciled_count += 1
        elif post_status == 0:
            unresolved_ambiguous = True

    if read_errors or unresolved_ambiguous:
        state = PhysicalDeploymentState.UNCERTAIN
    elif verified_count == len(owned_rules):
        state = PhysicalDeploymentState.SUCCEEDED
    elif verified_count:
        state = PhysicalDeploymentState.PARTIAL
    else:
        state = PhysicalDeploymentState.FAILED

    return PhysicalDeploymentResult(
        operation_cookie=operation_cookie,
        dpids=dpids,
        requested_count=len(owned_rules),
        accepted_count=accepted_count,
        verified_count=verified_count,
        reconciled_count=reconciled_count,
        state=state,
        errors=errors,
    )


def cleanup_physical_path_deployment(
    deployment: PhysicalDeploymentResult,
    base_url: str = ofctl_client.DEFAULT_BASE_URL,
) -> PhysicalCleanupResult:
    """Delete only the deployment cookie on DPIDs recorded by that operation."""
    if not isinstance(deployment, PhysicalDeploymentResult):
        raise ValueError("deployment must be a PhysicalDeploymentResult")
    cookie = deployment.operation_cookie
    dpids = tuple(sorted(set(deployment.dpids)))
    if (
        type(cookie) is not int
        or not 0 < cookie <= MAX_COOKIE
        or not dpids
        or any(type(dpid) is not int or dpid <= 0 for dpid in dpids)
        or _OWNED_OPERATIONS.get(cookie) != dpids
    ):
        raise ValueError(
            "deployment must belong to an active operation with a valid cookie and DPID scope"
        )

    accepted = 0
    errors: list[str] = []
    for dpid in dpids:
        status, response = _post_flow(
            f"{base_url}/stats/flowentry/delete",
            {
                "dpid": dpid,
                "cookie": cookie,
                "cookie_mask": COOKIE_MASK,
                "table_id": "ALL",
            },
        )
        if status == 200:
            accepted += 1
        else:
            errors.append(
                f"Cookie-scoped delete failed on DPID {dpid}: "
                f"HTTP/status {status} {response}"
            )

    remaining = 0
    read_failed = False
    for dpid in dpids:
        status, flows, error = _read_flows(dpid, base_url)
        if status != 200:
            read_failed = True
            errors.append(f"Could not verify cleanup on DPID {dpid}: {error}")
            continue
        remaining += sum(_flow_cookie(flow) == cookie for flow in flows)

    if read_failed:
        state = PhysicalCleanupState.UNCERTAIN
        remaining_count: int | None = None
    elif remaining:
        state = (
            PhysicalCleanupState.UNCERTAIN
            if any("status 0 " in error for error in errors)
            else PhysicalCleanupState.FAILED
        )
        remaining_count = remaining
    else:
        state = PhysicalCleanupState.SUCCEEDED
        remaining_count = 0
        _OWNED_OPERATIONS.pop(cookie, None)

    return PhysicalCleanupResult(
        operation_cookie=cookie,
        requested_dpids=dpids,
        accepted_delete_count=accepted,
        remaining_flow_count=remaining_count,
        state=state,
        errors=errors,
    )


def _allocate_cookie(
    existing_flows: dict[int, list[dict]], dpids: tuple[int, ...]
) -> int:
    used_cookies = {
        cookie
        for dpid in dpids
        for flow in existing_flows.get(dpid, [])
        if (cookie := _flow_cookie(flow)) is not None
    }
    used_cookies.update(_OWNED_OPERATIONS)
    for _ in range(COOKIE_ALLOCATION_ATTEMPTS):
        candidate = secrets.randbits(64)
        if candidate and candidate not in used_cookies:
            return candidate
    raise RuntimeError("Could not allocate an unused physical-deployment cookie")


def _post_flow(url: str, payload: dict) -> tuple[int, str]:
    # One attempt only: a timeout is ambiguous and must be reconciled by cookie.
    return ofctl_client._post_json(url, payload, max_retries=0)


def _read_flows(
    dpid: int, base_url: str
) -> tuple[int, list[dict], str]:
    try:
        status, data = ofctl_client._get_json(f"{base_url}/stats/flow/{dpid}")
    except (ValueError, TypeError) as exc:
        return 0, [], f"invalid flow statistics response: {exc}"
    if status != 200:
        return status, [], "flow statistics request failed"
    if not isinstance(data, dict) or not isinstance(data.get(str(dpid)), list):
        return 0, [], "flow statistics response is missing the requested DPID"
    flows = data[str(dpid)]
    if any(not isinstance(flow, dict) for flow in flows):
        return 0, [], "flow statistics response contains a malformed entry"
    return 200, flows, ""


def _flow_cookie(flow: dict) -> int | None:
    value = flow.get("cookie")
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 0 <= value <= MAX_COOKIE:
        return value
    if isinstance(value, str):
        try:
            parsed = int(value, 0)
        except ValueError:
            return None
        if 0 <= parsed <= MAX_COOKIE:
            return parsed
    return None


def _owned_rule_is_present(rule: FlowRule, flows: list[dict]) -> bool:
    expected_match = {
        _FIELD_ALIASES.get(key, key): value for key, value in rule.match.items()
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

    for flow in flows:
        try:
            priority = int(flow.get("priority"))
        except (TypeError, ValueError):
            continue
        if (
            _flow_cookie(flow) == rule.cookie
            and priority == rule.priority
            and flow.get("match") == expected_match
            and flow.get("actions") == expected_actions
        ):
            return True
    return False
