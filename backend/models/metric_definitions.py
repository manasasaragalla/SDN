"""Canonical metric metadata shared by intent validation and resolution.

Units are canonical labels only. This module deliberately performs no unit
conversion and says nothing about whether a metric can be measured or enforced.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class MetricDefinition:
    identifier: str
    canonical_unit: str
    minimum: float | None = None
    maximum: float | None = None
    unit_semantics: str = "Values must use the canonical unit; conversion is unsupported."

    def validate_value(self, value: float) -> str | None:
        if self.minimum is not None and value < self.minimum:
            return f"must be at least {self.minimum:g}"
        if self.maximum is not None and value > self.maximum:
            return f"must be at most {self.maximum:g}"
        return None


METRIC_DEFINITIONS: Mapping[str, MetricDefinition] = MappingProxyType({
    "latency": MetricDefinition("latency", "ms", minimum=0),
    "bandwidth": MetricDefinition("bandwidth", "Mbps", minimum=0),
    "packet_loss": MetricDefinition("packet_loss", "%", minimum=0, maximum=100),
    "jitter": MetricDefinition("jitter", "ms", minimum=0),
    "availability": MetricDefinition("availability", "%", minimum=0, maximum=100),
})


def get_metric_definition(metric: str) -> MetricDefinition | None:
    """Return a known metric definition without guessing unknown semantics."""

    return METRIC_DEFINITIONS.get(metric)
