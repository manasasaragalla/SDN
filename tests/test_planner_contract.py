import pytest
from pydantic import ValidationError

from backend.capabilities import (
    DeploymentStatus,
    EligibilityStatus,
    ExecutionStatus,
    SatisfactionStatus,
    resolve_capabilities,
)
from backend.models.canonical_intent import (
    CanonicalIntent,
    Comparison,
    MetricConstraint,
    OptimizationDirection,
    OptimizationObjective,
    TrafficScope,
)
from backend.models.fingerprints import model_fingerprint
from backend.models.intent import Objective, StructuredIntent, Target
from backend.models.intent_normalization import normalize_intent
from backend.models.network import Host, Link, TopologyGraph
from backend.planner.models import (
    CandidateConstraintResult,
    CandidateFeasibility,
    CandidatePath,
    ConstraintAggregation,
    ConstraintEvaluationStatus,
    HardConstraintRequirement,
    KnownTopologyFact,
    MetricObservationPurpose,
    OptimizationStatus,
    Plan,
    PlanningReadiness,
    PlanningRequest,
    RequiredMetricObservation,
    UnknownTopologyFact,
)


@pytest.fixture
def planning_inputs():
    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        constraints=[
            MetricConstraint(
                metric="latency",
                comparison=Comparison.LTE,
                value=30,
                unit="ms",
            )
        ],
    )
    graph = TopologyGraph(
        switches={"s1": 1},
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
    capabilities = resolve_capabilities(intent, graph=graph)
    return intent, graph, capabilities


@pytest.fixture
def ready_request():
    graph = TopologyGraph(
        switches={"s1": 1, "s2": 2},
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
                switch="s2",
                switch_port=1,
            ),
        },
        links=[
            Link(
                node_a="s1",
                port_a=2,
                node_b="s2",
                port_b=2,
                bw_mbps=100,
                intf_a="s1-eth2",
                intf_b="s2-eth2",
            )
        ],
    )
    legacy = StructuredIntent(
        objective=Objective.MIN_BANDWIDTH,
        source="h1",
        destination="h4",
        target=Target(bandwidth_mbps=20),
    )
    normalized = normalize_intent(legacy)
    capabilities = resolve_capabilities(normalized, graph=graph)
    assert capabilities.eligibility == EligibilityStatus.CAPABILITY_READY
    return PlanningRequest(
        intent=normalized.canonical,
        topology=graph,
        capabilities=capabilities,
    )


def _ready_plan(
    request,
    candidates,
    satisfaction_status=SatisfactionStatus.NOT_VERIFIED,
):
    constraint = request.intent.constraints[0]
    requirement = HardConstraintRequirement(
        requirement_id="bandwidth-limit",
        constraint=constraint,
    )
    return Plan(
        request=request,
        capability_readiness=request.capabilities.eligibility,
        planning_readiness=PlanningReadiness.READY,
        satisfaction_status=satisfaction_status,
        hard_constraints=(requirement,),
        required_observations=(
            RequiredMetricObservation(
                observation_id="observe-bandwidth",
                requirement_id="bandwidth-limit",
                purpose=MetricObservationPurpose.HARD_CONSTRAINT,
                metric=constraint.metric,
                unit=constraint.unit,
            ),
        ),
        candidates=tuple(candidates),
    )


def _candidate(request, feasibility, *, reasons=("Path rationale.",)):
    return CandidatePath(
        path=("h1", "s1", "s2", "h4"),
        feasibility=feasibility,
        reasons=reasons,
        constraint_results=(
            CandidateConstraintResult(
                requirement_id="bandwidth-limit",
                status=ConstraintEvaluationStatus.NOT_EVALUATED,
            ),
        ),
    )


def test_planning_request_reuses_canonical_topology_and_capability_models(
    planning_inputs,
):
    intent, graph, capabilities = planning_inputs

    request = PlanningRequest(
        intent=intent,
        topology=graph,
        capabilities=capabilities,
    )

    assert request.intent == intent
    assert request.topology == graph
    assert request.capabilities == capabilities
    assert request.intent is not intent
    assert request.topology is not graph
    assert request.capabilities is not capabilities


