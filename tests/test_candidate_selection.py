from datetime import datetime, timedelta, timezone
import json
import math

import pytest
from pydantic import ValidationError

from backend.capabilities import CapabilityStatus, resolve_capabilities
from backend.models.canonical_intent import (
    CanonicalIntent,
    Comparison,
    MetricConstraint,
    OptimizationDirection,
    OptimizationObjective,
    TrafficScope,
)
from backend.models.network import Host, Link, TopologyGraph
from backend.models.fingerprints import model_fingerprint
from backend.models.measurement import LatencyResult
from backend.planner.candidate_selection import (
    CandidateSelectionResult,
    ObjectiveObservation,
    SelectionInputError,
    SelectionMethod,
    SelectionScope,
    SelectionStatus,
    assess_path_feasibility,
    physical_candidate_id,
    select_candidate,
)
from backend.planner.constraint_evaluation import (
    CandidateEvaluation as ConstraintCandidateEvaluation,
    EvaluationCandidate,
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
    ConnectionKind,
    EnumeratedPath,
    PathConnection,
    PathEnumerationResult,
    enumerate_candidate_paths,
    validate_physical_path,
)

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
RUN_ID = "evaluation-round-1"


def _host(name, switch, switch_port):
    suffix = 1 if name == "h1" else 4
    return Host(
        name=name,
        ip=f"10.0.0.{suffix}",
        mac=f"00:00:00:00:00:{suffix:02x}",
        switch=switch,
        switch_port=switch_port,
    )


def _graph(capacities=(100.0, 100.0)):
    links = [
        Link(
            node_a="s1",
            port_a=2 + index,
            node_b="s2",
            port_b=2 + index,
            bw_mbps=capacity,
        )
        for index, capacity in enumerate(capacities)
    ]
    return TopologyGraph(
        switches={"s1": 1, "s2": 2},
        hosts={
            "h1": _host("h1", "s1", 1),
            "h4": _host("h4", "s2", 1),
        },
        links=links,
    )


def _plan(
    constraints=(),
    *,
    capacities=(100.0, 100.0),
    optimization=None,
):
    graph = _graph(capacities)
    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        constraints=list(constraints),
        optimization=optimization,
    )
    capabilities = resolve_capabilities(intent, graph=graph)
    request = PlanningRequest(
        intent=intent,
        topology=graph,
        capabilities=capabilities,
    )
    hard_constraints = tuple(
        HardConstraintRequirement(requirement_id=f"r{index}", constraint=item)
        for index, item in enumerate(constraints)
    )
    required = [
        RequiredMetricObservation(
            observation_id=f"observation-{index}",
            requirement_id=f"r{index}",
            purpose=MetricObservationPurpose.HARD_CONSTRAINT,
            metric=item.metric,
            unit=item.unit,
        )
        for index, item in enumerate(constraints)
    ]
    if optimization is not None:
        required.append(
            RequiredMetricObservation(
                observation_id="objective-observation",
                requirement_id="objective",
                purpose=MetricObservationPurpose.OPTIMIZATION,
                metric=optimization.metric,
                unit=optimization.unit,
            )
        )
    return Plan(
        request=request,
        capability_readiness=request.capabilities.eligibility,
        planning_readiness=PlanningReadiness.CONDITIONAL,
        hard_constraints=hard_constraints,
        required_observations=tuple(required),
        optimization=optimization,
    )


def _enumeration(plan, *, truncated=False, paths=None):
    if paths is None:
        paths = enumerate_candidate_paths(
            plan.request.topology,
            "h1",
            "h4",
            candidate_limit=1 if truncated else 10,
        ).paths
    else:
        paths = tuple(paths)
    return PathEnumerationResult(
        source="h1",
        destination="h4",
        candidate_limit=max(1, len(paths)),
        paths=paths,
        truncated=truncated,
    )


def _freshness():
    return FreshnessPolicy(
        limits=(
            MetricFreshnessLimit(metric="latency", max_age=timedelta(minutes=5)),
            MetricFreshnessLimit(metric="bandwidth", max_age=timedelta(minutes=5)),
            MetricFreshnessLimit(metric="packet_loss", max_age=timedelta(minutes=5)),
            MetricFreshnessLimit(metric="jitter", max_age=timedelta(minutes=5)),
        )
    )


def _phase3c(
    plan,
    enumeration,
    *,
    run_id=RUN_ID,
    values=None,
    observation_statuses=None,
    freshness_policy=None,
    collected_at=NOW,
):
    fp = planning_request_fingerprint(plan.request)
    candidates = []
    observations = []
    for path in enumeration.paths:
        assessment = assess_path_feasibility(plan, path)
        if assessment.feasibility == CandidateFeasibility.PROVEN_INFEASIBLE:
            continue
        candidate = EvaluationCandidate(
            candidate_id=assessment.candidate_id,
            request_fingerprint=fp,
            path=path,
            feasibility=assessment.feasibility,
        )
        candidates.append(candidate)
        for index, requirement in enumerate(plan.hard_constraints):
            target = EvaluationTarget(
                candidate_id=candidate.candidate_id,
                request_fingerprint=fp,
                path_fingerprint=physical_path_fingerprint(path),
                requirement_id=requirement.requirement_id,
            )
            value = (values or {}).get(
                (candidate.candidate_id, requirement.requirement_id),
                _satisfying_value(requirement.constraint),
            )
            observation_status = (observation_statuses or {}).get(
                (candidate.candidate_id, requirement.requirement_id),
                ObservationStatus.VALID,
            )
            observations.append(
                MetricObservation(
                    target=target,
                    metric=requirement.constraint.metric,
                    unit=requirement.constraint.unit,
                    value=(
                        value
                        if observation_status == ObservationStatus.VALID
                        else None
                    ),
                    status=observation_status,
                    collected_at=collected_at,
                    source="selection-test",
                    evaluation_run_id=run_id,
                )
            )
    return evaluate_hard_constraints(
        plan,
        candidates,
        observations,
        evaluated_at=NOW,
        freshness_policy=freshness_policy or _freshness(),
        evaluation_run_id=run_id,
    )


def _satisfying_value(constraint):
    if constraint.comparison == Comparison.GT:
        return constraint.value + 1
    if constraint.comparison in (Comparison.GTE, Comparison.EQ):
        return constraint.value
    if constraint.comparison == Comparison.BETWEEN:
        return constraint.lower_bound
    if constraint.comparison == Comparison.LT:
        return constraint.value - 1
    if constraint.comparison == Comparison.LTE:
        return constraint.value
    raise AssertionError(f"Unhandled comparison: {constraint.comparison}")


def _selection(plan, enumeration, *, run_id=RUN_ID, **kwargs):
    evaluation = kwargs.pop("plan_evaluation", None)
    if evaluation is None:
        evaluation = _phase3c(plan, enumeration, run_id=run_id)
    return select_candidate(
        plan,
        enumeration,
        evaluation,
        evaluation_run_id=run_id,
        evaluated_at=NOW,
        freshness_policy=_freshness(),
        **kwargs,
    )


def _objective_observations(plan, enumeration, *, values=None):
    plan_fingerprint = model_fingerprint(plan)
    request_fp = planning_request_fingerprint(plan.request)
    result = []
    for index, path in enumerate(enumeration.paths):
        candidate_id = physical_candidate_id(plan, path)
        value = (values or [float(index + 1)])[index] if values is not None else 1.0
        packet_counts = (
            {
                "packets_requested": 100,
                "packets_sent": 100,
                "packets_received": round(100 * (1 - value / 100)),
            }
            if plan.optimization.metric == "packet_loss"
            and math.isfinite(value)
            and 0 <= value <= 100
            else {}
        )
        result.append(
            ObjectiveObservation(
                candidate_id=candidate_id,
                request_fingerprint=request_fp,
                plan_fingerprint=plan_fingerprint,
                path_fingerprint=physical_path_fingerprint(path),
                observation_id="objective-observation",
                requirement_id="objective",
                evaluation_run_id=RUN_ID,
                metric=plan.optimization.metric,
                unit=plan.optimization.unit,
                value=value,
                status=ObservationStatus.VALID,
                collected_at=NOW,
                source="selection-test",
                **packet_counts,
            )
        )
    return tuple(result)


