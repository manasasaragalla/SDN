from datetime import datetime, timedelta, timezone
from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import BaseModel, ValidationError

from backend.capabilities import resolve_capabilities
from backend.models.canonical_intent import (
    CanonicalIntent,
    Comparison,
    MetricConstraint,
    TrafficScope,
)
from backend.models.network import Host, Link, TopologyGraph
from backend.planner.constraint_evaluation import (
    CandidateEvaluation,
    EvaluationCandidate,
    EvaluationInputError,
    EvaluationStatus,
    EvaluationTarget,
    FreshnessPolicy,
    MetricFreshnessLimit,
    MetricObservation,
    ObservationStatus,
    PlanEvaluation,
    RequirementEvaluation,
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
from backend.planner.path_enumeration import (
    EnumeratedPath,
    enumerate_candidate_paths,
)

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)


def _host(name, switch, port):
    last_octet = 1 if name == "h1" else 4
    return Host(
        name=name,
        ip=f"10.0.0.{last_octet}",
        mac=f"00:00:00:00:00:{last_octet:02x}",
        switch=switch,
        switch_port=port,
    )


def _graph(*, parallel=False):
    if parallel:
        return TopologyGraph(
            switches={"s1": 1, "s2": 2},
            hosts={"h1": _host("h1", "s1", 1), "h4": _host("h4", "s2", 1)},
            links=[
                Link(node_a="s1", port_a=2, node_b="s2", port_b=2),
                Link(node_a="s1", port_a=3, node_b="s2", port_b=3),
            ],
        )
    return TopologyGraph(
        switches={"s1": 1},
        hosts={"h1": _host("h1", "s1", 1), "h4": _host("h4", "s1", 2)},
        links=[],
    )


def _context(constraints, *, parallel=False):
    graph = _graph(parallel=parallel)
    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        constraints=constraints,
    )
    request = PlanningRequest(
        intent=intent,
        topology=graph,
        capabilities=resolve_capabilities(intent, graph=graph),
    )
    hard_constraints = tuple(
        HardConstraintRequirement(
            requirement_id=f"r{index}",
            constraint=constraint,
        )
        for index, constraint in enumerate(constraints)
    )
    plan = Plan(
        request=request,
        capability_readiness=request.capabilities.eligibility,
        planning_readiness=PlanningReadiness.CONDITIONAL,
        hard_constraints=hard_constraints,
        required_observations=tuple(
            RequiredMetricObservation(
                observation_id=f"observation-{index}",
                requirement_id=f"r{index}",
                purpose=MetricObservationPurpose.HARD_CONSTRAINT,
                metric=constraint.metric,
                unit=constraint.unit,
            )
            for index, constraint in enumerate(constraints)
        ),
    )
    paths = enumerate_candidate_paths(graph, "h1", "h4", 10).paths
    return plan, tuple(paths)


def _candidate(plan, path, *, candidate_id="candidate-1", feasibility=CandidateFeasibility.CANDIDATE):
    return EvaluationCandidate(
        candidate_id=candidate_id,
        request_fingerprint=planning_request_fingerprint(plan.request),
        path=path,
        feasibility=feasibility,
    )


def _target(plan, candidate, requirement_id="r0"):
    return EvaluationTarget(
        candidate_id=candidate.candidate_id,
        request_fingerprint=planning_request_fingerprint(plan.request),
        path_fingerprint=physical_path_fingerprint(candidate.path),
        requirement_id=requirement_id,
    )


def _observation(
    plan,
    candidate,
    value,
    *,
    requirement_id="r0",
    metric="latency",
    unit="ms",
    status=ObservationStatus.VALID,
    collected_at=NOW,
    evaluation_run_id=None,
):
    return MetricObservation(
        target=_target(plan, candidate, requirement_id),
        metric=metric,
        unit=unit,
        value=value,
        status=status,
        collected_at=collected_at,
        source="normalized-test-observation",
        evaluation_run_id=evaluation_run_id,
    )


def _evaluate(plan, paths, observations, candidates=None, **kwargs):
    candidates = candidates or (_candidate(plan, paths[0]),)
    return evaluate_hard_constraints(
        plan,
        candidates,
        observations,
        evaluated_at=NOW,
        freshness_policy=FreshnessPolicy(
            limits=(
                MetricFreshnessLimit(metric="latency", max_age=timedelta(minutes=5)),
                MetricFreshnessLimit(metric="bandwidth", max_age=timedelta(minutes=5)),
                MetricFreshnessLimit(metric="packet_loss", max_age=timedelta(minutes=5)),
                MetricFreshnessLimit(metric="jitter", max_age=timedelta(minutes=5)),
            )
        ),
        **kwargs,
    )