def test_planning_request_isolated_from_mutation_of_constructor_inputs(
    planning_inputs,
):
    intent, graph, capabilities = planning_inputs
    request = PlanningRequest(
        intent=intent,
        topology=graph,
        capabilities=capabilities,
    )
    intent.constraints[0].value = 99
    graph.hosts["h1"].ip = "10.0.0.99"
    capabilities.reasons.append("mutated by caller")

    assert request.intent.constraints[0].value == 30
    assert request.topology.hosts["h1"].ip == "10.0.0.1"
    assert "mutated by caller" not in request.capabilities.reasons


def test_shared_canonical_and_topology_models_remain_mutable(planning_inputs):
    intent, graph, _ = planning_inputs

    intent.constraints[0].value = 31
    graph.hosts["h1"].ip = "10.0.0.31"

    assert intent.constraints[0].value == 31
    assert graph.hosts["h1"].ip == "10.0.0.31"


def test_nested_planner_owned_state_is_defensively_copied(ready_request):
    original_intent_fingerprint = ready_request.capabilities.intent_fingerprint
    original_topology_fingerprint = ready_request.capabilities.topology_fingerprint

    exposed_intent = ready_request.intent
    exposed_intent.constraints.append(
        MetricConstraint(
            metric="vendor_metric",
            comparison=Comparison.GTE,
            value=1,
            unit="widgets",
        )
    )
    exposed_topology = ready_request.topology
    exposed_topology.hosts["h1"].ip = "10.0.0.99"
    exposed_capabilities = ready_request.capabilities
    exposed_capabilities.eligibility = EligibilityStatus.INELIGIBLE
    exposed_capabilities.reasons.append("detached mutation")

    assert len(ready_request.intent.constraints) == 1
    assert ready_request.topology.hosts["h1"].ip == "10.0.0.1"
    assert ready_request.capabilities.eligibility == EligibilityStatus.CAPABILITY_READY
    assert "detached mutation" not in ready_request.capabilities.reasons
    assert ready_request.capabilities.intent_fingerprint == original_intent_fingerprint
    assert ready_request.capabilities.topology_fingerprint == original_topology_fingerprint


def test_planner_dict_and_serialization_results_are_detached(ready_request):
    original_fingerprint = ready_request.capabilities.topology_fingerprint
    exposed_dict = ready_request.__dict__
    exposed_dict["topology"].switches["s1"] = 99
    dumped = ready_request.model_dump()
    dumped["topology"]["switches"]["s1"] = 99
    dumped["capabilities"]["topology_fingerprint"] = "stale"
    serialized = ready_request.model_dump_json()
    assert serialized

    assert ready_request.topology.switches["s1"] == 1
    assert ready_request.capabilities.topology_fingerprint == original_fingerprint


@pytest.mark.parametrize(
    "model, update",
    [
        ("request_constraints", {"intent": {"constraints": []}}),
        ("request_fingerprint", {"capabilities": {"topology_fingerprint": "stale"}}),
        ("plan_constraints", {"hard_constraints": ()}),
    ],
)
def test_planner_model_copy_rejects_unvalidated_updates(
    ready_request,
    model,
    update,
):
    plan = _ready_plan(
        ready_request,
        (_candidate(ready_request, CandidateFeasibility.CANDIDATE),),
    )
    target = ready_request if model.startswith("request") else plan

    with pytest.raises(TypeError, match="do not support model_copy"):
        target.model_copy(update=update)


def test_planning_request_model_construct_requires_validated_construction(
    planning_inputs,
):
    intent, graph, capabilities = planning_inputs

    with pytest.raises(
        TypeError,
        match="PlanningRequest requires validated construction",
    ):
        PlanningRequest.model_construct(
            intent=intent,
            topology=graph,
            capabilities=capabilities,
        )