def test_candidate_ids_bind_complete_physical_path_and_ignore_enumeration_order():
    plan = _plan()
    enumeration = _enumeration(plan)
    forward_ids = [physical_candidate_id(plan, path) for path in enumeration.paths]
    reverse_ids = [
        physical_candidate_id(plan, path) for path in reversed(enumeration.paths)
    ]

    assert len(set(forward_ids)) == 2
    assert reverse_ids == list(reversed(forward_ids))
    assert [path.nodes for path in enumeration.paths] == [
        path.nodes for path in reversed(enumeration.paths)
    ]


def test_selector_rejects_incomplete_untruncated_enumeration():
    plan = _plan()
    complete = _enumeration(plan)
    partial = PathEnumerationResult(
        source="h1",
        destination="h4",
        candidate_limit=2,
        paths=complete.paths[:1],
        truncated=False,
    )
    evaluation = _phase3c(plan, partial)

    with pytest.raises(SelectionInputError, match="do not match topology enumeration"):
        _selection(plan, partial, plan_evaluation=evaluation)


@pytest.mark.parametrize(
    "tamper",
    ["truncated_flag", "reordered_paths", "altered_paths", "omitted_untruncated_path"],
)
def test_selector_rejects_forged_enumeration(tamper):
    plan = _plan()
    complete = _enumeration(plan)
    if tamper == "truncated_flag":
        supplied = PathEnumerationResult(
            source="h1",
            destination="h4",
            candidate_limit=2,
            paths=complete.paths,
            truncated=True,
        )
    elif tamper == "reordered_paths":
        supplied = PathEnumerationResult(
            source="h1",
            destination="h4",
            candidate_limit=10,
            paths=tuple(reversed(complete.paths)),
            truncated=False,
        )
    elif tamper == "altered_paths":
        altered = complete.paths[1]
        supplied = PathEnumerationResult(
            source="h1",
            destination="h4",
            candidate_limit=10,
            paths=(altered, *complete.paths[1:]),
            truncated=False,
        )
    else:
        supplied = PathEnumerationResult(
            source="h1",
            destination="h4",
            candidate_limit=2,
            paths=complete.paths[:1],
            truncated=False,
        )
    evaluation = _phase3c(plan, complete)

    with pytest.raises(SelectionInputError, match="do not match topology enumeration"):
        _selection(plan, supplied, plan_evaluation=evaluation)


def test_selector_accepts_recomputed_complete_and_k_limited_enumerations():
    plan = _plan(
        (
            MetricConstraint(
                metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
            ),
        )
    )
    complete = _enumeration(plan)
    complete_result = _selection(plan, complete)
    truncated = PathEnumerationResult(
        source="h1",
        destination="h4",
        candidate_limit=1,
        paths=complete.paths[:1],
        truncated=True,
    )
    subset_result = _selection(plan, truncated)

    assert complete_result.status == SelectionStatus.SELECTED
    assert complete_result.selection_scope == SelectionScope.COMPLETE_ENUMERATION
    assert subset_result.status == SelectionStatus.SELECTED
    assert subset_result.selection_scope == SelectionScope.ENUMERATED_SUBSET


def test_parallel_link_order_does_not_change_physical_feasibility():
    constraint = MetricConstraint(
        metric="bandwidth", comparison=Comparison.GTE, value=20, unit="Mbps"
    )
    forward_plan = _plan((constraint,), capacities=(10, 100))
    forward_paths = _enumeration(forward_plan).paths
    forward_results = {
        path.connections[1].link_identity: assess_path_feasibility(
            forward_plan, path
        ).feasibility
        for path in forward_paths
    }

    original_graph = forward_plan.request.topology
    reversed_graph = TopologyGraph(
        switches=original_graph.switches,
        hosts=original_graph.hosts,
        links=list(reversed(original_graph.links)),
    )
    intent = forward_plan.request.intent
    request = PlanningRequest(
        intent=intent,
        topology=reversed_graph,
        capabilities=resolve_capabilities(intent, graph=reversed_graph),
    )
    reverse_plan = Plan(
        request=request,
        capability_readiness=request.capabilities.eligibility,
        planning_readiness=PlanningReadiness.CONDITIONAL,
        hard_constraints=forward_plan.hard_constraints,
        required_observations=forward_plan.required_observations,
    )
    reverse_results = {
        path.connections[1].link_identity: assess_path_feasibility(
            reverse_plan, path
        ).feasibility
        for path in _enumeration(reverse_plan).paths
    }

    assert reverse_results == forward_results


def test_exact_path_validation_rejects_wrong_port_identity_and_duplicate_topology():
    plan = _plan()
    path = _enumeration(plan).paths[0]
    switch_connection = path.connections[1]
    wrong_port_connection = PathConnection(
        kind=ConnectionKind.SWITCH_LINK,
        from_node=switch_connection.from_node,
        to_node=switch_connection.to_node,
        from_port=switch_connection.from_port + 10,
        to_port=switch_connection.to_port,
        link_identity=tuple(
            sorted(
                (
                    (switch_connection.from_node, switch_connection.from_port + 10),
                    (switch_connection.to_node, switch_connection.to_port),
                )
            )
        ),
    )
    wrong_port_path = EnumeratedPath(
        nodes=path.nodes,
        connections=(path.connections[0], wrong_port_connection, path.connections[2]),
    )
    with pytest.raises(SelectionInputError, match="exactly one physical"):
        assess_path_feasibility(plan, wrong_port_path)

    nonexistent_connection = PathConnection(
        kind=ConnectionKind.SWITCH_LINK,
        from_node="s1",
        to_node="s2",
        from_port=90,
        to_port=90,
        link_identity=(("s1", 90), ("s2", 90)),
    )
    nonexistent_link_path = EnumeratedPath(
        nodes=path.nodes,
        connections=(
            path.connections[0],
            nonexistent_connection,
            path.connections[2],
        ),
    )
    with pytest.raises(SelectionInputError, match="exactly one physical"):
        assess_path_feasibility(plan, nonexistent_link_path)

    duplicate_graph = TopologyGraph(
        switches={"s1": 1, "s2": 2},
        hosts=plan.request.topology.hosts,
        links=plan.request.topology.links
        + [plan.request.topology.links[0]],
    )
    duplicate_intent = plan.request.intent
    duplicate_request = PlanningRequest(
        intent=duplicate_intent,
        topology=duplicate_graph,
        capabilities=resolve_capabilities(duplicate_intent, graph=duplicate_graph),
    )
    duplicate_plan = Plan(
        request=duplicate_request,
        capability_readiness=duplicate_request.capabilities.eligibility,
        planning_readiness=PlanningReadiness.CONDITIONAL,
        hard_constraints=plan.hard_constraints,
        required_observations=plan.required_observations,
    )
    with pytest.raises(SelectionInputError, match="Duplicate physical switch link"):
        assess_path_feasibility(duplicate_plan, path)


def test_exact_path_validator_rejects_wrong_host_attachment_port():
    plan = _plan()
    path = _enumeration(plan).paths[0]
    first = PathConnection(
        kind=ConnectionKind.HOST_ATTACHMENT,
        from_node="h1",
        to_node="s1",
        to_port=99,
    )
    malformed = EnumeratedPath(
        nodes=path.nodes,
        connections=(first, *path.connections[1:]),
    )
    with pytest.raises(ValueError, match="host attachments"):
        validate_physical_path(
            plan.request.topology, malformed, "h1", "h4"
        )


