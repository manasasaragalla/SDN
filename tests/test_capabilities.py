import pytest
from pydantic import ValidationError

from backend.capabilities import (
    CapabilityStatus,
    DeploymentStatus,
    EligibilityStatus,
    ExecutionStatus,
    ExecutionMode,
    SatisfactionStatus,
    resolve_capabilities,
)
from backend.models.canonical_intent import (
    CanonicalIntent,
    MetricConstraint,
    OptimizationDirection,
    OptimizationObjective,
    RequestedAction,
    TrafficScope,
    TrafficSelector,
)
from backend.models.intent import (
    Constraints,
    LossTolerance,
    Objective,
    StructuredIntent,
    Target,
)
from backend.models.intent_normalization import normalize_intent
from backend.models.network import Host, Link, TopologyGraph
from backend.validator.path_validator import validate_rate_limit


@pytest.fixture
def graph():
    return TopologyGraph(
        switches={"s1": 1, "s2": 2, "s3": 3, "s4": 4},
        hosts={
            "h1": Host(name="h1", ip="10.0.0.1", mac="00:00:00:00:00:01", switch="s1", switch_port=1),
            "h4": Host(name="h4", ip="10.0.0.4", mac="00:00:00:00:00:04", switch="s4", switch_port=1),
        },
        links=[
            Link(node_a="s1", port_a=2, node_b="s2", port_b=1, bw_mbps=100, intf_a="s1-eth2", intf_b="s2-eth1"),
            Link(node_a="s2", port_a=2, node_b="s4", port_b=2, bw_mbps=100, intf_a="s2-eth2", intf_b="s4-eth2"),
            Link(node_a="s1", port_a=3, node_b="s3", port_b=1, bw_mbps=100, intf_a="s1-eth3", intf_b="s3-eth1"),
            Link(node_a="s3", port_a=2, node_b="s4", port_b=3, bw_mbps=100, intf_a="s3-eth2", intf_b="s4-eth3"),
        ],
    )


def canonical(**kwargs):
    return CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        **kwargs,
    )


def _parallel_capacity_graph(capacities):
    return TopologyGraph(
        switches={"s1": 1, "s2": 2},
        hosts={
            "h1": Host(name="h1", ip="10.0.0.1", mac="00:00:00:00:00:01", switch="s1", switch_port=1),
            "h4": Host(name="h4", ip="10.0.0.4", mac="00:00:00:00:00:04", switch="s2", switch_port=1),
        },
        links=[
            Link(
                node_a="s1",
                port_a=2 + index,
                node_b="s2",
                port_b=2 + index,
                bw_mbps=capacity,
                intf_a=f"s1-eth{2 + index}",
                intf_b=f"s2-eth{2 + index}",
            )
            for index, capacity in enumerate(capacities)
        ],
    )


def test_metric_definitions_are_used_by_canonical_unit_validation():
    with pytest.raises(ValidationError, match="requires unit"):
        canonical(
            constraints=[
                {
                    "metric": "latency",
                    "comparison": "LTE",
                    "value": 20,
                    "unit": "seconds",
                }
            ]
        )


@pytest.mark.parametrize(
    ("metric", "unit", "comparison", "value", "expected_measurement"),
    [
        ("latency", "ms", "LTE", 30, CapabilityStatus.SUPPORTED),
        ("bandwidth", "Mbps", "GTE", 20, CapabilityStatus.SUPPORTED),
        ("packet_loss", "%", "LTE", 1, CapabilityStatus.SUPPORTED),
        ("jitter", "ms", "LTE", 5, CapabilityStatus.UNSUPPORTED),
        ("availability", "%", "GTE", 99, CapabilityStatus.UNSUPPORTED),
    ],
)
def test_initial_metric_capability_states(
    graph,
    metric,
    unit,
    comparison,
    value,
    expected_measurement,
):
    result = resolve_capabilities(
        canonical(
            constraints=[
                MetricConstraint(
                    metric=metric,
                    comparison=comparison,
                    value=value,
                    unit=unit,
                )
            ]
        ),
        graph=graph,
    )
    assessment = result.constraints[0]
    assert assessment.recognized.status == CapabilityStatus.SUPPORTED
    assert assessment.measurable.status == expected_measurement


