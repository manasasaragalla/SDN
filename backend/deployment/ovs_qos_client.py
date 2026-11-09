"""Deployment client for OVS QoS queues via `ovs-vsctl` (see
docs/adr-004-bandwidth-mechanism.md for why this, and not OpenFlow
meters, is this project's per-flow rate-limiting mechanism).

Runs `ovs-vsctl` as a plain subprocess, not through a Mininet node object:
every switch in this project's topology is created with the default
Mininet OVSSwitch (inNamespace=False), so its interfaces and the OVS
instance managing them are directly reachable from this same root network
namespace -- exactly like backend/deployment/ofctl_client.py doesn't need
a Mininet object to reach Ryu's REST API over plain HTTP.
"""
from __future__ import annotations

import re
import subprocess

from backend.models.qos import QueueConfig

OVS_VSCTL = "ovs-vsctl"
PROJECT_OWNER = "sdn-intent-agent"
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _run(args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run([OVS_VSCTL, *args], capture_output=True, text=True, timeout=10)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _owned_by_project(table: str, row_uuid: str) -> bool | None:
    rc, owner, _ = _run(
        ["get", table, row_uuid, "external_ids:owner"]
    )
    if rc != 0:
        return None
    return owner.strip().strip('"') == PROJECT_OWNER


def clear_queue(queue: QueueConfig) -> bool:
    """Remove only project-owned QoS resources attached to this interface.

    An unowned QoS row is left untouched and prevents replacement; the
    caller must not silently overwrite another application's configuration.
    """
    rc, qos_output, _ = _run(["get", "port", queue.intf, "qos"])
    if rc != 0:
        return False

    qos_match = _UUID_RE.search(qos_output)
    if qos_match is None:
        return qos_output.strip() in ("", "[]")

    qos_uuid = qos_match.group(0)
    is_owned = _owned_by_project("qos", qos_uuid)
    if is_owned is not True:
        return False

    rc, queues_output, _ = _run(["get", "qos", qos_uuid, "queues"])
    if rc != 0:
        return False

    owned_queue_uuids: list[str] = []
    for queue_uuid in _UUID_RE.findall(queues_output):
        queue_is_owned = _owned_by_project("queue", queue_uuid)
        if queue_is_owned is not True:
            return False
        owned_queue_uuids.append(queue_uuid)

    cleanup_args = [
        "clear", "port", queue.intf, "qos",
        "--",
        "destroy", "qos", qos_uuid,
    ]
    for queue_uuid in owned_queue_uuids:
        cleanup_args.extend(["--", "destroy", "queue", queue_uuid])

    rc, _, _ = _run(cleanup_args)
    return rc == 0


def deploy_queue(queue: QueueConfig) -> bool:
    """Creates a linux-htb QoS record with one queue capped at
    max_rate_bps, attaches it to queue.intf, and reads the port's `qos`
    column back to confirm the attachment actually took (Step 6's
    "verify... not just trust a 200 response", applied here to
    ovs-vsctl's equivalent: a zero exit code alone)."""
    if not clear_queue(queue):
        return False

    rc, _, err = _run([
        "--",
        "set", "port", queue.intf, "qos=@newqos",
        "--",
        "--id=@newqos", "create", "qos", "type=linux-htb",
        f"external_ids:owner={PROJECT_OWNER}",
        f"queues:{queue.queue_id}=@q0",
        "--",
        "--id=@q0", "create", "queue",
        f"other-config:max-rate={queue.max_rate_bps}",
        f"external_ids:owner={PROJECT_OWNER}",
    ])
    if rc != 0:
        return False

    rc, out, _ = _run(["get", "port", queue.intf, "qos"])
    return rc == 0 and out not in ("", "[]")


def verify_queue_rate(queue: QueueConfig) -> bool:
    """Independent re-check that the deployed queue's configured max-rate
    is actually what was requested, by reading the Queue table back --
    the OVS-side analogue of ofctl_client._rule_is_present, so a
    successful-looking deploy_queue() call can still be caught if OVS
    silently used different config than what was asked for."""
    rc, out, _ = _run(["get", "port", queue.intf, "qos"])
    if rc != 0 or out in ("", "[]"):
        return False
    rc, out, _ = _run(["--columns=other_config", "list", "queue"])
    if rc != 0:
        return False
    return f"max-rate=\"{queue.max_rate_bps}\"" in out or f"max-rate={queue.max_rate_bps}" in out
