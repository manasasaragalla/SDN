"""Versioned, declarative network intent independent of legacy execution.

Canonical intents describe requirements only. They do not identify an
executable strategy or imply that a metric or action is supported.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.models.metric_definitions import get_metric_definition

_IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_.-]{0,63}$"
_UNIT_PATTERN = r"^[A-Za-z%][A-Za-z0-9%/._-]{0,31}$"
_FiniteNumber = Annotated[float, Field(allow_inf_nan=False)]


class Comparison(str, Enum):
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    EQ = "EQ"
    BETWEEN = "BETWEEN"


class OptimizationDirection(str, Enum):
    MINIMIZE = "MINIMIZE"
    MAXIMIZE = "MAXIMIZE"


class _CanonicalModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class TrafficSelector(_CanonicalModel):
    """Declarative packet selectors; support is determined elsewhere."""

    protocol: str | None = Field(
        default=None,
        min_length=1,
        max_length=32,
        pattern=_IDENTIFIER_PATTERN,
    )
    source_port: int | None = Field(default=None, ge=1, le=65535)
    destination_port: int | None = Field(default=None, ge=1, le=65535)

    @field_validator("protocol", mode="before")
    @classmethod
    def normalize_protocol(cls, value: object) -> object:
        return value.lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_ports(self) -> "TrafficSelector":
        has_port = self.source_port is not None or self.destination_port is not None
        if has_port and self.protocol is None:
            raise ValueError("A port selector requires an explicit protocol")
        if has_port and self.protocol == "icmp":
            raise ValueError("ICMP selectors cannot include transport ports")
        return self


class TrafficScope(_CanonicalModel):
    source: str = Field(min_length=1, max_length=32)
    destination: str = Field(min_length=1, max_length=32)
    selector: TrafficSelector | None = None

    @model_validator(mode="after")
    def validate_endpoints(self) -> "TrafficScope":
        if self.source == self.destination:
            raise ValueError("source and destination must differ")
        return self


class MetricConstraint(_CanonicalModel):
    """One declarative metric comparison.

    Scalar comparisons use `value`; BETWEEN uses inclusive `lower_bound`
    and `upper_bound`. Tolerance, when supplied, is absolute in `unit`.
    """

    metric: str = Field(min_length=1, max_length=64, pattern=_IDENTIFIER_PATTERN)
    comparison: Comparison
    unit: str = Field(min_length=1, max_length=32, pattern=_UNIT_PATTERN)
    value: _FiniteNumber | None = None
    lower_bound: _FiniteNumber | None = None
    upper_bound: _FiniteNumber | None = None
    tolerance: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None

    @model_validator(mode="after")
    def validate_shape_and_unit(self) -> "MetricConstraint":
        definition = get_metric_definition(self.metric)
        if definition is not None and self.unit != definition.canonical_unit:
            raise ValueError(
                f"Metric {self.metric!r} requires unit "
                f"{definition.canonical_unit!r}"
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
        return self


class OptimizationObjective(_CanonicalModel):
    metric: str = Field(min_length=1, max_length=64, pattern=_IDENTIFIER_PATTERN)
    direction: OptimizationDirection
    unit: str = Field(min_length=1, max_length=32, pattern=_UNIT_PATTERN)

    @model_validator(mode="after")
    def validate_unit(self) -> "OptimizationObjective":
        definition = get_metric_definition(self.metric)
        if definition is not None and self.unit != definition.canonical_unit:
            raise ValueError(
                f"Metric {self.metric!r} requires unit "
                f"{definition.canonical_unit!r}"
            )
        return self


class RequestedAction(_CanonicalModel):
    """User-requested action data, not a resolved execution handler."""

    name: str = Field(min_length=1, max_length=64, pattern=_IDENTIFIER_PATTERN)
    parameters: dict[
        str,
        str | int | float | bool | None,
    ] = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def validate_finite_parameters(
        cls,
        parameters: dict[str, str | int | float | bool | None],
    ) -> dict[str, str | int | float | bool | None]:
        for name, value in parameters.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(
                    f"Action parameter {name!r} must be finite"
                )
        return parameters


class LegacyMetadata(_CanonicalModel):
    """Legacy information retained without assigning new semantics."""

    loss_tolerance: str | None = Field(
        default=None,
        min_length=1,
        max_length=32,
        pattern=r"^[A-Z][A-Z0-9_]*$",
    )


class CanonicalIntent(_CanonicalModel):
    schema_version: Literal[1] = 1
    scope: TrafficScope
    constraints: list[MetricConstraint] = Field(default_factory=list)
    optimization: OptimizationObjective | None = None
    requested_actions: list[RequestedAction] = Field(default_factory=list)
    legacy_metadata: LegacyMetadata | None = None

    @model_validator(mode="after")
    def validate_constraint_consistency(self) -> "CanonicalIntent":
        units_by_metric: dict[str, str] = {}
        bounds: dict[str, list[tuple[str, float, bool]]] = {}
        for constraint in self.constraints:
            existing_unit = units_by_metric.setdefault(
                constraint.metric,
                constraint.unit,
            )
            if existing_unit != constraint.unit:
                raise ValueError(
                    f"Constraints for metric {constraint.metric!r} must use "
                    f"the same unit; found {existing_unit!r} and "
                    f"{constraint.unit!r}"
                )

            entries = bounds.setdefault(constraint.metric, [])

            if constraint.comparison == Comparison.GT:
                entries.append(("lower", constraint.value, False))
            elif constraint.comparison == Comparison.GTE:
                entries.append(("lower", constraint.value, True))
            elif constraint.comparison == Comparison.LT:
                entries.append(("upper", constraint.value, False))
            elif constraint.comparison == Comparison.LTE:
                entries.append(("upper", constraint.value, True))
            elif constraint.comparison == Comparison.EQ:
                entries.extend(
                    [
                        ("lower", constraint.value, True),
                        ("upper", constraint.value, True),
                    ]
                )
            else:
                entries.extend(
                    [
                        ("lower", constraint.lower_bound, True),
                        ("upper", constraint.upper_bound, True),
                    ]
                )

        for metric, entries in bounds.items():
            lower = max(
                (entry for entry in entries if entry[0] == "lower"),
                key=lambda entry: entry[1],
                default=None,
            )
            upper = min(
                (entry for entry in entries if entry[0] == "upper"),
                key=lambda entry: entry[1],
                default=None,
            )
            if lower is None or upper is None:
                continue
            if lower[1] > upper[1] or (
                lower[1] == upper[1]
                and not (lower[2] and upper[2])
            ):
                raise ValueError(
                    f"Constraints for metric {metric!r} in unit "
                    f"{units_by_metric[metric]!r} have an empty intersection"
                )
        return self