@pytest.mark.parametrize(
    ("comparison", "value", "capacity", "expected"),
    [
        (Comparison.GT, 20, (20.0,), CandidateFeasibility.PROVEN_INFEASIBLE),
        (Comparison.GTE, 20, (20.0,), CandidateFeasibility.CANDIDATE),
        (Comparison.BETWEEN, None, (19.0,), CandidateFeasibility.PROVEN_INFEASIBLE),
        (Comparison.EQ, 20, (19.0,), CandidateFeasibility.PROVEN_INFEASIBLE),
        (Comparison.EQ, 20, (18.0,), CandidateFeasibility.PROVEN_INFEASIBLE),
        (Comparison.EQ, 20, (18.0,), CandidateFeasibility.CANDIDATE),
        (Comparison.GTE, 20, (None,), CandidateFeasibility.UNKNOWN),
    ],
)
def test_bandwidth_capacity_establishes_only_static_path_feasibility(
    comparison, value, capacity, expected
):
    kwargs = (
        {"lower_bound": 20, "upper_bound": 30}
        if comparison == Comparison.BETWEEN
        else {"value": value}
    )
    tolerance = 2 if comparison == Comparison.EQ and expected == CandidateFeasibility.CANDIDATE else None
    constraint = MetricConstraint(
        metric="bandwidth",
        comparison=comparison,
        unit="Mbps",
        tolerance=tolerance,
        **kwargs,
    )
    plan = _plan((constraint,), capacities=capacity)
    assessment = assess_path_feasibility(plan, _enumeration(plan).paths[0])

    assert assessment.feasibility == expected


def test_parallel_feasible_and_infeasible_candidates_are_assessed_independently():
    constraint = MetricConstraint(
        metric="bandwidth", comparison=Comparison.GTE, value=20, unit="Mbps"
    )
    plan = _plan((constraint,), capacities=(10, 100))
    enumeration = _enumeration(plan)
    assessments = [
        assess_path_feasibility(plan, path) for path in enumeration.paths
    ]

    assert {item.feasibility for item in assessments} == {
        CandidateFeasibility.PROVEN_INFEASIBLE,
        CandidateFeasibility.CANDIDATE,
    }
    result = _selection(plan, enumeration)
    assert result.status == SelectionStatus.SELECTED
    assert result.selected_candidate.feasibility == CandidateFeasibility.CANDIDATE


def test_unknown_feasibility_blocks_selection_even_when_another_candidate_passes():
    constraint = MetricConstraint(
        metric="bandwidth", comparison=Comparison.GTE, value=20, unit="Mbps"
    )
    plan = _plan((constraint,), capacities=(100, None))
    enumeration = _enumeration(plan)

    result = _selection(plan, enumeration)

    assert result.status == SelectionStatus.INSUFFICIENT_EVIDENCE
    assert result.selected_candidate is None


def test_unknown_feasibility_blocks_no_satisfying_conclusion_for_known_failure():
    constraint = MetricConstraint(
        metric="bandwidth", comparison=Comparison.GTE, value=20, unit="Mbps"
    )
    plan = _plan((constraint,), capacities=(10, None))
    result = _selection(plan, _enumeration(plan))

    assert result.status == SelectionStatus.INSUFFICIENT_EVIDENCE
    assert result.selected_candidate is None


def test_all_proven_infeasible_candidates_return_no_eligible_candidate():
    constraint = MetricConstraint(
        metric="bandwidth", comparison=Comparison.GTE, value=20, unit="Mbps"
    )
    plan = _plan((constraint,), capacities=(10, 15))

    result = _selection(plan, _enumeration(plan))

    assert result.status == SelectionStatus.NO_ELIGIBLE_CANDIDATE


def test_acceptance_intent_above_1000_mbps_is_rejected_by_static_capacity():
    from backend.llm.mock import MockLLM
    from backend.models.intent_normalization import normalize_intent

    canonical = normalize_intent(
        MockLLM().parse_intent(
            "Find a path from h1 to h4 with bandwidth above 1000 Mbps."
        )
    ).canonical
    plan = _plan(canonical.constraints, capacities=(10, 15))

    result = _selection(plan, _enumeration(plan))

    assert result.status == SelectionStatus.NO_ELIGIBLE_CANDIDATE
    assert result.selected_candidate is None


def test_truncated_enumeration_cannot_establish_no_eligible_hard_constraint_path():
    constraint = MetricConstraint(
        metric="bandwidth", comparison=Comparison.GTE, value=20, unit="Mbps"
    )
    plan = _plan((constraint,), capacities=(10, 15))
    path = _enumeration(plan).paths[:1]
    enumeration = PathEnumerationResult(
        source="h1",
        destination="h4",
        candidate_limit=1,
        paths=path,
        truncated=True,
    )

    result = _selection(plan, enumeration)

    assert result.status == SelectionStatus.INSUFFICIENT_EVIDENCE
    assert result.selected_candidate is None


def test_hard_constraints_select_neutral_deterministic_physical_fingerprint():
    constraint = MetricConstraint(
        metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
    )
    plan = _plan((constraint,))
    enumeration = _enumeration(plan)
    result = _selection(plan, enumeration)
    selected_ids = {
        _selection(plan, enumeration).selected_candidate.candidate_id
        for _ in range(2)
    }

    assert result.status == SelectionStatus.SELECTED
    assert result.selection_method == SelectionMethod.NEUTRAL_DETERMINISTIC
    assert len(selected_ids) == 1


def test_phase3c_violation_precedes_unknown_for_candidate_aggregation():
    constraints = (
        MetricConstraint(
            metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
        ),
        MetricConstraint(
            metric="packet_loss", comparison=Comparison.LTE, value=2, unit="%"
        ),
    )
    plan = _plan(constraints)
    enumeration = _enumeration(plan)
    first_candidate = physical_candidate_id(plan, enumeration.paths[0])
    result = _phase3c(
        plan,
        enumeration,
        values={(first_candidate, "r0"): 60, (first_candidate, "r1"): 1},
    )
    candidate = next(item for item in result.candidates if item.candidate_id == first_candidate)

    assert candidate.status == EvaluationStatus.VIOLATED
    assert [item.status for item in candidate.requirements] == [
        EvaluationStatus.VIOLATED,
        EvaluationStatus.SATISFIED,
    ]


def test_hard_constraint_violation_precedes_another_unknown_constraint():
    constraints = (
        MetricConstraint(
            metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
        ),
        MetricConstraint(
            metric="packet_loss", comparison=Comparison.LTE, value=2, unit="%"
        ),
    )
    plan = _plan(constraints)
    enumeration = _enumeration(plan)
    candidate_id = physical_candidate_id(plan, enumeration.paths[0])
    evaluation = _phase3c(
        plan,
        enumeration,
        values={(candidate_id, "r0"): 60},
        observation_statuses={
            (candidate_id, "r1"): ObservationStatus.FAILED,
        },
    )
    candidate = next(item for item in evaluation.candidates if item.candidate_id == candidate_id)

    assert candidate.status == EvaluationStatus.VIOLATED
    assert [item.status for item in candidate.requirements] == [
        EvaluationStatus.VIOLATED,
        EvaluationStatus.UNKNOWN,
    ]


