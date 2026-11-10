import pytest
from pydantic import ValidationError

from backend.models.canonical_intent import Comparison, OptimizationDirection
from backend.models.intent import (
    Action,
    Constraints,
    LossTolerance,
    Metric,
    MetricConstraint,
    MetricUnit,
    Objective,
    StructuredIntent,
    Target,
)
from backend.models.intent_normalization import (
    LegacyExecutionHint,
    normalize_intent,
)


def test_normalize_legacy_latency_to_optimization_hint():
    legacy = StructuredIntent(
        objective=Objective.MINIMIZE_LATENCY,
        source="h1",
        destination="h4",
    )

    result = normalize_intent(legacy)

    assert result.canonical.scope.source == "h1"
    assert result.canonical.scope.destination == "h4"
    assert result.canonical.optimization.metric == "latency"
    assert result.canonical.optimization.direction == OptimizationDirection.MINIMIZE
    assert result.canonical.optimization.unit == "ms"
    assert result.canonical.constraints == []
    assert result.legacy_execution_hint == LegacyExecutionHint.MINIMIZE_LATENCY


def test_normalize_legacy_bandwidth_to_gte_and_preserve_target():
    legacy = StructuredIntent(
        objective=Objective.MIN_BANDWIDTH,
        source="h1",
        destination="h4",
        target=Target(bandwidth_mbps=20),
    )

    result = normalize_intent(legacy)

    assert result.canonical.scope.source == legacy.source
    assert result.canonical.scope.destination == legacy.destination
    assert result.canonical.constraints[0].metric == "bandwidth"
    assert result.canonical.constraints[0].comparison == Comparison.GTE
    assert result.canonical.constraints[0].value == legacy.target.bandwidth_mbps
    assert result.canonical.constraints[0].unit == "Mbps"
    assert result.legacy_execution_hint == LegacyExecutionHint.MIN_BANDWIDTH


def test_normalize_canonical_maximize_bandwidth_objective():
    intent = StructuredIntent(
        objective=Objective.MAXIMIZE_BANDWIDTH,
        source="h1",
        destination="h4",
    )

    result = normalize_intent(intent)

    assert result.canonical.optimization.metric == "bandwidth"
    assert result.canonical.optimization.direction == OptimizationDirection.MAXIMIZE
    assert result.canonical.optimization.unit == "Mbps"
    assert result.canonical.constraints == []
    assert result.legacy_execution_hint is None


def test_loss_tolerance_is_preserved_as_metadata_not_packet_loss():
    legacy = StructuredIntent(
        objective=Objective.MINIMIZE_LATENCY,
        source="h1",
        destination="h4",
        constraints=Constraints(loss_tolerance=LossTolerance.HIGH),
    )

    result = normalize_intent(legacy)

    assert result.canonical.legacy_metadata.loss_tolerance == "HIGH"
    assert result.canonical.constraints == []


def test_generalized_structured_intent_normalizes_without_execution_hint():
    legacy = StructuredIntent(
        source="h1",
        destination="h4",
        constraints=Constraints(
            metrics=[
                MetricConstraint(
                    metric=Metric.BANDWIDTH,
                    unit=MetricUnit.MBPS,
                    min_value=10,
                    max_value=20,
                ),
                MetricConstraint(
                    metric=Metric.LATENCY,
                    unit=MetricUnit.MS,
                    optimization="MINIMIZE",
                ),
            ]
        ),
    )

    result = normalize_intent(legacy)

    assert result.canonical.constraints[0].comparison == Comparison.BETWEEN
    assert result.canonical.optimization.metric == "latency"
    assert result.legacy_execution_hint is None


@pytest.mark.parametrize(
    ("comparison", "value", "lower_bound", "upper_bound"),
    [
        (Comparison.EQ, 50, None, None),
        (Comparison.BETWEEN, None, 10, 50),
    ],
)
def test_explicit_comparison_fields_normalize_without_losing_operator(
    comparison, value, lower_bound, upper_bound
):
    intent = StructuredIntent(
        source="h1",
        destination="h4",
        constraints=Constraints(
            metrics=[
                MetricConstraint(
                    metric=Metric.LATENCY,
                    unit=MetricUnit.MS,
                    comparison=comparison,
                    value=value,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                )
            ]
        ),
    )

    canonical = normalize_intent(intent).canonical.constraints[0]
    assert canonical.comparison == comparison
    assert canonical.value == value
    assert canonical.lower_bound == lower_bound
    assert canonical.upper_bound == upper_bound


def test_reject_multiple_legacy_optimization_objectives():
    legacy = StructuredIntent(
        source="h1",
        destination="h4",
        constraints=Constraints(
            metrics=[
                MetricConstraint(
                    metric=Metric.LATENCY,
                    unit=MetricUnit.MS,
                    optimization="MINIMIZE",
                ),
                MetricConstraint(
                    metric=Metric.BANDWIDTH,
                    unit=MetricUnit.MBPS,
                    optimization="MAXIMIZE",
                ),
            ]
        ),
    )

    with pytest.raises(ValueError, match="one optimization objective"):
        normalize_intent(legacy)


def test_normalizer_converts_legacy_objective_and_generalized_constraint():
    legacy = StructuredIntent(
        objective=Objective.MINIMIZE_LATENCY,
        source="h1",
        destination="h4",
    ).model_copy(
        update={
            "constraints": Constraints(
                metrics=[
                    MetricConstraint(
                        metric=Metric.BANDWIDTH,
                        unit=MetricUnit.MBPS,
                        min_value=10,
                    )
                ]
            )
        }
    )

    canonical = normalize_intent(legacy).canonical
    assert canonical.optimization.metric == "latency"
    assert len(canonical.constraints) == 1
    assert canonical.constraints[0].metric == "bandwidth"
    assert canonical.constraints[0].comparison == Comparison.GTE
    assert canonical.constraints[0].value == 10


def test_normalizer_rejects_conflicting_objectives():
    legacy = StructuredIntent(
        objective=Objective.MINIMIZE_LATENCY,
        source="h1",
        destination="h4",
        constraints=Constraints(
            metrics=[
                MetricConstraint(
                    metric=Metric.BANDWIDTH,
                    unit=MetricUnit.MBPS,
                    optimization="MAXIMIZE",
                )
            ]
        ),
    )
    with pytest.raises(ValueError, match="conflicting objectives"):
        normalize_intent(legacy)


def test_reject_legacy_target_with_non_bandwidth_or_generalized_intent():
    with pytest.raises(ValidationError, match="cannot be combined"):
        StructuredIntent(
            objective=Objective.MINIMIZE_LATENCY,
            source="h1",
            destination="h4",
            target=Target(bandwidth_mbps=10),
        )
    with pytest.raises(ValidationError, match="cannot be combined"):
        StructuredIntent(
            source="h1",
            destination="h4",
            target=Target(bandwidth_mbps=10),
            constraints=Constraints(
                metrics=[
                    MetricConstraint(
                        metric=Metric.LATENCY,
                        unit=MetricUnit.MS,
                        max_value=20,
                    )
                ]
            ),
        )


def test_resolved_action_is_not_mistaken_for_a_requested_action():
    legacy = StructuredIntent(
        objective=Objective.MINIMIZE_LATENCY,
        source="h1",
        destination="h4",
        action=Action.REROUTE,
    )

    with pytest.raises(ValueError, match="normalize the request before"):
        normalize_intent(legacy)
