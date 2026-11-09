"""Pure adapters from the existing intent model to canonical intent."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.models.canonical_intent import (
    CanonicalIntent,
    Comparison,
    MetricConstraint as CanonicalMetricConstraint,
    OptimizationDirection,
    OptimizationObjective,
    LegacyMetadata,
    TrafficScope,
    TrafficSelector as CanonicalTrafficSelector,
)
from backend.models.intent import Objective, StructuredIntent


class LegacyExecutionHint(str, Enum):
    """Identifies an existing pipeline; it is not a new execution choice."""

    MINIMIZE_LATENCY = "MINIMIZE_LATENCY"
    MIN_BANDWIDTH = "MIN_BANDWIDTH"


@dataclass(frozen=True)
class NormalizedIntent:
    canonical: CanonicalIntent
    legacy_execution_hint: LegacyExecutionHint | None = None


def _legacy_metadata(intent: StructuredIntent) -> LegacyMetadata | None:
    tolerance = (
        intent.constraints.loss_tolerance
        if intent.constraints is not None
        else None
    )
    if tolerance is None:
        return None
    return LegacyMetadata(loss_tolerance=tolerance.value)


def _legacy_metric_constraint(item) -> tuple[
    CanonicalMetricConstraint | None,
    OptimizationObjective | None,
]:
    metric = item.metric.value.lower()
    unit = item.unit.value

    if item.comparison is not None:
        constraint = CanonicalMetricConstraint(
            metric=metric,
            comparison=item.comparison,
            unit=unit,
            value=item.value,
            lower_bound=item.lower_bound,
            upper_bound=item.upper_bound,
        )
        return constraint, None

    if item.optimization is not None:
        direction = OptimizationDirection(item.optimization.value)
        return None, OptimizationObjective(
            metric=metric,
            direction=direction,
            unit=unit,
        )

    if item.min_value is not None and item.max_value is not None:
        if item.min_value == item.max_value:
            constraint = CanonicalMetricConstraint(
                metric=metric,
                comparison=Comparison.EQ,
                value=item.min_value,
                unit=unit,
            )
        else:
            constraint = CanonicalMetricConstraint(
                metric=metric,
                comparison=Comparison.BETWEEN,
                lower_bound=item.min_value,
                upper_bound=item.max_value,
                unit=unit,
            )
    elif item.min_value is not None:
        constraint = CanonicalMetricConstraint(
            metric=metric,
            comparison=Comparison.GTE,
            value=item.min_value,
            unit=unit,
        )
    elif item.max_value is not None:
        constraint = CanonicalMetricConstraint(
            metric=metric,
            comparison=Comparison.LTE,
            value=item.max_value,
            unit=unit,
        )
    else:
        raise ValueError(
            f"Metric constraint {metric!r} has no bounds or optimization"
        )
    return constraint, None


def normalize_intent(intent: StructuredIntent) -> NormalizedIntent:
    """Normalize a validated legacy/generalized intent without mutation.

    Legacy intents receive a compatibility hint so existing callers can
    continue selecting their current pipeline. A hint does not imply a
    generalized capability or alter the original StructuredIntent.
    """

    if intent.action is not None:
        raise ValueError(
            "Cannot normalize an intent with a resolved legacy action; "
            "normalize the request before decision-making"
        )

    metrics = (
        intent.constraints.metrics
        if intent.constraints is not None
        else []
    )

    hint: LegacyExecutionHint | None = None
    canonical_constraints: list[CanonicalMetricConstraint] = []
    optimization: OptimizationObjective | None = None

    if intent.objective == Objective.MINIMIZE_LATENCY:
        if intent.target is not None:
            raise ValueError(
                "MINIMIZE_LATENCY cannot be combined with a legacy target"
            )
        hint = LegacyExecutionHint.MINIMIZE_LATENCY
        optimization = OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        )
    elif intent.objective == Objective.MIN_BANDWIDTH:
        if intent.target is None or intent.target.bandwidth_mbps is None:
            raise ValueError(
                "MIN_BANDWIDTH requires target.bandwidth_mbps"
            )
        hint = LegacyExecutionHint.MIN_BANDWIDTH
        canonical_constraints.append(
            CanonicalMetricConstraint(
                metric="bandwidth",
                comparison=Comparison.GTE,
                value=intent.target.bandwidth_mbps,
                unit="Mbps",
            )
        )
    elif intent.objective is not None:
        raise ValueError(
            f"Unsupported legacy objective: {intent.objective!r}"
        )
    elif intent.objective is None and intent.target is not None:
        raise ValueError(
            "A legacy target cannot be combined with a generalized intent"
        )

    for item in metrics:
        constraint, candidate_optimization = _legacy_metric_constraint(item)
        if constraint is not None:
            canonical_constraints.append(constraint)
        if candidate_optimization is not None:
            if optimization is not None and optimization != candidate_optimization:
                raise ValueError(
                    "Canonical intents support one optimization objective; "
                    "conflicting objectives are ambiguous"
                )
            optimization = candidate_optimization

    selector = None
    if intent.traffic_selector is not None:
        selector = CanonicalTrafficSelector(
            protocol=intent.traffic_selector.protocol,
            destination_port=intent.traffic_selector.dst_port,
        )

    canonical = CanonicalIntent(
        scope=TrafficScope(
            source=intent.source,
            destination=intent.destination,
            selector=selector,
        ),
        constraints=canonical_constraints,
        optimization=optimization,
        legacy_metadata=_legacy_metadata(intent),
    )
    return NormalizedIntent(
        canonical=canonical,
        legacy_execution_hint=hint,
    )
