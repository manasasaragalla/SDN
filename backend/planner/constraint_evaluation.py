"""Pure evaluation of hard constraints against normalized observations."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
import math
from typing import Sequence

from pydantic import Field, field_validator, model_validator

from backend.capabilities import CapabilityStatus, RequirementResolution
from backend.models.canonical_intent import Comparison, MetricConstraint
from backend.models.fingerprints import model_fingerprint
from backend.models.metric_definitions import get_metric_definition
from backend.models.network import Link
from backend.planner.models import (
    CandidateFeasibility,
    Plan,
    PlanningRequest,
    _PlannerModel,
)
from backend.planner.path_enumeration import (
    ConnectionKind,
    EnumeratedPath,
)


class EvaluationInputError(ValueError):
    """Raised when evaluation inputs have inconsistent identities or policy."""


class ObservationStatus(str, Enum):
    VALID = "VALID"
    FAILED = "FAILED"
    INVALID = "INVALID"


class EvaluationStatus(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"


class EvaluationCandidate(_PlannerModel):
    """An explicitly identified physical candidate for this evaluation."""

    candidate_id: str = Field(min_length=1)
    request_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    path: EnumeratedPath
    feasibility: CandidateFeasibility


class EvaluationTarget(_PlannerModel):
    """The full identity binding for one candidate and one hard constraint."""

    candidate_id: str = Field(min_length=1)
    request_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    path_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    requirement_id: str = Field(min_length=1)


class MetricObservation(_PlannerModel):
    """A normalized measurement; raw parser results are not accepted."""

    target: EvaluationTarget
    metric: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    value: float | None = Field(default=None, allow_inf_nan=True)
    status: ObservationStatus
    collected_at: datetime
    source: str = Field(min_length=1)
    evaluation_run_id: str | None = Field(default=None, min_length=1)

    @field_validator("value", mode="before")
    @classmethod
    def reject_boolean_value(cls, value):
        if isinstance(value, bool):
            raise ValueError("Observation value must be numeric, not boolean.")
        return value

    @field_validator("collected_at")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collected_at must be timezone-aware")
        return value

    @field_validator("evaluation_run_id")
    @classmethod
    def require_nonempty_run_id(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("evaluation_run_id must be non-empty when supplied")
        return value


class MetricFreshnessLimit(_PlannerModel):
    metric: str = Field(min_length=1)
    max_age: timedelta

    @field_validator("max_age")
    @classmethod
    def require_nonnegative_age(cls, value: timedelta) -> timedelta:
        if value < timedelta(0):
            raise ValueError("max_age must not be negative")
        return value


class FreshnessPolicy(_PlannerModel):
    """Explicit per-metric maximum observation ages; no defaults are applied."""

    limits: tuple[MetricFreshnessLimit, ...] = ()

    @model_validator(mode="after")
    def require_unique_metrics(self) -> "FreshnessPolicy":
        metrics = [limit.metric for limit in self.limits]
        if len(metrics) != len(set(metrics)):
            raise ValueError("Freshness policy metrics must be unique")
        return self

    def max_age_for(self, metric: str) -> timedelta | None:
        return next(
            (limit.max_age for limit in self.limits if limit.metric == metric),
            None,
        )


class RequirementEvaluation(_PlannerModel):
    target: EvaluationTarget
    metric: str
    unit: str
    status: EvaluationStatus
    observed_value: float | None = None
    reason: str | None = None

    @field_validator("observed_value", mode="before")
    @classmethod
    def reject_boolean_observed_value(cls, value):
        if isinstance(value, bool):
            raise ValueError("Observed value must be numeric, not boolean.")
        return value

    @model_validator(mode="after")
    def validate_observed_value_for_status(self) -> "RequirementEvaluation":
        if self.status in (EvaluationStatus.SATISFIED, EvaluationStatus.VIOLATED):
            if self.observed_value is None or not math.isfinite(self.observed_value):
                raise ValueError(
                    "Satisfied or violated results require a finite observed value"
                )
        elif self.observed_value is not None:
            raise ValueError(
                "Only satisfied or violated results may include an observed value"
            )
        return self


class CandidateEvaluation(_PlannerModel):
    candidate_id: str
    request_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    path_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    feasibility: CandidateFeasibility
    status: EvaluationStatus
    requirements: tuple[RequirementEvaluation, ...] = ()
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def preserve_candidate_aggregation(self) -> "CandidateEvaluation":
        if self.feasibility == CandidateFeasibility.PROVEN_INFEASIBLE:
            if (
                self.status != EvaluationStatus.NOT_EVALUATED
                or self.requirements
            ):
                raise ValueError(
                    "Proven-infeasible candidates must be NOT_EVALUATED without requirement results"
                )
            return self

        if not self.requirements:
            expected = EvaluationStatus.NOT_EVALUATED
        else:
            requirement_statuses = {
                requirement.status for requirement in self.requirements
            }
            if any(
                requirement.target.candidate_id != self.candidate_id
                or requirement.target.request_fingerprint
                != self.request_fingerprint
                or requirement.target.path_fingerprint != self.path_fingerprint
                for requirement in self.requirements
            ):
                raise ValueError(
                    "Requirement results must match their candidate and physical path"
                )
            if len(
                {
                    requirement.target.requirement_id
                    for requirement in self.requirements
                }
            ) != len(self.requirements):
                raise ValueError("Candidate requirement results must be unique")
            if EvaluationStatus.VIOLATED in requirement_statuses:
                expected = EvaluationStatus.VIOLATED
            elif requirement_statuses == {EvaluationStatus.SATISFIED}:
                expected = EvaluationStatus.SATISFIED
            else:
                expected = EvaluationStatus.UNKNOWN

        if self.status != expected:
            raise ValueError(
                f"Candidate status must be {expected.value} for its feasibility and requirement results"
            )
        return self


class PlanEvaluation(_PlannerModel):
    request_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    plan_fingerprint: str | None = Field(
        default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    freshness_policy_fingerprint: str | None = Field(
        default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    evaluation_run_id: str | None = Field(default=None, min_length=1)
    evaluated_at: datetime
    status: EvaluationStatus
    candidates: tuple[CandidateEvaluation, ...] = ()
    reasons: tuple[str, ...] = ()

    @field_validator("evaluated_at")
    @classmethod
    def require_aware_evaluation_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def preserve_plan_aggregation(self) -> "PlanEvaluation":
        if self.evaluation_run_id is not None and self.plan_fingerprint is None:
            raise ValueError(
                "A run-bound plan evaluation must include its plan fingerprint"
            )
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("Plan evaluation candidate IDs must be unique")
        if any(
            candidate.request_fingerprint != self.request_fingerprint
            for candidate in self.candidates
        ):
            raise ValueError(
                "Candidate results must match the plan evaluation request fingerprint"
            )

        eligible = [
            candidate
            for candidate in self.candidates
            if candidate.feasibility != CandidateFeasibility.PROVEN_INFEASIBLE
        ]
        if not eligible:
            expected = EvaluationStatus.NOT_EVALUATED
        elif any(
            candidate.status == EvaluationStatus.SATISFIED
            for candidate in eligible
        ):
            expected = EvaluationStatus.SATISFIED
        elif all(
            candidate.status == EvaluationStatus.VIOLATED
            for candidate in eligible
        ):
            expected = EvaluationStatus.VIOLATED
        elif all(
            candidate.status == EvaluationStatus.NOT_EVALUATED
            and not candidate.requirements
            for candidate in eligible
        ):
            expected = EvaluationStatus.NOT_EVALUATED
        else:
            expected = EvaluationStatus.UNKNOWN

        if self.status != expected:
            raise ValueError(
                f"Plan evaluation status must be {expected.value} for its candidate results"
            )
        return self


def planning_request_fingerprint(request: PlanningRequest) -> str:
    return model_fingerprint(request)


def physical_path_fingerprint(path: EnumeratedPath) -> str:
    """Fingerprint every ordered node and physical connection attribute."""

    return model_fingerprint(path)


def _validate_candidate_path(plan: Plan, candidate: EvaluationCandidate) -> None:
    intent = plan.request.intent
    path = candidate.path
    if path.nodes[0] != intent.scope.source or path.nodes[-1] != intent.scope.destination:
        raise EvaluationInputError(
            f"Candidate {candidate.candidate_id!r} path endpoints do not match the intent scope"
        )

    graph = plan.request.topology
    source = graph.hosts.get(intent.scope.source)
    destination = graph.hosts.get(intent.scope.destination)
    if source is None or destination is None:
        raise EvaluationInputError("Intent endpoints are absent from the request topology")
    if path.nodes[1] != source.switch or path.nodes[-2] != destination.switch:
        raise EvaluationInputError(
            f"Candidate {candidate.candidate_id!r} has an invalid host attachment path"
        )
    if any(node not in graph.switches for node in path.nodes[1:-1]):
        raise EvaluationInputError(
            f"Candidate {candidate.candidate_id!r} references an unknown switch"
        )

    first, *middle, last = path.connections
    if not (
        first.from_node == source.name
        and first.to_node == source.switch
        and first.from_port is None
        and first.to_port == source.switch_port
    ):
        raise EvaluationInputError(
            f"Candidate {candidate.candidate_id!r} source attachment does not match topology"
        )
    if not (
        last.from_node == destination.switch
        and last.to_node == destination.name
        and last.from_port == destination.switch_port
        and last.to_port is None
    ):
        raise EvaluationInputError(
            f"Candidate {candidate.candidate_id!r} destination attachment does not match topology"
        )

    for connection in middle:
        matching = any(
            (
                link.node_a == connection.from_node
                and link.node_b == connection.to_node
                and link.port_a == connection.from_port
                and link.port_b == connection.to_port
            )
            or (
                link.node_b == connection.from_node
                and link.node_a == connection.to_node
                and link.port_b == connection.from_port
                and link.port_a == connection.to_port
            )
            for link in graph.links
            if isinstance(link, Link)
        )
        if not matching:
            raise EvaluationInputError(
                f"Candidate {candidate.candidate_id!r} contains a switch "
                "connection absent from topology"
            )


def _capabilities_by_requirement(
    plan: Plan,
) -> dict[str, RequirementResolution]:
    assessments = plan.request.capabilities.constraints
    expected: dict[str, tuple[int, str]] = {}
    for index, requirement in enumerate(plan.hard_constraints):
        metric = requirement.constraint.metric
        requirement_id = f"constraint:{index}:{metric}"
        expected[requirement_id] = (index, metric)

    actual: dict[str, RequirementResolution] = {}
    for assessment in assessments:
        requirement_id = assessment.requirement_id
        if requirement_id in actual:
            raise EvaluationInputError(
                f"Duplicate capability assessment {requirement_id!r}"
            )
        if requirement_id not in expected:
            raise EvaluationInputError(
                f"Unexpected capability assessment {requirement_id!r}"
            )
        _, metric = expected[requirement_id]
        if assessment.kind != "constraint" or assessment.metric != metric:
            raise EvaluationInputError(
                f"Capability assessment {requirement_id!r} is bound to the wrong constraint"
            )
        actual[requirement_id] = assessment

    missing = set(expected) - set(actual)
    if missing:
        raise EvaluationInputError(
            "Missing capability assessment(s): " + ", ".join(sorted(missing))
        )
    return {
        requirement_id: actual[requirement_id]
        for requirement_id in expected
    }


def _constraint_capability_status(
    requirement_id: str,
    metric: str,
    capabilities_by_requirement: dict[str, RequirementResolution],
) -> tuple[bool, str]:
    capability = capabilities_by_requirement[requirement_id]
    if (
        capability.kind != "constraint"
        or capability.metric != metric
        or capability.validated.status != CapabilityStatus.SUPPORTED
        or capability.measurable is None
        or capability.measurable.status != CapabilityStatus.SUPPORTED
    ):
        return False, "The hard constraint is not both validated and measurable."
    return True, ""


def _compare(value: float, constraint: MetricConstraint) -> bool:
    comparison = constraint.comparison
    if comparison == Comparison.GT:
        return value > constraint.value
    if comparison == Comparison.GTE:
        return value >= constraint.value
    if comparison == Comparison.LT:
        return value < constraint.value
    if comparison == Comparison.LTE:
        return value <= constraint.value
    if comparison == Comparison.EQ:
        if constraint.tolerance is None:
            return value == constraint.value
        return abs(value - constraint.value) <= constraint.tolerance
    if comparison == Comparison.BETWEEN:
        return constraint.lower_bound <= value <= constraint.upper_bound
    raise AssertionError(f"Unhandled comparison operator: {comparison}")


def _evaluate_requirement(
    *,
    target: EvaluationTarget,
    constraint: MetricConstraint,
    capability_supported: bool,
    capability_reason: str,
    observations: list[MetricObservation],
    evaluated_at: datetime,
    freshness_policy: FreshnessPolicy,
) -> RequirementEvaluation:
    if not capability_supported:
        return RequirementEvaluation(
            target=target,
            metric=constraint.metric,
            unit=constraint.unit,
            status=EvaluationStatus.UNSUPPORTED,
            reason=capability_reason,
        )

    if constraint.tolerance is not None and constraint.comparison != Comparison.EQ:
        return RequirementEvaluation(
            target=target,
            metric=constraint.metric,
            unit=constraint.unit,
            status=EvaluationStatus.UNSUPPORTED,
            reason="Tolerance is supported only for EQ comparisons.",
        )

    if len(observations) > 1:
        return RequirementEvaluation(
            target=target,
            metric=constraint.metric,
            unit=constraint.unit,
            status=EvaluationStatus.UNKNOWN,
            reason="Multiple observations target the same candidate requirement.",
        )
    if not observations:
        return RequirementEvaluation(
            target=target,
            metric=constraint.metric,
            unit=constraint.unit,
            status=EvaluationStatus.UNKNOWN,
            reason="No observation was supplied for this candidate requirement.",
        )

    observation = observations[0]
    if observation.status != ObservationStatus.VALID:
        return RequirementEvaluation(
            target=target,
            metric=constraint.metric,
            unit=constraint.unit,
            status=EvaluationStatus.UNKNOWN,
            reason=f"Observation status is {observation.status.value}.",
        )
    if observation.value is None:
        return RequirementEvaluation(
            target=target,
            metric=constraint.metric,
            unit=constraint.unit,
            status=EvaluationStatus.UNKNOWN,
            reason="A valid observation must contain a numeric value.",
        )
    if observation.metric != constraint.metric:
        return RequirementEvaluation(
            target=target,
            metric=constraint.metric,
            unit=constraint.unit,
            status=EvaluationStatus.UNKNOWN,
            reason="Observation metric does not match the hard constraint.",
        )
    if observation.unit != constraint.unit:
        return RequirementEvaluation(
            target=target,
            metric=constraint.metric,
            unit=constraint.unit,
            status=EvaluationStatus.UNKNOWN,
            reason="Observation unit does not match the hard constraint.",
        )
    if observation.collected_at > evaluated_at:
        return RequirementEvaluation(
            target=target,
            metric=constraint.metric,
            unit=constraint.unit,
            status=EvaluationStatus.UNKNOWN,
            reason="Observation timestamp is in the future.",
        )
    max_age = freshness_policy.max_age_for(constraint.metric)
    if max_age is None:
        raise EvaluationInputError(
            f"No freshness limit was supplied for metric {constraint.metric!r}"
        )
    if evaluated_at - observation.collected_at > max_age:
        return RequirementEvaluation(
            target=target,
            metric=constraint.metric,
            unit=constraint.unit,
            status=EvaluationStatus.UNKNOWN,
            reason="Observation is older than the configured freshness limit.",
        )
    definition = get_metric_definition(constraint.metric)
    if definition is None:
        return RequirementEvaluation(
            target=target,
            metric=constraint.metric,
            unit=constraint.unit,
            status=EvaluationStatus.UNSUPPORTED,
            reason="Metric has no registered value-domain definition.",
        )
    if not math.isfinite(observation.value):
        return RequirementEvaluation(
            target=target,
            metric=constraint.metric,
            unit=constraint.unit,
            status=EvaluationStatus.UNKNOWN,
            reason="Observation value must be finite.",
        )
    domain_error = definition.validate_value(observation.value)
    if domain_error:
        return RequirementEvaluation(
            target=target,
            metric=constraint.metric,
            unit=constraint.unit,
            status=EvaluationStatus.UNKNOWN,
            reason=f"Observation is outside the metric domain: {domain_error}.",
        )

    satisfied = _compare(observation.value, constraint)
    return RequirementEvaluation(
        target=target,
        metric=constraint.metric,
        unit=constraint.unit,
        status=(
            EvaluationStatus.SATISFIED
            if satisfied
            else EvaluationStatus.VIOLATED
        ),
        observed_value=observation.value,
        reason="Observation satisfies the hard constraint."
        if satisfied
        else "Observation violates the hard constraint.",
    )


def _aggregate_requirements(
    results: Sequence[RequirementEvaluation],
) -> EvaluationStatus:
    if not results:
        return EvaluationStatus.NOT_EVALUATED
    statuses = {result.status for result in results}
    if EvaluationStatus.VIOLATED in statuses:
        return EvaluationStatus.VIOLATED
    if statuses == {EvaluationStatus.SATISFIED}:
        return EvaluationStatus.SATISFIED
    return EvaluationStatus.UNKNOWN


def evaluate_hard_constraints(
    plan: Plan,
    candidates: Sequence[EvaluationCandidate],
    observations: Sequence[MetricObservation],
    *,
    evaluated_at: datetime,
    freshness_policy: FreshnessPolicy,
    evaluation_run_id: str | None = None,
) -> PlanEvaluation:
    """Evaluate supplied normalized observations without execution side effects."""

    if evaluation_run_id is not None and (
        not isinstance(evaluation_run_id, str) or not evaluation_run_id.strip()
    ):
        raise EvaluationInputError("evaluation_run_id must be a non-empty string")
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise EvaluationInputError("evaluated_at must be timezone-aware")
    request_fingerprint = planning_request_fingerprint(plan.request)
    candidates_by_id: dict[str, EvaluationCandidate] = {}
    eligible: list[EvaluationCandidate] = []
    for candidate in candidates:
        if candidate.candidate_id in candidates_by_id:
            raise EvaluationInputError(
                f"Duplicate candidate ID {candidate.candidate_id!r}"
            )
        candidates_by_id[candidate.candidate_id] = candidate
        if candidate.request_fingerprint != request_fingerprint:
            raise EvaluationInputError(
                f"Candidate {candidate.candidate_id!r} is bound to a different planning request"
            )
        _validate_candidate_path(plan, candidate)
        if candidate.feasibility != CandidateFeasibility.PROVEN_INFEASIBLE:
            eligible.append(candidate)

    constraints = plan.hard_constraints
    capabilities_by_requirement = _capabilities_by_requirement(plan)
    if eligible:
        for index, requirement in enumerate(constraints):
            if freshness_policy.max_age_for(requirement.constraint.metric) is None:
                raise EvaluationInputError(
                    f"No freshness limit was supplied for metric {requirement.constraint.metric!r}"
                )
    targets_by_key: dict[tuple[str, str], EvaluationTarget] = {}
    candidate_paths: dict[str, str] = {}
    for candidate in eligible:
        path_fingerprint = physical_path_fingerprint(candidate.path)
        candidate_paths[candidate.candidate_id] = path_fingerprint
        for requirement in constraints:
            target = EvaluationTarget(
                candidate_id=candidate.candidate_id,
                request_fingerprint=request_fingerprint,
                path_fingerprint=path_fingerprint,
                requirement_id=requirement.requirement_id,
            )
            targets_by_key[
                (candidate.candidate_id, requirement.requirement_id)
            ] = target

    observations_by_key: dict[tuple[str, str, str, str], list[MetricObservation]] = {}
    expected_target_keys = {
        (
            target.candidate_id,
            target.request_fingerprint,
            target.path_fingerprint,
            target.requirement_id,
        )
        for target in targets_by_key.values()
    }
    for observation in observations:
        if observation.evaluation_run_id != evaluation_run_id:
            raise EvaluationInputError(
                "Observation evaluation_run_id does not match the evaluation"
            )
        target = observation.target
        key = (
            target.candidate_id,
            target.request_fingerprint,
            target.path_fingerprint,
            target.requirement_id,
        )
        if key not in expected_target_keys:
            raise EvaluationInputError(
                "Observation target does not identify an eligible candidate requirement"
            )
        observations_by_key.setdefault(key, []).append(observation)

    if not constraints:
        candidate_results = tuple(
            CandidateEvaluation(
                candidate_id=candidate.candidate_id,
                request_fingerprint=request_fingerprint,
                path_fingerprint=candidate_paths[candidate.candidate_id],
                feasibility=candidate.feasibility,
                status=EvaluationStatus.NOT_EVALUATED,
                reasons=("No hard constraints were requested.",),
            )
            for candidate in eligible
        )
        return PlanEvaluation(
            request_fingerprint=request_fingerprint,
            plan_fingerprint=model_fingerprint(plan),
            freshness_policy_fingerprint=model_fingerprint(freshness_policy),
            evaluation_run_id=evaluation_run_id,
            evaluated_at=evaluated_at,
            status=EvaluationStatus.NOT_EVALUATED,
            candidates=candidate_results,
            reasons=("No hard constraints were requested.",),
        )

    candidate_results: list[CandidateEvaluation] = []
    for candidate in eligible:
        path_fingerprint = candidate_paths[candidate.candidate_id]
        requirement_results: list[RequirementEvaluation] = []
        for index, requirement in enumerate(constraints):
            target = targets_by_key[
                (candidate.candidate_id, requirement.requirement_id)
            ]
            key = (
                target.candidate_id,
                target.request_fingerprint,
                target.path_fingerprint,
                target.requirement_id,
            )
            capability_id = f"constraint:{index}:{requirement.constraint.metric}"
            supported, capability_reason = _constraint_capability_status(
                capability_id,
                requirement.constraint.metric,
                capabilities_by_requirement,
            )
            requirement_results.append(
                _evaluate_requirement(
                    target=target,
                    constraint=requirement.constraint,
                    capability_supported=supported,
                    capability_reason=capability_reason,
                    observations=observations_by_key.get(key, []),
                    evaluated_at=evaluated_at,
                    freshness_policy=freshness_policy,
                )
            )
        candidate_status = _aggregate_requirements(requirement_results)
        candidate_results.append(
            CandidateEvaluation(
                candidate_id=candidate.candidate_id,
                request_fingerprint=request_fingerprint,
                path_fingerprint=path_fingerprint,
                feasibility=candidate.feasibility,
                status=candidate_status,
                requirements=tuple(requirement_results),
            )
        )

    if not candidate_results:
        plan_status = EvaluationStatus.NOT_EVALUATED
        reasons = ("No eligible candidates were supplied.",)
    elif any(
        candidate.status == EvaluationStatus.SATISFIED
        for candidate in candidate_results
    ):
        plan_status = EvaluationStatus.SATISFIED
        reasons = ("At least one eligible candidate satisfies every hard constraint.",)
    elif all(
        candidate.status == EvaluationStatus.VIOLATED
        for candidate in candidate_results
    ):
        plan_status = EvaluationStatus.VIOLATED
        reasons = ("Every eligible candidate violates at least one hard constraint.",)
    else:
        plan_status = EvaluationStatus.UNKNOWN
        reasons = ("No eligible candidate is known to satisfy every hard constraint.",)

    return PlanEvaluation(
        request_fingerprint=request_fingerprint,
        plan_fingerprint=model_fingerprint(plan),
        freshness_policy_fingerprint=model_fingerprint(freshness_policy),
        evaluation_run_id=evaluation_run_id,
        evaluated_at=evaluated_at,
        status=plan_status,
        candidates=tuple(candidate_results),
        reasons=reasons,
    )