def test_unknown_hard_constraint_evidence_blocks_otherwise_satisfied_selection():
    constraint = MetricConstraint(
        metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
    )
    plan = _plan((constraint,))
    enumeration = _enumeration(plan)
    evaluation = _phase3c(plan, enumeration)
    altered = PlanEvaluation(
        request_fingerprint=evaluation.request_fingerprint,
        plan_fingerprint=evaluation.plan_fingerprint,
        freshness_policy_fingerprint=evaluation.freshness_policy_fingerprint,
        evaluation_run_id=evaluation.evaluation_run_id,
        evaluated_at=evaluation.evaluated_at,
        status=EvaluationStatus.UNKNOWN,
        candidates=tuple(
            ConstraintCandidateEvaluation(
                candidate_id=item.candidate_id,
                request_fingerprint=item.request_fingerprint,
                path_fingerprint=item.path_fingerprint,
                feasibility=item.feasibility,
                status=EvaluationStatus.UNKNOWN,
                requirements=(
                    RequirementEvaluation(
                        target=item.requirements[0].target,
                        metric=item.requirements[0].metric,
                        unit=item.requirements[0].unit,
                        status=EvaluationStatus.UNKNOWN,
                        reason="unresolved",
                    ),
                ),
            )
            for item in evaluation.candidates
        ),
        reasons=("unknown",),
    )
    result = _selection(plan, enumeration, plan_evaluation=altered)
    assert result.status == SelectionStatus.INSUFFICIENT_EVIDENCE


def test_unsupported_hard_constraint_result_blocks_selection():
    constraint = MetricConstraint(
        metric="jitter", comparison=Comparison.LTE, value=5, unit="ms"
    )
    plan = _plan((constraint,))
    result = _selection(plan, _enumeration(plan))

    assert result.status == SelectionStatus.INSUFFICIENT_EVIDENCE


def test_missing_hard_constraint_evaluation_is_rejected_as_incomplete_mapping():
    constraint = MetricConstraint(
        metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
    )
    plan = _plan((constraint,))
    enumeration = _enumeration(plan)
    assessments = [
        assess_path_feasibility(plan, path) for path in enumeration.paths
    ]
    candidates = tuple(
        ConstraintCandidateEvaluation(
            candidate_id=assessment.candidate_id,
            request_fingerprint=assessment.request_fingerprint,
            path_fingerprint=assessment.path_fingerprint,
            feasibility=assessment.feasibility,
            status=EvaluationStatus.NOT_EVALUATED,
        )
        for assessment in assessments
    )
    evaluation = PlanEvaluation(
        request_fingerprint=assessments[0].request_fingerprint,
        plan_fingerprint=assessments[0].plan_fingerprint,
        freshness_policy_fingerprint=model_fingerprint(_freshness()),
        evaluation_run_id=RUN_ID,
        evaluated_at=NOW,
        status=EvaluationStatus.NOT_EVALUATED,
        candidates=candidates,
    )

    with pytest.raises(SelectionInputError, match="exactly cover"):
        _selection(plan, enumeration, plan_evaluation=evaluation)


def test_truncated_hard_constraint_selection_reports_subset_scope():
    constraint = MetricConstraint(
        metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
    )
    plan = _plan((constraint,))
    paths = _enumeration(plan).paths
    enumeration = PathEnumerationResult(
        source="h1",
        destination="h4",
        candidate_limit=1,
        paths=paths[:1],
        truncated=True,
    )

    result = _selection(plan, enumeration)

    assert result.status == SelectionStatus.SELECTED
    assert result.search_truncated is True
    assert result.selection_scope == SelectionScope.ENUMERATED_SUBSET
    assert result.selection_method == SelectionMethod.NEUTRAL_DETERMINISTIC


def test_truncated_hard_constraint_without_satisfying_subset_is_insufficient():
    constraint = MetricConstraint(
        metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
    )
    plan = _plan((constraint,))
    paths = _enumeration(plan).paths[:1]
    enumeration = PathEnumerationResult(
        source="h1",
        destination="h4",
        candidate_limit=1,
        paths=paths,
        truncated=True,
    )
    candidate_id = physical_candidate_id(plan, paths[0])
    evaluation = _phase3c(
        plan,
        enumeration,
        values={(candidate_id, "r0"): 60},
    )

    result = _selection(plan, enumeration, plan_evaluation=evaluation)

    assert result.status == SelectionStatus.INSUFFICIENT_EVIDENCE
    assert result.selected_candidate is None


def test_truncated_objective_returns_insufficient_evidence_and_no_selection():
    objective = OptimizationObjective(
        metric="latency",
        direction=OptimizationDirection.MINIMIZE,
        unit="ms",
    )
    plan = _plan(optimization=objective)
    enumeration = _enumeration(plan)
    truncated = PathEnumerationResult(
        source="h1",
        destination="h4",
        candidate_limit=1,
        paths=enumeration.paths[:1],
        truncated=True,
    )

    result = _selection(plan, truncated)

    assert result.status == SelectionStatus.INSUFFICIENT_EVIDENCE
    assert result.search_truncated
    assert result.selected_candidate is None


@pytest.mark.parametrize("validation_method", ["constructor", "model_validate_json"])
def test_result_model_rejects_non_insufficient_truncated_objective_state(
    validation_method,
):
    objective = OptimizationObjective(
        metric="latency",
        direction=OptimizationDirection.MINIMIZE,
        unit="ms",
    )
    plan = _plan(optimization=objective)
    complete = _enumeration(plan)
    truncated = PathEnumerationResult(
        source="h1",
        destination="h4",
        candidate_limit=1,
        paths=complete.paths[:1],
        truncated=True,
    )
    result = _selection(plan, truncated)
    assert result.status == SelectionStatus.INSUFFICIENT_EVIDENCE

    payload = result.model_dump(mode="json")
    payload["status"] = SelectionStatus.UNSUPPORTED_OBJECTIVE.value
    with pytest.raises(ValidationError, match="requires INSUFFICIENT_EVIDENCE"):
        if validation_method == "constructor":
            CandidateSelectionResult(**payload)
        else:
            CandidateSelectionResult.model_validate_json(json.dumps(payload))


def test_objective_only_selection_uses_generalized_capability():
    objective = OptimizationObjective(
        metric="latency",
        direction=OptimizationDirection.MINIMIZE,
        unit="ms",
    )
    plan = _plan(optimization=objective)

    enumeration = _enumeration(plan)
    observations = _objective_observations(plan, enumeration, values=[30, 10])
    result = _selection(
        plan,
        enumeration,
        objective_observations=observations,
    )

    assert result.status == SelectionStatus.SELECTED
    assert result.selection_method == SelectionMethod.OBJECTIVE_RANKING
    assert result.selected_candidate.objective_value == 10
    assert (
        plan.request.capabilities.optimization.generalized_objective_ranking.status
        == CapabilityStatus.SUPPORTED
    )


def test_candidate_selector_ranks_distinct_objective_observations():
    objective = OptimizationObjective(
        metric="latency",
        direction=OptimizationDirection.MINIMIZE,
        unit="ms",
    )
    plan = _plan(optimization=objective)
    enumeration = _enumeration(plan)
    observations = _objective_observations(plan, enumeration, values=[30, 10])

    result = _selection(
        plan,
        enumeration,
        objective_observations=observations,
    )

    assert result.status == SelectionStatus.SELECTED
    assert result.selection_method == SelectionMethod.OBJECTIVE_RANKING
    assert result.selected_candidate.objective_value == 10


@pytest.mark.parametrize(
    ("metric", "unit", "direction", "values", "expected_value"),
    [
        ("latency", "ms", OptimizationDirection.MINIMIZE, [30, 10], 10),
        ("latency", "ms", OptimizationDirection.MAXIMIZE, [30, 10], 30),
        ("bandwidth", "Mbps", OptimizationDirection.MINIMIZE, [30, 10], 10),
        ("bandwidth", "Mbps", OptimizationDirection.MAXIMIZE, [30, 10], 30),
    ],
)
def test_generalized_objective_ranks_supported_metrics_and_directions(
    metric, unit, direction, values, expected_value
):
    objective = OptimizationObjective(
        metric=metric,
        direction=direction,
        unit=unit,
    )
    plan = _plan(optimization=objective)
    enumeration = _enumeration(plan)
    result = _selection(
        plan,
        enumeration,
        objective_observations=_objective_observations(
            plan,
            enumeration,
            values=values,
        ),
    )

    assert result.status == SelectionStatus.SELECTED
    assert result.selection_method == SelectionMethod.OBJECTIVE_RANKING
    assert result.selected_candidate.objective_value == expected_value
    assert (
        plan.request.capabilities.optimization.generalized_objective_ranking.status
        == CapabilityStatus.SUPPORTED
    )