def test_plan_model_construct_cannot_create_apparently_ready_plan(ready_request):
    with pytest.raises(TypeError, match="Plan requires validated construction"):
        Plan.model_construct(
            request=ready_request,
            capability_readiness=EligibilityStatus.CAPABILITY_READY,
            planning_readiness=PlanningReadiness.READY,
            hard_constraints=(),
            candidates=(),
        )


def test_valid_planner_construction_serialization_equality_and_fingerprints(
    ready_request,
):
    dumped = ready_request.model_dump(mode="python")
    restored = PlanningRequest.model_validate(dumped)
    shallow_copy = ready_request.model_copy()

    assert restored == ready_request
    assert shallow_copy == ready_request
    assert model_fingerprint(restored.topology) == (
        ready_request.capabilities.topology_fingerprint
    )
    assert restored.model_dump_json()


def test_topology_fingerprint_is_dictionary_order_independent(ready_request):
    topology = ready_request.topology
    reordered = TopologyGraph(
        switches=dict(reversed(list(topology.switches.items()))),
        hosts=dict(reversed(list(topology.hosts.items()))),
        links=topology.links,
    )

    assert model_fingerprint(reordered) == model_fingerprint(topology)


@pytest.mark.parametrize(
    "changed_property",
    [
        "host_ip",
        "host_switch",
        "host_port",
        "link_capacity",
        "link_endpoint",
        "link_port",
        "switch_dpid",
    ],
)
def test_topology_fingerprint_changes_with_execution_relevant_properties(
    ready_request,
    changed_property,
):
    topology = ready_request.topology
    changed = topology.model_copy(deep=True)
    if changed_property == "host_ip":
        changed.hosts["h1"].ip = "10.0.0.99"
    elif changed_property == "host_switch":
        changed.hosts["h4"].switch = "s1"
    elif changed_property == "host_port":
        changed.hosts["h4"].switch_port = 9
    elif changed_property == "link_capacity":
        changed.links[0].bw_mbps = 90
    elif changed_property == "link_endpoint":
        changed.links[0].node_b = "s3"
    elif changed_property == "link_port":
        changed.links[0].port_b = 9
    else:
        changed.switches["s1"] = 99

    assert model_fingerprint(changed) != model_fingerprint(topology)


def test_none_and_topology_graph_have_distinct_fingerprints(ready_request):
    assert model_fingerprint(None) != model_fingerprint(ready_request.topology)


def test_plan_isolated_from_original_request_inputs_and_nested_mutations(
    ready_request,
):
    original_intent = ready_request.intent
    original_topology = ready_request.topology
    original_capabilities = ready_request.capabilities
    plan = _ready_plan(
        ready_request,
        (_candidate(ready_request, CandidateFeasibility.CANDIDATE),),
    )

    original_intent.constraints[0].value = 99
    original_topology.hosts["h1"].ip = "10.0.0.99"
    original_capabilities.eligibility = EligibilityStatus.INELIGIBLE
    original_capabilities.reasons.append("mutated after plan construction")

    exposed_request = plan.request
    exposed_request.intent.constraints[0].value = 77
    exposed_request.topology.links[0].bw_mbps = 1
    exposed_request.capabilities.reasons.append("detached plan mutation")
    exposed_constraints = plan.hard_constraints
    exposed_constraints[0].constraint.value = 88

    assert plan.request.intent.constraints[0].value == 20
    assert plan.request.topology.hosts["h1"].ip == "10.0.0.1"
    assert plan.request.topology.links[0].bw_mbps == 100
    assert plan.request.capabilities.eligibility == EligibilityStatus.CAPABILITY_READY
    assert "mutated after plan construction" not in plan.request.capabilities.reasons
    assert "detached plan mutation" not in plan.request.capabilities.reasons
    assert plan.hard_constraints[0].constraint.value == 20


