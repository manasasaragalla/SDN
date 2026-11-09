"""Manual comparison-boundary checks for the pure Phase 3C evaluator."""

from datetime import datetime, timedelta, timezone

from backend.capabilities import resolve_capabilities
from backend.models.canonical_intent import (
    CanonicalIntent,
    Comparison,
    MetricConstraint,
    TrafficScope,
)
from backend.models.network import Host, TopologyGraph
from backend.planner.constraint_evaluation import (
    EvaluationCandidate,
    EvaluationStatus,
    EvaluationTarget,
    FreshnessPolicy,
    MetricFreshnessLimit,
    MetricObservation,
    ObservationStatus,
    evaluate_hard_constraints,
    physical_path_fingerprint,
    planning_request_fingerprint,
)
from backend.planner.models import (
    CandidateFeasibility,
    HardConstraintRequirement,
    MetricObservationPurpose,
    Plan,
    PlanningReadiness,
    PlanningRequest,
    RequiredMetricObservation,
)
from backend.planner.path_enumeration import enumerate_candidate_paths


EVALUATED_AT = datetime.now(timezone.utc)
FRESHNESS_POLICY = FreshnessPolicy(
    limits=(
        MetricFreshnessLimit(
            metric="latency",
            max_age=timedelta(minutes=5),
        ),
    )
)


def _build_evaluation(
    comparison,
    measured_value,
    *,
    value=None,
    lower_bound=None,
    upper_bound=None,
    tolerance=None,
):
    constraint = MetricConstraint(
        metric="latency",
        comparison=comparison,
        value=value,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        tolerance=tolerance,
        unit="ms",
    )
    graph = TopologyGraph(
        switches={"s1": 4},
        hosts={
            "h1": Host(
                name="h1",
                ip="10.0.0.1",
                mac="00:00:00:00:00:01",
                switch="s1",
                switch_port=1,
            ),
            "h4": Host(
                name="h4",
                ip="10.0.0.4",
                mac="00:00:00:00:00:04",
                switch="s1",
                switch_port=2,
            ),
        },
        links=[],
    )
    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        constraints=[constraint],
    )
    request = PlanningRequest(
        intent=intent,
        topology=graph,
        capabilities=resolve_capabilities(intent, graph=graph),
    )
    requirement_id = "r0"
    plan = Plan(
        request=request,
        capability_readiness=request.capabilities.eligibility,
        planning_readiness=PlanningReadiness.CONDITIONAL,
        hard_constraints=(
            HardConstraintRequirement(
                requirement_id=requirement_id,
                constraint=constraint,
            ),
        ),
        required_observations=(
            RequiredMetricObservation(
                observation_id="observation-0",
                requirement_id=requirement_id,
                purpose=MetricObservationPurpose.HARD_CONSTRAINT,
                metric=constraint.metric,
                unit=constraint.unit,
            ),
        ),
    )
    path = enumerate_candidate_paths(graph, "h1", "h4", 10).paths[0]
    candidate = EvaluationCandidate(
        candidate_id="boundary-candidate",
        request_fingerprint=planning_request_fingerprint(request),
        path=path,
        feasibility=CandidateFeasibility.CANDIDATE,
    )
    target = EvaluationTarget(
        candidate_id=candidate.candidate_id,
        request_fingerprint=planning_request_fingerprint(request),
        path_fingerprint=physical_path_fingerprint(path),
        requirement_id=requirement_id,
    )
    observation = MetricObservation(
        target=target,
        metric=constraint.metric,
        unit=constraint.unit,
        value=measured_value,
        status=ObservationStatus.VALID,
        collected_at=EVALUATED_AT,
        source="normalized-manual-boundary-test",
    )
    result = evaluate_hard_constraints(
        plan,
        (candidate,),
        (observation,),
        evaluated_at=EVALUATED_AT,
        freshness_policy=FRESHNESS_POLICY,
    )
    return result.status


def _run_case(name, expected, comparison, measured_value, **constraint_kwargs):
    try:
        actual = _build_evaluation(comparison, measured_value, **constraint_kwargs)
    except Exception as exc:
        print(
            f"{name}: expected={expected.value}, actual=ERROR "
            f"({type(exc).__name__}: {exc}) — FAIL"
        )
        return False

    passed = actual == expected
    print(
        f"{name}: expected={expected.value}, actual={actual.value} — "
        f"{'PASS' if passed else 'FAIL'}"
    )
    return passed


def main():
    cases = (
        (
            "LTE exact threshold",
            EvaluationStatus.SATISFIED,
            Comparison.LTE,
            20.0,
            {"value": 20.0},
        ),
        (
            "LTE slightly above threshold",
            EvaluationStatus.VIOLATED,
            Comparison.LTE,
            20.0001,
            {"value": 20.0},
        ),
        (
            "GTE exact threshold",
            EvaluationStatus.SATISFIED,
            Comparison.GTE,
            20.0,
            {"value": 20.0},
        ),
        (
            "GTE slightly below threshold",
            EvaluationStatus.VIOLATED,
            Comparison.GTE,
            19.9999,
            {"value": 20.0},
        ),
        (
            "BETWEEN exact lower boundary",
            EvaluationStatus.SATISFIED,
            Comparison.BETWEEN,
            10.0,
            {"lower_bound": 10.0, "upper_bound": 20.0},
        ),
        (
            "BETWEEN exact upper boundary",
            EvaluationStatus.SATISFIED,
            Comparison.BETWEEN,
            20.0,
            {"lower_bound": 10.0, "upper_bound": 20.0},
        ),
        (
            "BETWEEN just below lower boundary",
            EvaluationStatus.VIOLATED,
            Comparison.BETWEEN,
            9.9999,
            {"lower_bound": 10.0, "upper_bound": 20.0},
        ),
        (
            "BETWEEN just above upper boundary",
            EvaluationStatus.VIOLATED,
            Comparison.BETWEEN,
            20.0001,
            {"lower_bound": 10.0, "upper_bound": 20.0},
        ),
        (
            "EQ tolerance exact equality",
            EvaluationStatus.SATISFIED,
            Comparison.EQ,
            20.0,
            {"value": 20.0, "tolerance": 0.5},
        ),
        (
            "EQ tolerance exact inclusive difference",
            EvaluationStatus.SATISFIED,
            Comparison.EQ,
            20.5,
            {"value": 20.0, "tolerance": 0.5},
        ),
        (
            "EQ tolerance difference just over limit",
            EvaluationStatus.VIOLATED,
            Comparison.EQ,
            20.5001,
            {"value": 20.0, "tolerance": 0.5},
        ),
        (
            "EQ without tolerance exact equality",
            EvaluationStatus.SATISFIED,
            Comparison.EQ,
            20.0,
            {"value": 20.0},
        ),
        (
            "EQ without tolerance non-zero difference",
            EvaluationStatus.VIOLATED,
            Comparison.EQ,
            20.0001,
            {"value": 20.0},
        ),
    )

    outcomes = []
    for name, expected, comparison, measured_value, constraint_kwargs in cases:
        outcomes.append(
            _run_case(
                name,
                expected,
                comparison,
                measured_value,
                **constraint_kwargs,
            )
        )

    passed = sum(outcomes)
    failed = len(outcomes) - passed
    print(f"\nSummary: {passed} passed, {failed} failed, {len(outcomes)} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
