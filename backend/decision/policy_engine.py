
"""Deterministic planner for generalized network intents.

This module performs topology-aware planning only. It does not deploy
flows, execute commands, or let the LLM choose network configurations.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.models.intent import (
    Metric,
    MetricConstraint,
    StructuredIntent,
)
from backend.models.network import TopologyGraph


SUPPORTED_METRICS = {
    Metric.LATENCY,
    Metric.BANDWIDTH,
}


class PolicyPlan(BaseModel):
    """Topology-aware plan produced before measurement and execution."""

    source: str
    destination: str
    candidate_paths: list[list[str]] = Field(default_factory=list)
    rejected_paths: dict[str, str] = Field(default_factory=dict)
    constraints: list[MetricConstraint] = Field(default_factory=list)
    supported_metrics: list[Metric] = Field(default_factory=list)
    unsupported_metrics: list[Metric] = Field(default_factory=list)

    @property
    def feasible(self) -> bool:
        return bool(self.candidate_paths) and not self.unsupported_metrics


def build_policy_plan(
    intent: StructuredIntent,
    graph: TopologyGraph,
    max_hops: int = 6,
) -> PolicyPlan:
    """Validate an intent against topology and produce candidate paths.

    This is a planning stage, not a guarantee that measured network
    performance will satisfy the requested constraints.
    """

    if intent.source not in graph.hosts:
        raise ValueError(f"Unknown source host: {intent.source}")

    if intent.destination not in graph.hosts:
        raise ValueError(f"Unknown destination host: {intent.destination}")

    constraints = (
        intent.constraints.metrics
        if intent.constraints is not None
        else []
    )

    supported = [
        item.metric
        for item in constraints
        if item.metric in SUPPORTED_METRICS
    ]

    unsupported = [
        item.metric
        for item in constraints
        if item.metric not in SUPPORTED_METRICS
    ]

    paths = graph.all_simple_paths(
        intent.source,
        intent.destination,
        max_hops=max_hops,
    )

    candidates: list[list[str]] = []
    rejected: dict[str, str] = {}

    bandwidth_constraints = [
        item
        for item in constraints
        if item.metric == Metric.BANDWIDTH
    ]

    for path in paths:
        reason = graph.validate_path(path)

        if reason is not None:
            rejected[" -> ".join(path)] = reason
            continue

        capacity = graph.path_capacity_mbps(path)

        # A known static bottleneck below the requested minimum
        # makes this path provably infeasible.
        impossible = False

        for constraint in bandwidth_constraints:
            minimum = constraint.min_value

            if (
                minimum is not None
                and capacity is not None
                and capacity < minimum
            ):
                rejected[" -> ".join(path)] = (
                    f"Path capacity ({capacity} Mbps) is below "
                    f"the required minimum ({minimum} Mbps)"
                )
                impossible = True
                break

        if not impossible:
            candidates.append(path)

    return PolicyPlan(
        source=intent.source,
        destination=intent.destination,
        candidate_paths=candidates,
        rejected_paths=rejected,
        constraints=constraints,
        supported_metrics=supported,
        unsupported_metrics=unsupported,
    )