def test_objective_ties_use_physical_path_fingerprint_deterministically():
    objective = OptimizationObjective(
        metric="latency",
        direction=OptimizationDirection.MINIMIZE,
        unit="ms",
    )
    plan = _plan(optimization=objective)
    enumeration = _enumeration(plan)
    result = _selection(
        plan,
        enumeration,
        objective_observations=_objective_observations(
            plan,
            enumeration,
            values=[10, 10],
        ),
    )

    expected = min(
        result.candidates,
        key=lambda candidate: candidate.path_fingerprint,
    )
    assert result.selected_candidate == expected


@pytest.mark.parametrize(
    ("direction", "values", "expected_value"),
    [
        (OptimizationDirection.MINIMIZE, [0.0, 25.0], 0.0),
        (OptimizationDirection.MAXIMIZE, [0.0, 25.0], 25.0),
    ],
)
def test_packet_loss_objective_ranks_candidates(direction, values, expected_value):
    objective = OptimizationObjective(
        metric="packet_loss",
        direction=direction,
        unit="%",
    )
    plan = _plan(optimization=objective)
    enumeration = _enumeration(plan)
    observations = _objective_observations(plan, enumeration, values=values)

    result = _selection(
        plan,
        enumeration,
        objective_observations=observations,
    )

    assert result.status == SelectionStatus.SELECTED
    assert result.selected_candidate.objective_value == expected_value
    assert (
        plan.request.capabilities.optimization.generalized_objective_ranking.status
        == CapabilityStatus.SUPPORTED
    )
    assert plan.request.capabilities.optimization.executable.status != CapabilityStatus.SUPPORTED


def test_packet_loss_objective_ties_use_physical_path_fingerprint():
    objective = OptimizationObjective(
        metric="packet_loss",
        direction=OptimizationDirection.MINIMIZE,
        unit="%",
    )
    plan = _plan(optimization=objective)
    enumeration = _enumeration(plan)
    result = _selection(
        plan,
        enumeration,
        objective_observations=_objective_observations(
            plan,
            enumeration,
            values=[12.0, 12.0],
        ),
    )

    assert result.selected_candidate == min(
        result.candidates,
        key=lambda candidate: candidate.path_fingerprint,
    )


@pytest.mark.parametrize(
    "constraints",
    [
        (
            MetricConstraint(
                metric="latency",
                comparison=Comparison.LTE,
                value=50,
                unit="ms",
            ),
        ),
        (
            MetricConstraint(
                metric="bandwidth",
                comparison=Comparison.GTE,
                value=20,
                unit="Mbps",
            ),
        ),
        (
            MetricConstraint(
                metric="latency",
                comparison=Comparison.LTE,
                value=50,
                unit="ms",
            ),
            MetricConstraint(
                metric="bandwidth",
                comparison=Comparison.GTE,
                value=20,
                unit="Mbps",
            ),
        ),
    ],
)
def test_packet_loss_objective_combines_with_hard_constraints(constraints):
    objective = OptimizationObjective(
        metric="packet_loss",
        direction=OptimizationDirection.MINIMIZE,
        unit="%",
    )
    plan = _plan(constraints, optimization=objective)
    enumeration = _enumeration(plan)
    result = _selection(
        plan,
        enumeration,
        objective_observations=_objective_observations(
            plan,
            enumeration,
            values=[20.0, 10.0],
        ),
    )

    assert result.status == SelectionStatus.SELECTED
    assert result.selected_candidate.hard_constraint_status == EvaluationStatus.SATISFIED
    assert result.selected_candidate.objective_value == 10.0


def test_packet_loss_objective_rejects_candidate_violating_hard_constraint():
    constraint = MetricConstraint(
        metric="latency",
        comparison=Comparison.LTE,
        value=30,
        unit="ms",
    )
    objective = OptimizationObjective(
        metric="packet_loss",
        direction=OptimizationDirection.MAXIMIZE,
        unit="%",
    )
    plan = _plan((constraint,), optimization=objective)
    enumeration = _enumeration(plan)
    violating_id = physical_candidate_id(plan, enumeration.paths[1])
    evaluation = _phase3c(
        plan,
        enumeration,
        values={(violating_id, "r0"): 40},
    )
    observations = tuple(
        observation
        for observation in _objective_observations(
            plan,
            enumeration,
            values=[0.0, 100.0],
        )
        if observation.candidate_id != violating_id
    )

    result = _selection(
        plan,
        enumeration,
        plan_evaluation=evaluation,
        objective_observations=observations,
    )

    assert result.status == SelectionStatus.SELECTED
    assert result.selected_candidate.candidate_id != violating_id
    assert result.selected_candidate.hard_constraint_status == EvaluationStatus.SATISFIED


def test_packet_loss_objective_rejects_truncated_enumeration():
    objective = OptimizationObjective(
        metric="packet_loss",
        direction=OptimizationDirection.MINIMIZE,
        unit="%",
    )
    plan = _plan(optimization=objective)
    complete = _enumeration(plan)
    truncated = PathEnumerationResult(
        source="h1",
        destination="h4",
        candidate_limit=1,
        paths=complete.paths[:1],
        truncated=True,
    )

    result = _selection(
        plan,
        truncated,
        objective_observations=_objective_observations(
            plan,
            truncated,
            values=[0.0],
        ),
    )

    assert result.status == SelectionStatus.INSUFFICIENT_EVIDENCE
    assert result.selected_candidate is None


def test_packet_loss_objective_with_no_eligible_candidates():
    constraint = MetricConstraint(
        metric="bandwidth",
        comparison=Comparison.GTE,
        value=20,
        unit="Mbps",
    )
    objective = OptimizationObjective(
        metric="packet_loss",
        direction=OptimizationDirection.MINIMIZE,
        unit="%",
    )
    plan = _plan(
        (constraint,),
        capacities=(10, 15),
        optimization=objective,
    )

    result = _selection(plan, _enumeration(plan))

    assert result.status == SelectionStatus.NO_ELIGIBLE_CANDIDATE
    assert result.selected_candidate is None


def test_packet_loss_ping_factory_rejects_empty_or_invalid_measurements():
    objective = OptimizationObjective(
        metric="packet_loss",
        direction=OptimizationDirection.MINIMIZE,
        unit="%",
    )
    plan = _plan(optimization=objective)
    path = _enumeration(plan).paths[0]
    identity = {
        "candidate_id": physical_candidate_id(plan, path),
        "request_fingerprint": planning_request_fingerprint(plan.request),
        "plan_fingerprint": model_fingerprint(plan),
        "path_fingerprint": physical_path_fingerprint(path),
        "observation_id": "objective-observation",
        "requirement_id": "objective",
        "evaluation_run_id": RUN_ID,
        "collected_at": NOW,
        "source": "ping",
    }

    valid_ping = LatencyResult(
        packets_sent=5,
        packets_received=4,
        packet_loss_pct=20.0,
        packets_requested=5,
        raw_output="5 packets transmitted, 4 received, 20% packet loss",
    )
    observation = ObjectiveObservation.from_ping_result(valid_ping, **identity)
    assert observation.status == ObservationStatus.VALID
    assert observation.value == 20.0
    assert ObjectiveObservation.model_validate_json(
        observation.model_dump_json()
    ) == observation

    completed_total_loss = ObjectiveObservation.from_ping_result(
        LatencyResult(
            packets_sent=5,
            packets_received=0,
            packet_loss_pct=100.0,
            packets_requested=5,
            raw_output="5 packets transmitted, 0 received, 100% packet loss",
        ),
        **identity,
    )
    assert completed_total_loss.status == ObservationStatus.VALID
    assert completed_total_loss.value == 100.0

    invalid_results = (
        LatencyResult(
            packets_sent=0,
            packets_received=0,
            packet_loss_pct=100.0,
            packets_requested=5,
            raw_output="command not found",
        ),
        LatencyResult(
            packets_sent=5,
            packets_received=6,
            packet_loss_pct=0.0,
            packets_requested=5,
            raw_output="invalid counts",
        ),
        LatencyResult(
            packets_sent=5,
            packets_received=4,
            packet_loss_pct=101.0,
            packets_requested=5,
            raw_output="invalid percentage",
        ),
    )
    for measurement in invalid_results:
        rejected = ObjectiveObservation.from_ping_result(
            measurement,
            **identity,
        )
        assert rejected.status == ObservationStatus.FAILED
        assert rejected.value is None


