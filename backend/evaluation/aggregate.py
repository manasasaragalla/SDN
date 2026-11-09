"""Pure aggregation of evaluation runs (Phase 13) -- no Mininet/Ryu/root
dependency, so this is unit-testable with synthetic run records
(tests/test_evaluation_aggregate.py) exactly like the decision-layer
modules are tested with a stub deploy_and_measure. The real experiment
runner (evaluation/run_evaluation.py) produces the actual `EvaluationRun`
records this consumes; this module never invents or estimates a
measurement itself.

Input shape: a list of dicts, each an `EvaluationRun.model_dump()`
(backend/models/evaluation.py) -- i.e. with "scenario" and a nested
"pipeline" dict carrying "mode", "final_satisfied", "initial_satisfied",
"correction_iterations", "execution_time_s", etc. A run whose "pipeline"
is None (an infrastructure-level failure -- e.g. the Ryu REST API became
unreachable mid-run -- distinct from a genuine measured NOT_SATISFIED
outcome) is excluded from every statistic below and counted separately
under "infra_errors", never silently folded into a measured failure.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def _mean(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    if not values:
        return None
    return sum(values) / len(values)


def aggregate_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Groups runs by (scenario, mode) and computes per-group statistics,
    plus a per-scenario ONE_SHOT-vs-CLOSED_LOOP comparison answering
    "did closed-loop correction improve intent satisfaction here?".

    Returns:
        {
          "groups": {
            "<scenario>|<mode>": {
              "scenario": ..., "mode": ..., "n_runs": ...,
              "initial_satisfaction_rate": ..., "final_satisfaction_rate": ...,
              "mean_correction_iterations": ..., "mean_execution_time_s": ...,
              "mean_final_throughput_mbps": ...,
            }, ...
          },
          "scenario_comparison": {
            "<scenario>": {
              "one_shot_satisfaction_rate": ..., "closed_loop_satisfaction_rate": ...,
              "improvement": closed_loop_rate - one_shot_rate (None if either mode missing),
              "runs_where_correction_helped": count of CLOSED_LOOP runs that started
                  unsatisfied and ended satisfied,
              "runs_where_correction_ran_but_did_not_help": count of CLOSED_LOOP runs
                  that started and stayed unsatisfied despite >=1 correction iteration,
            }, ...
          },
          "overall": {
            "one_shot_satisfaction_rate": ..., "closed_loop_satisfaction_rate": ...,
            "overall_improvement": ...,
          },
        }
    """
    infra_errors: dict[str, int] = defaultdict(int)
    usable_runs = []
    for run in runs:
        if run.get("pipeline") is None:
            infra_errors[run["scenario"]] += 1
            continue
        usable_runs.append(run)

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for run in usable_runs:
        scenario = run["scenario"]
        pipeline = run["pipeline"]
        groups[(scenario, pipeline["mode"])].append(run)

    group_stats: dict[str, dict] = {}
    for (scenario, mode), group_runs in groups.items():
        pipelines = [r["pipeline"] for r in group_runs]
        n = len(pipelines)
        group_stats[f"{scenario}|{mode}"] = {
            "scenario": scenario,
            "mode": mode,
            "n_runs": n,
            "initial_satisfaction_rate": sum(1 for p in pipelines if p["initial_satisfied"]) / n,
            "final_satisfaction_rate": sum(1 for p in pipelines if p["final_satisfied"]) / n,
            "mean_correction_iterations": _mean([p["correction_iterations"] for p in pipelines]),
            "mean_execution_time_s": _mean([p["execution_time_s"] for p in pipelines]),
            "mean_final_throughput_mbps": _mean([p["final_throughput_mbps"] for p in pipelines]),
        }

    scenarios = sorted({run["scenario"] for run in runs})
    scenario_comparison: dict[str, dict] = {}
    for scenario in scenarios:
        one_shot = group_stats.get(f"{scenario}|ONE_SHOT")
        closed_loop = group_stats.get(f"{scenario}|CLOSED_LOOP")

        closed_loop_runs = [r["pipeline"] for r in groups.get((scenario, "CLOSED_LOOP"), [])]
        runs_helped = sum(
            1 for p in closed_loop_runs
            if not p["initial_satisfied"] and p["final_satisfied"] and p["correction_iterations"] > 0
        )
        runs_ran_but_failed = sum(
            1 for p in closed_loop_runs
            if not p["initial_satisfied"] and not p["final_satisfied"] and p["correction_iterations"] > 0
        )

        improvement = None
        if one_shot is not None and closed_loop is not None:
            improvement = closed_loop["final_satisfaction_rate"] - one_shot["final_satisfaction_rate"]

        scenario_comparison[scenario] = {
            "one_shot_satisfaction_rate": one_shot["final_satisfaction_rate"] if one_shot else None,
            "closed_loop_satisfaction_rate": closed_loop["final_satisfaction_rate"] if closed_loop else None,
            "improvement": improvement,
            "runs_where_correction_helped": runs_helped,
            "runs_where_correction_ran_but_did_not_help": runs_ran_but_failed,
        }

    all_one_shot = [r["pipeline"] for r in usable_runs if r["pipeline"]["mode"] == "ONE_SHOT"]
    all_closed_loop = [r["pipeline"] for r in usable_runs if r["pipeline"]["mode"] == "CLOSED_LOOP"]
    one_shot_rate = (sum(1 for p in all_one_shot if p["final_satisfied"]) / len(all_one_shot)
                      if all_one_shot else None)
    closed_loop_rate = (sum(1 for p in all_closed_loop if p["final_satisfied"]) / len(all_closed_loop)
                         if all_closed_loop else None)
    overall_improvement = (closed_loop_rate - one_shot_rate
                            if one_shot_rate is not None and closed_loop_rate is not None else None)

    return {
        "groups": group_stats,
        "scenario_comparison": scenario_comparison,
        "overall": {
            "one_shot_satisfaction_rate": one_shot_rate,
            "closed_loop_satisfaction_rate": closed_loop_rate,
            "overall_improvement": overall_improvement,
        },
        "infra_errors": dict(infra_errors),
        "n_infra_errors_total": sum(infra_errors.values()),
    }
