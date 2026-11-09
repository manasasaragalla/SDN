"""Network-aware decision layer for the MINIMIZE_LATENCY objective (brief
section 13/19). Deliberately does NOT invent or estimate latency from
topology alone: it deploys each real candidate path in turn and measures
actual RTT with ping, then picks the best one from what was actually
measured. The LLM never sees or influences this -- it only supplied the
objective/source/destination; this module is the only place path
selection happens, using real topology (backend/models/network.py) and
real measurement.

`deploy_and_measure` is injected so this module has no direct dependency
on Mininet or the Ryu REST client -- it's testable with a stub callable
(see tests/test_latency_decision.py), and the CLI wires in the real one
that compiles+validates+deploys via backend.compiler/backend.validator/
backend.deployment and measures with backend.measurement.latency.
"""
from __future__ import annotations

from typing import Callable

from backend.models.decision import CandidateMeasurement, DecisionError, LatencyDecisionResult
from backend.models.measurement import LatencyResult
from backend.models.network import TopologyGraph

DeployAndMeasure = Callable[[list[str]], LatencyResult]


def select_latency_path(
    graph: TopologyGraph,
    source: str,
    destination: str,
    deploy_and_measure: DeployAndMeasure,
    max_hops: int = 6,
) -> LatencyDecisionResult:
    candidates = graph.all_simple_paths(source, destination, max_hops=max_hops)
    if not candidates:
        raise DecisionError(f"no path exists between {source} and {destination} in the current topology")

    measurements: list[CandidateMeasurement] = []
    for path in candidates:
        latency = deploy_and_measure(path)
        measurements.append(CandidateMeasurement(path=path, latency=latency))

    reachable = [m for m in measurements if m.latency.reachable and m.latency.rtt_avg_ms is not None]
    if not reachable:
        raise DecisionError(
            f"none of the {len(candidates)} candidate path(s) between {source} and {destination} "
            "achieved connectivity"
        )

    best = min(reachable, key=lambda m: m.latency.rtt_avg_ms)

    return LatencyDecisionResult(candidates=measurements, selected_path=best.path)