@pytest.mark.parametrize(
    ("comparison", "value", "expected"),
    [
        (Comparison.GT, 10, EvaluationStatus.VIOLATED),
        (Comparison.GT, 10.01, EvaluationStatus.SATISFIED),
        (Comparison.GTE, 10, EvaluationStatus.SATISFIED),
        (Comparison.LT, 10, EvaluationStatus.VIOLATED),
        (Comparison.LT, 9.99, EvaluationStatus.SATISFIED),
        (Comparison.LTE, 10, EvaluationStatus.SATISFIED),
        (Comparison.EQ, 10, EvaluationStatus.SATISFIED),
        (Comparison.EQ, 10.0001, EvaluationStatus.VIOLATED),
    ],
)
def test_scalar_comparison_operators_and_boundaries(comparison, value, expected):
    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=comparison, value=10, unit="ms")]
    )
    candidate = _candidate(plan, paths[0])

    result = _evaluate(plan, paths, (_observation(plan, candidate, value),))

    assert result.status == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (9.99, EvaluationStatus.VIOLATED),
        (10, EvaluationStatus.SATISFIED),
        (20, EvaluationStatus.SATISFIED),
        (20.01, EvaluationStatus.VIOLATED),
    ],
)
def test_between_bounds_are_inclusive(value, expected):
    plan, paths = _context(
        [
            MetricConstraint(
                metric="latency",
                comparison=Comparison.BETWEEN,
                lower_bound=10,
                upper_bound=20,
                unit="ms",
            )
        ]
    )
    candidate = _candidate(plan, paths[0])
    assert _evaluate(
        plan, paths, (_observation(plan, candidate, value),)
    ).status == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(9, EvaluationStatus.SATISFIED), (11, EvaluationStatus.SATISFIED), (11.01, EvaluationStatus.VIOLATED)],
)
def test_eq_absolute_tolerance_is_inclusive_without_extra_epsilon(value, expected):
    plan, paths = _context(
        [
            MetricConstraint(
                metric="latency",
                comparison=Comparison.EQ,
                value=10,
                tolerance=1,
                unit="ms",
            )
        ]
    )
    candidate = _candidate(plan, paths[0])
    assert _evaluate(
        plan, paths, (_observation(plan, candidate, value),)
    ).status == expected


@pytest.mark.parametrize(
    ("status", "value"),
    [
        (ObservationStatus.FAILED, 100),
        (ObservationStatus.INVALID, 10),
        (ObservationStatus.VALID, None),
        (ObservationStatus.VALID, float("nan")),
        (ObservationStatus.VALID, float("inf")),
    ],
)
def test_failed_missing_and_nonfinite_observations_are_unknown(status, value):
    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")]
    )
    candidate = _candidate(plan, paths[0])
    result = _evaluate(plan, paths, (_observation(plan, candidate, value, status=status),))
    assert result.status == EvaluationStatus.UNKNOWN


def test_missing_observation_is_unknown():
    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")]
    )
    assert _evaluate(plan, paths, ()).status == EvaluationStatus.UNKNOWN


@pytest.mark.parametrize(
    ("metric", "unit", "value"),
    [
        ("latency", "seconds", 10),
        ("packet_loss", "%", 101),
    ],
)
def test_unit_mismatch_and_metric_domain_violations_are_unknown(metric, unit, value):
    constraint_unit = "ms" if metric == "latency" else "%"
    plan, paths = _context(
        [
            MetricConstraint(
                metric=metric,
                comparison=Comparison.LTE,
                value=50 if metric == "latency" else 100,
                unit=constraint_unit,
            )
        ]
    )
    candidate = _candidate(plan, paths[0])
    result = _evaluate(
        plan,
        paths,
        (_observation(plan, candidate, value, metric=metric, unit=unit),),
    )
    assert result.status == EvaluationStatus.UNKNOWN


@pytest.mark.parametrize(
    ("collected_at", "expected"),
    [
        (NOW + timedelta(seconds=1), EvaluationStatus.UNKNOWN),
        (NOW - timedelta(minutes=5), EvaluationStatus.SATISFIED),
        (NOW - timedelta(minutes=5, microseconds=1), EvaluationStatus.UNKNOWN),
    ],
)
def test_future_stale_and_exact_age_limit(collected_at, expected):
    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")]
    )
    candidate = _candidate(plan, paths[0])
    result = _evaluate(
        plan, paths, (_observation(plan, candidate, 20, collected_at=collected_at),)
    )
    assert result.status == expected