def test_packet_loss_is_measurable_but_not_plannable_or_executable(graph):
    result = resolve_capabilities(
        canonical(
            constraints=[
                MetricConstraint(
                    metric="packet_loss",
                    comparison="LTE",
                    value=1,
                    unit="%",
                )
            ]
        ),
        graph=graph,
    )
    assessment = result.constraints[0]
    assert assessment.measurable.status == CapabilityStatus.SUPPORTED
    assert assessment.plannable.status == CapabilityStatus.UNSUPPORTED
    assert assessment.executable.status == CapabilityStatus.UNSUPPORTED
    assert result.eligibility == EligibilityStatus.INELIGIBLE


def test_unknown_metric_and_unit_semantics_fail_closed(graph):
    result = resolve_capabilities(
        canonical(
            constraints=[
                MetricConstraint(
                    metric="vendor_metric",
                    comparison="GTE",
                    value=2,
                    unit="widgets/s",
                )
            ]
        ),
        graph=graph,
    )
    assessment = result.constraints[0]
    assert assessment.recognized.status == CapabilityStatus.UNSUPPORTED
    assert assessment.validated.status == CapabilityStatus.UNSUPPORTED
    assert not result.capability_ready
    assert any("unit semantics" in reason for reason in assessment.validated.reasons)


def test_invalid_metric_value_is_rejected_semantically(graph):
    result = resolve_capabilities(
        canonical(
            constraints=[
                MetricConstraint(
                    metric="packet_loss",
                    comparison="LTE",
                    value=101,
                    unit="%",
                )
            ]
        ),
        graph=graph,
    )
    assert result.constraints[0].validated.status == CapabilityStatus.UNSUPPORTED
    assert "at most 100" in result.constraints[0].validated.reasons[0]
    assert not result.capability_ready


def test_eq_constraint_tolerance_is_validated_for_evaluation(graph):
    result = resolve_capabilities(
        canonical(
            constraints=[
                MetricConstraint(
                    metric="latency",
                    comparison="EQ",
                    value=30,
                    unit="ms",
                    tolerance=1,
                )
            ]
        ),
        graph=graph,
    )
    assert result.constraints[0].validated.status == CapabilityStatus.SUPPORTED


@pytest.mark.parametrize("comparison", ["GT", "GTE", "LT", "LTE", "BETWEEN"])
def test_tolerance_on_non_eq_comparisons_remains_unsupported(graph, comparison):
    kwargs = (
        {"lower_bound": 10, "upper_bound": 30}
        if comparison == "BETWEEN"
        else {"value": 20}
    )
    result = resolve_capabilities(
        canonical(
            constraints=[
                MetricConstraint(
                    metric="latency",
                    comparison=comparison,
                    unit="ms",
                    tolerance=1,
                    **kwargs,
                )
            ]
        ),
        graph=graph,
    )
    assert result.constraints[0].validated.status == CapabilityStatus.UNSUPPORTED
    assert "only for EQ" in result.constraints[0].validated.reasons[0]


def test_legacy_latency_is_capable_without_claiming_generalized_support(graph):
    legacy = StructuredIntent(
        objective=Objective.MINIMIZE_LATENCY,
        source="h1",
        destination="h4",
    )
    result = resolve_capabilities(normalize_intent(legacy), graph=graph)

    assert result.legacy_execution_hint.value == "MINIMIZE_LATENCY"
    assert result.optimization.plannable.status == CapabilityStatus.SUPPORTED
    assert result.optimization.executable.status == CapabilityStatus.SUPPORTED
    assert (
        result.optimization.generalized_objective_ranking.status
        == CapabilityStatus.UNSUPPORTED
    )
    assert result.capability_ready
    assert result.execution_status == ExecutionStatus.NOT_DISPATCHED
    assert result.deployment_status == DeploymentStatus.NOT_ATTEMPTED
    assert result.satisfaction_status == SatisfactionStatus.NOT_VERIFIED

    generalized = resolve_capabilities(
        normalize_intent(legacy),
        graph=graph,
        execution_mode=ExecutionMode.GENERALIZED,
    )
    assert generalized.optimization.executable.status == CapabilityStatus.CONDITIONAL
    assert (
        generalized.optimization.generalized_objective_ranking.status
        == CapabilityStatus.SUPPORTED
    )
    assert not generalized.capability_ready


