"""Network-aware decision layer for the MIN_BANDWIDTH objective (brief
Phase 11, Step 4). Follows the exact same shape as
backend/decision/latency_decision.py: it does not estimate throughput
from topology alone, it deploys each real candidate path in turn and
measures actual achieved throughput with iperf3 (backend/measurement/
throughput.py, already implemented for the latency phase's groundwork).
The LLM never sees or influences this.

Selection policy (revised in Phase 12 -- see below for why):
among candidates whose REAL measured throughput already meets
target_mbps, picks the one with the SMALLEST such measurement (the
cheapest path that still satisfies the floor), not the single highest-
throughput candidate overall. If no candidate meets target, falls back to
the highest measured throughput available (still the best real option,
even though it's short), preserving the original NOT-SATISFIED-reporting
behavior for a genuinely infeasible target.

Why this changed from "always pick highest measured throughput": a
MIN_BANDWIDTH intent is a floor ("at least N Mbps"), not "give me the
fastest path regardless of N". Always routing onto the highest-capacity
path (i) wastes that path's spare capacity on a flow that didn't need it
and (ii) starves the Phase 12 closed-loop correction mechanism (backend/
cli.py's `_run_bandwidth`, which throttles competing traffic on the
selected path) of anything to ever actually do: in this project's diamond
topology, only the lower-capacity Path A shares a link with the
background/competing traffic (h2->h3), so if Path B (uncontended,
higher-capacity) is always preferred, the selected path never overlaps
with any traffic the correction loop could throttle. Preferring the
cheapest sufficient path is also a defensible traffic-engineering
practice in its own right: it reserves high-capacity paths for flows that
actually need them instead of first-come-first-served on whichever
measured fastest.

`deploy_and_measure` is injected exactly as in latency_decision.py, so
this module has no direct dependency on Mininet, Ryu, or ovs-vsctl --
testable with a stub callable (tests/test_bandwidth_decision.py); the CLI
wires in the real one.
"""
from __future__ import annotations

from typing import Callable

from backend.models.decision import BandwidthDecisionResult, CandidateThroughputMeasurement, DecisionError
from backend.models.measurement import ThroughputResult
from backend.models.network import TopologyGraph

DeployAndMeasure = Callable[[list[str]], ThroughputResult]


def select_bandwidth_path(
    graph: TopologyGraph,
    source: str,
    destination: str,
    target_mbps: float,
    deploy_and_measure: DeployAndMeasure,
    max_hops: int = 6,
) -> BandwidthDecisionResult:
    candidates = graph.all_simple_paths(source, destination, max_hops=max_hops)
    if not candidates:
        raise DecisionError(f"no path exists between {source} and {destination} in the current topology")

    measurements: list[CandidateThroughputMeasurement] = []
    for path in candidates:
        throughput = deploy_and_measure(path)
        measurements.append(
            CandidateThroughputMeasurement(
                path=path,
                throughput=throughput,
                static_capacity_mbps=graph.path_capacity_mbps(path),
            )
        )

    reachable = [m for m in measurements if m.throughput.succeeded and m.throughput.achieved_mbps is not None]
    if not reachable:
        raise DecisionError(
            f"none of the {len(candidates)} candidate path(s) between {source} and {destination} "
            "produced a usable iperf3 measurement"
        )

    # Prefer the cheapest candidate that already meets the target (see
    # module docstring); only maximize throughput when nothing does, so a
    # genuinely infeasible target still gets the best real option
    # available rather than an arbitrary one. Either way this always
    # compares real measured throughput, never static capacity -- a path
    # with a bigger nominal link bw= can still measure lower than expected
    # under real contention or forwarding overhead.
    meeting_target = [m for m in reachable if m.throughput.achieved_mbps >= target_mbps]
    if meeting_target:
        best = min(meeting_target, key=lambda m: m.throughput.achieved_mbps)
    else:
        best = max(reachable, key=lambda m: m.throughput.achieved_mbps)

    return BandwidthDecisionResult(target_mbps=target_mbps, candidates=measurements, selected_path=best.path)