def test_freshness_inputs_must_be_explicit_and_timezone_aware():
    with pytest.raises(ValidationError, match="timezone-aware"):
        MetricObservation(
            target=EvaluationTarget(
                candidate_id="c",
                request_fingerprint="a" * 64,
                path_fingerprint="b" * 64,
                requirement_id="r",
            ),
            metric="latency",
            unit="ms",
            value=1,
            status=ObservationStatus.VALID,
            collected_at=datetime(2026, 11, 4),
            source="test",
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        PlanEvaluation(
            request_fingerprint="a" * 64,
            evaluated_at=datetime(2026, 11, 4),
            status=EvaluationStatus.UNKNOWN,
        )
    with pytest.raises(ValidationError, match="must not be negative"):
        MetricFreshnessLimit(metric="latency", max_age=timedelta(seconds=-1))


@pytest.mark.parametrize("value", [True, False])
def test_boolean_observation_values_are_rejected(value):
    plan, paths = _context(
        [
            MetricConstraint(
                metric="packet_loss",
                comparison=Comparison.LTE,
                value=5,
                unit="%",
            )
        ]
    )
    candidate = _candidate(plan, paths[0])

    with pytest.raises(ValidationError, match="not boolean"):
        _observation(
            plan,
            candidate,
            value,
            metric="packet_loss",
            unit="%",
        )


@pytest.mark.parametrize("value", [1, 1.25])
def test_numeric_integer_and_float_observation_values_are_accepted(value):
    observation = MetricObservation(
        target=EvaluationTarget(
            candidate_id="candidate",
            request_fingerprint="a" * 64,
            path_fingerprint="b" * 64,
            requirement_id="requirement",
        ),
        metric="latency",
        unit="ms",
        value=value,
        status=ObservationStatus.VALID,
        collected_at=NOW,
        source="test",
    )
    assert observation.value == value


def test_boolean_input_cannot_coerce_into_satisfied_constraint():
    plan, paths = _context(
        [
            MetricConstraint(
                metric="packet_loss",
                comparison=Comparison.LTE,
                value=5,
                unit="%",
            )
        ]
    )
    candidate = _candidate(plan, paths[0])
    with pytest.raises(ValidationError):
        _observation(
            plan,
            candidate,
            True,
            metric="packet_loss",
            unit="%",
        )


def test_duplicate_observations_for_target_are_unknown():
    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")]
    )
    candidate = _candidate(plan, paths[0])
    observation = _observation(plan, candidate, 20)
    result = _evaluate(plan, paths, (observation, observation))
    assert result.status == EvaluationStatus.UNKNOWN
    assert "Multiple observations" in result.candidates[0].requirements[0].reason


def test_observation_with_wrong_identity_is_rejected():
    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")]
    )
    candidate = _candidate(plan, paths[0])
    expected = _target(plan, candidate)
    wrong_target = EvaluationTarget(
        candidate_id="another-candidate",
        request_fingerprint=expected.request_fingerprint,
        path_fingerprint=expected.path_fingerprint,
        requirement_id=expected.requirement_id,
    )
    observation = MetricObservation(
        target=wrong_target,
        metric="latency",
        unit="ms",
        value=20,
        status=ObservationStatus.VALID,
        collected_at=NOW,
        source="test",
    )
    with pytest.raises(EvaluationInputError, match="does not identify"):
        _evaluate(plan, paths, (observation,))


def test_observation_with_wrong_physical_path_fingerprint_is_rejected():
    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")]
    )
    candidate = _candidate(plan, paths[0])
    target = _target(plan, candidate)
    wrong_target = EvaluationTarget(
        candidate_id=target.candidate_id,
        request_fingerprint=target.request_fingerprint,
        path_fingerprint="0" * 64,
        requirement_id=target.requirement_id,
    )
    observation = MetricObservation(
        target=wrong_target,
        metric="latency",
        unit="ms",
        value=20,
        status=ObservationStatus.VALID,
        collected_at=NOW,
        source="test",
    )
    with pytest.raises(EvaluationInputError, match="does not identify"):
        _evaluate(plan, paths, (observation,))


