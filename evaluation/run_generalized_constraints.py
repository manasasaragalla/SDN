"""Run one generalized hard-constraint scenario on the live diamond testbed.

Examples (run as root with the system Python that provides Mininet):
    sudo mn -c
    sudo PYTHONPATH=. python3 evaluation/run_generalized_constraints.py bandwidth
    sudo PYTHONPATH=. python3 evaluation/run_generalized_constraints.py latency
    sudo PYTHONPATH=. python3 evaluation/run_generalized_constraints.py combined
    sudo PYTHONPATH=. python3 evaluation/run_generalized_constraints.py minimize-latency
    sudo PYTHONPATH=. python3 evaluation/run_generalized_constraints.py maximize-bandwidth
    sudo PYTHONPATH=. python3 evaluation/run_generalized_constraints.py constrained-minimize-latency
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _intent(scenario: str):
    from backend.models.canonical_intent import (
        CanonicalIntent,
        Comparison,
        MetricConstraint,
        OptimizationDirection,
        OptimizationObjective,
        TrafficScope,
    )

    constraints = []
    optimization = None
    if scenario in ("latency", "combined"):
        constraints.append(
            MetricConstraint(
                metric="latency",
                comparison=Comparison.LTE,
                value=50,
                unit="ms",
            )
        )
    if scenario in ("bandwidth", "combined"):
        constraints.append(
            MetricConstraint(
                metric="bandwidth",
                comparison=Comparison.GTE,
                value=20,
                unit="Mbps",
            )
        )
    if scenario == "minimize-latency":
        optimization = OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        )
    elif scenario == "maximize-bandwidth":
        optimization = OptimizationObjective(
            metric="bandwidth",
            direction=OptimizationDirection.MAXIMIZE,
            unit="Mbps",
        )
    elif scenario == "constrained-minimize-latency":
        constraints.append(
            MetricConstraint(
                metric="bandwidth",
                comparison=Comparison.GTE,
                value=20,
                unit="Mbps",
            )
        )
        optimization = OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        )
    return CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        constraints=constraints,
        optimization=optimization,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenario",
        choices=(
            "bandwidth",
            "latency",
            "combined",
            "minimize-latency",
            "maximize-bandwidth",
            "constrained-minimize-latency",
        ),
        help="hard-constraint or objective-optimization scenario to evaluate",
    )
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run this command with sudo so Mininet can create network namespaces")

    from mininet.log import setLogLevel

    from backend.cli import OFP_PORT, RYU_BASE_URL, _start_ryu
    from backend.decision.topology_graph import build_from_mininet
    from backend.orchestration.generalized_constraints import (
        run_generalized_constraint_demo,
    )
    from backend.orchestration.generalized_latency import read_live_topology_snapshot
    from testbed.topology.diamond import (
        build_diamond_topology,
        start as start_topology,
    )

    setLogLevel("warning")
    ryu_process = None
    net = None
    try:
        ryu_process = _start_ryu()
        net = build_diamond_topology(controller_port=OFP_PORT)
        start_topology(net)
        time.sleep(2)
        graph = build_from_mininet(net)
        planned_snapshot = read_live_topology_snapshot(graph, RYU_BASE_URL)
        result = run_generalized_constraint_demo(
            graph,
            source_host=net.get("h1"),
            destination_host=net.get("h4"),
            intent=_intent(args.scenario),
            planned_snapshot=planned_snapshot,
            fresh_snapshot_provider=lambda: read_live_topology_snapshot(
                graph, RYU_BASE_URL
            ),
            base_url=RYU_BASE_URL,
        )
        selected = (
            result.selection.selected_candidate
            if result.selection is not None
            else None
        )
        summary = {
            "scenario": args.scenario,
            "status": result.status.value,
            "selected_path": (
                list(selected.path.nodes) if selected is not None else None
            ),
            "final_average_rtt_ms": (
                result.final_measurement.rtt_avg_ms
                if result.final_measurement is not None
                else None
            ),
            "error": result.error,
            "execution_id": result.execution_id,
            "evidence_json": result.evidence_json_path,
            "evidence_markdown": result.evidence_markdown_path,
        }
        print(json.dumps(summary, indent=2))
        return 0 if result.status.value == "SUCCEEDED" else 1
    finally:
        if net is not None:
            net.stop()
        if ryu_process is not None:
            ryu_process.terminate()
            try:
                ryu_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                ryu_process.kill()
                ryu_process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
