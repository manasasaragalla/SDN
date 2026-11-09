
"""Generalized structured network intent schema.

The LLM translates natural-language requests into this schema.
The deterministic network engine validates, plans and executes them.

Supports:
- Legacy latency and bandwidth objectives.
- Multiple network metrics.
- Minimum and maximum thresholds.
- Range constraints.
- Optimization objectives.
- Strict validation of units and values.

The intent schema is not a network configuration.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from backend.models.canonical_intent import Comparison


# ---------------------------------------------------------
# Legacy objectives: retained for existing pipelines
# ---------------------------------------------------------

class Objective(str, Enum):
    MINIMIZE_LATENCY = "MINIMIZE_LATENCY"
    MIN_BANDWIDTH = "MIN_BANDWIDTH"


# ---------------------------------------------------------
# Generalized network metrics
# ---------------------------------------------------------

class Metric(str, Enum):
    LATENCY = "LATENCY"
    BANDWIDTH = "BANDWIDTH"
    PACKET_LOSS = "PACKET_LOSS"
    JITTER = "JITTER"
    AVAILABILITY = "AVAILABILITY"


class Operator(str, Enum):
    """Optimization operators."""

    MINIMIZE = "MINIMIZE"
    MAXIMIZE = "MAXIMIZE"


class MetricUnit(str, Enum):
    MS = "ms"
    MBPS = "Mbps"
    PERCENT = "%"


# ---------------------------------------------------------
# Existing enums
# ---------------------------------------------------------

class LossTolerance(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Action(str, Enum):
    REROUTE = "REROUTE"
    RATE_LIMIT = "RATE_LIMIT"
    PRIORITIZE = "PRIORITIZE"
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


# ---------------------------------------------------------
# Generalized metric constraint
# ---------------------------------------------------------

class MetricConstraint(BaseModel):
    """A threshold, range or optimization requirement.

    New LLM output can preserve an explicit `comparison` and its scalar
    `value` or inclusive `lower_bound`/`upper_bound` fields. The legacy
    `min_value`/`max_value` representation remains accepted.

    Examples:

    Legacy bandwidth at least 30 Mbps:
        min_value=30, max_value=None

    Legacy bandwidth at most 50 Mbps:
        min_value=None, max_value=50

    Legacy bandwidth between 30 and 50 Mbps:
        min_value=30, max_value=50

    Explicit latency below 50 ms:
        comparison=LT, value=50

    Explicit bandwidth between 30 and 50 Mbps:
        comparison=BETWEEN, lower_bound=30, upper_bound=50

    Legacy exact bandwidth of 40 Mbps:
        min_value=40, max_value=40

    Minimize latency:
        optimization=Operator.MINIMIZE

    Maximize bandwidth:
        optimization=Operator.MAXIMIZE
    """

    metric: Metric

    unit: MetricUnit

    comparison: Optional[Comparison] = None

    value: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)

    lower_bound: Optional[float] = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )

    upper_bound: Optional[float] = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )

    min_value: Optional[float] = Field(
        default=None,
        ge=0,
    )

    max_value: Optional[float] = Field(
        default=None,
        ge=0,
    )

    optimization: Optional[Operator] = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_constraint(self) -> "MetricConstraint":

        expected_units = {
            Metric.LATENCY: MetricUnit.MS,
            Metric.BANDWIDTH: MetricUnit.MBPS,
            Metric.PACKET_LOSS: MetricUnit.PERCENT,
            Metric.JITTER: MetricUnit.MS,
            Metric.AVAILABILITY: MetricUnit.PERCENT,
        }

        expected_unit = expected_units[self.metric]

        if self.unit != expected_unit:
            raise ValueError(
                f"{self.metric.value} requires unit "
                f"{expected_unit.value}"
            )

        legacy_bounds = self.min_value is not None or self.max_value is not None
        explicit_bounds = (
            self.value is not None
            or self.lower_bound is not None
            or self.upper_bound is not None
        )
        if self.comparison is not None:
            if self.optimization is not None or legacy_bounds:
                raise ValueError(
                    "Explicit comparisons cannot be combined with legacy bounds or optimization"
                )
            if self.comparison == Comparison.BETWEEN:
                if (
                    self.value is not None
                    or self.lower_bound is None
                    or self.upper_bound is None
                ):
                    raise ValueError(
                        "BETWEEN requires lower_bound and upper_bound only"
                    )
                if self.lower_bound > self.upper_bound:
                    raise ValueError("lower_bound cannot exceed upper_bound")
            elif (
                self.value is None
                or self.lower_bound is not None
                or self.upper_bound is not None
            ):
                raise ValueError(
                    f"{self.comparison.value} requires value only"
                )
            values = (
                (self.lower_bound, self.upper_bound)
                if self.comparison == Comparison.BETWEEN
                else (self.value,)
            )
        else:
            if explicit_bounds:
                raise ValueError(
                    "Explicit comparison values require a comparison operator"
                )
            values = (self.min_value, self.max_value)

        # A constraint must specify bounds or optimization.
        has_bounds = legacy_bounds or explicit_bounds
        if self.optimization is not None and has_bounds:
            raise ValueError(
                "Optimization cannot be combined with min_value "
                "or max_value in the same metric constraint"
            )

        if not has_bounds and self.optimization is None:
            raise ValueError(
                "Specify at least one bound or an optimization operator"
            )

        if (
            self.comparison is None
            and self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise ValueError("min_value cannot be greater than max_value")

        for value in values:
            if value is None:
                continue

            if self.metric in (
                Metric.LATENCY,
                Metric.BANDWIDTH,
                Metric.JITTER,
            ) and value <= 0:
                raise ValueError(
                    f"{self.metric.value} values must be greater than zero"
                )

            # Physical upper bounds.
            if self.metric == Metric.BANDWIDTH and value > 1000:
                raise ValueError(
                    "Bandwidth cannot exceed 1000 Mbps"
                )

            if self.metric in (
                Metric.PACKET_LOSS,
                Metric.AVAILABILITY,
            ) and value > 100:
                raise ValueError(
                    f"{self.metric.value} must be between 0 and 100 percent"
                )

        return self


# ---------------------------------------------------------
# Constraints
# ---------------------------------------------------------

class Constraints(BaseModel):
    """Collection of network requirements."""

    loss_tolerance: Optional[LossTolerance] = None

    metrics: list[MetricConstraint] = Field(
        default_factory=list,
    )

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_unique_metrics(self) -> "Constraints":

        metric_names = [item.metric for item in self.metrics]

        if len(metric_names) != len(set(metric_names)):
            raise ValueError(
                "Each metric can appear only once. "
                "Use min_value and max_value for ranges."
            )

        return self


# ---------------------------------------------------------
# Legacy target
# ---------------------------------------------------------

class Target(BaseModel):
    """Legacy target retained for existing bandwidth pipelines."""

    bandwidth_mbps: Optional[float] = Field(
        default=None,
        gt=0,
        le=1000,
    )

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------
# Traffic selector
# ---------------------------------------------------------

class TrafficSelector(BaseModel):
    """Identifies the traffic affected by a network intent."""

    protocol: Optional[str] = None

    dst_port: Optional[int] = Field(
        default=None,
        ge=1,
        le=65535,
    )

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_protocol(self) -> "TrafficSelector":

        if self.protocol is not None:
            self.protocol = self.protocol.lower()

            if self.protocol not in ("tcp", "udp", "icmp"):
                raise ValueError(
                    "protocol must be tcp, udp, or icmp"
                )

        return self


# ---------------------------------------------------------
# Complete structured intent
# ---------------------------------------------------------

class StructuredIntent(BaseModel):
    """Complete representation of a network intent.

    Legacy objective and target fields remain available for
    compatibility with the existing execution pipelines.

    New intents can use constraints.metrics.
    """

    objective: Optional[Objective] = None

    source: str = Field(
        min_length=1,
        max_length=32,
    )

    destination: str = Field(
        min_length=1,
        max_length=32,
    )

    traffic_selector: Optional[TrafficSelector] = None

    target: Optional[Target] = None

    constraints: Optional[Constraints] = None

    # Set by the deterministic decision layer.
    action: Optional[Action] = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_intent(self) -> "StructuredIntent":

        if self.source == self.destination:
            raise ValueError(
                "source and destination must differ"
            )

        has_metric_constraints = (
            self.constraints is not None
            and bool(self.constraints.metrics)
        )

        if self.objective is None and not has_metric_constraints:
            raise ValueError(
                "Intent must contain an objective or at least "
                "one metric constraint"
            )

        # Preserve the legacy bandwidth pipeline contract.
        if self.objective == Objective.MIN_BANDWIDTH:
            if (
                self.target is None
                or self.target.bandwidth_mbps is None
            ):
                raise ValueError(
                    "MIN_BANDWIDTH objective requires "
                    "target.bandwidth_mbps"
                )
        elif self.target is not None:
            raise ValueError(
                "A legacy target cannot be combined with an objective other than MIN_BANDWIDTH"
            )

        return self