def test_candidate_request_fingerprint_and_endpoints_are_validated():
    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")]
    )
    invalid_binding = EvaluationCandidate(
        candidate_id="candidate-1",
        request_fingerprint="0" * 64,
        path=paths[0],
        feasibility=CandidateFeasibility.CANDIDATE,
    )
    with pytest.raises(EvaluationInputError, match="different planning request"):
        _evaluate(plan, paths, (), candidates=(invalid_binding,))

    wrong_path = enumerate_candidate_paths(_graph(), "h4", "h1", 1).paths[0]
    candidate = _candidate(plan, wrong_path)
    with pytest.raises(EvaluationInputError, match="endpoints"):
        _evaluate(plan, (wrong_path,), (), candidates=(candidate,))


def _replace_plan_capability_assessments(plan, assessments):
    capabilities = deepcopy(plan.request.capabilities)
    capabilities.constraints = assessments
    request = PlanningRequest(
        intent=plan.request.intent,
        topology=plan.request.topology,
        capabilities=capabilities,
    )
    return Plan(
        request=request,
        capability_readiness=plan.capability_readiness,
        planning_readiness=plan.planning_readiness,
        hard_constraints=plan.hard_constraints,
        required_observations=plan.required_observations,
    )


def test_capability_assessments_bind_by_requirement_id_after_reordering():
    plan, paths = _context(
        [
            MetricConstraint(
                metric="packet_loss",
                comparison=Comparison.LTE,
                value=101,
                unit="%",
            ),
            MetricConstraint(
                metric="packet_loss",
                comparison=Comparison.LTE,
                value=5,
                unit="%",
            ),
        ]
    )
    reordered_plan = _replace_plan_capability_assessments(
        plan,
        list(reversed(plan.request.capabilities.constraints)),
    )
    candidate = _candidate(reordered_plan, paths[0])
    observations = (
        _observation(
            reordered_plan,
            candidate,
            50,
            requirement_id="r0",
            metric="packet_loss",
            unit="%",
        ),
        _observation(
            reordered_plan,
            candidate,
            1,
            requirement_id="r1",
            metric="packet_loss",
            unit="%",
        ),
    )

    result = _evaluate(
        reordered_plan, paths, observations, candidates=(candidate,)
    )

    assert result.candidates[0].requirements[0].status == EvaluationStatus.UNSUPPORTED
    assert result.candidates[0].requirements[1].status == EvaluationStatus.SATISFIED
    assert result.status == EvaluationStatus.UNKNOWN


@pytest.mark.parametrize(
    "mutation",
    ["missing", "duplicate", "mismatched-id", "mismatched-metric"],
)
def test_invalid_capability_assessment_sets_are_rejected(mutation):
    plan, paths = _context(
        [
            MetricConstraint(
                metric="packet_loss",
                comparison=Comparison.LTE,
                value=101,
                unit="%",
            ),
            MetricConstraint(
                metric="packet_loss",
                comparison=Comparison.LTE,
                value=5,
                unit="%",
            ),
        ]
    )
    assessments = deepcopy(plan.request.capabilities.constraints)
    if mutation == "missing":
        assessments.pop()
    elif mutation == "duplicate":
        assessments.append(deepcopy(assessments[0]))
    else:
        if mutation == "mismatched-id":
            assessments[0].requirement_id = "wrong-requirement"
        else:
            assessments[0].metric = "latency"
    invalid_plan = _replace_plan_capability_assessments(plan, assessments)
    candidate = _candidate(invalid_plan, paths[0])

    with pytest.raises(EvaluationInputError, match="(?i)capability assessment"):
        _evaluate(
            invalid_plan, paths, (), candidates=(candidate,)
        )


def test_parallel_physical_paths_with_same_nodes_evaluate_independently():
    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")],
        parallel=True,
    )
    candidates = (
        _candidate(plan, paths[0], candidate_id="parallel-a"),
        _candidate(plan, paths[1], candidate_id="parallel-b"),
    )
    assert paths[0].nodes == paths[1].nodes
    assert physical_path_fingerprint(paths[0]) != physical_path_fingerprint(paths[1])
    observations = (
        _observation(plan, candidates[0], 20),
        _observation(plan, candidates[1], 40),
    )
    result = _evaluate(plan, paths, observations, candidates=candidates)
    assert [candidate.status for candidate in result.candidates] == [
        EvaluationStatus.SATISFIED,
        EvaluationStatus.VIOLATED,
    ]
    assert result.status == EvaluationStatus.SATISFIED


@pytest.mark.parametrize(
    ("feasibility", "expected"),
    [
        (CandidateFeasibility.CANDIDATE, EvaluationStatus.SATISFIED),
        (CandidateFeasibility.UNKNOWN, EvaluationStatus.SATISFIED),
    ],
)
def test_candidate_and_unknown_topology_feasibility_can_be_evaluated(feasibility, expected):
    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")]
    )
    candidate = _candidate(plan, paths[0], feasibility=feasibility)
    result = _evaluate(plan, paths, (_observation(plan, candidate, 20),))
    assert result.candidates[0].status == expected