def test_legacy_loss_tolerance_is_informational_and_does_not_change_legacy_eligibility(graph):
    legacy = StructuredIntent(
        objective=Objective.MINIMIZE_LATENCY,
        source="h1",
        destination="h4",
        constraints=Constraints(loss_tolerance=LossTolerance.HIGH),
    )
    result = resolve_capabilities(normalize_intent(legacy), graph=graph)

    assert result.legacy_metadata.status == CapabilityStatus.CONDITIONAL
    assert result.legacy_execution_hint.value == "MINIMIZE_LATENCY"
    assert result.capability_ready


def test_legacy_bandwidth_target_remains_capable_with_known_topology_capacity(graph):
    legacy = StructuredIntent(
        objective=Objective.MIN_BANDWIDTH,
        source="h1",
        destination="h4",
        target=Target(bandwidth_mbps=20),
    )
    result = resolve_capabilities(normalize_intent(legacy), graph=graph)

    assert result.legacy_execution_hint.value == "MIN_BANDWIDTH"
    assert result.constraints[0].plannable.status == CapabilityStatus.SUPPORTED
    assert result.constraints[0].executable.status == CapabilityStatus.SUPPORTED
    assert result.capability_ready


def test_multiple_constraints_and_optimization_are_all_required(graph):
    result = resolve_capabilities(
        canonical(
            constraints=[
                MetricConstraint(
                    metric="bandwidth",
                    comparison="GTE",
                    value=20,
                    unit="Mbps",
                ),
                MetricConstraint(
                    metric="packet_loss",
                    comparison="LTE",
                    value=1,
                    unit="%",
                ),
            ],
            optimization=OptimizationObjective(
                metric="latency",
                direction=OptimizationDirection.MINIMIZE,
                unit="ms",
            ),
        ),
        graph=graph,
    )

    assert len(result.constraints) == 2
    assert result.optimization.metric == "latency"
    assert (
        result.optimization.generalized_objective_ranking.status
        == CapabilityStatus.SUPPORTED
    )
    assert result.optimization.plannable.status == CapabilityStatus.SUPPORTED
    assert result.optimization.executable.status != CapabilityStatus.SUPPORTED
    assert result.constraints[0].requirement_id.startswith("constraint:0")
    assert result.constraints[1].plannable.status == CapabilityStatus.UNSUPPORTED
    assert result.eligibility == EligibilityStatus.INELIGIBLE


def test_generalized_bandwidth_objective_has_measured_execution_strategy(graph):
    result = resolve_capabilities(
        canonical(
            constraints=[
                MetricConstraint(
                    metric="latency",
                    comparison="LTE",
                    value=50,
                    unit="ms",
                )
            ],
            optimization=OptimizationObjective(
                metric="bandwidth",
                direction=OptimizationDirection.MAXIMIZE,
                unit="Mbps",
            ),
        ),
        graph=graph,
        execution_mode=ExecutionMode.GENERALIZED,
    )

    assert result.optimization.generalized_objective_ranking.status == CapabilityStatus.SUPPORTED
    assert result.optimization.executable.status == CapabilityStatus.SUPPORTED
    assert result.constraints[0].executable.status == CapabilityStatus.SUPPORTED


def test_generalized_latency_objective_has_measured_execution_strategy(graph):
    result = resolve_capabilities(
        canonical(
            optimization=OptimizationObjective(
                metric="latency",
                direction=OptimizationDirection.MINIMIZE,
                unit="ms",
            )
        ),
        graph=graph,
        execution_mode=ExecutionMode.GENERALIZED,
    )

    assert (
        result.optimization.generalized_objective_ranking.status
        == CapabilityStatus.SUPPORTED
    )
    assert result.optimization.plannable.status == CapabilityStatus.SUPPORTED
    assert result.optimization.executable.status == CapabilityStatus.SUPPORTED


