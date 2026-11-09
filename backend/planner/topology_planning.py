"""Side-effect-free candidate ranking from explicitly configured topology facts."""

from __future__ import annotations

from math import prod
from typing import Any

from backend.models.canonical_intent import CanonicalIntent, Comparison
from backend.models.fingerprints import model_fingerprint
from backend.models.network import Link, TopologyGraph
from backend.planner.path_enumeration import (
    ConnectionKind,
    EnumeratedPath,
    enumerate_candidate_paths,
    physical_path_capacity_mbps,
)

DEFAULT_CANDIDATE_LIMIT = 128


def plan_on_topology(
    intent: CanonicalIntent,
    graph: TopologyGraph,
    *,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    """Enumerate and rank paths using configured capacity, delay and loss only.

    Configured link values are design facts, not measured throughput or live
    latency evidence. Unsupported or incomplete metrics remain UNKNOWN and
    cannot be used to claim a constraint passes.
    """
    enumeration = enumerate_candidate_paths(
        graph,
        intent.scope.source,
        intent.scope.destination,
        candidate_limit,
    )
    candidates: list[dict[str, Any]] = []
    for path in enumeration.paths:
        metrics, links = _path_facts(graph, path)
        constraint_results = [
            _evaluate_constraint(constraint, metrics)
            for constraint in intent.constraints
        ]
        statuses = [result["status"] for result in constraint_results]
        if "VIOLATED" in statuses:
            candidate_status = "REJECTED"
        elif all(status == "SATISFIED" for status in statuses):
            candidate_status = "ELIGIBLE"
        else:
            candidate_status = "UNKNOWN"
        candidates.append(
            {
                "candidate_id": model_fingerprint(path),
                "path": list(path.nodes),
                "physical_links": links,
                "configured_metrics": metrics,
                "constraints": constraint_results,
                "status": candidate_status,
                "selection": "NOT_SELECTED",
                "reasons": _candidate_reasons(
                    constraint_results,
                    candidate_status,
                    metrics,
                ),
            }
        )

    eligible = [item for item in candidates if item["status"] == "ELIGIBLE"]
    selected: dict[str, Any] | None = None
    selection_reason: str | None = None
    optimization = intent.optimization
    if eligible:
        if optimization is None:
            selected = eligible[0]
            selection_reason = (
                "Selected the first eligible path in deterministic physical-path order; "
                "no optimization objective was requested."
            )
        else:
            objective_key = _metric_key(optimization.metric)
            if objective_key is None:
                selection_reason = (
                    f"Optimization metric {optimization.metric!r} has no configured "
                    "topology fact available for ranking."
                )
            elif any(item["configured_metrics"][objective_key] is None for item in eligible):
                selection_reason = (
                    f"Configured {optimization.metric} is missing for at least one "
                    "eligible path; objective ranking was not performed."
                )
            else:
                reverse = optimization.direction.value == "MAXIMIZE"
                selected = sorted(
                    eligible,
                    key=lambda item: (
                        item["configured_metrics"][objective_key],
                        item["candidate_id"],
                    ),
                    reverse=reverse,
                )[0]
                selection_reason = (
                    f"Ranked eligible candidates by configured "
                    f"{optimization.metric} ({optimization.direction.value.lower()})."
                )
                if len(eligible) == 1:
                    selection_reason += (
                        " Only one candidate satisfied all known hard constraints; "
                        "this is not a comparative optimization result."
                    )

    if selected is not None:
        selected["selection"] = "SELECTED"
        selected["reasons"].append(selection_reason or "Selected.")
        status = "SELECTED"
    elif not enumeration.paths:
        status = "NO_PATH"
        selection_reason = "No physical path connects the selected hosts."
    elif not eligible and all(item["status"] == "REJECTED" for item in candidates):
        status = "NO_ELIGIBLE_PATH"
        selection_reason = "Every candidate violates at least one configured hard constraint."
    elif any(item["status"] == "UNKNOWN" for item in candidates) or eligible:
        status = "INSUFFICIENT_CONFIGURED_DATA"
        selection_reason = selection_reason or (
            "Available topology facts do not prove every hard constraint or objective."
        )
    else:
        status = "NO_ELIGIBLE_PATH"
        selection_reason = "No candidate satisfies the requested hard constraints."

    if enumeration.truncated:
        status = "INCOMPLETE_SEARCH"
        selection_reason = (
            "Candidate enumeration reached its limit; the result is incomplete "
            "and no global optimality claim is made."
        )
        if selected is not None:
            selected["selection"] = "NOT_SELECTED"
            selected = None

    return {
        "status": status,
        "source": intent.scope.source,
        "destination": intent.scope.destination,
        "optimization": (
            intent.optimization.model_dump(mode="json")
            if intent.optimization is not None
            else None
        ),
        "constraints": [
            constraint.model_dump(mode="json")
            for constraint in intent.constraints
        ],
        "candidate_count": len(candidates),
        "candidate_limit": candidate_limit,
        "truncated": enumeration.truncated,
        "selected_candidate_id": selected["candidate_id"] if selected else None,
        "selection_reason": selection_reason,
        "candidates": candidates,
        "provenance": (
            "DESIGN topology values are configured properties only. Capacity is "
            "not achieved throughput; configured delay is not measured RTT; no "
            "live measurement was collected."
        ),
    }


def _path_facts(
    graph: TopologyGraph,
    path: EnumeratedPath,
) -> tuple[dict[str, float | None], list[dict[str, Any]]]:
    path_links: list[Link] = []
    path_hosts = [
        graph.hosts[name]
        for name in (path.nodes[0], path.nodes[-1])
        if name in graph.hosts
    ]
    serialized_links: list[dict[str, Any]] = []
    for connection in path.connections:
        if connection.kind == ConnectionKind.SWITCH_LINK:
            link = _link_for_connection(graph, connection)
            if link is None:
                continue
            path_links.append(link)
            serialized_links.append(
                {
                    "node_a": connection.from_node,
                    "port_a": connection.from_port,
                    "node_b": connection.to_node,
                    "port_b": connection.to_port,
                    "capacity_mbps": link.bw_mbps,
                    "delay_ms": link.delay_ms,
                    "packet_loss_percent": link.packet_loss_percent,
                    "admin_up": link.admin_up,
                }
            )
        else:
            host_name = (
                connection.from_node
                if connection.from_node in graph.hosts
                else connection.to_node
            )
            host = graph.hosts.get(host_name)
            if host is not None:
                serialized_links.append(
                    {
                        "node_a": connection.from_node,
                        "port_a": connection.from_port,
                        "node_b": connection.to_node,
                        "port_b": connection.to_port,
                        "capacity_mbps": host.attachment_capacity_mbps,
                        "delay_ms": host.attachment_delay_ms,
                        "packet_loss_percent": host.attachment_packet_loss_percent,
                        "admin_up": host.attachment_admin_up,
                    }
                )
    link_capacities = [
        link.bw_mbps for link in path_links if link.bw_mbps is not None
    ] + [
        host.attachment_capacity_mbps
        for host in path_hosts
        if host.attachment_capacity_mbps is not None
    ]
    capacity = (
        min(link_capacities)
        if link_capacities and all(link.bw_mbps is not None for link in path_links)
        else None
    )
    latency_values = [link.delay_ms for link in path_links]
    loss_values = [link.packet_loss_percent for link in path_links]
    latency_values.extend(
        host.attachment_delay_ms
        for host in path_hosts
        if host.attachment_delay_ms is not None
    )
    loss_values.extend(
        host.attachment_packet_loss_percent
        for host in path_hosts
        if host.attachment_packet_loss_percent is not None
    )
    latency = sum(latency_values) if latency_values and all(
        value is not None for value in latency_values
    ) else None
    loss = (
        100.0 * (1.0 - prod(1.0 - value / 100.0 for value in loss_values))
        if loss_values and all(value is not None for value in loss_values)
        else None
    )
    return (
        {
            "bandwidth_mbps": capacity,
            "latency_ms": latency,
            "packet_loss_percent": loss,
        },
        serialized_links,
    )


def _link_for_connection(graph: TopologyGraph, connection) -> Link | None:
    matches = [
        link
        for link in graph.links
        if (
            link.node_a == connection.from_node
            and link.port_a == connection.from_port
            and link.node_b == connection.to_node
            and link.port_b == connection.to_port
        )
        or (
            link.node_b == connection.from_node
            and link.port_b == connection.from_port
            and link.node_a == connection.to_node
            and link.port_a == connection.to_port
        )
    ]
    return matches[0] if len(matches) == 1 else None


def _metric_key(metric: str) -> str | None:
    return {
        "bandwidth": "bandwidth_mbps",
        "latency": "latency_ms",
        "packet_loss": "packet_loss_percent",
    }.get(metric)


def _evaluate_constraint(constraint, metrics: dict[str, float | None]) -> dict[str, Any]:
    key = _metric_key(constraint.metric)
    observed = metrics.get(key) if key else None
    result: dict[str, Any] = {
        "metric": constraint.metric,
        "comparison": constraint.comparison.value,
        "unit": constraint.unit,
        "threshold": (
            [constraint.lower_bound, constraint.upper_bound]
            if constraint.comparison == Comparison.BETWEEN
            else constraint.value
        ),
        "configured_value": observed,
        "status": "UNKNOWN",
    }
    if observed is None:
        result["reason"] = (
            "Required configured topology value is missing; no measurement was substituted."
        )
        return result
    if constraint.comparison == Comparison.GT:
        satisfied = observed > constraint.value
    elif constraint.comparison == Comparison.GTE:
        satisfied = observed >= constraint.value
    elif constraint.comparison == Comparison.LT:
        satisfied = observed < constraint.value
    elif constraint.comparison == Comparison.LTE:
        satisfied = observed <= constraint.value
    elif constraint.comparison == Comparison.EQ:
        tolerance = constraint.tolerance or 0
        satisfied = abs(observed - constraint.value) <= tolerance
    else:
        satisfied = constraint.lower_bound <= observed <= constraint.upper_bound
    result["status"] = "SATISFIED" if satisfied else "VIOLATED"
    result["reason"] = (
        "Configured topology value satisfies the constraint."
        if satisfied
        else "Configured topology value violates the constraint."
    )
    return result


def _candidate_reasons(
    constraints: list[dict[str, Any]],
    status: str,
    metrics: dict[str, float | None],
) -> list[str]:
    reasons = [
        f"Configured bottleneck capacity: {metrics['bandwidth_mbps']} Mbps."
        if metrics["bandwidth_mbps"] is not None
        else "Configured bottleneck capacity is unknown."
    ]
    reasons.extend(
        f"{item['metric']} {item['status'].lower()}: {item['reason']}"
        for item in constraints
    )
    if status == "REJECTED":
        reasons.append("Rejected before objective ranking because a hard constraint failed.")
    elif status == "UNKNOWN":
        reasons.append("Not eligible for selection until missing configured facts are provided.")
    return reasons