def test_proven_infeasible_candidates_are_excluded():
    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")]
    )
    candidate = _candidate(
        plan, paths[0], feasibility=CandidateFeasibility.PROVEN_INFEASIBLE
    )
    result = _evaluate(plan, paths, (), candidates=(candidate,))
    assert result.status == EvaluationStatus.NOT_EVALUATED
    assert result.candidates == ()


def test_conjunctive_constraints_and_plan_aggregation():
    constraints = [
        MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms"),
        MetricConstraint(metric="bandwidth", comparison=Comparison.GTE, value=10, unit="Mbps"),
    ]
    plan, paths = _context(constraints, parallel=True)
    candidate = _candidate(plan, paths[0])
    observations = (
        _observation(plan, candidate, 20, requirement_id="r0"),
        _observation(
            plan,
            candidate,
            20,
            requirement_id="r1",
            metric="bandwidth",
            unit="Mbps",
        ),
    )
    assert _evaluate(plan, paths, observations).status == EvaluationStatus.SATISFIED

    violated_and_unknown = (
        _observation(plan, candidate, 40, requirement_id="r0"),
    )
    assert _evaluate(plan, paths, violated_and_unknown).status == EvaluationStatus.VIOLATED


def test_unsupported_metric_is_not_confused_with_plannability():
    plan, paths = _context(
        [MetricConstraint(metric="packet_loss", comparison=Comparison.LTE, value=5, unit="%")]
    )
    candidate = _candidate(plan, paths[0])
    result = _evaluate(
        plan,
        paths,
        (_observation(plan, candidate, 1, metric="packet_loss", unit="%"),),
    )
    assert result.status == EvaluationStatus.SATISFIED
    assert plan.request.capabilities.constraints[0].plannable.status.value == "UNSUPPORTED"


def test_unmeasurable_metric_is_unsupported_even_with_a_supplied_observation():
    plan, paths = _context(
        [MetricConstraint(metric="jitter", comparison=Comparison.LTE, value=5, unit="ms")]
    )
    candidate = _candidate(plan, paths[0])
    result = _evaluate(
        plan,
        paths,
        (_observation(plan, candidate, 1, metric="jitter", unit="ms"),),
    )
    assert result.status == EvaluationStatus.UNKNOWN
    assert result.candidates[0].requirements[0].status == EvaluationStatus.UNSUPPORTED


def test_zero_packets_missing_throughput_and_failed_execution_stay_invalid():
    plan, paths = _context(
        [MetricConstraint(metric="packet_loss", comparison=Comparison.LTE, value=10, unit="%")]
    )
    candidate = _candidate(plan, paths[0])
    zero_packet_result = _observation(
        plan, candidate, 100, metric="packet_loss", unit="%", status=ObservationStatus.FAILED
    )
    assert _evaluate(plan, paths, (zero_packet_result,)).status == EvaluationStatus.UNKNOWN

    throughput_plan, throughput_paths = _context(
        [MetricConstraint(metric="bandwidth", comparison=Comparison.GTE, value=10, unit="Mbps")],
        parallel=True,
    )
    throughput_candidate = _candidate(throughput_plan, throughput_paths[0])
    missing_throughput = _observation(
        throughput_plan,
        throughput_candidate,
        None,
        metric="bandwidth",
        unit="Mbps",
    )
    assert _evaluate(
        throughput_plan, throughput_paths, (missing_throughput,)
    ).status == EvaluationStatus.UNKNOWN


def test_no_constraints_and_no_eligible_candidates_are_not_evaluated():
    plan, paths = _context([])
    candidate = _candidate(plan, paths[0])
    no_constraints = evaluate_hard_constraints(
        plan,
        (candidate,),
        (),
        evaluated_at=NOW,
        freshness_policy=FreshnessPolicy(limits=()),
    )
    assert no_constraints.status == EvaluationStatus.NOT_EVALUATED

    constrained_plan, constrained_paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")]
    )
    infeasible = _candidate(
        constrained_plan,
        constrained_paths[0],
        feasibility=CandidateFeasibility.PROVEN_INFEASIBLE,
    )
    no_eligible = evaluate_hard_constraints(
        constrained_plan,
        (infeasible,),
        (),
        evaluated_at=NOW,
        freshness_policy=FreshnessPolicy(limits=()),
    )
    assert no_eligible.status == EvaluationStatus.NOT_EVALUATED