def test_optimization_and_constraint_unit_mismatch_is_rejected(graph):
    # Unknown identifiers remain structurally extensible; resolution still
    # rejects comparing their unlike units across requirement types.
    intent = canonical(
        constraints=[
            MetricConstraint(
                metric="vendor_metric",
                comparison="GTE",
                value=2,
                unit="widgets/s",
            )
        ],
        optimization=OptimizationObjective(
            metric="vendor_metric",
            direction="MINIMIZE",
            unit="widgets/min",
        ),
    )
    result = resolve_capabilities(intent, graph=graph)
    assert "different units" in result.constraints[0].validated.reasons[0]
    assert "different units" in result.optimization.validated.reasons[0]
    assert not result.capability_ready


@pytest.mark.parametrize(
    ("metric", "unit", "expected"),
    [
        ("latency", "ms", CapabilityStatus.SUPPORTED),
        ("bandwidth", "Mbps", CapabilityStatus.SUPPORTED),
        ("packet_loss", "%", CapabilityStatus.SUPPORTED),
        ("jitter", "ms", CapabilityStatus.UNSUPPORTED),
        ("availability", "%", CapabilityStatus.UNSUPPORTED),
    ],
)
def test_only_measurable_supported_metrics_enable_generalized_objective_ranking(
    graph, metric, unit, expected
):
    result = resolve_capabilities(
        canonical(
            optimization=OptimizationObjective(
                metric=metric,
                direction=OptimizationDirection.MINIMIZE,
                unit=unit,
            )
        ),
        graph=graph,
    )

    assert (
        result.optimization.generalized_objective_ranking.status
        == expected
    )
    if metric == "packet_loss":
        assert result.optimization.measurable.status == CapabilityStatus.SUPPORTED
        assert result.optimization.plannable.status == CapabilityStatus.SUPPORTED
        assert result.optimization.executable.status == CapabilityStatus.UNSUPPORTED


def test_unsupported_requested_actions_are_not_executable(graph):
    for action_name in ("prioritize", "allow", "block", "vendor_action"):
        result = resolve_capabilities(
            canonical(requested_actions=[RequestedAction(name=action_name)]),
            graph=graph,
        )
        assert result.actions[0].executable.status == CapabilityStatus.UNSUPPORTED
        assert not result.capability_ready


def test_rate_limit_is_conditional_and_requires_a_positive_rate(graph):
    missing_rate = resolve_capabilities(
        canonical(requested_actions=[RequestedAction(name="rate_limit")]),
        graph=graph,
    )
    assert missing_rate.actions[0].validated.status == CapabilityStatus.CONDITIONAL
    assert missing_rate.actions[0].executable.status == CapabilityStatus.CONDITIONAL
    assert not missing_rate.capability_ready

    rate = resolve_capabilities(
        canonical(
            requested_actions=[
                RequestedAction(
                    name="rate_limit",
                    parameters={"rate_mbps": 10},
                )
            ]
        ),
        graph=graph,
    )
    assert rate.actions[0].validated.status == CapabilityStatus.SUPPORTED
    assert rate.actions[0].executable.status == CapabilityStatus.CONDITIONAL


def test_rate_limit_requires_qos_compiler_topology_metadata(graph):
    links_without_interfaces = graph.model_copy(
        update={
            "links": [
                link.model_copy(update={"intf_a": None, "intf_b": None})
                for link in graph.links
            ]
        }
    )
    result = resolve_capabilities(
        canonical(
            requested_actions=[
                RequestedAction(name="rate_limit", parameters={"rate_mbps": 10})
            ]
        ),
        graph=links_without_interfaces,
    )
    assert result.actions[0].executable.status == CapabilityStatus.CONDITIONAL
    assert any(
        "interface metadata" in condition
        for condition in result.actions[0].executable.missing_conditions
    )


def test_rate_limit_rejects_rate_above_all_known_qos_egress_capacities(graph):
    low_capacity_graph = graph.model_copy(
        update={
            "links": [
                link.model_copy(update={"bw_mbps": 5})
                for link in graph.links
            ]
        }
    )
    result = resolve_capabilities(
        canonical(
            requested_actions=[
                RequestedAction(name="rate_limit", parameters={"rate_mbps": 10})
            ]
        ),
        graph=low_capacity_graph,
    )

    rate_limit = result.actions[0]
    assert rate_limit.validated.status == CapabilityStatus.UNSUPPORTED
    assert rate_limit.executable.status == CapabilityStatus.UNSUPPORTED
    assert any("exceeds the known QoS egress capacity" in reason for reason in rate_limit.validated.reasons)
    assert result.eligibility == EligibilityStatus.INELIGIBLE


