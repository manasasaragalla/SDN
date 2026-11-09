"""Phase 13 research-evaluation harness: runs the MIN_BANDWIDTH objective
through both the ONE_SHOT and CLOSED_LOOP pipelines, repeated across four
real bandwidth scenarios (see SCENARIOS below), against the live
Mininet + Open vSwitch + Ryu testbed -- the same real iperf3/OVS-QoS
machinery backend/cli.py's demo uses (backend/pipeline/bandwidth.py),
just driven repeatedly and recorded compactly for comparison instead of
printed once per invocation and thrown away.

  ONE_SHOT:    decision -> validation -> deployment -> one real
               measurement -> stop, whatever it shows.
  CLOSED_LOOP: decision -> validation -> deployment -> real measurement
               -> feedback -> bounded real correction (throttle the real
               competing background flow, redeploy, re-measure) -> repeat
               up to 3 times.

No measurement is ever estimated or simulated: every throughput number
this script records comes from a real `iperf3` run against the live
testbed, and every background-traffic rate change is a real `ovs-vsctl`
QoS redeploy, exactly as in the CLI demo.

One Ryu controller and one Mininet topology are brought up once for the
whole sweep (not once per run) -- each individual run still deletes and
redeploys real OpenFlow rules and the real background traffic before its
own measurement, which is the same repeated-redeploy pattern a single CLI
invocation already does across its own candidates/correction iterations.
This is a deliberate, documented efficiency choice (see docs/experiments.md),
not a shortcut that reuses stale measurements.

Must be run with root privileges and the system python3, exactly like
backend/cli.py:

    sudo mn -c
    PYTHONPATH=. python3 evaluation/run_evaluation.py

Optional flags let a long sweep be split across multiple invocations
without losing earlier results -- each invocation writes its own
timestamped result file under evaluation/results/, and can be combined
afterwards with evaluation/summarize.py:

    PYTHONPATH=. python3 evaluation/run_evaluation.py --scenarios feasible,boundary
    PYTHONPATH=. python3 evaluation/run_evaluation.py --modes ONE_SHOT --repetitions 5
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Four real bandwidth scenarios on this project's diamond topology
# (Path A = h1-s1-s2-s4-h4, a 10 Mbps link that shares its s2-s4 hop with
# the background flow; Path B = h1-s1-s3-s5-s4-h4, an uncontended 50 Mbps
# link), chosen from this project's own previously-documented real
# behavior (docs/experiments.md, Phase 11/12 sections) on this exact
# testbed -- not arbitrary numbers picked to force an outcome.
SCENARIOS = [
    {
        "name": "feasible",
        "description": "Clearly feasible target, comfortably within Path B's "
                        "uncontended real capacity.",
        "target_mbps": 20.0,
    },
    {
        "name": "boundary",
        "description": "Target right at Path A's real measured ceiling under "
                        "background contention (~5.1-5.2 Mbps) -- outcome is "
                        "genuinely noisy run to run, in either mode.",
        "target_mbps": 5.15,
    },
    {
        "name": "correctable",
        "description": "Target just above Path A's typical contended throughput -- "
                        "empirically shown (docs/experiments.md, Phase 12) to "
                        "sometimes need, and succeed via, one real correction "
                        "iteration.",
        "target_mbps": 5.05,
    },
    {
        "name": "infeasible",
        "description": "Genuinely infeasible target -- above even Path B's real "
                        "ceiling, and Path B never shares a link with the "
                        "throttleable background flow, so correction cannot help "
                        "it either.",
        "target_mbps": 49.0,
    },
]

INTENT_SOURCE = "h1"
INTENT_DEST = "h4"


def run_one(net, graph, target_mbps: float, mode: str, verbose: bool = True):
    """One real ONE_SHOT or CLOSED_LOOP run for a given target: real
    candidate evaluation (select_bandwidth_path), then the shared real
    pipeline (backend/pipeline/bandwidth.run_bandwidth_pipeline)."""
    from backend.cli import BACKGROUND_RATE_MBPS, PRIMARY_IPERF_PORT, RYU_BASE_URL, _setup_background_traffic
    from backend.decision.bandwidth_decision import select_bandwidth_path
    from backend.pipeline.bandwidth import make_candidate_deploy_and_measure, run_bandwidth_pipeline

    all_switches = list(graph.switches)

    def setup_bg(rate_mbps: float) -> None:
        _setup_background_traffic(net, graph, all_switches, rate_mbps=rate_mbps)

    deploy_and_measure = make_candidate_deploy_and_measure(
        net, graph, target_mbps, RYU_BASE_URL, setup_bg, BACKGROUND_RATE_MBPS,
        port=PRIMARY_IPERF_PORT, verbose=verbose,
    )
    decision = select_bandwidth_path(graph, INTENT_SOURCE, INTENT_DEST, target_mbps, deploy_and_measure)

    pipeline_result, *_ = run_bandwidth_pipeline(
        net, graph, INTENT_SOURCE, INTENT_DEST, target_mbps, RYU_BASE_URL,
        decision.selected_path, setup_bg, BACKGROUND_RATE_MBPS,
        mode=mode, port=PRIMARY_IPERF_PORT, verbose=verbose,
    )
    return pipeline_result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenarios", default=None,
                         help="Comma-separated subset of scenario names to run (default: all four)")
    parser.add_argument("--modes", default="ONE_SHOT,CLOSED_LOOP",
                         help="Comma-separated modes to run (default: both)")
    parser.add_argument("--repetitions", type=int, default=3,
                         help="Real repetitions per (scenario, mode) pair (default: 3)")
    args = parser.parse_args()

    scenario_names = set(args.scenarios.split(",")) if args.scenarios else None
    scenarios = [s for s in SCENARIOS if scenario_names is None or s["name"] in scenario_names]
    if not scenarios:
        print(f"No scenarios matched --scenarios={args.scenarios!r}; known scenarios: "
              f"{[s['name'] for s in SCENARIOS]}")
        return 1
    modes = args.modes.split(",")

    from mininet.log import setLogLevel

    from backend.cli import OFP_PORT, _start_ryu
    from backend.decision.topology_graph import build_from_mininet
    from testbed.topology.diamond import build_diamond_topology
    from testbed.topology.diamond import start as start_topology

    setLogLevel("warning")

    results_dir = PROJECT_ROOT / "evaluation" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    runs_path = results_dir / f"evaluation_runs_{stamp}.json"

    import signal

    RUN_TIMEOUT_S = 45  # hard wall-clock budget per real run (a real run, even
    # with 3 correction iterations, has never taken more than ~35s observed)

    class _RunTimedOut(Exception):
        pass

    def _alarm_handler(signum, frame):
        raise _RunTimedOut(f"run exceeded {RUN_TIMEOUT_S}s wall-clock budget")

    def _build_environment():
        """(Re)builds a fresh Ryu controller subprocess + Mininet topology.
        Used both for the initial bring-up and to recover after a run that
        left Mininet/OVS/Ryu in a stuck state (observed empirically: a
        long-running evaluation session doing dozens of sequential real
        `host.cmd()` calls can occasionally leave a Mininet host's shell
        unresponsive to further commands -- a known Mininet limitation,
        not something backend/deployment's own bounded HTTP/subprocess
        retries can fix, since the hang is in Mininet's own pexpect-style
        command channel, not in any single HTTP or ovs-vsctl call)."""
        proc = _start_ryu()
        n = build_diamond_topology(controller_port=OFP_PORT)
        start_topology(n)
        time.sleep(2)
        g = build_from_mininet(n)
        return proc, n, g

    print("Starting Ryu controller (ofctl_rest)...")
    print("Building testbed topology...")
    ryu_proc, net, graph = _build_environment()
    all_runs: list[dict] = []
    total = len(scenarios) * len(modes) * args.repetitions
    done = 0
    t_sweep_start = time.monotonic()
    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)

    try:
        for scenario in scenarios:
            for mode in modes:
                for rep in range(1, args.repetitions + 1):
                    done += 1
                    print(f"\n=== [{done}/{total}] scenario={scenario['name']} mode={mode} "
                          f"rep={rep}/{args.repetitions} target={scenario['target_mbps']} Mbps ===")
                    # A per-run infrastructure failure (a transient REST/
                    # ovs-vsctl stall that outlasted backend/deployment's
                    # own bounded retries, or a hung Mininet host shell
                    # caught by the RUN_TIMEOUT_S alarm) must not lose
                    # every real run already collected this sweep. It's
                    # recorded honestly as an infra error (pipeline=None),
                    # never faked into a measured NOT_SATISFIED outcome --
                    # see backend/models/evaluation.py's EvaluationRun
                    # docstring.
                    signal.alarm(RUN_TIMEOUT_S)
                    try:
                        result = run_one(net, graph, scenario["target_mbps"], mode, verbose=True)
                        signal.alarm(0)
                        record = {
                            "scenario": scenario["name"],
                            "scenario_description": scenario["description"],
                            "repetition": rep,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "pipeline": result.model_dump(mode="json"),
                            "error": None,
                        }
                        print(f"  -> initial_satisfied={result.initial_satisfied} "
                              f"final_satisfied={result.final_satisfied} "
                              f"correction_iterations={result.correction_iterations} "
                              f"time={result.execution_time_s:.1f}s")
                    except Exception as exc:  # noqa: BLE001 -- deliberately broad: any
                        # infra failure here must be recorded and the sweep
                        # must continue, not crash and lose prior real runs.
                        signal.alarm(0)
                        record = {
                            "scenario": scenario["name"],
                            "scenario_description": scenario["description"],
                            "repetition": rep,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "pipeline": None,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                        print(f"  -> INFRA ERROR (not a measured result): {record['error']}")
                        print("  Rebuilding Ryu + Mininet topology to recover clean state...")
                        # Deliberately do NOT call net.stop() here: when the
                        # timeout fired inside a Mininet host's .cmd(), that
                        # host's pexpect-style shell is left in a
                        # permanently broken state (its internal "waiting"
                        # flag stuck), and net.stop() tries to run cleanup
                        # commands through that same broken shell -- which
                        # raises again and can cascade into losing the rest
                        # of the sweep. `mn -c` is the same external,
                        # process-level cleanup this project's own docs
                        # already tell a human operator to run between CLI
                        # invocations; running it here is the safe
                        # equivalent for automatic recovery.
                        try:
                            ryu_proc.kill()
                            ryu_proc.wait(timeout=5)
                        except Exception:  # noqa: BLE001
                            pass
                        subprocess.run(["mn", "-c"], capture_output=True, timeout=30)
                        ryu_proc, net, graph = _build_environment()

                    all_runs.append(record)
                    # Incremental write: a later failure never loses runs
                    # already collected in this sweep.
                    runs_path.write_text(json.dumps(all_runs, indent=2))
    finally:
        signal.signal(signal.SIGALRM, old_handler)
        # Best-effort: if the last run's timeout left this net's host
        # shells broken, net.stop() itself can raise (see the recovery
        # path above) -- never let that crash past the incremental
        # results this sweep already wrote to disk.
        try:
            if net is not None:
                net.stop()
        except Exception:  # noqa: BLE001
            subprocess.run(["mn", "-c"], capture_output=True, timeout=30)
        try:
            ryu_proc.kill()
            ryu_proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass

    elapsed = time.monotonic() - t_sweep_start
    n_errors = sum(1 for r in all_runs if r["pipeline"] is None)
    print(f"\nSweep finished: {len(all_runs)} run(s) ({len(all_runs) - n_errors} real measured, "
          f"{n_errors} infra error(s)) in {elapsed:.1f}s")
    print(f"Wrote evaluation run(s) to {runs_path.relative_to(PROJECT_ROOT)}")

    if all_runs:
        from backend.evaluation.aggregate import aggregate_runs
        summary = aggregate_runs(all_runs)
        summary_path = results_dir / f"evaluation_summary_{stamp}.json"
        summary_path.write_text(json.dumps(summary, indent=2))
        print(f"Wrote aggregate summary to {summary_path.relative_to(PROJECT_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