def test_planning_request_rejects_capabilities_for_different_intent_or_topology(
    planning_inputs,
):
    intent, graph, _ = planning_inputs
    different_intent = CanonicalIntent(
        scope=intent.scope,
        constraints=[
            MetricConstraint(
                metric="latency",
                comparison=Comparison.LTE,
                value=31,
                unit="ms",
            )
        ],
    )
    intent_capabilities = resolve_capabilities(different_intent, graph=graph)
    with pytest.raises(ValidationError, match="different canonical intent"):
        PlanningRequest(
            intent=intent,
            topology=graph,
            capabilities=intent_capabilities,
        )

    different_topology = graph.model_copy(update={"switches": {"s1": 9}})
    topology_capabilities = resolve_capabilities(intent, graph=different_topology)
    with pytest.raises(ValidationError, match="different topology"):
        PlanningRequest(
            intent=intent,
            topology=graph,
            capabilities=topology_capabilities,
        )


def test_plan_uses_request_snapshot_after_original_topology_mutation(planning_inputs):
    intent, graph, capabilities = planning_inputs
    request = PlanningRequest(
        intent=intent,
        topology=graph,
        capabilities=capabilities,
    )
    graph.switches["s1"] = 9

    plan = Plan(
        request=request,
        capability_readiness=capabilities.eligibility,
        planning_readiness=PlanningReadiness.BLOCKED,
        hard_constraints=(
            HardConstraintRequirement(
                requirement_id="latency-limit",
                constraint=intent.constraints[0],
            ),
        ),
        required_observations=(
            RequiredMetricObservation(
                observation_id="observe-latency",
                requirement_id="latency-limit",
                purpose=MetricObservationPurpose.HARD_CONSTRAINT,
                metric="latency",
                unit="ms",
            ),
        ),
    )

    assert plan.request.topology.switches["s1"] == 1


def test_plan_keeps_readiness_and_runtime_states_separate(planning_inputs):
    intent, graph, capabilities = planning_inputs
    request = PlanningRequest(
        intent=intent,
        topology=graph,
        capabilities=capabilities,
    )
    requirement = HardConstraintRequirement(
        requirement_id="latency-limit",
        constraint=intent.constraints[0],
    )
    plan = Plan(
        request=request,
        capability_readiness=capabilities.eligibility,
        planning_readiness=PlanningReadiness.BLOCKED,
        hard_constraints=(requirement,),
        required_observations=(
            RequiredMetricObservation(
                observation_id="observe-latency",
                requirement_id="latency-limit",
                purpose=MetricObservationPurpose.HARD_CONSTRAINT,
                metric="latency",
                unit="ms",
            ),
        ),
    )

    assert plan.capability_readiness == EligibilityStatus.INELIGIBLE
    assert plan.planning_readiness == PlanningReadiness.BLOCKED
    assert plan.execution_status == ExecutionStatus.NOT_DISPATCHED
    assert plan.deployment_status == DeploymentStatus.NOT_ATTEMPTED
    assert plan.satisfaction_status == SatisfactionStatus.NOT_VERIFIED
    assert plan.optimization_status == OptimizationStatus.NOT_APPLIED


def test_candidate_preserves_known_unknown_facts_and_reasons():
    candidate = CandidatePath(
        path=("h1", "s1", "h4"),
        feasibility=CandidateFeasibility.UNKNOWN,
        reasons=("Capacity metadata is missing.",),
        known_facts=(
            KnownTopologyFact(
                name="hop_count",
                value=1,
                source="topology graph",
            ),
        ),
        unknown_facts=(
            UnknownTopologyFact(
                name="link_capacity",
                reason="The topology does not contain bandwidth metadata.",
            ),
        ),
    )

    assert candidate.feasibility == CandidateFeasibility.UNKNOWN
    assert candidate.known_facts[0].value == 1
    assert candidate.unknown_facts[0].name == "link_capacity"
    assert candidate.reasons


def test_proven_infeasibility_requires_an_explanation():
    with pytest.raises(ValidationError, match="requires explanatory reasons"):
        CandidatePath(
            path=("h1", "s1", "h4"),
            feasibility=CandidateFeasibility.PROVEN_INFEASIBLE,
        )


def test_candidate_requires_inclusion_rationale():
    with pytest.raises(ValidationError, match="inclusion rationale"):
        CandidatePath(
            path=("h1", "s1", "h4"),
            feasibility=CandidateFeasibility.CANDIDATE,
        )