def test_rate_limit_capacity_unknown_remains_conditional(graph):
    unknown_capacity_graph = graph.model_copy(
        update={
            "links": [
                link.model_copy(update={"bw_mbps": None})
                for link in graph.links
            ]
        }
    )
    result = resolve_capabilities(
        canonical(
            requested_actions=[
                RequestedAction(name="rate_limit", parameters={"rate_mbps": 10})
            ]
        ),
        graph=unknown_capacity_graph,
    )

    rate_limit = result.actions[0]
    assert rate_limit.validated.status == CapabilityStatus.CONDITIONAL
    assert rate_limit.executable.status == CapabilityStatus.CONDITIONAL
    assert any("capacity metadata is required" in condition for condition in rate_limit.validated.missing_conditions)
    assert result.eligibility == EligibilityStatus.CONDITIONAL


def test_rate_limit_mixed_candidate_capacities_keeps_feasible_path(graph):
    mixed_capacity_graph = graph.model_copy(
        update={
            "links": [
                link.model_copy(
                    update={
                        "bw_mbps": (
                            5
                            if {link.node_a, link.node_b} == {"s1", "s2"}
                            else 20
                            if {link.node_a, link.node_b} == {"s1", "s3"}
                            else link.bw_mbps
                        )
                    }
                )
                for link in graph.links
            ]
        }
    )
    candidate_paths = mixed_capacity_graph.all_simple_paths("h1", "h4")
    capacity_by_path = {
        tuple(path): mixed_capacity_graph.link_between(
            path[1],
            path[2],
        ).bw_mbps
        for path in candidate_paths
    }

    insufficient_path = next(
        path for path, capacity in capacity_by_path.items() if capacity == 5
    )
    sufficient_path = next(
        path for path, capacity in capacity_by_path.items() if capacity == 20
    )
    assert not validate_rate_limit(
        10,
        capacity_by_path[insufficient_path],
    ).valid
    assert validate_rate_limit(
        10,
        capacity_by_path[sufficient_path],
    ).valid

    result = resolve_capabilities(
        canonical(
            requested_actions=[
                RequestedAction(name="rate_limit", parameters={"rate_mbps": 10})
            ]
        ),
        graph=mixed_capacity_graph,
    )

    rate_limit = result.actions[0]
    assert rate_limit.validated.status == CapabilityStatus.SUPPORTED
    assert rate_limit.executable.status == CapabilityStatus.CONDITIONAL
    assert result.eligibility == EligibilityStatus.CONDITIONAL
    assert not any(
        "exceeds the known QoS egress capacity" in reason
        for reason in rate_limit.validated.reasons
    )


def test_rate_limit_accepts_rate_equal_to_egress_capacity(graph):
    boundary_capacity_graph = graph.model_copy(
        update={
            "links": [
                link.model_copy(
                    update={"bw_mbps": 10}
                    if {link.node_a, link.node_b} == {"s1", "s2"}
                    else {}
                )
                for link in graph.links
            ]
        }
    )
    boundary_path = next(
        path
        for path in boundary_capacity_graph.all_simple_paths("h1", "h4")
        if boundary_capacity_graph.link_between(path[1], path[2]).bw_mbps == 10
    )
    boundary_capacity = boundary_capacity_graph.link_between(
        boundary_path[1],
        boundary_path[2],
    ).bw_mbps

    # validate_rate_limit rejects rate > capacity, so equality is accepted.
    assert validate_rate_limit(10, boundary_capacity).valid

    result = resolve_capabilities(
        canonical(
            requested_actions=[
                RequestedAction(name="rate_limit", parameters={"rate_mbps": 10})
            ]
        ),
        graph=boundary_capacity_graph,
    )

    assert result.actions[0].validated.status == CapabilityStatus.SUPPORTED
    assert result.eligibility == EligibilityStatus.CONDITIONAL