@pytest.mark.parametrize(
    ("value", "packets_sent", "packets_received"),
    [
        (0.0, 0, 0),
        (0.0, 5, 6),
        (-1.0, 100, 101),
        (101.0, 100, 0),
        (float("nan"), 100, 100),
        (float("inf"), 100, 100),
    ],
)
def test_packet_loss_valid_observation_rejects_invalid_counts_or_value(
    value, packets_sent, packets_received
):
    objective = OptimizationObjective(
        metric="packet_loss",
        direction=OptimizationDirection.MINIMIZE,
        unit="%",
    )
    plan = _plan(optimization=objective)
    path = _enumeration(plan).paths[0]
    base = _objective_observations(
        plan,
        _enumeration(plan),
        values=[0.0, 0.0],
    )[0].model_dump()
    base.update(
        value=value,
        packets_sent=packets_sent,
        packets_received=packets_received,
    )

    with pytest.raises(ValidationError):
        ObjectiveObservation(**base)


@pytest.mark.parametrize(
    ("completion_field", "completion_value"),
    [
        ("packets_requested", None),
        ("packets_requested", 5),
    ],
)
def test_packet_loss_valid_observation_requires_matching_completion_evidence(
    completion_field,
    completion_value,
):
    plan = _plan(
        optimization=OptimizationObjective(
            metric="packet_loss",
            direction=OptimizationDirection.MINIMIZE,
            unit="%",
        )
    )
    observation = _objective_observations(
        plan,
        _enumeration(plan),
        values=[0.0, 0.0],
    )[0]
    payload = observation.model_dump()
    payload[completion_field] = completion_value

    with pytest.raises(ValidationError):
        type(observation)(**payload)

    json_payload = observation.model_dump(mode="json")
    json_payload[completion_field] = completion_value
    with pytest.raises(ValidationError):
        type(observation).model_validate_json(json.dumps(json_payload))


def test_packet_loss_valid_observation_requires_requested_count_field():
    plan = _plan(
        optimization=OptimizationObjective(
            metric="packet_loss",
            direction=OptimizationDirection.MINIMIZE,
            unit="%",
        )
    )
    observation = _objective_observations(
        plan,
        _enumeration(plan),
        values=[0.0, 0.0],
    )[0]
    payload = observation.model_dump()
    del payload["packets_requested"]
    json_payload = observation.model_dump(mode="json")
    del json_payload["packets_requested"]

    with pytest.raises(ValidationError):
        type(observation).model_validate(payload)
    with pytest.raises(ValidationError):
        type(observation).model_validate_json(json.dumps(json_payload))


def test_failed_packet_loss_observation_without_completion_evidence_is_representable():
    plan = _plan(
        optimization=OptimizationObjective(
            metric="packet_loss",
            direction=OptimizationDirection.MINIMIZE,
            unit="%",
        )
    )
    base = _objective_observations(
        plan,
        _enumeration(plan),
        values=[0.0, 0.0],
    )[0].model_dump()
    base.update(
        status=ObservationStatus.FAILED,
        value=None,
        packets_requested=None,
        packets_sent=0,
        packets_received=0,
    )

    failed = ObjectiveObservation(**base)
    assert failed.status == ObservationStatus.FAILED
    assert not failed.has_valid_packet_loss_evidence
    assert ObjectiveObservation.model_validate_json(
        failed.model_dump_json()
    ) == failed


def test_selector_rejects_packet_loss_observation_missing_completion_evidence():
    plan = _plan(
        optimization=OptimizationObjective(
            metric="packet_loss",
            direction=OptimizationDirection.MINIMIZE,
            unit="%",
        )
    )
    enumeration = _enumeration(plan)
    observations = list(
        _objective_observations(plan, enumeration, values=[0.0, 0.0])
    )
    object.__setattr__(observations[0], "packets_requested", None)

    with pytest.raises(SelectionInputError, match="invalid measurement counts or value"):
        _selection(
            plan,
            enumeration,
            objective_observations=tuple(observations),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("packets_sent", True),
        ("packets_received", False),
        ("value", True),
    ],
)
def test_packet_loss_objective_observation_rejects_booleans(field, value):
    plan = _plan(
        optimization=OptimizationObjective(
            metric="packet_loss",
            direction=OptimizationDirection.MINIMIZE,
            unit="%",
        )
    )
    observation = _objective_observations(
        plan,
        _enumeration(plan),
        values=[0.0, 0.0],
    )[0]
    base = observation.model_dump()
    base[field] = value

    with pytest.raises(ValidationError):
        ObjectiveObservation(**base)
    json_payload = observation.model_dump(mode="json")
    json_payload[field] = value
    with pytest.raises(ValidationError):
        ObjectiveObservation.model_validate_json(json.dumps(json_payload))


def test_packet_loss_objective_requires_complete_fresh_run_bound_observations():
    objective = OptimizationObjective(
        metric="packet_loss",
        direction=OptimizationDirection.MINIMIZE,
        unit="%",
    )
    plan = _plan(optimization=objective)
    enumeration = _enumeration(plan)
    valid = _objective_observations(plan, enumeration, values=[10.0, 20.0])

    missing = _selection(plan, enumeration, objective_observations=valid[:1])
    assert missing.status == SelectionStatus.INSUFFICIENT_EVIDENCE

    with pytest.raises(SelectionInputError, match="Duplicate objective"):
        _selection(
            plan,
            enumeration,
            objective_observations=valid + valid[:1],
        )

    stale = tuple(
        ObjectiveObservation(
            **{
                **item.model_dump(),
                "collected_at": NOW - timedelta(minutes=10),
            }
        )
        for item in valid
    )
    assert _selection(
        plan,
        enumeration,
        objective_observations=stale,
    ).status == SelectionStatus.INSUFFICIENT_EVIDENCE

    future = tuple(
        ObjectiveObservation(
            **{
                **item.model_dump(),
                "collected_at": NOW + timedelta(seconds=1),
            }
        )
        for item in valid
    )
    assert _selection(
        plan,
        enumeration,
        objective_observations=future,
    ).status == SelectionStatus.INSUFFICIENT_EVIDENCE

    for field, value in (
        ("candidate_id", "unknown-candidate"),
        ("path_fingerprint", "0" * 64),
        ("request_fingerprint", "0" * 64),
        ("plan_fingerprint", "0" * 64),
        ("evaluation_run_id", "other-run"),
        ("unit", "fraction"),
    ):
        altered = tuple(
            ObjectiveObservation(
                **{
                    **item.model_dump(),
                    field: value,
                }
            )
            for item in valid
        )
        with pytest.raises(SelectionInputError):
            _selection(
                plan,
                enumeration,
                objective_observations=altered,
            )


