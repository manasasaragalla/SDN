import math

import pytest
from pydantic import ValidationError

from backend.models.canonical_intent import (
    CanonicalIntent,
    Comparison,
    MetricConstraint,
    OptimizationDirection,
    OptimizationObjective,
    RequestedAction,
    TrafficScope,
    TrafficSelector,
)


def test_canonical_intent_constructs_and_serializes_versioned_shape():
    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        constraints=[
            MetricConstraint(
                metric="bandwidth",
                comparison="GTE",
                value=20,
                unit="Mbps",
            )
        ],
    )

    data = intent.model_dump(mode="json")
    assert data["schema_version"] == 1
    assert data["scope"] == {
        "source": "h1",
        "destination": "h4",
        "selector": None,
    }
    assert data["constraints"][0] == {
        "metric": "bandwidth",
        "comparison": "GTE",
        "unit": "Mbps",
        "value": 20.0,
        "lower_bound": None,
        "upper_bound": None,
        "tolerance": None,
    }


def test_multiple_constraints_and_independent_optimization_are_supported():
    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
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
    )

    assert len(intent.constraints) == 2
    assert intent.optimization.metric == "latency"


def test_unknown_metric_and_action_are_declarative_not_executable():
    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        constraints=[
            MetricConstraint(
                metric="vendor_metric",
                comparison="GTE",
                value=2,
                unit="widgets/s",
            )
        ],
        requested_actions=[
            RequestedAction(
                name="vendor_action",
                parameters={"mode": "careful"},
            )
        ],
    )

    assert intent.constraints[0].metric == "vendor_metric"
    assert intent.requested_actions[0].name == "vendor_action"
    assert not hasattr(intent.constraints[0], "executable")
    assert not hasattr(intent.requested_actions[0], "executable")


@pytest.mark.parametrize(
    ("lower", "upper"),
    [(20, 30), (20, 20)],
)
def test_between_bounds_accept_valid_ranges(lower, upper):
    constraint = MetricConstraint(
        metric="bandwidth",
        comparison="BETWEEN",
        lower_bound=lower,
        upper_bound=upper,
        unit="Mbps",
    )
    assert constraint.lower_bound == lower
    assert constraint.upper_bound == upper


@pytest.mark.parametrize(
    "constraints",
    [
        [
            {"metric": "bandwidth", "comparison": "GTE", "value": 30, "unit": "Mbps"},
            {"metric": "bandwidth", "comparison": "LTE", "value": 20, "unit": "Mbps"},
        ],
        [
            {"metric": "latency", "comparison": "GT", "value": 10, "unit": "ms"},
            {"metric": "latency", "comparison": "LTE", "value": 10, "unit": "ms"},
        ],
    ],
)
def test_reject_contradictory_constraint_intersections(constraints):
    with pytest.raises(ValidationError, match="empty intersection"):
        CanonicalIntent(
            scope=TrafficScope(source="h1", destination="h4"),
            constraints=constraints,
        )


def test_valid_overlapping_constraints_are_allowed():
    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        constraints=[
            {"metric": "bandwidth", "comparison": "GTE", "value": 20, "unit": "Mbps"},
            {"metric": "bandwidth", "comparison": "LTE", "value": 30, "unit": "Mbps"},
        ],
    )
    assert len(intent.constraints) == 2


def test_same_metric_same_unit_consistent_bounds_are_accepted():
    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        constraints=[
            {
                "metric": "vendor_metric",
                "comparison": "GTE",
                "value": 20,
                "unit": "widgets/s",
            },
            {
                "metric": "vendor_metric",
                "comparison": "LTE",
                "value": 30,
                "unit": "widgets/s",
            },
        ],
    )

    assert len(intent.constraints) == 2


def test_same_metric_different_units_are_rejected():
    with pytest.raises(ValidationError, match="must use the same unit"):
        CanonicalIntent(
            scope=TrafficScope(source="h1", destination="h4"),
            constraints=[
                {
                    "metric": "vendor_metric",
                    "comparison": "GTE",
                    "value": 30,
                    "unit": "widgets/s",
                },
                {
                    "metric": "vendor_metric",
                    "comparison": "LTE",
                    "value": 20,
                    "unit": "widgets/min",
                },
            ],
        )


def test_different_metrics_may_use_different_units():
    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        constraints=[
            {
                "metric": "vendor_metric_a",
                "comparison": "GTE",
                "value": 10,
                "unit": "widgets/s",
            },
            {
                "metric": "vendor_metric_b",
                "comparison": "LTE",
                "value": 5,
                "unit": "widgets/min",
            },
        ],
    )

    assert len(intent.constraints) == 2


def test_known_metric_rejects_invalid_unit():
    with pytest.raises(ValidationError, match="requires unit"):
        MetricConstraint(
            metric="latency",
            comparison="LTE",
            value=30,
            unit="Mbps",
        )


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        MetricConstraint(
            metric="latency",
            comparison="LTE",
            value=30,
            unit="ms",
            command="delete all flows",
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"metric": "latency", "comparison": "APPROX", "value": 5, "unit": "ms"},
        {"metric": "latency", "comparison": "BETWEEN", "value": 5, "unit": "ms"},
        {"metric": "latency", "comparison": "LTE", "unit": "ms"},
        {
            "metric": "latency",
            "comparison": "GTE",
            "value": 5,
            "lower_bound": 2,
            "unit": "ms",
        },
    ],
)
def test_malformed_comparison_shapes_are_rejected(payload):
    with pytest.raises(ValidationError):
        MetricConstraint.model_validate(payload)


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_non_finite_constraint_values_are_rejected(value):
    with pytest.raises(ValidationError):
        MetricConstraint(
            metric="latency",
            comparison="LTE",
            value=value,
            unit="ms",
        )


def test_non_finite_action_parameter_is_rejected():
    with pytest.raises(ValidationError, match="must be finite"):
        RequestedAction(
            name="rate_limit",
            parameters={"rate": math.inf},
        )


def test_reversed_between_range_is_rejected():
    with pytest.raises(ValidationError, match="cannot exceed"):
        MetricConstraint(
            metric="bandwidth",
            comparison="BETWEEN",
            lower_bound=50,
            upper_bound=20,
            unit="Mbps",
        )


def test_protocol_and_port_selector_are_validated():
    selector = TrafficSelector(protocol="TCP", destination_port=443)
    assert selector.protocol == "tcp"

    with pytest.raises(ValidationError, match="requires an explicit protocol"):
        TrafficSelector(destination_port=443)
    with pytest.raises(ValidationError, match="cannot include transport ports"):
        TrafficSelector(protocol="icmp", destination_port=8)


def test_canonical_structure_rejects_same_endpoints_and_unknown_version():
    with pytest.raises(ValidationError, match="must differ"):
        TrafficScope(source="h1", destination="h1")
    with pytest.raises(ValidationError):
        CanonicalIntent(
            schema_version=2,
            scope={"source": "h1", "destination": "h4"},
        )