def test_reroute_reports_existing_primitive_with_orchestration_condition(graph):
    result = resolve_capabilities(
        canonical(requested_actions=[RequestedAction(name="reroute")]),
        graph=graph,
    )
    assert result.actions[0].recognized.status == CapabilityStatus.SUPPORTED
    assert result.actions[0].executable.status == CapabilityStatus.CONDITIONAL
    assert not result.capability_ready


def test_missing_topology_hosts_and_no_path_are_ineligible(graph):
    unknown_host_intent = CanonicalIntent(
        scope=TrafficScope(source="h9", destination="h4")
    )
    unknown_host = resolve_capabilities(unknown_host_intent, graph=graph)
    assert unknown_host.scope.status == CapabilityStatus.UNSUPPORTED
    assert unknown_host.eligibility == EligibilityStatus.INELIGIBLE

    disconnected = TopologyGraph(
        switches={"s1": 1, "s4": 4},
        hosts=graph.hosts,
        links=[],
    )
    no_path = resolve_capabilities(
        CanonicalIntent(scope=TrafficScope(source="h1", destination="h4")),
        graph=disconnected,
    )
    assert no_path.topology.status == CapabilityStatus.UNSUPPORTED
    assert not no_path.capability_ready


def test_different_host_names_with_identical_ipv4_are_ineligible(graph):
    duplicate_ip_graph = graph.model_copy(
        update={
            "hosts": {
                **graph.hosts,
                "h4": graph.hosts["h4"].model_copy(
                    update={"ip": graph.hosts["h1"].ip}
                ),
            }
        }
    )
    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4")
    )

    result = resolve_capabilities(intent, graph=duplicate_ip_graph)

    assert result.scope.status == CapabilityStatus.UNSUPPORTED
    assert result.topology.status == CapabilityStatus.UNSUPPORTED
    assert any("same IPv4 address" in reason for reason in result.reasons)
    assert result.eligibility == EligibilityStatus.INELIGIBLE
    assert not result.capability_ready


def test_empty_intent_is_semantically_ineligible(graph):
    result = resolve_capabilities(
        CanonicalIntent(scope=TrafficScope(source="h1", destination="h4")),
        graph=graph,
    )
    assert result.request.status == CapabilityStatus.UNSUPPORTED
    assert not result.capability_ready


def test_selectors_are_rejected_before_any_execution_is_considered(graph):
    intent = CanonicalIntent(
        scope=TrafficScope(
            source="h1",
            destination="h4",
            selector=TrafficSelector(protocol="tcp", destination_port=443),
        )
    )
    result = resolve_capabilities(intent, graph=graph)
    assert result.scope.status == CapabilityStatus.UNSUPPORTED
    assert result.eligibility == EligibilityStatus.INELIGIBLE


def test_unknown_capacity_is_conditional_and_known_impossible_target_fails(graph):
    unknown_capacity = graph.model_copy(
        update={
            "links": [
                link.model_copy(update={"bw_mbps": None})
                for link in graph.links
            ]
        }
    )
    target_intent = normalize_intent(
        StructuredIntent(
            objective=Objective.MIN_BANDWIDTH,
            source="h1",
            destination="h4",
            target=Target(bandwidth_mbps=20),
        )
    )
    conditional = resolve_capabilities(target_intent, graph=unknown_capacity)
    assert conditional.topology.status == CapabilityStatus.SUPPORTED
    assert conditional.constraints[0].plannable.status == CapabilityStatus.CONDITIONAL
    assert conditional.eligibility == EligibilityStatus.CONDITIONAL

    low_capacity = graph.model_copy(
        update={
            "links": [
                link.model_copy(update={"bw_mbps": 10})
                for link in graph.links
            ]
        }
    )
    infeasible = resolve_capabilities(target_intent, graph=low_capacity)
    assert infeasible.constraints[0].plannable.status == CapabilityStatus.UNSUPPORTED
    assert infeasible.eligibility == EligibilityStatus.INELIGIBLE


