"""Typed contracts for a future pure generalized planner.

These models describe planning inputs and outputs. They do not enumerate
paths, infer measurements, evaluate constraints, or execute network changes.
"""

from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.capabilities import (
    CapabilityResolution,
    DeploymentStatus,
    EligibilityStatus,
    ExecutionStatus,
    SatisfactionStatus,
)
from backend.models.canonical_intent import (
    CanonicalIntent,
    MetricConstraint,
    OptimizationObjective,
)
from backend.models.fingerprints import model_fingerprint
from backend.models.network import TopologyGraph


class _PlannerModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    @classmethod
    def model_construct(cls, _fields_set=None, **values):
        raise TypeError(
            f"{cls.__name__} requires validated construction; "
            "model_construct() is not supported"
        )

    def __getattribute__(self, name: str):
        if name == "__dict__":
            return deepcopy(super().__getattribute__(name))
        value = super().__getattribute__(name)
        if name in type(self).model_fields and _requires_detached_copy(value):
            return deepcopy(value)
        return value

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> "_PlannerModel":
        if update is not None:
            raise TypeError(
                "Planner models do not support model_copy(update=...); construct and validate a new model instead"
            )
        return super().model_copy(deep=deep)


def _requires_detached_copy(value: Any) -> bool:
    if isinstance(value, _PlannerModel):
        return False
    if isinstance(value, BaseModel):
        return True
    if isinstance(value, (dict, list, set)):
        return True
    if isinstance(value, tuple):
        return any(_requires_detached_copy(item) for item in value)
    return False


def _copy_input_state(value: Any) -> Any:
    return deepcopy(value)


class PlanningReadiness(str, Enum):
    READY = "READY"
    CONDITIONAL = "CONDITIONAL"
    BLOCKED = "BLOCKED"


class CandidateFeasibility(str, Enum):
    """Topology feasibility only; CANDIDATE does not mean constraint-satisfied."""

    CANDIDATE = "CANDIDATE"
    PROVEN_INFEASIBLE = "PROVEN_INFEASIBLE"
    UNKNOWN = "UNKNOWN"


class ConstraintAggregation(str, Enum):
    ALL = "ALL"