def test_plan_preserves_constraints_conjunctively_and_separately_from_objective(
    planning_inputs,
):
    bandwidth = MetricConstraint(
        metric="bandwidth",
        comparison=Comparison.GTE,
        value=20,
        unit="Mbps",
    )
    intent, graph, _ = planning_inputs
    intent = CanonicalIntent(
        scope=intent.scope,
        constraints=[intent.constraints[0], bandwidth],
        optimization=OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        ),
    )
    capabilities = resolve_capabilities(intent, graph=graph)
    request = PlanningRequest(
        intent=intent,
        topology=graph,
        capabilities=capabilities,
    )
    requirements = (
        HardConstraintRequirement(
            requirement_id="latency-limit",
            constraint=intent.constraints[0],
        ),
        HardConstraintRequirement(
            requirement_id="bandwidth-floor",
            constraint=bandwidth,
        ),
    )
    observations = (
        RequiredMetricObservation(
            observation_id="observe-latency",
            requirement_id="latency-limit",
            purpose=MetricObservationPurpose.HARD_CONSTRAINT,
            metric="latency",
            unit="ms",
        ),
        RequiredMetricObservation(
            observation_id="observe-bandwidth",
            requirement_id="bandwidth-floor",
            purpose=MetricObservationPurpose.HARD_CONSTRAINT,
            metric="bandwidth",
            unit="Mbps",
        ),
        RequiredMetricObservation(
            observation_id="optimize-latency",
            requirement_id="objective",
            purpose=MetricObservationPurpose.OPTIMIZATION,
            metric="latency",
            unit="ms",
        ),
    )
    candidate = CandidatePath(
        path=("h1", "s1", "h4"),
        feasibility=CandidateFeasibility.CANDIDATE,
        reasons=("Contract fixture candidate included for model validation.",),
        constraint_results=(
            CandidateConstraintResult(
                requirement_id="latency-limit",
                status=ConstraintEvaluationStatus.NOT_EVALUATED,
            ),
            CandidateConstraintResult(
                requirement_id="bandwidth-floor",
                status=ConstraintEvaluationStatus.NOT_EVALUATED,
            ),
        ),
    )

    plan = Plan(
        request=request,
        capability_readiness=capabilities.eligibility,
        planning_readiness=PlanningReadiness.CONDITIONAL,
        hard_constraints=requirements,
        constraint_aggregation=ConstraintAggregation.ALL,
        required_observations=observations,
        optimization=intent.optimization,
        candidates=(candidate,),
    )

    assert plan.constraint_aggregation == ConstraintAggregation.ALL
    assert [item.requirement_id for item in plan.hard_constraints] == [
        "latency-limit",
        "bandwidth-floor",
    ]
    assert [item.status for item in candidate.constraint_results] == [
        ConstraintEvaluationStatus.NOT_EVALUATED,
        ConstraintEvaluationStatus.NOT_EVALUATED,
    ]
    assert plan.optimization.metric == "latency"
    assert plan.optimization_status == OptimizationStatus.NOT_APPLIED
    assert plan.satisfaction_status == SatisfactionStatus.NOT_VERIFIED


@pytest.mark.parametrize(
    "feasibilities, error",
    [
        (
            (CandidateFeasibility.PROVEN_INFEASIBLE,),
            "at least one candidate path",
        ),
        (
            (CandidateFeasibility.CANDIDATE, CandidateFeasibility.UNKNOWN),
            "cannot classify a candidate's topology feasibility as unknown",
        ),
        ((), "at least one candidate path"),
    ],
)
def test_ready_requires_a_candidate_and_no_unknown_paths(
    ready_request,
    feasibilities,
    error,
):
    candidates = tuple(
        _candidate(ready_request, feasibility)
        for feasibility in feasibilities
    )
    with pytest.raises(ValidationError, match=error):
        _ready_plan(ready_request, candidates)


