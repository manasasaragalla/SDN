"""Pre-deployment validation (brief section 15/22). Runs before anything
is compiled or sent to Ryu. Checks that never touch the network -- pure
functions over the TopologyGraph and the proposed path/action, so they
can be unit tested without mininet.
"""
from __future__ import annotations

from backend.models.flow import FlowRule
from backend.models.network import TopologyGraph
from backend.models.validation import ValidationResult

SUPPORTED_ACTIONS = {"REROUTE", "RATE_LIMIT"}
MIN_PRIORITY, MAX_PRIORITY = 1, 65535


def validate_path_for_reroute(
    graph: TopologyGraph,
    action: str,
    path: list[str],
    src_ip: str,
    dst_ip: str,
) -> ValidationResult:
    """Structural + topological validation of a proposed REROUTE, before
    any FlowRule is compiled."""
    reasons: list[str] = []

    if action not in SUPPORTED_ACTIONS:
        reasons.append(f"unsupported action: {action} (supported: {sorted(SUPPORTED_ACTIONS)})")
        # An unsupported action makes every other check meaningless (there's
        # no compiler for it), so stop here rather than piling on noise.
        return ValidationResult.fail(*reasons)

    topology_reason = graph.validate_path(path)
    if topology_reason is not None:
        reasons.append(topology_reason)
        return ValidationResult.fail(*reasons)

    source_host, dest_host = path[0], path[-1]
    if graph.hosts[source_host].ip != src_ip:
        reasons.append(
            f"src_ip {src_ip} does not match {source_host}'s actual IP ({graph.hosts[source_host].ip})"
        )
    if graph.hosts[dest_host].ip != dst_ip:
        reasons.append(
            f"dst_ip {dst_ip} does not match {dest_host}'s actual IP ({graph.hosts[dest_host].ip})"
        )
    if src_ip == dst_ip:
        reasons.append("src_ip and dst_ip must differ")

    if reasons:
        return ValidationResult.fail(*reasons)
    return ValidationResult.ok()


def validate_path_for_bandwidth(
    graph: TopologyGraph,
    path: list[str],
    src_ip: str,
    dst_ip: str,
    target_mbps: float,
) -> ValidationResult:
    """Pre-deployment feasibility check for a MIN_BANDWIDTH candidate
    (brief Step 7: "reject infeasible targets... before deployment", e.g.
    "requesting 50 Mbps over a 10 Mbps path"). Runs the same structural
    checks validate_path_for_reroute does (this path IS a REROUTE
    structurally -- MIN_BANDWIDTH still needs the primary flow's path
    installed, see docs/adr-004), plus one bandwidth-specific check: the
    path's static bottleneck capacity (TopologyGraph.path_capacity_mbps,
    from real TCLink bw= values) must be at least target_mbps.

    This is deliberately a topology fact, not a promise the target will be
    achieved -- real contention (background traffic) or software-
    forwarding overhead can still make a topologically-feasible target
    fail in practice, which is exactly what the post-deployment iperf3
    measurement (backend/measurement/throughput.py) is for. This check
    only rules out targets that are provably impossible before spending
    any time deploying and measuring them.
    """
    reasons: list[str] = []

    structural = validate_path_for_reroute(graph, "REROUTE", path, src_ip, dst_ip)
    if not structural.valid:
        reasons.extend(structural.reasons)
        return ValidationResult.fail(*reasons)

    capacity = graph.path_capacity_mbps(path)
    if capacity is not None and capacity < target_mbps:
        reasons.append(
            f"path capacity ({capacity} Mbps) is below the requested target ({target_mbps} Mbps); "
            "this path cannot satisfy this intent regardless of contention"
        )

    if target_mbps <= 0:
        reasons.append(f"target_mbps must be positive, got {target_mbps}")

    if reasons:
        return ValidationResult.fail(*reasons)
    return ValidationResult.ok()


def validate_rate_limit(rate_mbps: float, path_capacity_mbps: float | None = None) -> ValidationResult:
    """Validates a RATE_LIMIT action's own proposed rate (used for the
    background/competing flow, see docs/adr-004): the rate must be
    positive, and if the link's static capacity is known, the rate can't
    exceed it (asking OVS to cap a flow at more than the link can ever
    carry is not a meaningful configuration)."""
    reasons: list[str] = []
    if rate_mbps <= 0:
        reasons.append(f"rate_mbps must be positive, got {rate_mbps}")
    if path_capacity_mbps is not None and rate_mbps > path_capacity_mbps:
        reasons.append(
            f"requested rate ({rate_mbps} Mbps) exceeds the link's static capacity ({path_capacity_mbps} Mbps)"
        )
    if reasons:
        return ValidationResult.fail(*reasons)
    return ValidationResult.ok()


def validate_flow_rules(graph: TopologyGraph, rules: list[FlowRule]) -> ValidationResult:
    """Validates already-compiled rules before they're sent to Ryu: every
    dpid is a real switch in the topology, priorities are in OpenFlow's
    valid range, and no two rules for the same dpid have an identical
    match with different actions (a direct, deployable conflict)."""
    reasons: list[str] = []
    known_dpids = set(graph.switches.values())

    seen: dict[tuple[int, tuple], list[dict]] = {}
    for rule in rules:
        if rule.dpid not in known_dpids:
            reasons.append(f"rule targets unknown dpid: {rule.dpid}")
        if not (MIN_PRIORITY <= rule.priority <= MAX_PRIORITY):
            reasons.append(f"rule priority out of range: {rule.priority}")

        key = (rule.dpid, tuple(sorted(rule.match.items(), key=lambda kv: kv[0])))
        seen.setdefault(key, []).append(rule.actions)

    for key, action_lists in seen.items():
        distinct = {tuple(tuple(sorted(a.items())) for a in actions) for actions in action_lists}
        if len(distinct) > 1:
            reasons.append(f"conflicting rules for dpid={key[0]} match={dict(key[1])}: {action_lists}")

    if reasons:
        return ValidationResult.fail(*reasons)
    return ValidationResult.ok()