def test_plan_status_is_violated_only_when_all_candidates_are_violated():
    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")],
        parallel=True,
    )
    candidates = (
        _candidate(plan, paths[0], candidate_id="a"),
        _candidate(plan, paths[1], candidate_id="b"),
    )
    result = _evaluate(
        plan,
        paths,
        (
            _observation(plan, candidates[0], 40),
            _observation(plan, candidates[1], 50),
        ),
        candidates=candidates,
    )
    assert result.status == EvaluationStatus.VIOLATED

    partially_unknown = _evaluate(
        plan,
        paths,
        (_observation(plan, candidates[0], 40),),
        candidates=candidates,
    )
    assert partially_unknown.status == EvaluationStatus.UNKNOWN


def test_result_models_reject_contradictory_candidate_and_plan_states():
    target = EvaluationTarget(
        candidate_id="candidate",
        request_fingerprint="a" * 64,
        path_fingerprint="b" * 64,
        requirement_id="r0",
    )
    violated = RequirementEvaluation(
        target=target,
        metric="latency",
        unit="ms",
        status=EvaluationStatus.VIOLATED,
        observed_value=50,
    )
    with pytest.raises(ValidationError, match="Candidate status must be VIOLATED"):
        CandidateEvaluation(
            candidate_id="candidate",
            request_fingerprint="a" * 64,
            path_fingerprint="b" * 64,
            feasibility=CandidateFeasibility.CANDIDATE,
            status=EvaluationStatus.SATISFIED,
            requirements=(violated,),
        )
    with pytest.raises(ValidationError, match="Proven-infeasible"):
        CandidateEvaluation(
            candidate_id="candidate",
            request_fingerprint="a" * 64,
            path_fingerprint="b" * 64,
            feasibility=CandidateFeasibility.PROVEN_INFEASIBLE,
            status=EvaluationStatus.SATISFIED,
        )
    with pytest.raises(ValidationError, match="Plan evaluation status"):
        PlanEvaluation(
            request_fingerprint="a" * 64,
            evaluated_at=NOW,
            status=EvaluationStatus.SATISFIED,
            candidates=(),
        )


def test_result_models_enforce_plan_aggregation_and_roundtrip():
    fp = "b" * 64
    request_fp = "a" * 64

    def candidate(candidate_id, status):
        return CandidateEvaluation(
            candidate_id=candidate_id,
            request_fingerprint=request_fp,
            path_fingerprint=fp,
            feasibility=CandidateFeasibility.CANDIDATE,
            status=status,
            requirements=(
                RequirementEvaluation(
                    target=EvaluationTarget(
                        candidate_id=candidate_id,
                        request_fingerprint=request_fp,
                        path_fingerprint=fp,
                        requirement_id="r0",
                    ),
                    metric="latency",
                    unit="ms",
                    status=status,
                    observed_value=10
                    if status in (
                        EvaluationStatus.SATISFIED,
                        EvaluationStatus.VIOLATED,
                    )
                    else None,
                ),
            ),
        )

    mixed = PlanEvaluation(
        request_fingerprint=request_fp,
        evaluated_at=NOW,
        status=EvaluationStatus.UNKNOWN,
        candidates=(
            candidate("violated", EvaluationStatus.VIOLATED),
            candidate("unknown", EvaluationStatus.UNKNOWN),
        ),
    )
    assert PlanEvaluation.model_validate(mixed.model_dump(mode="json")) == mixed
    all_violated = PlanEvaluation(
        request_fingerprint=request_fp,
        evaluated_at=NOW,
        status=EvaluationStatus.VIOLATED,
        candidates=(candidate("one", EvaluationStatus.VIOLATED),),
    )
    assert all_violated.status == EvaluationStatus.VIOLATED
    no_eligible = PlanEvaluation(
        request_fingerprint=request_fp,
        evaluated_at=NOW,
        status=EvaluationStatus.NOT_EVALUATED,
        candidates=(
            CandidateEvaluation(
                candidate_id="excluded",
                request_fingerprint=request_fp,
                path_fingerprint=fp,
                feasibility=CandidateFeasibility.PROVEN_INFEASIBLE,
                status=EvaluationStatus.NOT_EVALUATED,
            ),
        ),
    )
    assert no_eligible.status == EvaluationStatus.NOT_EVALUATED