def test_ready_plan_keeps_measurement_satisfaction_unverified(ready_request):
    plan = _ready_plan(
        ready_request,
        (_candidate(ready_request, CandidateFeasibility.CANDIDATE),),
    )

    assert plan.planning_readiness == PlanningReadiness.READY
    assert plan.candidates[0].constraint_results[0].status == (
        ConstraintEvaluationStatus.NOT_EVALUATED
    )
    assert plan.satisfaction_status == SatisfactionStatus.NOT_VERIFIED


@pytest.mark.parametrize(
    "status",
    [
        ConstraintEvaluationStatus.SATISFIED,
        ConstraintEvaluationStatus.UNSATISFIED,
        ConstraintEvaluationStatus.UNKNOWN,
    ],
)
def test_phase_3a_rejects_unevidenced_constraint_evaluations(status):
    with pytest.raises(ValidationError):
        CandidateConstraintResult(
            requirement_id="bandwidth-limit",
            status=status,
        )


@pytest.mark.parametrize("status", ["SATISFIED", "UNSATISFIED"])
def test_phase_3a_rejects_plan_satisfaction_claims(ready_request, status):
    with pytest.raises(ValidationError):
        _ready_plan(
            ready_request,
            (_candidate(ready_request, CandidateFeasibility.CANDIDATE),),
            satisfaction_status=status,
        )


@pytest.mark.parametrize("mutation", ["missing", "extra", "value", "unit"])
def test_plan_must_preserve_exact_originating_constraints(
    planning_inputs,
    mutation,
):
    intent, graph, capabilities = planning_inputs
    if mutation == "unit":
        intent = CanonicalIntent(
            scope=intent.scope,
            constraints=[
                MetricConstraint(
                    metric="vendor_metric",
                    comparison=Comparison.GTE,
                    value=30,
                    unit="widgets",
                )
            ],
        )
        capabilities = resolve_capabilities(intent, graph=graph)
    request = PlanningRequest(
        intent=intent,
        topology=graph,
        capabilities=capabilities,
    )
    original = intent.constraints[0]
    if mutation == "missing":
        requirements = ()
    elif mutation == "extra":
        requirements = (
            HardConstraintRequirement(
                requirement_id="latency-limit",
                constraint=original,
            ),
            HardConstraintRequirement(
                requirement_id="extra",
                constraint=MetricConstraint(
                    metric="vendor_metric",
                    comparison=Comparison.GTE,
                    value=1,
                    unit="widgets",
                ),
            ),
        )
    else:
        changed = original.model_copy(
            update={"value": 31} if mutation == "value" else {"unit": "widgets/min"}
        )
        requirements = (
            HardConstraintRequirement(
                requirement_id="latency-limit",
                constraint=changed,
            ),
        )

    with pytest.raises(ValidationError, match="exactly preserve"):
        Plan(
            request=request,
            capability_readiness=capabilities.eligibility,
            planning_readiness=PlanningReadiness.BLOCKED,
            hard_constraints=requirements,
        )


def test_plan_rejects_candidate_that_drops_a_hard_constraint(planning_inputs):
    intent, graph, capabilities = planning_inputs
    request = PlanningRequest(
        intent=intent,
        topology=graph,
        capabilities=capabilities,
    )
    requirement = HardConstraintRequirement(
        requirement_id="latency-limit",
        constraint=intent.constraints[0],
    )

    with pytest.raises(ValidationError, match="every hard constraint"):
        Plan(
            request=request,
            capability_readiness=capabilities.eligibility,
            planning_readiness=PlanningReadiness.CONDITIONAL,
            hard_constraints=(requirement,),
            required_observations=(
                RequiredMetricObservation(
                    observation_id="observe-latency",
                    requirement_id="latency-limit",
                    purpose=MetricObservationPurpose.HARD_CONSTRAINT,
                    metric="latency",
                    unit="ms",
                ),
            ),
            candidates=(
                CandidatePath(
                    path=("h1", "s1", "h4"),
                    feasibility=CandidateFeasibility.CANDIDATE,
                    reasons=("Contract fixture candidate included for model validation.",),
                    constraint_results=(),
                ),
            ),
        )