def test_failed_ping_measurements_never_become_valid_objective_observations():
    objective = OptimizationObjective(
        metric="packet_loss",
        direction=OptimizationDirection.MINIMIZE,
        unit="%",
    )
    plan = _plan(optimization=objective)
    enumeration = _enumeration(plan)
    identities = []
    for path in enumeration.paths:
        identities.append(
            {
                "candidate_id": physical_candidate_id(plan, path),
                "request_fingerprint": planning_request_fingerprint(plan.request),
                "plan_fingerprint": model_fingerprint(plan),
                "path_fingerprint": physical_path_fingerprint(path),
                "observation_id": "objective-observation",
                "requirement_id": "objective",
                "evaluation_run_id": RUN_ID,
                "collected_at": NOW,
                "source": "ping",
            }
        )
    observations = tuple(
        ObjectiveObservation.from_ping_result(
            LatencyResult(
                packets_sent=0,
                packets_received=0,
                packet_loss_pct=100,
                packets_requested=5,
                raw_output="command not found",
            ),
            **identity,
        )
        for identity in identities
    )

    assert all(item.status == ObservationStatus.FAILED for item in observations)
    assert all(item.value is None for item in observations)
    result = _selection(
        plan,
        enumeration,
        objective_observations=observations,
    )
    assert result.status == SelectionStatus.INSUFFICIENT_EVIDENCE


def test_objective_ranking_requires_all_hard_constraints_to_pass():
    constraints = (
        MetricConstraint(
            metric="latency",
            comparison=Comparison.LTE,
            value=50,
            unit="ms",
        ),
        MetricConstraint(
            metric="latency",
            comparison=Comparison.GTE,
            value=10,
            unit="ms",
        ),
    )
    objective = OptimizationObjective(
        metric="bandwidth",
        direction=OptimizationDirection.MAXIMIZE,
        unit="Mbps",
    )
    plan = _plan(constraints, optimization=objective)
    enumeration = _enumeration(plan)
    violating_candidate_id = physical_candidate_id(plan, enumeration.paths[1])
    evaluation = _phase3c(
        plan,
        enumeration,
        values={
            (violating_candidate_id, "r0"): 60,
            (violating_candidate_id, "r1"): 20,
        },
    )
    objective_observations = tuple(
        observation
        for observation in _objective_observations(
            plan,
            enumeration,
            values=[10, 100],
        )
        if observation.candidate_id != violating_candidate_id
    )

    result = _selection(
        plan,
        enumeration,
        plan_evaluation=evaluation,
        objective_observations=objective_observations,
    )

    assert result.status == SelectionStatus.SELECTED
    assert result.selected_candidate.candidate_id != violating_candidate_id
    assert result.selected_candidate.hard_constraint_status == EvaluationStatus.SATISFIED


def test_objective_result_reports_no_eligible_paths_when_all_are_infeasible():
    constraint = MetricConstraint(
        metric="bandwidth",
        comparison=Comparison.GTE,
        value=20,
        unit="Mbps",
    )
    objective = OptimizationObjective(
        metric="latency",
        direction=OptimizationDirection.MINIMIZE,
        unit="ms",
    )
    plan = _plan(
        (constraint,),
        capacities=(10, 15),
        optimization=objective,
    )

    result = _selection(plan, _enumeration(plan))

    assert result.status == SelectionStatus.NO_ELIGIBLE_CANDIDATE
    assert result.selected_candidate is None


def test_constraint_failure_precedes_objective_ranking():
    constraint = MetricConstraint(
        metric="latency", comparison=Comparison.LTE, value=20, unit="ms"
    )
    objective = OptimizationObjective(
        metric="latency",
        direction=OptimizationDirection.MINIMIZE,
        unit="ms",
    )
    plan = _plan((constraint,), optimization=objective)
    enumeration = _enumeration(plan)
    values = {
        (physical_candidate_id(plan, path), "r0"): 30
        for path in enumeration.paths
    }
    evaluation = _phase3c(plan, enumeration, values=values)

    result = _selection(plan, enumeration, plan_evaluation=evaluation)

    assert result.status == SelectionStatus.NO_SATISFYING_CANDIDATE


def test_objective_duplicate_mismatched_and_stale_evidence_are_rejected_or_unknown():
    objective = OptimizationObjective(
        metric="latency",
        direction=OptimizationDirection.MINIMIZE,
        unit="ms",
    )
    plan = _plan(optimization=objective)
    enumeration = _enumeration(plan)
    observations = _objective_observations(plan, enumeration)
    with pytest.raises(SelectionInputError, match="Duplicate objective"):
        _selection(
            plan,
            enumeration,
            objective_observations=observations + observations[:1],
        )
    wrong_run = observations[0].model_copy(deep=True)
    with pytest.raises(TypeError, match="model_copy"):
        wrong_run.model_copy(update={"evaluation_run_id": "wrong"})
    stale = tuple(
        ObjectiveObservation(
            **{
                **item.model_dump(),
                "collected_at": NOW - timedelta(minutes=10),
            }
        )
        for item in observations
    )
    result = _selection(plan, enumeration, objective_observations=stale)
    assert result.status == SelectionStatus.INSUFFICIENT_EVIDENCE
    missing = _selection(plan, enumeration)
    assert missing.status == SelectionStatus.INSUFFICIENT_EVIDENCE


def test_objective_identity_mismatches_are_rejected():
    objective = OptimizationObjective(
        metric="latency",
        direction=OptimizationDirection.MINIMIZE,
        unit="ms",
    )
    plan = _plan(optimization=objective)
    enumeration = _enumeration(plan)
    observation = _objective_observations(plan, enumeration)[0]
    original = observation.model_dump()
    mismatches = (
        ("evaluation_run_id", "other-run"),
        ("request_fingerprint", "0" * 64),
        ("plan_fingerprint", "0" * 64),
        ("candidate_id", "unknown-candidate"),
        ("path_fingerprint", "0" * 64),
        ("requirement_id", "wrong-requirement"),
        ("unit", "us"),
    )
    for field, value in mismatches:
        altered = dict(original)
        altered[field] = value
        bad_observation = ObjectiveObservation(**altered)
        with pytest.raises(SelectionInputError):
            _selection(
                plan,
                enumeration,
                objective_observations=(bad_observation,),
            )


def test_supported_objective_requires_complete_objective_evidence():
    objective = OptimizationObjective(
        metric="latency",
        direction=OptimizationDirection.MINIMIZE,
        unit="ms",
    )
    plan = _plan(optimization=objective)
    enumeration = _enumeration(plan)
    observations = _objective_observations(plan, enumeration)

    result = _selection(
        plan,
        enumeration,
        objective_observations=observations[:1],
    )

    assert result.status == SelectionStatus.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize(
    ("status", "value", "collected_at"),
    [
        (ObservationStatus.FAILED, None, NOW),
        (ObservationStatus.INVALID, None, NOW),
        (ObservationStatus.VALID, float("nan"), NOW),
        (ObservationStatus.VALID, float("inf"), NOW),
        (ObservationStatus.VALID, -1.0, NOW),
        (ObservationStatus.VALID, 10.0, NOW + timedelta(minutes=1)),
    ],
)
def test_invalid_future_and_non_finite_objective_evidence_is_insufficient(
    status, value, collected_at
):
    objective = OptimizationObjective(
        metric="latency",
        direction=OptimizationDirection.MINIMIZE,
        unit="ms",
    )
    plan = _plan(optimization=objective)
    enumeration = _enumeration(plan)
    valid = _objective_observations(plan, enumeration)
    bad = tuple(
        ObjectiveObservation(
            **{
                **item.model_dump(),
                "status": status,
                "value": value,
                "collected_at": collected_at,
            }
        )
        for item in valid
    )

    result = _selection(plan, enumeration, objective_observations=bad)

    assert result.status == SelectionStatus.INSUFFICIENT_EVIDENCE