def test_supported_construction_paths_validate_phase_3c_models():
    target = EvaluationTarget(
        candidate_id="candidate",
        request_fingerprint="a" * 64,
        path_fingerprint="b" * 64,
        requirement_id="r0",
    )
    invalid_plan = {
        "request_fingerprint": "a" * 64,
        "evaluated_at": NOW,
        "status": EvaluationStatus.SATISFIED,
        "candidates": (),
    }
    invalid_observation = {
        "target": target,
        "metric": "latency",
        "unit": "ms",
        "value": True,
        "status": ObservationStatus.VALID,
        "collected_at": NOW,
        "source": "test",
    }

    with pytest.raises(ValidationError, match="Plan evaluation status"):
        PlanEvaluation(**invalid_plan)
    with pytest.raises(ValidationError, match="Plan evaluation status"):
        PlanEvaluation.model_validate(invalid_plan)
    with pytest.raises(ValidationError, match="Plan evaluation status"):
        PlanEvaluation.model_validate_json(
            '{"request_fingerprint":"' + ("a" * 64)
            + '","evaluated_at":"2026-11-04T12:00:00Z",'
            '"status":"SATISFIED","candidates":[]}'
        )

    with pytest.raises(ValidationError, match="not boolean"):
        MetricObservation(**invalid_observation)
    with pytest.raises(ValidationError, match="not boolean"):
        MetricObservation.model_validate(invalid_observation)
    with pytest.raises(ValidationError, match="not boolean"):
        MetricObservation.model_validate_json(
            '{"target":{"candidate_id":"candidate","request_fingerprint":"'
            + ("a" * 64)
            + '","path_fingerprint":"'
            + ("b" * 64)
            + '","requirement_id":"r0"},"metric":"latency","unit":"ms",'
            '"value":true,"status":"VALID",'
            '"collected_at":"2026-11-04T12:00:00Z","source":"test"}'
        )


def test_planner_construction_guards_and_validated_instance_revalidation():
    target = EvaluationTarget(
        candidate_id="candidate",
        request_fingerprint="a" * 64,
        path_fingerprint="b" * 64,
        requirement_id="r0",
    )
    valid_observation = MetricObservation(
        target=target,
        metric="latency",
        unit="ms",
        value=10,
        status=ObservationStatus.VALID,
        collected_at=NOW,
        source="test",
    )
    valid_plan = PlanEvaluation(
        request_fingerprint="a" * 64,
        evaluated_at=NOW,
        status=EvaluationStatus.NOT_EVALUATED,
    )
    valid_candidate = CandidateEvaluation(
        candidate_id="candidate",
        request_fingerprint="a" * 64,
        path_fingerprint="b" * 64,
        feasibility=CandidateFeasibility.CANDIDATE,
        status=EvaluationStatus.NOT_EVALUATED,
    )

    with pytest.raises(
        TypeError, match="MetricObservation requires validated construction"
    ):
        MetricObservation.model_construct(**valid_observation.model_dump())
    with pytest.raises(
        TypeError, match="PlanEvaluation requires validated construction"
    ):
        PlanEvaluation.model_construct(**valid_plan.model_dump())
    with pytest.raises(
        TypeError, match="CandidateEvaluation requires validated construction"
    ):
        CandidateEvaluation.model_construct(**valid_candidate.model_dump())
    with pytest.raises(TypeError, match="do not support model_copy"):
        valid_observation.model_copy(update={"value": True})
    with pytest.raises(TypeError, match="do not support model_copy"):
        valid_plan.model_copy(update={"status": EvaluationStatus.SATISFIED})
    with pytest.raises(TypeError, match="do not support model_copy"):
        valid_candidate.model_copy(update={"status": EvaluationStatus.SATISFIED})

    restored_observation = MetricObservation.model_validate_json(
        valid_observation.model_dump_json()
    )
    restored_plan = PlanEvaluation.model_validate_json(valid_plan.model_dump_json())
    restored_candidate = CandidateEvaluation.model_validate_json(
        valid_candidate.model_dump_json()
    )
    assert restored_observation == valid_observation
    assert restored_plan == valid_plan
    assert restored_candidate == valid_candidate

    forged_plan = BaseModel.model_construct.__func__(
        PlanEvaluation,
        request_fingerprint="a" * 64,
        evaluated_at=NOW,
        status=EvaluationStatus.SATISFIED,
        candidates=(),
    )
    forged_observation = BaseModel.model_construct.__func__(
        MetricObservation,
        target=target,
        metric="latency",
        unit="ms",
        value=True,
        status=ObservationStatus.VALID,
        collected_at=NOW,
        source="test",
    )
    forged_candidate = BaseModel.model_construct.__func__(
        CandidateEvaluation,
        candidate_id="candidate",
        request_fingerprint="a" * 64,
        path_fingerprint="b" * 64,
        feasibility=CandidateFeasibility.CANDIDATE,
        status=EvaluationStatus.SATISFIED,
        requirements=(),
    )
    assert forged_plan.status == EvaluationStatus.SATISFIED
    assert forged_observation.value is True
    assert forged_candidate.status == EvaluationStatus.SATISFIED

    with pytest.raises(ValidationError, match="Plan evaluation status"):
        PlanEvaluation.model_validate(forged_plan)
    with pytest.raises(ValidationError, match="not boolean"):
        MetricObservation.model_validate(forged_observation)
    with pytest.raises(
        ValidationError, match="Candidate status must be NOT_EVALUATED"
    ):
        CandidateEvaluation.model_validate(forged_candidate)


