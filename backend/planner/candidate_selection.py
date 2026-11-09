"""Pure deterministic selection among exact physical path candidates."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import math

from pydantic import Field, StrictInt, field_validator, model_validator

from backend.capabilities import CapabilityStatus
from backend.models.canonical_intent import Comparison, MetricConstraint
from backend.models.fingerprints import model_fingerprint
from backend.models.metric_definitions import get_metric_definition
from backend.models.measurement import LatencyResult
from backend.models.network import TopologyGraph
from backend.planner.constraint_evaluation import (
    CandidateEvaluation,
    EvaluationStatus,
    FreshnessPolicy,
    ObservationStatus,
    PlanEvaluation,
    _compare,
    physical_path_fingerprint,
    planning_request_fingerprint,
)
from backend.planner.models import (
    CandidateFeasibility,
    MetricObservationPurpose,
    Plan,
    _PlannerModel,
)
from backend.planner.path_enumeration import (
    EnumeratedPath,
    InvalidPathRequestError,
    InvalidTopologyError,
    PathEnumerationResult,
    enumerate_candidate_paths,
    physical_path_capacity_mbps,
    validate_physical_path,
)


class SelectionInputError(ValueError):
    """Raised when selection evidence or physical identities are inconsistent."""


class SelectionStatus(str, Enum):
    SELECTED = "SELECTED"
    NO_SELECTION_CRITERIA = "NO_SELECTION_CRITERIA"
    NO_ELIGIBLE_CANDIDATE = "NO_ELIGIBLE_CANDIDATE"
    NO_SATISFYING_CANDIDATE = "NO_SATISFYING_CANDIDATE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNSUPPORTED_OBJECTIVE = "UNSUPPORTED_OBJECTIVE"


class SelectionMethod(str, Enum):
    OBJECTIVE_RANKING = "OBJECTIVE_RANKING"
    NEUTRAL_DETERMINISTIC = "NEUTRAL_DETERMINISTIC"


class SelectionScope(str, Enum):
    COMPLETE_ENUMERATION = "COMPLETE_ENUMERATION"
    ENUMERATED_SUBSET = "ENUMERATED_SUBSET"


class ObjectiveObservation(_PlannerModel):
    """One objective value bound to a physical candidate and evaluation run."""

    candidate_id: str = Field(min_length=1)
    request_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    plan_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    path_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    observation_id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    evaluation_run_id: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    value: float | None = Field(default=None, allow_inf_nan=True)
    status: ObservationStatus
    collected_at: datetime
    source: str = Field(min_length=1)
    packets_requested: StrictInt | None = Field(default=None, ge=0)
    packets_sent: StrictInt | None = Field(default=None, ge=0)
    packets_received: StrictInt | None = Field(default=None, ge=0)

    @field_validator("value", mode="before")
    @classmethod
    def reject_boolean_value(cls, value):
        if isinstance(value, bool):
            raise ValueError("Objective value must be numeric, not boolean.")
        return value

    @field_validator("collected_at")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collected_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_packet_loss_evidence(self) -> "ObjectiveObservation":
        if self.metric != "packet_loss":
            if any(
                count is not None
                for count in (
                    self.packets_requested,
                    self.packets_sent,
                    self.packets_received,
                )
            ):
                raise ValueError(
                    "Ping packet counts are only valid for packet-loss observations"
                )
            return self
        if (
            self.status == ObservationStatus.VALID
            and (
                self.packets_requested is None
                or self.packets_requested <= 0
                or self.packets_sent != self.packets_requested
            )
        ):
            raise ValueError(
                "A valid packet-loss observation requires complete requested-count evidence"
            )
        if (self.packets_sent is None) != (self.packets_received is None):
            raise ValueError("Packet-loss evidence requires both packet counts")
        if (
            self.status == ObservationStatus.VALID
            and not self.has_valid_packet_loss_evidence
        ):
            raise ValueError(
                "A valid packet-loss observation requires usable counts and a consistent finite percentage"
            )
        return self

    @property
    def has_valid_packet_loss_evidence(self) -> bool:
        if self.metric != "packet_loss":
            return True
        if (
            self.status != ObservationStatus.VALID
            or self.packets_requested is None
            or self.packets_requested <= 0
            or self.packets_sent is None
            or self.packets_sent <= 0
            or self.packets_sent != self.packets_requested
            or self.packets_received is None
            or self.packets_received < 0
            or self.packets_received > self.packets_sent
            or self.value is None
            or not math.isfinite(self.value)
            or not 0 <= self.value <= 100
        ):
            return False
        expected_loss = (
            100.0
            * (self.packets_sent - self.packets_received)
            / self.packets_sent
        )
        return math.isclose(self.value, expected_loss, rel_tol=0, abs_tol=0.5)

    @classmethod
    def from_ping_result(
        cls,
        result: LatencyResult,
        *,
        candidate_id: str,
        request_fingerprint: str,
        plan_fingerprint: str,
        path_fingerprint: str,
        observation_id: str,
        requirement_id: str,
        evaluation_run_id: str,
        collected_at: datetime,
        source: str,
    ) -> "ObjectiveObservation":
        """Normalize ping packet-loss evidence without treating parser fallbacks as data."""
        succeeded = result.measurement_succeeded
        return cls(
            candidate_id=candidate_id,
            request_fingerprint=request_fingerprint,
            plan_fingerprint=plan_fingerprint,
            path_fingerprint=path_fingerprint,
            observation_id=observation_id,
            requirement_id=requirement_id,
            evaluation_run_id=evaluation_run_id,
            metric="packet_loss",
            unit="%",
            value=result.packet_loss_pct if succeeded else None,
            status=(
                ObservationStatus.VALID
                if succeeded
                else ObservationStatus.FAILED
            ),
            collected_at=collected_at,
            source=source,
            packets_requested=result.packets_requested,
            packets_sent=result.packets_sent,
            packets_received=result.packets_received,
        )


class PathFeasibilityAssessment(_PlannerModel):
    candidate_id: str = Field(min_length=1)
    request_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    plan_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    path_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    feasibility: CandidateFeasibility
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def preserve_candidate_identity(self) -> "PathFeasibilityAssessment":
        if self.candidate_id != _candidate_id_from_fingerprints(
            self.request_fingerprint, self.path_fingerprint
        ):
            raise ValueError(
                "Candidate ID must bind its request and physical path fingerprints"
            )
        return self


class SelectedCandidate(_PlannerModel):
    candidate_id: str = Field(min_length=1)
    path: EnumeratedPath
    path_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    feasibility: CandidateFeasibility
    hard_constraint_status: EvaluationStatus
    objective_value: float | None = None

    @field_validator("objective_value", mode="before")
    @classmethod
    def reject_boolean_objective_value(cls, value):
        if isinstance(value, bool):
            raise ValueError("Objective value must be numeric, not boolean.")
        return value

    @model_validator(mode="after")
    def validate_objective_value(self) -> "SelectedCandidate":
        if self.path_fingerprint != physical_path_fingerprint(self.path):
            raise ValueError("Selected candidate path fingerprint does not match its path")
        if self.objective_value is not None and not math.isfinite(self.objective_value):
            raise ValueError("Selected objective value must be finite")
        return self


class CandidateSelectionResult(_PlannerModel):
    originating_plan: Plan
    enumeration: PathEnumerationResult
    plan_evaluation: PlanEvaluation
    freshness_policy: FreshnessPolicy
    objective_observations: tuple[ObjectiveObservation, ...] = ()
    request_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    plan_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    evaluation_run_id: str = Field(min_length=1)
    evaluated_at: datetime
    status: SelectionStatus
    candidates: tuple[SelectedCandidate, ...] = ()
    selected_candidate: SelectedCandidate | None = None
    selection_method: SelectionMethod | None = None
    search_truncated: bool
    selection_scope: SelectionScope
    reasons: tuple[str, ...] = ()

    @field_validator("evaluated_at")
    @classmethod
    def require_aware_evaluation_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        return value

    @field_validator("evaluation_run_id")
    @classmethod
    def require_nonempty_run_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evaluation_run_id must be non-empty")
        return value

    @model_validator(mode="after")
    def preserve_selection_invariants(self) -> "CandidateSelectionResult":
        plan = self.originating_plan
        evaluation = self.plan_evaluation
        if (
            self.request_fingerprint
            != planning_request_fingerprint(plan.request)
            or self.plan_fingerprint != model_fingerprint(plan)
        ):
            raise ValueError("Selection fingerprints do not match the originating plan")
        try:
            expected_enumeration = enumerate_candidate_paths(
                plan.request.topology,
                plan.request.intent.scope.source,
                plan.request.intent.scope.destination,
                self.enumeration.candidate_limit,
            )
        except (InvalidPathRequestError, InvalidTopologyError, ValueError) as error:
            raise ValueError(f"Cannot validate result enumeration: {error}") from error
        if (
            self.enumeration.source != expected_enumeration.source
            or self.enumeration.destination != expected_enumeration.destination
            or self.enumeration.paths != expected_enumeration.paths
            or self.enumeration.truncated != expected_enumeration.truncated
        ):
            raise ValueError("Result enumeration does not match the originating topology")
        if (
            self.search_truncated != self.enumeration.truncated
            or self.search_truncated
            != (self.selection_scope == SelectionScope.ENUMERATED_SUBSET)
        ):
            raise ValueError("Selection scope must reflect validated enumeration truncation")
        if (
            evaluation.request_fingerprint != self.request_fingerprint
            or evaluation.plan_fingerprint != self.plan_fingerprint
            or evaluation.evaluation_run_id != self.evaluation_run_id
            or evaluation.evaluated_at != self.evaluated_at
            or self.freshness_policy is None
            or evaluation.freshness_policy_fingerprint
            != model_fingerprint(self.freshness_policy)
        ):
            raise ValueError("Result evidence identities or freshness policy do not match")
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("Selection candidate IDs must be unique")
        expected_candidate_ids = tuple(
            physical_candidate_id(plan, path) for path in self.enumeration.paths
        )
        if tuple(candidate_ids) != expected_candidate_ids:
            raise ValueError("Result candidates must exactly match the validated enumeration")
        evaluated_by_id = {
            candidate.candidate_id: candidate
            for candidate in evaluation.candidates
        }
        objective = plan.optimization
        objective_requirement = next(
            (
                item
                for item in plan.required_observations
                if item.purpose == MetricObservationPurpose.OPTIMIZATION
            ),
            None,
        )
        objective_by_candidate: dict[str, ObjectiveObservation] = {}
        observation_ids: set[tuple[str, str]] = set()
        for observation in self.objective_observations:
            if objective is None or objective_requirement is None:
                raise ValueError("Objective observations require a planned objective")
            if (
                observation.candidate_id in objective_by_candidate
                or (observation.candidate_id, observation.observation_id)
                in observation_ids
            ):
                raise ValueError("Objective observations must be unique")
            observation_ids.add(
                (observation.candidate_id, observation.observation_id)
            )
            objective_by_candidate[observation.candidate_id] = observation
            matching_candidate = next(
                (
                    candidate
                    for candidate in self.candidates
                    if candidate.candidate_id == observation.candidate_id
                ),
                None,
            )
            if matching_candidate is None or (
                observation.observation_id != objective_requirement.observation_id
                or observation.requirement_id != objective_requirement.requirement_id
                or observation.metric != objective.metric
                or observation.unit != objective.unit
                or observation.request_fingerprint != self.request_fingerprint
                or observation.plan_fingerprint != self.plan_fingerprint
                or observation.evaluation_run_id != self.evaluation_run_id
                or observation.path_fingerprint != matching_candidate.path_fingerprint
                or matching_candidate.feasibility
                == CandidateFeasibility.PROVEN_INFEASIBLE
            ):
                raise ValueError("Objective observation identity does not match the plan")
        expected_eval_ids: set[str] = set()
        for candidate in self.candidates:
            assessment = assess_path_feasibility(plan, candidate.path)
            if (
                candidate.candidate_id
                != _candidate_id_from_fingerprints(
                    self.request_fingerprint, candidate.path_fingerprint
                )
                or candidate.path_fingerprint
                != physical_path_fingerprint(candidate.path)
                or candidate.feasibility != assessment.feasibility
            ):
                raise ValueError(
                    "Candidate ID must bind the result request and physical path fingerprints"
                )
            phase3c = evaluated_by_id.get(candidate.candidate_id)
            if candidate.feasibility != CandidateFeasibility.PROVEN_INFEASIBLE:
                expected_eval_ids.add(candidate.candidate_id)
            if phase3c is not None and (
                phase3c.request_fingerprint != self.request_fingerprint
                or phase3c.path_fingerprint != candidate.path_fingerprint
                or phase3c.feasibility != candidate.feasibility
                or phase3c.status != candidate.hard_constraint_status
            ):
                raise ValueError("Result candidate does not match its Phase 3C evaluation")
            expected_constraint_status = (
                EvaluationStatus.NOT_EVALUATED
                if not plan.hard_constraints
                or candidate.feasibility == CandidateFeasibility.PROVEN_INFEASIBLE
                else candidate.hard_constraint_status
            )
            if plan.hard_constraints and candidate.feasibility != CandidateFeasibility.PROVEN_INFEASIBLE:
                if phase3c is None or len(phase3c.requirements) != len(plan.hard_constraints):
                    raise ValueError("Candidate is missing Phase 3C hard-constraint evidence")
                statuses_by_id = {
                    item.target.requirement_id: item.status
                    for item in phase3c.requirements
                }
                requirements_by_id = {
                    item.requirement_id: item for item in plan.hard_constraints
                }
                if set(statuses_by_id) != {
                    requirement.requirement_id
                    for requirement in plan.hard_constraints
                }:
                    raise ValueError("Candidate constraint evidence does not match the plan")
                if any(
                    item.metric != requirements_by_id[
                        item.target.requirement_id
                    ].constraint.metric
                    or item.unit
                    != requirements_by_id[item.target.requirement_id].constraint.unit
                    for item in phase3c.requirements
                ):
                    raise ValueError("Candidate constraint evidence metric/unit mismatch")
                if any(
                    (
                        item.status == EvaluationStatus.SATISFIED
                        and (
                            item.observed_value is None
                            or not _compare(
                                item.observed_value,
                                requirements_by_id[
                                    item.target.requirement_id
                                ].constraint,
                            )
                        )
                    )
                    or (
                        item.status == EvaluationStatus.VIOLATED
                        and (
                            item.observed_value is None
                            or _compare(
                                item.observed_value,
                                requirements_by_id[
                                    item.target.requirement_id
                                ].constraint,
                            )
                        )
                    )
                    for item in phase3c.requirements
                ):
                    raise ValueError(
                        "Candidate constraint status contradicts its observed value"
                    )
                expected_constraint_status = phase3c.status
            if candidate.hard_constraint_status != expected_constraint_status:
                raise ValueError("Candidate hard-constraint status is inconsistent")
            observation = objective_by_candidate.get(candidate.candidate_id)
            if observation is None:
                if candidate.objective_value is not None:
                    raise ValueError("Candidate objective value has no matching observation")
            elif candidate.objective_value is not None and (
                observation.status != ObservationStatus.VALID
                or observation.value is None
                or not math.isfinite(observation.value)
                or candidate.objective_value != observation.value
            ):
                raise ValueError("Candidate objective evidence is inconsistent")
        if set(evaluated_by_id) != expected_eval_ids:
            raise ValueError("Phase 3C results do not cover the result candidates")

        hard_constraints_present = bool(plan.hard_constraints)
        objective_requested = plan.optimization is not None
        if objective_requested and self.search_truncated and (
            self.status != SelectionStatus.INSUFFICIENT_EVIDENCE
        ):
            raise ValueError(
                "Truncated enumeration with an objective requires INSUFFICIENT_EVIDENCE"
            )
        if self.status == SelectionStatus.SELECTED:
            if self.selected_candidate is None or self.selection_method is None:
                raise ValueError("A selected result requires one selected candidate and method")
            matches = [
                candidate
                for candidate in self.candidates
                if candidate.candidate_id == self.selected_candidate.candidate_id
            ]
            if len(matches) != 1 or matches[0] != self.selected_candidate:
                raise ValueError("Selected candidate must occur exactly once in candidates")
            if (
                self.selected_candidate.feasibility != CandidateFeasibility.CANDIDATE
            ):
                raise ValueError("Selected candidate is not eligible for selection")
            expected_hard_status = (
                EvaluationStatus.SATISFIED
                if hard_constraints_present
                else EvaluationStatus.NOT_EVALUATED
            )
            if self.selected_candidate.hard_constraint_status != expected_hard_status:
                raise ValueError(
                    "Selected candidate does not satisfy the hard-constraint invariant"
                )
            expected_method = (
                SelectionMethod.OBJECTIVE_RANKING
                if objective_requested
                else SelectionMethod.NEUTRAL_DETERMINISTIC
            )
            if self.selection_method != expected_method:
                raise ValueError("Selection method does not match the request criteria")
            if objective_requested:
                if self.selected_candidate.objective_value is None:
                    raise ValueError("Objective selection requires valid objective evidence")
                capability = plan.request.capabilities.optimization
                if (
                    objective is None
                    or capability is None
                    or capability.generalized_objective_ranking is None
                    or capability.generalized_objective_ranking.status
                    != CapabilityStatus.SUPPORTED
                ):
                    raise ValueError("Objective ranking is not explicitly supported")
                selected_evidence = objective_by_candidate.get(
                    self.selected_candidate.candidate_id
                )
                if selected_evidence is None:
                    raise ValueError("Selected objective lacks exactly one observation")
                max_age = self.freshness_policy.max_age_for(objective.metric)
                definition = get_metric_definition(objective.metric)
                if (
                    selected_evidence.metric != objective.metric
                    or selected_evidence.unit != objective.unit
                    or selected_evidence.status != ObservationStatus.VALID
                    or selected_evidence.value is None
                    or not math.isfinite(selected_evidence.value)
                    or selected_evidence.collected_at > self.evaluated_at
                    or max_age is None
                    or self.evaluated_at - selected_evidence.collected_at
                    > max_age
                    or definition is None
                    or definition.validate_value(selected_evidence.value) is not None
                ):
                    raise ValueError("Selected objective evidence is invalid")
                eligible = [
                    candidate
                    for candidate in self.candidates
                    if candidate.feasibility == CandidateFeasibility.CANDIDATE
                    and (
                        not hard_constraints_present
                        or candidate.hard_constraint_status
                        == EvaluationStatus.SATISFIED
                    )
                ]
                if any(
                    candidate.feasibility == CandidateFeasibility.UNKNOWN
                    or (
                        hard_constraints_present
                        and candidate.feasibility == CandidateFeasibility.CANDIDATE
                        and candidate.hard_constraint_status
                        not in (EvaluationStatus.SATISFIED, EvaluationStatus.VIOLATED)
                    )
                    for candidate in self.candidates
                ):
                    raise ValueError("Selected result contains unresolved candidate evidence")
                if any(
                    candidate.candidate_id not in objective_by_candidate
                    for candidate in eligible
                ):
                    raise ValueError("Objective evidence does not cover every eligible candidate")
                if set(objective_by_candidate) != {
                    candidate.candidate_id for candidate in eligible
                }:
                    raise ValueError("Objective evidence contains non-eligible candidates")
                for candidate in eligible:
                    evidence = objective_by_candidate[candidate.candidate_id]
                    if (
                        evidence.status != ObservationStatus.VALID
                        or evidence.value is None
                        or not math.isfinite(evidence.value)
                        or evidence.collected_at > self.evaluated_at
                        or max_age is None
                        or self.evaluated_at - evidence.collected_at > max_age
                        or definition is None
                        or definition.validate_value(evidence.value) is not None
                    ):
                        raise ValueError("Objective ranking contains invalid evidence")
                ranked = sorted(
                    eligible,
                    key=lambda candidate: (
                        -objective_by_candidate[candidate.candidate_id].value
                        if objective.direction.value == "MAXIMIZE"
                        else objective_by_candidate[candidate.candidate_id].value,
                        candidate.path_fingerprint,
                    ),
                )
                if not ranked or ranked[0] != self.selected_candidate:
                    raise ValueError("Selected candidate is not the deterministic objective winner")
            elif self.selected_candidate.objective_value is not None:
                raise ValueError("Neutral selection cannot contain an objective value")
            else:
                if any(
                    candidate.feasibility == CandidateFeasibility.UNKNOWN
                    or (
                        hard_constraints_present
                        and candidate.feasibility == CandidateFeasibility.CANDIDATE
                        and candidate.hard_constraint_status
                        not in (EvaluationStatus.SATISFIED, EvaluationStatus.VIOLATED)
                    )
                    for candidate in self.candidates
                ):
                    raise ValueError("Selected result contains unresolved candidate evidence")
                eligible = [
                    candidate
                    for candidate in self.candidates
                    if candidate.feasibility == CandidateFeasibility.CANDIDATE
                    and (
                        not hard_constraints_present
                        or candidate.hard_constraint_status
                        == EvaluationStatus.SATISFIED
                    )
                ]
                if (
                    not eligible
                    or min(eligible, key=lambda candidate: candidate.path_fingerprint)
                    != self.selected_candidate
                ):
                    raise ValueError("Selected candidate is not the deterministic eligible path")
            if self.search_truncated and self.selection_method == SelectionMethod.OBJECTIVE_RANKING:
                raise ValueError("Truncated enumeration cannot claim objective selection")
        elif self.selected_candidate is not None or self.selection_method is not None:
            raise ValueError("A non-selected result cannot contain a selected candidate")
        if (
            self.status == SelectionStatus.NO_SELECTION_CRITERIA
            and (hard_constraints_present or objective_requested)
        ):
            raise ValueError("NO_SELECTION_CRITERIA requires no constraints or objective")
        if (
            self.status == SelectionStatus.UNSUPPORTED_OBJECTIVE
            and not objective_requested
        ):
            raise ValueError("UNSUPPORTED_OBJECTIVE requires an objective")
        if self.status == SelectionStatus.UNSUPPORTED_OBJECTIVE:
            capability = plan.request.capabilities.optimization
            ranking = (
                capability.generalized_objective_ranking
                if capability is not None
                else None
            )
            eligible = [
                candidate
                for candidate in self.candidates
                if candidate.feasibility == CandidateFeasibility.CANDIDATE
            ]
            if (
                ranking is not None
                and ranking.status == CapabilityStatus.SUPPORTED
            ) or not eligible or any(
                candidate.feasibility == CandidateFeasibility.UNKNOWN
                or (
                    hard_constraints_present
                    and candidate.hard_constraint_status
                    not in (EvaluationStatus.SATISFIED, EvaluationStatus.VIOLATED)
                )
                for candidate in self.candidates
            ) or (
                hard_constraints_present
                and not any(
                    candidate.hard_constraint_status == EvaluationStatus.SATISFIED
                    for candidate in eligible
                )
            ):
                raise ValueError("UNSUPPORTED_OBJECTIVE is inconsistent with candidate evidence")
        if (
            self.status == SelectionStatus.NO_SATISFYING_CANDIDATE
            and not hard_constraints_present
        ):
            raise ValueError("NO_SATISFYING_CANDIDATE requires hard constraints")
        if self.status == SelectionStatus.NO_SATISFYING_CANDIDATE:
            eligible = [
                candidate
                for candidate in self.candidates
                if candidate.feasibility == CandidateFeasibility.CANDIDATE
            ]
            if (
                self.search_truncated
                or not eligible
                or any(
                    candidate.feasibility == CandidateFeasibility.UNKNOWN
                    or candidate.hard_constraint_status != EvaluationStatus.VIOLATED
                    for candidate in self.candidates
                    if candidate.feasibility != CandidateFeasibility.PROVEN_INFEASIBLE
                )
            ):
                raise ValueError("NO_SATISFYING_CANDIDATE is inconsistent with evidence")
        if self.status == SelectionStatus.NO_ELIGIBLE_CANDIDATE and (
            self.search_truncated
            or any(
                candidate.feasibility != CandidateFeasibility.PROVEN_INFEASIBLE
                for candidate in self.candidates
            )
        ):
            raise ValueError("NO_ELIGIBLE_CANDIDATE requires only proven-infeasible paths")
        return self

    @property
    def hard_constraints_present(self) -> bool:
        return bool(self.originating_plan.hard_constraints)

    @property
    def objective_requested(self) -> bool:
        return self.originating_plan.optimization is not None


def physical_candidate_id(plan: Plan, path: EnumeratedPath) -> str:
    """Derive identity from the request and complete ordered physical path."""
    if not isinstance(plan, Plan) or not isinstance(path, EnumeratedPath):
        raise SelectionInputError("plan and path must be validated planner models")
    request_fingerprint = planning_request_fingerprint(plan.request)
    path_fingerprint = physical_path_fingerprint(path)
    return _candidate_id_from_fingerprints(request_fingerprint, path_fingerprint)


class _IdentityPayload(_PlannerModel):
    request_fingerprint: str
    path_fingerprint: str


def _candidate_id_from_fingerprints(
    request_fingerprint: str, path_fingerprint: str
) -> str:
    digest = model_fingerprint(
        _IdentityPayload(
            request_fingerprint=request_fingerprint,
            path_fingerprint=path_fingerprint,
        )
    )
    return f"physical-{digest}"


def assess_path_feasibility(
    plan: Plan,
    path: EnumeratedPath,
) -> PathFeasibilityAssessment:
    """Assess exact topology and known bandwidth capacity without measurements."""
    if not isinstance(plan, Plan) or not isinstance(path, EnumeratedPath):
        raise SelectionInputError("plan and path must be validated planner models")
    request_fingerprint = planning_request_fingerprint(plan.request)
    plan_fingerprint = model_fingerprint(plan)
    path_fingerprint = physical_path_fingerprint(path)
    candidate_id = physical_candidate_id(plan, path)
    intent_scope = plan.request.intent.scope
    try:
        validate_physical_path(
            plan.request.topology,
            path,
            intent_scope.source,
            intent_scope.destination,
        )
    except (InvalidTopologyError, ValueError) as error:
        raise SelectionInputError(f"Invalid physical candidate path: {error}") from error

    lower_bandwidth_constraints = [
        requirement.constraint
        for requirement in plan.hard_constraints
        if requirement.constraint.metric == "bandwidth"
        and requirement.constraint.unit == "Mbps"
        and requirement.constraint.comparison
        in (Comparison.GT, Comparison.GTE, Comparison.EQ, Comparison.BETWEEN)
    ]
    if not lower_bandwidth_constraints:
        return PathFeasibilityAssessment(
            candidate_id=candidate_id,
            request_fingerprint=request_fingerprint,
            plan_fingerprint=plan_fingerprint,
            path_fingerprint=path_fingerprint,
            feasibility=CandidateFeasibility.CANDIDATE,
            reasons=("Exact physical path matches the request topology.",),
        )

    capacity = physical_path_capacity_mbps(plan.request.topology, path)
    capacity_complete = capacity is not None
    known_capacities = (
        [capacity]
        if capacity is not None
        else _known_physical_path_capacities(plan.request.topology, path)
    )
    known_upper_bound = min(known_capacities) if known_capacities else None

    for constraint in lower_bandwidth_constraints:
        threshold = _minimum_possible_satisfying_value(constraint)
        if threshold is None or known_upper_bound is None:
            continue
        impossible = (
            known_upper_bound <= threshold
            if constraint.comparison == Comparison.GT
            else known_upper_bound < threshold
        )
        if impossible:
            return PathFeasibilityAssessment(
                candidate_id=candidate_id,
                request_fingerprint=request_fingerprint,
                plan_fingerprint=plan_fingerprint,
                path_fingerprint=path_fingerprint,
                feasibility=CandidateFeasibility.PROVEN_INFEASIBLE,
                reasons=(
                    "Known physical path capacity cannot satisfy a bandwidth lower bound.",
                ),
            )

    if not capacity_complete:
        return PathFeasibilityAssessment(
            candidate_id=candidate_id,
            request_fingerprint=request_fingerprint,
            plan_fingerprint=plan_fingerprint,
            path_fingerprint=path_fingerprint,
            feasibility=CandidateFeasibility.UNKNOWN,
            reasons=("Physical path bandwidth capacity is unknown.",),
        )

    return PathFeasibilityAssessment(
        candidate_id=candidate_id,
        request_fingerprint=request_fingerprint,
        plan_fingerprint=plan_fingerprint,
        path_fingerprint=path_fingerprint,
        feasibility=CandidateFeasibility.CANDIDATE,
        reasons=(
            "Known physical capacity does not disprove the bandwidth constraints; "
            "runtime satisfaction remains unverified.",
        ),
    )


def _known_physical_path_capacities(
    graph: TopologyGraph, path: EnumeratedPath
) -> list[float]:
    known: list[float] = []
    for connection in path.connections:
        if connection.link_identity is None:
            continue
        for link in graph.links:
            if (
                (
                    link.node_a == connection.from_node
                    and link.port_a == connection.from_port
                    and link.node_b == connection.to_node
                    and link.port_b == connection.to_port
                )
                or (
                    link.node_b == connection.from_node
                    and link.port_b == connection.from_port
                    and link.node_a == connection.to_node
                    and link.port_a == connection.to_port
                )
            ) and (
                link.bw_mbps is not None
                and not isinstance(link.bw_mbps, bool)
                and math.isfinite(link.bw_mbps)
                and link.bw_mbps >= 0
            ):
                known.append(link.bw_mbps)
                break
    return known


def _minimum_possible_satisfying_value(
    constraint: MetricConstraint,
) -> float | None:
    if constraint.comparison in (Comparison.GT, Comparison.GTE):
        return constraint.value
    if constraint.comparison == Comparison.BETWEEN:
        return constraint.lower_bound
    if constraint.comparison == Comparison.EQ:
        tolerance = constraint.tolerance or 0.0
        return max(0.0, constraint.value - tolerance)
    return None


def _build_result(
    plan: Plan,
    run_id: str,
    evaluated_at: datetime,
    status: SelectionStatus,
    assessments: tuple[PathFeasibilityAssessment, ...],
    enumeration: PathEnumerationResult,
    reasons: tuple[str, ...],
    *,
    plan_evaluation: PlanEvaluation,
    freshness_policy: FreshnessPolicy,
    objective_observations: tuple[ObjectiveObservation, ...],
    evaluation_candidates: dict[str, CandidateEvaluation] | None = None,
    objective_values: dict[str, float] | None = None,
    selected_id: str | None = None,
    method: SelectionMethod | None = None,
) -> CandidateSelectionResult:
    evaluation_candidates = evaluation_candidates or {}
    objective_values = objective_values or {}
    candidates = tuple(
        SelectedCandidate(
            candidate_id=assessment.candidate_id,
            path=path,
            path_fingerprint=assessment.path_fingerprint,
            feasibility=assessment.feasibility,
            hard_constraint_status=evaluation_candidates.get(
                assessment.candidate_id
            ).status
            if assessment.candidate_id in evaluation_candidates
            else EvaluationStatus.NOT_EVALUATED,
            objective_value=objective_values.get(assessment.candidate_id),
        )
        for path, assessment in zip(enumeration.paths, assessments, strict=True)
    )
    selected = next(
        (candidate for candidate in candidates if candidate.candidate_id == selected_id),
        None,
    )
    return CandidateSelectionResult(
        originating_plan=plan,
        enumeration=enumeration,
        plan_evaluation=plan_evaluation,
        freshness_policy=freshness_policy,
        objective_observations=objective_observations,
        request_fingerprint=planning_request_fingerprint(plan.request),
        plan_fingerprint=model_fingerprint(plan),
        evaluation_run_id=run_id,
        evaluated_at=evaluated_at,
        status=status,
        candidates=candidates,
        selected_candidate=selected,
        selection_method=method,
        search_truncated=enumeration.truncated,
        selection_scope=(
            SelectionScope.ENUMERATED_SUBSET
            if enumeration.truncated
            else SelectionScope.COMPLETE_ENUMERATION
        ),
        reasons=reasons,
    )


def select_candidate(
    plan: Plan,
    enumeration: PathEnumerationResult,
    plan_evaluation: PlanEvaluation,
    *,
    evaluation_run_id: str,
    evaluated_at: datetime,
    objective_observations: tuple[ObjectiveObservation, ...] = (),
    freshness_policy: FreshnessPolicy | None = None,
) -> CandidateSelectionResult:
    """Select a physical path from validated Phase 3B and Phase 3C evidence."""
    if (
        not isinstance(plan, Plan)
        or not isinstance(enumeration, PathEnumerationResult)
        or not isinstance(plan_evaluation, PlanEvaluation)
    ):
        raise SelectionInputError(
            "Selection requires a Plan, PathEnumerationResult, and PlanEvaluation"
        )
    if not isinstance(evaluation_run_id, str) or not evaluation_run_id.strip():
        raise SelectionInputError("evaluation_run_id must be a non-empty string")
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise SelectionInputError("evaluated_at must be timezone-aware")
    request_fingerprint = planning_request_fingerprint(plan.request)
    plan_fingerprint = model_fingerprint(plan)
    if (
        plan_evaluation.request_fingerprint != request_fingerprint
        or plan_evaluation.plan_fingerprint != plan_fingerprint
        or plan_evaluation.evaluation_run_id != evaluation_run_id
        or plan_evaluation.evaluated_at != evaluated_at
    ):
        raise SelectionInputError(
            "Phase 3C evaluation identity, run, plan, or timestamp does not match selection"
        )
    scope = plan.request.intent.scope
    if (
        enumeration.source != scope.source
        or enumeration.destination != scope.destination
    ):
        raise SelectionInputError("Physical enumeration endpoints do not match the plan")
    try:
        expected_enumeration = enumerate_candidate_paths(
            plan.request.topology,
            scope.source,
            scope.destination,
            enumeration.candidate_limit,
        )
    except (InvalidPathRequestError, InvalidTopologyError, ValueError) as error:
        raise SelectionInputError(
            f"Could not verify physical enumeration against the request topology: {error}"
        ) from error
    if (
        enumeration.paths != expected_enumeration.paths
        or enumeration.truncated != expected_enumeration.truncated
    ):
        raise SelectionInputError(
            "Physical enumeration paths or truncation state do not match topology enumeration"
        )

    if (
        freshness_policy is None
        or plan_evaluation.freshness_policy_fingerprint
        != model_fingerprint(freshness_policy)
    ):
        raise SelectionInputError(
            "Selection freshness policy does not match the Phase 3C evaluation policy"
        )

    def _result(*args, **kwargs) -> CandidateSelectionResult:
        return _build_result(
            *args,
            plan_evaluation=plan_evaluation,
            freshness_policy=freshness_policy,
            objective_observations=objective_observations,
            **kwargs,
        )

    raw_candidate_ids = []
    for path in enumeration.paths:
        try:
            validate_physical_path(
                plan.request.topology, path, scope.source, scope.destination
            )
        except (InvalidTopologyError, ValueError) as error:
            raise SelectionInputError(
                f"Invalid physical candidate path: {error}"
            ) from error
        raw_candidate_ids.append(physical_candidate_id(plan, path))
    candidate_ids = raw_candidate_ids
    if len(candidate_ids) != len(set(candidate_ids)):
        raise SelectionInputError("Duplicate physical candidate identity")

    evaluation_by_id = {
        candidate.candidate_id: candidate
        for candidate in plan_evaluation.candidates
    }
    if not set(evaluation_by_id).issubset(candidate_ids):
        raise SelectionInputError(
            "Phase 3C results contain a candidate outside the physical enumeration"
        )
    paths_by_id = dict(zip(candidate_ids, enumeration.paths, strict=True))
    expected_requirements = {
        requirement.requirement_id: requirement.constraint
        for requirement in plan.hard_constraints
    }
    for candidate_id, candidate in evaluation_by_id.items():
        if (
            candidate.request_fingerprint != request_fingerprint
            or candidate.path_fingerprint
            != physical_path_fingerprint(paths_by_id[candidate_id])
        ):
            raise SelectionInputError(
                "Phase 3C candidate evidence does not match its physical path"
            )
        actual_requirement_ids = {
            requirement.target.requirement_id
            for requirement in candidate.requirements
        }
        if actual_requirement_ids != set(expected_requirements):
            raise SelectionInputError(
                "Phase 3C candidate results do not exactly cover the plan hard constraints"
            )
        for requirement in candidate.requirements:
            constraint = expected_requirements[requirement.target.requirement_id]
            if (
                requirement.metric != constraint.metric
                or requirement.unit != constraint.unit
            ):
                raise SelectionInputError(
                    "Phase 3C requirement evidence does not match its hard constraint"
                )

    objective = plan.optimization
    objective_requirement = next(
        (
            item
            for item in plan.required_observations
            if item.purpose == MetricObservationPurpose.OPTIMIZATION
        ),
        None,
    )
    objective_by_id: dict[str, ObjectiveObservation] = {}
    for observation in objective_observations:
        if objective is None or objective_requirement is None:
            raise SelectionInputError(
                "Objective evidence was supplied without an optimization objective"
            )
        if observation.observation_id != objective_requirement.observation_id:
            raise SelectionInputError("Objective evidence has an unexpected observation ID")
        if observation.requirement_id != objective_requirement.requirement_id:
            raise SelectionInputError("Objective evidence has a mismatched requirement ID")
        if observation.evaluation_run_id != evaluation_run_id:
            raise SelectionInputError("Objective evidence has a mismatched evaluation run ID")
        if observation.request_fingerprint != request_fingerprint:
            raise SelectionInputError("Objective evidence has a mismatched request fingerprint")
        if observation.plan_fingerprint != plan_fingerprint:
            raise SelectionInputError("Objective evidence has a mismatched plan fingerprint")
        if (
            observation.metric != objective.metric
            or observation.unit != objective.unit
        ):
            raise SelectionInputError("Objective evidence has a mismatched metric or unit")
        if (
            observation.metric == "packet_loss"
            and observation.status == ObservationStatus.VALID
            and not observation.has_valid_packet_loss_evidence
        ):
            raise SelectionInputError(
                "Packet-loss objective evidence has invalid measurement counts or value"
            )
        if observation.candidate_id not in candidate_ids:
            raise SelectionInputError("Objective evidence identifies an unknown candidate")
        path = paths_by_id[observation.candidate_id]
        if observation.path_fingerprint != physical_path_fingerprint(path):
            raise SelectionInputError("Objective evidence has a mismatched path fingerprint")
        if observation.candidate_id in objective_by_id:
            raise SelectionInputError("Duplicate objective observation")
        objective_by_id[observation.candidate_id] = observation

    assessments = tuple(
        assess_path_feasibility(plan, path) for path in enumeration.paths
    )
    expected_eval_ids = {
        assessment.candidate_id
        for assessment in assessments
        if assessment.feasibility != CandidateFeasibility.PROVEN_INFEASIBLE
    }
    if set(evaluation_by_id) != expected_eval_ids:
        raise SelectionInputError(
            "Phase 3C results do not exactly cover non-infeasible physical candidates"
        )
    if not set(objective_by_id).issubset(expected_eval_ids):
        raise SelectionInputError(
            "Objective evidence identifies a proven-infeasible physical candidate"
        )
    for assessment in assessments:
        candidate = evaluation_by_id.get(assessment.candidate_id)
        if candidate is None:
            continue
        if (
            candidate.request_fingerprint != assessment.request_fingerprint
            or candidate.path_fingerprint != assessment.path_fingerprint
            or candidate.feasibility != assessment.feasibility
        ):
            raise SelectionInputError(
                "Phase 3C candidate evidence does not match its physical path assessment"
            )

    if not plan.hard_constraints and objective is None:
        return _result(
            plan,
            evaluation_run_id,
            evaluated_at,
            SelectionStatus.NO_SELECTION_CRITERIA,
            assessments,
            enumeration,
            ("No hard constraints or optimization objective were requested.",),
            evaluation_candidates=evaluation_by_id,
        )

    if any(
        assessment.feasibility == CandidateFeasibility.UNKNOWN
        for assessment in assessments
    ):
        return _result(
            plan,
            evaluation_run_id,
            evaluated_at,
            SelectionStatus.INSUFFICIENT_EVIDENCE,
            assessments,
            enumeration,
            ("At least one enumerated physical candidate has unknown feasibility.",),
            evaluation_candidates=evaluation_by_id,
        )

    if objective is not None and enumeration.truncated:
        return _result(
            plan,
            evaluation_run_id,
            evaluated_at,
            SelectionStatus.INSUFFICIENT_EVIDENCE,
            assessments,
            enumeration,
            ("Truncated enumeration cannot support objective ranking.",),
            evaluation_candidates=evaluation_by_id,
        )

    potentially_eligible = [
        assessment
        for assessment in assessments
        if assessment.feasibility == CandidateFeasibility.CANDIDATE
    ]
    if not potentially_eligible:
        if enumeration.truncated and plan.hard_constraints:
            return _result(
                plan,
                evaluation_run_id,
                evaluated_at,
                SelectionStatus.INSUFFICIENT_EVIDENCE,
                assessments,
                enumeration,
                ("Truncated enumeration cannot establish that no candidate is eligible.",),
                evaluation_candidates=evaluation_by_id,
            )
        return _result(
            plan,
            evaluation_run_id,
            evaluated_at,
            SelectionStatus.NO_ELIGIBLE_CANDIDATE,
            assessments,
            enumeration,
            ("Every enumerated physical candidate is proven infeasible.",),
            evaluation_candidates=evaluation_by_id,
        )

    satisfying: list[PathFeasibilityAssessment] = []
    if plan.hard_constraints:
        for assessment in potentially_eligible:
            status = evaluation_by_id[assessment.candidate_id].status
            if status in (
                EvaluationStatus.UNKNOWN,
                EvaluationStatus.UNSUPPORTED,
                EvaluationStatus.NOT_EVALUATED,
            ):
                return _result(
                    plan,
                    evaluation_run_id,
                    evaluated_at,
                    SelectionStatus.INSUFFICIENT_EVIDENCE,
                    assessments,
                    enumeration,
                    ("Hard-constraint evidence is unresolved for a physical candidate.",),
                    evaluation_candidates=evaluation_by_id,
                )
            if status == EvaluationStatus.SATISFIED:
                satisfying.append(assessment)
        if not satisfying:
            if enumeration.truncated:
                return _result(
                    plan,
                    evaluation_run_id,
                    evaluated_at,
                    SelectionStatus.INSUFFICIENT_EVIDENCE,
                    assessments,
                    enumeration,
                    ("No enumerated candidate satisfies the constraints and search was truncated.",),
                    evaluation_candidates=evaluation_by_id,
                )
            return _result(
                plan,
                evaluation_run_id,
                evaluated_at,
                SelectionStatus.NO_SATISFYING_CANDIDATE,
                assessments,
                enumeration,
                ("Every eligible candidate violates at least one hard constraint.",),
                evaluation_candidates=evaluation_by_id,
            )
    else:
        satisfying = potentially_eligible

    objective_values: dict[str, float] = {}
    if objective is not None:
        capability = plan.request.capabilities.optimization
        objective_ranking = (
            capability.generalized_objective_ranking
            if capability is not None
            else None
        )
        if (
            objective_ranking is None
            or objective_ranking.status != CapabilityStatus.SUPPORTED
        ):
            return _result(
                plan,
                evaluation_run_id,
                evaluated_at,
                SelectionStatus.UNSUPPORTED_OBJECTIVE,
                assessments,
                enumeration,
                ("Generalized objective ranking is not explicitly supported.",),
                evaluation_candidates=evaluation_by_id,
            )
        if (
            capability.kind != "optimization"
            or capability.requirement_id != f"optimization:{objective.metric}"
            or capability.metric != objective.metric
            or capability.validated.status != CapabilityStatus.SUPPORTED
        ):
            raise SelectionInputError(
                "Objective capability assessment does not match the requested objective"
            )

        if objective_requirement is None:
            raise SelectionInputError("Plan has no required observation for its objective")
        expected_objective_ids = {item.candidate_id for item in satisfying}
        supplied_objective_ids = set(objective_by_id)
        if supplied_objective_ids - expected_objective_ids:
            raise SelectionInputError(
                "Objective evidence contains a non-eligible physical candidate"
            )
        if supplied_objective_ids != expected_objective_ids:
            return _result(
                plan,
                evaluation_run_id,
                evaluated_at,
                SelectionStatus.INSUFFICIENT_EVIDENCE,
                assessments,
                enumeration,
                ("Objective evidence is missing or does not cover every eligible candidate.",),
                evaluation_candidates=evaluation_by_id,
            )
        max_age = (
            freshness_policy.max_age_for(objective.metric)
            if freshness_policy is not None
            else None
        )
        if max_age is None:
            return _result(
                plan,
                evaluation_run_id,
                evaluated_at,
                SelectionStatus.INSUFFICIENT_EVIDENCE,
                assessments,
                enumeration,
                ("No objective evidence freshness limit was supplied.",),
                evaluation_candidates=evaluation_by_id,
            )
        definition = get_metric_definition(objective.metric)
        if definition is None:
            return _result(
                plan,
                evaluation_run_id,
                evaluated_at,
                SelectionStatus.INSUFFICIENT_EVIDENCE,
                assessments,
                enumeration,
                ("Objective metric has no registered value-domain definition.",),
                evaluation_candidates=evaluation_by_id,
            )
        for observation in objective_by_id.values():
            if (
                observation.status != ObservationStatus.VALID
                or observation.value is None
                or not math.isfinite(observation.value)
                or observation.collected_at > evaluated_at
                or evaluated_at - observation.collected_at > max_age
                or definition.validate_value(observation.value) is not None
            ):
                return _result(
                    plan,
                    evaluation_run_id,
                    evaluated_at,
                    SelectionStatus.INSUFFICIENT_EVIDENCE,
                    assessments,
                    enumeration,
                    ("Objective evidence is invalid, stale, future-dated, or non-finite.",),
                    evaluation_candidates=evaluation_by_id,
                )
            objective_values[observation.candidate_id] = observation.value
        reverse = objective.direction.value == "MAXIMIZE"
        chosen = sorted(
            satisfying,
            key=lambda item: (
                -objective_values[item.candidate_id]
                if reverse
                else objective_values[item.candidate_id],
                item.path_fingerprint,
            ),
        )[0]
        method = SelectionMethod.OBJECTIVE_RANKING
    else:
        chosen = min(satisfying, key=lambda item: item.path_fingerprint)
        method = SelectionMethod.NEUTRAL_DETERMINISTIC

    selection_status = SelectionStatus.SELECTED
    result = _result(
        plan,
        evaluation_run_id,
        evaluated_at,
        selection_status,
        assessments,
        enumeration,
        ("Selection is a pure planning result and does not imply deployment or runtime satisfaction.",),
        evaluation_candidates=evaluation_by_id,
        objective_values=objective_values,
        selected_id=chosen.candidate_id,
        method=method,
    )
    if plan.hard_constraints and result.selected_candidate.hard_constraint_status != EvaluationStatus.SATISFIED:
        raise SelectionInputError("Selected candidate lacks satisfied hard constraints")
    if objective is not None and result.selected_candidate.objective_value is None:
        raise SelectionInputError("Selected candidate lacks valid objective evidence")
    return result