def test_phase3c_request_and_plan_fingerprint_mismatches_are_rejected():
    plan = _plan(
        (
            MetricConstraint(
                metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
            ),
        )
    )
    enumeration = _enumeration(plan)
    for field, value in (
        ("request_fingerprint", "0" * 64),
        ("plan_fingerprint", "0" * 64),
    ):
        evaluation = PlanEvaluation(
            request_fingerprint=(
                value
                if field == "request_fingerprint"
                else planning_request_fingerprint(plan.request)
            ),
            plan_fingerprint=(
                value
                if field == "plan_fingerprint"
                else model_fingerprint(plan)
            ),
            evaluation_run_id=RUN_ID,
            evaluated_at=NOW,
            status=EvaluationStatus.NOT_EVALUATED,
            candidates=(),
        )
        with pytest.raises(SelectionInputError, match="identity, run"):
            select_candidate(
                plan,
                enumeration,
                evaluation,
                evaluation_run_id=RUN_ID,
                evaluated_at=NOW,
            )


def test_selected_result_round_trips_and_remains_immutable():
    plan = _plan(
        (
            MetricConstraint(
                metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
            ),
        )
    )
    result = _selection(plan, _enumeration(plan))
    restored = CandidateSelectionResult.model_validate_json(result.model_dump_json())

    assert restored == result
    with pytest.raises(ValidationError):
        result.status = SelectionStatus.NO_ELIGIBLE_CANDIDATE


def test_evaluation_run_mismatch_is_rejected_by_phase3d():
    plan = _plan(
        (
            MetricConstraint(
                metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
            ),
        )
    )
    enumeration = _enumeration(plan)
    evaluation = _phase3c(plan, enumeration, run_id="different-run")

    with pytest.raises(SelectionInputError, match="identity, run"):
        select_candidate(
            plan,
            enumeration,
            evaluation,
            evaluation_run_id=RUN_ID,
            evaluated_at=NOW,
        )


def test_freshness_policy_must_match_phase3c_evaluation_policy():
    constraint = MetricConstraint(
        metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
    )
    plan = _plan((constraint,))
    enumeration = _enumeration(plan)
    two_day_policy = FreshnessPolicy(
        limits=(
            MetricFreshnessLimit(metric="latency", max_age=timedelta(days=2)),
        )
    )
    evaluation = _phase3c(
        plan,
        enumeration,
        freshness_policy=two_day_policy,
        collected_at=NOW - timedelta(days=1),
    )
    matching = select_candidate(
        plan,
        enumeration,
        evaluation,
        evaluation_run_id=RUN_ID,
        evaluated_at=NOW,
        freshness_policy=two_day_policy,
    )
    assert matching.status == SelectionStatus.SELECTED

    for changed_policy in (
        FreshnessPolicy(
            limits=(
                MetricFreshnessLimit(
                    metric="latency", max_age=timedelta(minutes=5)
                ),
            )
        ),
        FreshnessPolicy(
            limits=(
                MetricFreshnessLimit(metric="latency", max_age=timedelta(days=5)),
            )
        ),
    ):
        with pytest.raises(SelectionInputError, match="freshness policy"):
            select_candidate(
                plan,
                enumeration,
                evaluation,
                evaluation_run_id=RUN_ID,
                evaluated_at=NOW,
                freshness_policy=changed_policy,
            )


def test_phase3d_rejects_missing_freshness_identity_and_changed_evaluation_time():
    constraint = MetricConstraint(
        metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
    )
    plan = _plan((constraint,))
    enumeration = _enumeration(plan)
    evaluation = _phase3c(plan, enumeration)
    legacy_evaluation = PlanEvaluation.model_validate(
        evaluation.model_dump(exclude={"freshness_policy_fingerprint"})
    )
    with pytest.raises(SelectionInputError, match="freshness policy"):
        select_candidate(
            plan,
            enumeration,
            legacy_evaluation,
            evaluation_run_id=RUN_ID,
            evaluated_at=NOW,
            freshness_policy=_freshness(),
        )
    with pytest.raises(SelectionInputError, match="timestamp"):
        select_candidate(
            plan,
            enumeration,
            evaluation,
            evaluation_run_id=RUN_ID,
            evaluated_at=NOW + timedelta(seconds=1),
            freshness_policy=_freshness(),
        )


def test_no_selection_criteria_returns_no_selection_and_preserves_truncation():
    plan = _plan()
    enumeration = _enumeration(plan)
    result = _selection(plan, enumeration)
    truncated = PathEnumerationResult(
        source="h1",
        destination="h4",
        candidate_limit=1,
        paths=enumeration.paths[:1],
        truncated=True,
    )
    truncated_result = _selection(plan, truncated)

    assert result.status == SelectionStatus.NO_SELECTION_CRITERIA
    assert result.selected_candidate is None
    assert truncated_result.status == SelectionStatus.NO_SELECTION_CRITERIA
    assert truncated_result.search_truncated


def test_selection_result_rejects_selected_candidate_not_in_result_set():
    plan = _plan(
        (
            MetricConstraint(
                metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
            ),
        )
    )
    enumeration = _enumeration(plan)
    selected = _selection(plan, enumeration).selected_candidate
    assert selected is not None
    valid_result = _selection(plan, enumeration)
    payload = valid_result.model_dump(mode="python")
    payload["candidates"] = ()
    with pytest.raises(ValidationError, match="validated enumeration"):
        CandidateSelectionResult.model_validate(payload)


def test_result_model_derives_hard_constraint_criteria_from_originating_plan():
    plan = _plan(
        (
            MetricConstraint(
                metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
            ),
        )
    )
    result = _selection(plan, _enumeration(plan))
    payload = result.model_dump(mode="python")
    payload["candidates"][0]["hard_constraint_status"] = EvaluationStatus.NOT_EVALUATED

    with pytest.raises(ValidationError):
        CandidateSelectionResult.model_validate(payload)

    payload = result.model_dump(mode="python")
    payload["hard_constraints_present"] = False
    with pytest.raises(ValidationError):
        CandidateSelectionResult.model_validate(payload)


def test_objective_result_requires_matching_observation_not_just_numeric_value():
    objective = OptimizationObjective(
        metric="latency",
        direction=OptimizationDirection.MINIMIZE,
        unit="ms",
    )
    plan = _plan(optimization=objective)
    enumeration = _enumeration(plan)
    result = _selection(
        plan,
        enumeration,
        objective_observations=_objective_observations(plan, enumeration),
    )
    payload = result.model_dump(mode="python")
    payload["objective_observations"] = ()

    with pytest.raises(ValidationError, match="objective"):
        CandidateSelectionResult.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("request_fingerprint", "0" * 64),
        ("evaluation_run_id", "wrong-run"),
    ],
)
def test_selected_result_rejects_mismatched_provenance(field, value):
    plan = _plan(
        (
            MetricConstraint(
                metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
            ),
        )
    )
    result = _selection(plan, _enumeration(plan))
    payload = result.model_dump(mode="python")
    payload[field] = value

    with pytest.raises(ValidationError):
        CandidateSelectionResult.model_validate(payload)


def test_selected_result_rejects_candidate_identity_outside_validated_paths():
    plan = _plan(
        (
            MetricConstraint(
                metric="latency", comparison=Comparison.LTE, value=50, unit="ms"
            ),
        )
    )
    result = _selection(plan, _enumeration(plan))
    payload = result.model_dump(mode="python")
    payload["selected_candidate"]["candidate_id"] = "forged-candidate"

    with pytest.raises(ValidationError):
        CandidateSelectionResult.model_validate(payload)


def test_candidate_selection_has_no_measurement_or_network_execution_imports():
    from pathlib import Path
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import backend.planner.candidate_selection; "
            "blocked = {'backend.measurement', 'backend.deployment', "
            "'backend.pipeline', 'backend.cli', 'backend.compiler', "
            "'mininet', 'ryu', 'scapy'}; "
            "assert not blocked.intersection(sys.modules)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
