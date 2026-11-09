
"""LLM-facing structured output schema.

The LLM can describe network intent, but cannot populate internal
execution decisions or generate network configurations.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models.intent import (
    Constraints,
    Objective,
    StructuredIntent,
    Target,
    TrafficSelector,
)
from backend.llm.base import LLMClarificationRequiredError


class LLMIntentOutput(BaseModel):
    """Fields the LLM is permitted to produce."""

    model_config = ConfigDict(extra="forbid")

    objective: Optional[Objective] = None

    source: str = Field(min_length=1, max_length=32)
    destination: str = Field(min_length=1, max_length=32)

    traffic_selector: Optional[TrafficSelector] = None
    target: Optional[Target] = None
    constraints: Optional[Constraints] = None
    clarification_required: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
    )

    @model_validator(mode="after")
    def validate_output(self) -> "LLMIntentOutput":
        if self.source == self.destination:
            raise ValueError("source and destination must differ")

        if self.clarification_required is not None:
            if self.objective is not None or self.target is not None or (
                self.constraints is not None
                and (
                    self.constraints.metrics
                    or self.constraints.loss_tolerance is not None
                )
            ):
                raise ValueError(
                    "A clarification response cannot also contain a network intent"
                )
            return self

        has_metrics = (
            self.constraints is not None
            and bool(self.constraints.metrics)
        )

        if self.objective is None and not has_metrics:
            raise ValueError(
                "Output must contain an objective or metric constraints"
            )

        if self.objective == Objective.MIN_BANDWIDTH:
            if (
                self.target is None
                or self.target.bandwidth_mbps is None
            ):
                raise ValueError(
                    "MIN_BANDWIDTH requires target.bandwidth_mbps"
                )
        elif self.target is not None:
            raise ValueError("target cannot be combined with an objective other than MIN_BANDWIDTH")

        return self

    def to_structured_intent(self) -> StructuredIntent:
        if self.clarification_required is not None:
            raise LLMClarificationRequiredError(self.clarification_required)
        return StructuredIntent.model_validate(
            self.model_dump(exclude={"clarification_required"})
        )
