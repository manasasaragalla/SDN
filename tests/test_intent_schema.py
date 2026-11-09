"""Phase 3 tests: structured intent schema, no network involved."""
import pytest
from pydantic import ValidationError

from backend.models.intent import (
    Constraints,
    LossTolerance,
    Objective,
    StructuredIntent,
    Target,
)


def test_minimize_latency_minimal():
    intent = StructuredIntent(objective=Objective.MINIMIZE_LATENCY, source="h1", destination="h4")
    assert intent.objective == Objective.MINIMIZE_LATENCY
    assert intent.target is None


def test_minimize_latency_with_loss_tolerance():
    intent = StructuredIntent(
        objective=Objective.MINIMIZE_LATENCY,
        source="h1",
        destination="h4",
        constraints=Constraints(loss_tolerance=LossTolerance.HIGH),
    )
    assert intent.constraints.loss_tolerance == LossTolerance.HIGH


def test_min_bandwidth_requires_target():
    with pytest.raises(ValidationError):
        StructuredIntent(objective=Objective.MIN_BANDWIDTH, source="h1", destination="h4")


def test_min_bandwidth_with_target():
    intent = StructuredIntent(
        objective=Objective.MIN_BANDWIDTH,
        source="h1",
        destination="h4",
        target=Target(bandwidth_mbps=20),
    )
    assert intent.target.bandwidth_mbps == 20


def test_source_destination_must_differ():
    with pytest.raises(ValidationError):
        StructuredIntent(objective=Objective.MINIMIZE_LATENCY, source="h1", destination="h1")


def test_unsupported_objective_rejected():
    with pytest.raises(ValidationError):
        StructuredIntent(objective="OPTIMIZE_ENERGY", source="h1", destination="h4")


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        StructuredIntent(
            objective=Objective.MINIMIZE_LATENCY,
            source="h1",
            destination="h4",
            made_up_field="anything",
        )


def test_legacy_objective_can_combine_with_generalized_hard_constraints():
    intent = StructuredIntent(
        objective=Objective.MINIMIZE_LATENCY,
        source="h1",
        destination="h4",
        constraints={
            "metrics": [
                {
                    "metric": "BANDWIDTH",
                    "unit": "Mbps",
                    "min_value": 10,
                }
            ]
        },
    )

    assert intent.objective == Objective.MINIMIZE_LATENCY
    assert intent.constraints.metrics[0].metric.value == "BANDWIDTH"


def test_legacy_objective_can_still_use_legacy_loss_tolerance():
    intent = StructuredIntent(
        objective=Objective.MINIMIZE_LATENCY,
        source="h1",
        destination="h4",
        constraints=Constraints(loss_tolerance=LossTolerance.HIGH),
    )

    assert intent.constraints.loss_tolerance == LossTolerance.HIGH


def test_bandwidth_target_range_enforced():
    with pytest.raises(ValidationError):
        Target(bandwidth_mbps=-5)
    with pytest.raises(ValidationError):
        Target(bandwidth_mbps=5000)