@pytest.mark.parametrize("reverse_links", [False, True])
@pytest.mark.parametrize(
    ("capacities", "expected_status", "expected_eligibility"),
    [
        ((10, 100), CapabilityStatus.SUPPORTED, EligibilityStatus.CAPABILITY_READY),
        ((10, 15), CapabilityStatus.UNSUPPORTED, EligibilityStatus.INELIGIBLE),
    ],
)
def test_parallel_bandwidth_capacity_resolution_is_order_independent(
    reverse_links,
    capacities,
    expected_status,
    expected_eligibility,
):
    graph = _parallel_capacity_graph(capacities)
    if reverse_links:
        graph = graph.model_copy(update={"links": list(reversed(graph.links))})
    intent = normalize_intent(
        StructuredIntent(
            objective=Objective.MIN_BANDWIDTH,
            source="h1",
            destination="h4",
            target=Target(bandwidth_mbps=20),
        )
    )

    results = [
        resolve_capabilities(intent, graph=graph)
        for _ in range(2)
    ]

    assert all(
        result.constraints[0].plannable.status == expected_status
        and result.eligibility == expected_eligibility
        for result in results
    )
    assert results[0] == results[1]


def test_parallel_bandwidth_with_missing_capacity_remains_conditional():
    graph = _parallel_capacity_graph((10, None))
    intent = normalize_intent(
        StructuredIntent(
            objective=Objective.MIN_BANDWIDTH,
            source="h1",
            destination="h4",
            target=Target(bandwidth_mbps=20),
        )
    )

    result = resolve_capabilities(intent, graph=graph)

    assert result.constraints[0].plannable.status == CapabilityStatus.CONDITIONAL
    assert result.eligibility == EligibilityStatus.CONDITIONAL


@pytest.mark.parametrize("reverse_links", [False, True])
def test_sufficient_parallel_capacity_with_unknown_link_stays_conditional(
    reverse_links,
):
    graph = _parallel_capacity_graph((100, None))
    if reverse_links:
        graph = graph.model_copy(update={"links": list(reversed(graph.links))})
    intent = normalize_intent(
        StructuredIntent(
            objective=Objective.MIN_BANDWIDTH,
            source="h1",
            destination="h4",
            target=Target(bandwidth_mbps=20),
        )
    )

    result = resolve_capabilities(intent, graph=graph)

    assert result.constraints[0].plannable.status == CapabilityStatus.CONDITIONAL
    assert result.eligibility == EligibilityStatus.CONDITIONAL


@pytest.mark.parametrize(
    ("capacities", "expected_validation"),
    [
        ((10, 100), CapabilityStatus.SUPPORTED),
        ((10, 15), CapabilityStatus.UNSUPPORTED),
        ((10, None), CapabilityStatus.CONDITIONAL),
    ],
)
def test_rate_limit_capability_checks_each_parallel_physical_egress(
    capacities,
    expected_validation,
):
    result = resolve_capabilities(
        canonical(
            requested_actions=[
                RequestedAction(
                    name="rate_limit",
                    parameters={"rate_mbps": 20},
                )
            ]
        ),
        graph=_parallel_capacity_graph(capacities),
    )

    assert result.actions[0].validated.status == expected_validation


def test_resolver_has_no_deployment_or_measurement_side_effects(
    graph,
    monkeypatch,
):
    from backend.deployment import ofctl_client, ovs_qos_client
    from backend.measurement import latency, throughput

    monkeypatch.setattr(
        ofctl_client,
        "add_flow",
        lambda *args, **kwargs: pytest.fail("flow deployment called"),
    )
    monkeypatch.setattr(
        ovs_qos_client,
        "deploy_queue",
        lambda *args, **kwargs: pytest.fail("QoS deployment called"),
    )
    monkeypatch.setattr(
        latency,
        "measure_latency",
        lambda *args, **kwargs: pytest.fail("ping measurement called"),
    )
    monkeypatch.setattr(
        throughput,
        "measure_throughput",
        lambda *args, **kwargs: pytest.fail("iperf3 measurement called"),
    )

    result = resolve_capabilities(
        normalize_intent(
            StructuredIntent(
                objective=Objective.MINIMIZE_LATENCY,
                source="h1",
                destination="h4",
            )
        ),
        graph=graph,
    )
    assert result.capability_ready