def test_evaluation_is_deterministic_does_not_mutate_inputs_or_plan_status():
    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")]
    )
    candidate = _candidate(plan, paths[0])
    observation = _observation(plan, candidate, 20)
    observation_dump = observation.model_dump(mode="json")
    candidate_dump = candidate.model_dump(mode="json")
    first = _evaluate(plan, paths, (observation,))
    second = _evaluate(plan, paths, (observation,))

    assert first == second
    assert observation.model_dump(mode="json") == observation_dump
    assert candidate.model_dump(mode="json") == candidate_dump
    assert plan.satisfaction_status.value == "NOT_VERIFIED"
    with pytest.raises(ValidationError):
        candidate.candidate_id = "mutated"


def test_evaluation_run_and_plan_fingerprint_propagate_backward_compatibly():
    from backend.models.fingerprints import model_fingerprint

    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")]
    )
    candidate = _candidate(plan, paths[0])
    observation = _observation(
        plan,
        candidate,
        20,
        evaluation_run_id="run-2026-11-04",
    )
    result = _evaluate(
        plan,
        paths,
        (observation,),
        evaluation_run_id="run-2026-11-04",
    )

    assert result.evaluation_run_id == "run-2026-11-04"
    assert result.plan_fingerprint == model_fingerprint(plan)
    assert result.freshness_policy_fingerprint is not None
    assert len(result.freshness_policy_fingerprint) == 64

    legacy_observation = _observation(plan, candidate, 20)
    legacy_result = _evaluate(plan, paths, (legacy_observation,))
    assert legacy_result.evaluation_run_id is None
    assert legacy_result.freshness_policy_fingerprint is not None


def test_evaluation_rejects_missing_or_mismatched_observation_run_identity():
    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")]
    )
    candidate = _candidate(plan, paths[0])
    unbound = _observation(plan, candidate, 20)
    with pytest.raises(EvaluationInputError, match="evaluation_run_id"):
        _evaluate(
            plan,
            paths,
            (unbound,),
            evaluation_run_id="run-1",
        )

    mismatched = _observation(
        plan,
        candidate,
        20,
        evaluation_run_id="run-2",
    )
    with pytest.raises(EvaluationInputError, match="evaluation_run_id"):
        _evaluate(
            plan,
            paths,
            (mismatched,),
            evaluation_run_id="run-1",
        )


def test_freshness_policy_must_cover_each_constraint_metric():
    plan, paths = _context(
        [MetricConstraint(metric="latency", comparison=Comparison.LTE, value=30, unit="ms")]
    )
    candidate = _candidate(plan, paths[0])
    with pytest.raises(EvaluationInputError, match="No freshness limit"):
        evaluate_hard_constraints(
            plan,
            (candidate,),
            (),
            evaluated_at=NOW,
            freshness_policy=FreshnessPolicy(
                limits=(
                    MetricFreshnessLimit(
                        metric="bandwidth", max_age=timedelta(minutes=5)
                    ),
                )
            ),
        )


def test_evaluator_imports_no_measurement_or_execution_modules():
    root = Path(__file__).parents[1]
    script = """
import sys
import backend.planner.constraint_evaluation
forbidden = (
    "backend.measurement",
    "backend.deployment",
    "backend.pipeline",
    "backend.cli",
    "backend.compiler",
    "mininet",
    "ryu",
)
loaded = [
    module for module in sys.modules
    if any(module == prefix or module.startswith(prefix + ".") for prefix in forbidden)
]
if loaded:
    raise SystemExit(f"unexpected execution dependencies loaded: {loaded}")
"""
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