class ConstraintEvaluationStatus(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    SATISFIED = "SATISFIED"
    UNSATISFIED = "UNSATISFIED"
    UNKNOWN = "UNKNOWN"


class MetricObservationPurpose(str, Enum):
    HARD_CONSTRAINT = "HARD_CONSTRAINT"
    OPTIMIZATION = "OPTIMIZATION"


class OptimizationStatus(str, Enum):
    NOT_APPLIED = "NOT_APPLIED"


class KnownTopologyFact(_PlannerModel):
    name: str = Field(min_length=1)
    value: str | int | float | bool
    unit: str | None = None
    source: str = Field(min_length=1)


class UnknownTopologyFact(_PlannerModel):
    name: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class PlanningRequest(_PlannerModel):
    """The complete, side-effect-free input contract for generalized planning."""

    intent: CanonicalIntent
    topology: TopologyGraph
    capabilities: CapabilityResolution

    @model_validator(mode="before")
    @classmethod
    def snapshot_input_state(cls, value: Any) -> Any:
        return _copy_input_state(value)

    @model_validator(mode="after")
    def bind_capabilities_to_inputs(self) -> "PlanningRequest":
        self.validate_capability_binding()
        return self

    def validate_capability_binding(self) -> None:
        if self.capabilities.intent_fingerprint != model_fingerprint(self.intent):
            raise ValueError(
                "Capability resolution was produced for a different canonical intent"
            )
        if self.capabilities.topology_fingerprint != model_fingerprint(self.topology):
            raise ValueError(
                "Capability resolution was produced for a different topology"
            )


class HardConstraintRequirement(_PlannerModel):
    """A stable identifier around one canonical hard constraint."""

    requirement_id: str = Field(min_length=1)
    constraint: MetricConstraint

    @model_validator(mode="before")
    @classmethod
    def snapshot_input_state(cls, value: Any) -> Any:
        return _copy_input_state(value)


class RequiredMetricObservation(_PlannerModel):
    """An observation needed later; declaring it does not collect it."""

    observation_id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    purpose: MetricObservationPurpose
    metric: str = Field(min_length=1)
    unit: str = Field(min_length=1)


class CandidateConstraintResult(_PlannerModel):
    """One hard constraint's independent, per-path evaluation state."""

    requirement_id: str = Field(min_length=1)
    status: Literal[ConstraintEvaluationStatus.NOT_EVALUATED]
    reasons: tuple[str, ...] = ()


class CandidatePath(_PlannerModel):
    """A path candidate and the evidence explaining its topology status.

    CANDIDATE means it has not been proven topologically impossible; it does
    not imply any hard constraint has been measured or satisfied.
    """

    path: tuple[str, ...] = Field(min_length=2)
    feasibility: CandidateFeasibility
    reasons: tuple[str, ...] = ()
    known_facts: tuple[KnownTopologyFact, ...] = ()
    unknown_facts: tuple[UnknownTopologyFact, ...] = ()
    constraint_results: tuple[CandidateConstraintResult, ...] = ()

    @model_validator(mode="after")
    def explain_path_disposition(self) -> "CandidatePath":
        if not self.reasons:
            raise ValueError(
                "Every candidate path requires explanatory reasons, including its inclusion rationale"
            )
        return self


class Plan(_PlannerModel):
    """Descriptive plan contract, separate from runtime execution outcomes."""

    request: PlanningRequest
    capability_readiness: EligibilityStatus
    planning_readiness: PlanningReadiness
    execution_status: ExecutionStatus = ExecutionStatus.NOT_DISPATCHED
    deployment_status: DeploymentStatus = DeploymentStatus.NOT_ATTEMPTED
    satisfaction_status: SatisfactionStatus = SatisfactionStatus.NOT_VERIFIED
    hard_constraints: tuple[HardConstraintRequirement, ...] = ()
    constraint_aggregation: ConstraintAggregation = ConstraintAggregation.ALL
    required_observations: tuple[RequiredMetricObservation, ...] = ()
    optimization: OptimizationObjective | None = None
    optimization_status: OptimizationStatus = OptimizationStatus.NOT_APPLIED
    candidates: tuple[CandidatePath, ...] = ()
    reasons: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def snapshot_input_state(cls, value: Any) -> Any:
        return _copy_input_state(value)

    @model_validator(mode="after")
    def preserve_requirements_per_candidate(self) -> "Plan":
        self.request.validate_capability_binding()
        if self.capability_readiness != self.request.capabilities.eligibility:
            raise ValueError(
                "Plan capability readiness must match its originating planning request"
            )
        if (
            self.planning_readiness == PlanningReadiness.READY
            and self.capability_readiness != EligibilityStatus.CAPABILITY_READY
        ):
            raise ValueError(
                "A ready plan requires capability readiness"
            )
        if (
            self.planning_readiness == PlanningReadiness.READY
            and not any(
                candidate.feasibility == CandidateFeasibility.CANDIDATE
                for candidate in self.candidates
            )
        ):
            raise ValueError(
                "A ready plan requires at least one candidate path"
            )
        if (
            self.planning_readiness == PlanningReadiness.READY
            and any(
                candidate.feasibility == CandidateFeasibility.UNKNOWN
                for candidate in self.candidates
            )
        ):
            raise ValueError(
                "A ready plan cannot classify a candidate's topology feasibility as unknown"
            )

        constraint_ids = [
            requirement.requirement_id
            for requirement in self.hard_constraints
        ]
        if len(set(constraint_ids)) != len(constraint_ids):
            raise ValueError("Hard constraint requirement IDs must be unique")
        planned_constraints = [
            requirement.constraint.model_dump(mode="json")
            for requirement in self.hard_constraints
        ]
        original_constraints = [
            constraint.model_dump(mode="json")
            for constraint in self.request.intent.constraints
        ]
        if planned_constraints != original_constraints:
            raise ValueError(
                "Plan hard constraints must exactly preserve the originating intent constraints in order"
            )
        if self.optimization != self.request.intent.optimization:
            raise ValueError(
                "Plan optimization must match its originating planning request"
            )

        constraint_observations = [
            observation
            for observation in self.required_observations
            if observation.purpose == MetricObservationPurpose.HARD_CONSTRAINT
        ]
        if (
            len(constraint_observations) != len(constraint_ids)
            or {observation.requirement_id for observation in constraint_observations}
            != set(constraint_ids)
        ):
            raise ValueError(
                "Each hard constraint must have exactly one required observation"
            )
        constraints_by_id = {
            requirement.requirement_id: requirement.constraint
            for requirement in self.hard_constraints
        }
        for observation in constraint_observations:
            constraint = constraints_by_id[observation.requirement_id]
            if (
                observation.metric != constraint.metric
                or observation.unit != constraint.unit
            ):
                raise ValueError(
                    "Hard constraint observations must match their metric and unit"
                )

        objective_observations = [
            observation
            for observation in self.required_observations
            if observation.purpose == MetricObservationPurpose.OPTIMIZATION
        ]
        if self.optimization is None and objective_observations:
            raise ValueError(
                "Optimization observations require an optimization objective"
            )
        if self.optimization is not None and len(objective_observations) != 1:
            raise ValueError(
                "An optimization objective must have exactly one required observation"
            )
        if self.optimization is not None:
            observation = objective_observations[0]
            if (
                observation.metric != self.optimization.metric
                or observation.unit != self.optimization.unit
            ):
                raise ValueError(
                    "Optimization observation must match the objective metric and unit"
                )

        expected_constraint_ids = set(constraint_ids)
        for candidate in self.candidates:
            candidate_ids = [
                result.requirement_id
                for result in candidate.constraint_results
            ]
            if (
                len(candidate_ids) != len(expected_constraint_ids)
                or set(candidate_ids) != expected_constraint_ids
            ):
                raise ValueError(
                    "Each candidate must preserve an independent result for every hard constraint"
                )
        return self
