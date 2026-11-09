"""Unit tests for the Phase 13 evaluation aggregation code
(backend/evaluation/aggregate.py) -- pure, synthetic run records, no
Mininet/Ryu/root needed here (the real runs come from
evaluation/run_evaluation.py, exercised against the live testbed
separately, not in this suite)."""
from backend.evaluation.aggregate import aggregate_runs


def _run(scenario, mode, initial_satisfied, final_satisfied, correction_iterations=0,
         execution_time_s=10.0, final_throughput_mbps=10.0):
    return {
        "scenario": scenario,
        "scenario_description": f"{scenario} scenario",
        "repetition": 1,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "pipeline": {
            "mode": mode,
            "target_mbps": 5.0,
            "selected_path": ["h1", "s1", "h4"],
            "initial_throughput_mbps": final_throughput_mbps,
            "initial_satisfied": initial_satisfied,
            "correction_iterations": correction_iterations,
            "correction_history": [],
            "background_rate_changes_mbps": [8.0],
            "final_throughput_mbps": final_throughput_mbps,
            "final_satisfied": final_satisfied,
            "final_validation_valid": True,
            "final_deployment_success": True,
            "execution_time_s": execution_time_s,
            "failure_reason": None if final_satisfied else "measured below target",
        },
    }


def test_groups_by_scenario_and_mode():
    runs = [
        _run("feasible", "ONE_SHOT", True, True),
        _run("feasible", "ONE_SHOT", True, True),
        _run("feasible", "CLOSED_LOOP", True, True),
    ]
    result = aggregate_runs(runs)
    assert result["groups"]["feasible|ONE_SHOT"]["n_runs"] == 2
    assert result["groups"]["feasible|CLOSED_LOOP"]["n_runs"] == 1
    assert result["groups"]["feasible|ONE_SHOT"]["final_satisfaction_rate"] == 1.0


def test_satisfaction_rates_computed_correctly():
    runs = [
        _run("boundary", "ONE_SHOT", True, True),
        _run("boundary", "ONE_SHOT", False, False),
    ]
    result = aggregate_runs(runs)
    group = result["groups"]["boundary|ONE_SHOT"]
    assert group["initial_satisfaction_rate"] == 0.5
    assert group["final_satisfaction_rate"] == 0.5


def test_closed_loop_correction_helped_is_counted():
    """A run that started unsatisfied, ran real corrections, and ended
    satisfied counts as 'correction helped'."""
    runs = [
        _run("correctable", "CLOSED_LOOP", initial_satisfied=False, final_satisfied=True,
             correction_iterations=1),
        _run("correctable", "ONE_SHOT", initial_satisfied=False, final_satisfied=False),
    ]
    result = aggregate_runs(runs)
    comparison = result["scenario_comparison"]["correctable"]
    assert comparison["runs_where_correction_helped"] == 1
    assert comparison["runs_where_correction_ran_but_did_not_help"] == 0
    assert comparison["one_shot_satisfaction_rate"] == 0.0
    assert comparison["closed_loop_satisfaction_rate"] == 1.0
    assert comparison["improvement"] == 1.0


def test_closed_loop_correction_ran_but_did_not_help_is_counted_not_hidden():
    """A genuine bounded correction failure (ran for real, stayed
    unsatisfied) must be counted honestly, not folded into 'no
    correction needed' or dropped."""
    runs = [
        _run("boundary", "CLOSED_LOOP", initial_satisfied=False, final_satisfied=False,
             correction_iterations=3),
    ]
    result = aggregate_runs(runs)
    comparison = result["scenario_comparison"]["boundary"]
    assert comparison["runs_where_correction_helped"] == 0
    assert comparison["runs_where_correction_ran_but_did_not_help"] == 1
    assert comparison["closed_loop_satisfaction_rate"] == 0.0


def test_scenario_missing_one_mode_reports_none_improvement():
    runs = [_run("infeasible", "ONE_SHOT", False, False)]
    result = aggregate_runs(runs)
    comparison = result["scenario_comparison"]["infeasible"]
    assert comparison["closed_loop_satisfaction_rate"] is None
    assert comparison["improvement"] is None


def test_overall_aggregates_across_all_scenarios():
    runs = [
        _run("feasible", "ONE_SHOT", True, True),
        _run("feasible", "CLOSED_LOOP", True, True),
        _run("correctable", "ONE_SHOT", False, False),
        _run("correctable", "CLOSED_LOOP", False, True, correction_iterations=1),
    ]
    result = aggregate_runs(runs)
    overall = result["overall"]
    assert overall["one_shot_satisfaction_rate"] == 0.5
    assert overall["closed_loop_satisfaction_rate"] == 1.0
    assert overall["overall_improvement"] == 0.5


def test_infra_error_run_excluded_from_statistics_and_counted_separately():
    """A run where the pipeline itself is None (an infrastructure-level
    failure, e.g. the Ryu REST API became unreachable) must never be
    silently folded into a measured NOT_SATISFIED outcome -- it should
    be excluded from every satisfaction-rate computation and reported
    separately."""
    runs = [
        _run("boundary", "ONE_SHOT", True, True),
        {
            "scenario": "boundary",
            "scenario_description": "boundary scenario",
            "repetition": 2,
            "timestamp": "2026-01-01T00:00:00+00:00",
            "pipeline": None,
            "error": "transport error after 3 attempt(s): simulated stall",
        },
    ]
    result = aggregate_runs(runs)
    assert result["groups"]["boundary|ONE_SHOT"]["n_runs"] == 1
    assert result["groups"]["boundary|ONE_SHOT"]["final_satisfaction_rate"] == 1.0
    assert result["infra_errors"]["boundary"] == 1
    assert result["n_infra_errors_total"] == 1


def test_infeasible_target_never_satisfied_in_either_mode():
    """A genuinely infeasible target should show 0% satisfaction in both
    modes and no fabricated improvement."""
    runs = [
        _run("infeasible", "ONE_SHOT", False, False),
        _run("infeasible", "ONE_SHOT", False, False),
        _run("infeasible", "CLOSED_LOOP", False, False, correction_iterations=3),
        _run("infeasible", "CLOSED_LOOP", False, False, correction_iterations=3),
    ]
    result = aggregate_runs(runs)
    comparison = result["scenario_comparison"]["infeasible"]
    assert comparison["one_shot_satisfaction_rate"] == 0.0
    assert comparison["closed_loop_satisfaction_rate"] == 0.0
    assert comparison["improvement"] == 0.0
    assert comparison["runs_where_correction_ran_but_did_not_help"] == 2
