"""Candidate measurement and deployment for generalized hard constraints."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
import math
import re
from types import MappingProxyType
import uuid
from typing import Callable, Mapping

from backend.capabilities import ExecutionMode, resolve_capabilities
from backend.compiler.physical_path import compile_physical_path
from backend.deployment import ofctl_client
from backend.deployment.physical_path_executor import (
    cleanup_physical_path_deployment,
    deploy_physical_path_rules,
)
from backend.execution.models import PreflightResult, TopologySnapshot
from backend.execution.preflight import validate_preflight
from backend.execution.probe_preflight import (
    ProbePreflightResult,
    validate_probe_preflight,
)
from backend.measurement.latency import measure_latency
from backend.measurement.throughput import measure_throughput
from backend.models.canonical_intent import CanonicalIntent
from backend.models.deployment import (
    PhysicalCleanupResult,
    PhysicalDeploymentResult,
)
from backend.models.fingerprints import model_fingerprint
from backend.models.flow import FlowRule
from backend.models.measurement import LatencyResult, ThroughputResult
from backend.models.network import TopologyGraph
from backend.orchestration.latency_evidence import persist_latency_execution
from backend.planner.candidate_selection import (
    CandidateSelectionResult,
    ObjectiveObservation,
    SelectionStatus,
    assess_path_feasibility,
    physical_candidate_id,
    select_candidate,
)
from backend.planner.constraint_evaluation import (
    EvaluationCandidate,
    EvaluationStatus,
    EvaluationTarget,
    FreshnessPolicy,
    MetricFreshnessLimit,
    MetricObservation,
    ObservationStatus,
    PlanEvaluation,
    evaluate_hard_constraints,
    physical_path_fingerprint,
    planning_request_fingerprint,
)
from backend.planner.models import (
    CandidateFeasibility,
    HardConstraintRequirement,
    MetricObservationPurpose,
    Plan,
    PlanningReadiness,
    PlanningRequest,
    RequiredMetricObservation,
)
from backend.planner.path_enumeration import (
    EnumeratedPath,
    PathEnumerationResult,
    enumerate_candidate_paths,
)


class GeneralizedConstraintStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NO_SATISFYING_CANDIDATE = "NO_SATISFYING_CANDIDATE"
    NO_FEASIBLE_CANDIDATE = "NO_FEASIBLE_CANDIDATE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class _MeasurementContext:
    source_host: object
    destination_host: object
    destination_ip: str
    ping_count: int
    ping_timeout_s: int
    throughput_duration_s: int


@dataclass(frozen=True)
class _MeasurementStrategy:
    measurement_group: str
    source: str
    collect: Callable[[_MeasurementContext], LatencyResult | ThroughputResult]
    normalize: Callable[
        [LatencyResult | ThroughputResult], tuple[float | None, bool]
    ]
    uses_ping_packet_counts: bool = False


def _collect_ping(context: _MeasurementContext) -> LatencyResult:
    return measure_latency(
        context.source_host,
        context.destination_ip,
        count=context.ping_count,
        timeout_s=context.ping_timeout_s,
    )


def _collect_throughput(context: _MeasurementContext) -> ThroughputResult:
    return measure_throughput(
        context.source_host,
        context.destination_host,
        context.destination_ip,
        duration_s=context.throughput_duration_s,
    )


def _normalize_latency(
    result: LatencyResult | ThroughputResult,
) -> tuple[float | None, bool]:
    if not isinstance(result, LatencyResult):
        return None, False
    return (
        result.rtt_avg_ms,
        _valid_ping(result, "latency") and result.rtt_avg_ms is not None,
    )


def _normalize_packet_loss(
    result: LatencyResult | ThroughputResult,
) -> tuple[float | None, bool]:
    if not isinstance(result, LatencyResult):
        return None, False
    return result.packet_loss_pct, result.measurement_succeeded


def _normalize_bandwidth(
    result: LatencyResult | ThroughputResult,
) -> tuple[float | None, bool]:
    if not isinstance(result, ThroughputResult):
        return None, False
    value = result.received_mbps
    valid = (
        result.succeeded
        and value is not None
        and math.isfinite(value)
        and value >= 0
    )
    return value, valid


# Ping-derived metrics share a single real ping run per candidate. The
# strategy owns metric-specific normalization and evidence requirements.
MEASUREMENT_STRATEGIES: Mapping[str, _MeasurementStrategy] = MappingProxyType(
    {
        "latency": _MeasurementStrategy(
            "ping",
            "mininet-ping",
            _collect_ping,
            _normalize_latency,
        ),
        "packet_loss": _MeasurementStrategy(
            "ping",
            "mininet-ping",
            _collect_ping,
            _normalize_packet_loss,
            uses_ping_packet_counts=True,
        ),
        "bandwidth": _MeasurementStrategy(
            "iperf3",
            "iperf3-receiver",
            _collect_throughput,
            _normalize_bandwidth,
        ),
    }
)


@dataclass(frozen=True)
class GeneralizedConstraintProbe:
    candidate_id: str
    path: EnumeratedPath
    preflight: ProbePreflightResult | None = None
    preflight_snapshot: TopologySnapshot | None = None
    compiled_rules: tuple[FlowRule, ...] = ()
    deployment: PhysicalDeploymentResult | None = None
    cleanup: PhysicalCleanupResult | None = None
    measurements: dict[str, LatencyResult | ThroughputResult] = field(
        default_factory=dict
    )
    measurement_run_ids: dict[str, str] = field(default_factory=dict)
    measurement_timestamps: dict[str, datetime] = field(default_factory=dict)
    observations: tuple[MetricObservation, ...] = ()
    objective_observation: ObjectiveObservation | None = None
    error: str | None = None
    skip_reason: str | None = None
    operation_id: str = ""
    stage_timestamps: dict[str, str] = field(default_factory=dict)

    @property
    def measurement(self) -> LatencyResult | None:
        result = self.measurements.get("latency")
        if isinstance(result, LatencyResult):
            return result
        result = self.measurements.get("packet_loss")
        return result if isinstance(result, LatencyResult) else None

    @property
    def observation(self) -> ObjectiveObservation | None:
        return self.objective_observation

    @property
    def measurement_run_id(self) -> str:
        return next(iter(self.measurement_run_ids.values()), "")


@dataclass(frozen=True)
class GeneralizedConstraintResult:
    status: GeneralizedConstraintStatus
    measurement_run_id: str
    plan: Plan | None
    enumeration: PathEnumerationResult | None
    probes: tuple[GeneralizedConstraintProbe, ...] = ()
    selection: CandidateSelectionResult | None = None
    plan_evaluation: PlanEvaluation | None = None
    final_preflight: PreflightResult | None = None
    final_deployment: PhysicalDeploymentResult | None = None
    final_cleanup: PhysicalCleanupResult | None = None
    final_measurement: LatencyResult | None = None
    final_snapshot: TopologySnapshot | None = None
    final_rules: tuple[FlowRule, ...] = ()
    final_operation_id: str | None = None
    error: str | None = None
    execution_id: str = ""
    execution_started_at: datetime | None = None
    execution_completed_at: datetime | None = None
    evidence_json_path: str | None = None
    evidence_markdown_path: str | None = None
    final_stage_timestamps: dict[str, str] = field(default_factory=dict)


@dataclass
class _RunState:
    plan: Plan | None = None
    enumeration: PathEnumerationResult | None = None
    probes: list[GeneralizedConstraintProbe] = field(default_factory=list)
    selection: CandidateSelectionResult | None = None
    plan_evaluation: PlanEvaluation | None = None
    final_preflight: PreflightResult | None = None
    final_deployment: PhysicalDeploymentResult | None = None
    final_cleanup: PhysicalCleanupResult | None = None
    final_measurement: LatencyResult | None = None
    final_snapshot: TopologySnapshot | None = None
    final_rules: tuple[FlowRule, ...] = ()
    final_operation_id: str | None = None
    final_stage_timestamps: dict[str, str] = field(default_factory=dict)

    def partial(self, run_id: str, error: str) -> GeneralizedConstraintResult:
        return GeneralizedConstraintResult(
            status=GeneralizedConstraintStatus.FAILED,
            measurement_run_id=run_id,
            plan=self.plan,
            enumeration=self.enumeration,
            probes=tuple(self.probes),
            selection=self.selection,
            plan_evaluation=self.plan_evaluation,
            final_preflight=self.final_preflight,
            final_deployment=self.final_deployment,
            final_cleanup=self.final_cleanup,
            final_measurement=self.final_measurement,
            final_snapshot=self.final_snapshot,
            final_rules=self.final_rules,
            final_operation_id=self.final_operation_id,
            final_stage_timestamps=self.final_stage_timestamps,
            error=error,
        )


def build_generalized_plan(
    graph: TopologyGraph,
    intent: CanonicalIntent,
) -> Plan:
    """Bind canonical constraints/objective to existing capability and Plan contracts."""
    capabilities = resolve_capabilities(
        intent,
        graph=graph,
        execution_mode=ExecutionMode.GENERALIZED,
    )
    request = PlanningRequest(
        intent=intent,
        topology=graph,
        capabilities=capabilities,
    )
    hard_constraints = tuple(
        HardConstraintRequirement(
            requirement_id=f"constraint:{index}:{constraint.metric}",
            constraint=constraint,
        )
        for index, constraint in enumerate(intent.constraints)
    )
    required = [
        RequiredMetricObservation(
            observation_id=f"constraint-observation-{index}",
            requirement_id=requirement.requirement_id,
            purpose=MetricObservationPurpose.HARD_CONSTRAINT,
            metric=requirement.constraint.metric,
            unit=requirement.constraint.unit,
        )
        for index, requirement in enumerate(hard_constraints)
    ]
    if intent.optimization is not None:
        required.append(
            RequiredMetricObservation(
                observation_id="optimization-observation",
                requirement_id=f"optimization:{intent.optimization.metric}",
                purpose=MetricObservationPurpose.OPTIMIZATION,
                metric=intent.optimization.metric,
                unit=intent.optimization.unit,
            )
        )
    return Plan(
        request=request,
        capability_readiness=capabilities.eligibility,
        planning_readiness=PlanningReadiness.CONDITIONAL,
        hard_constraints=hard_constraints,
        optimization=intent.optimization,
        required_observations=tuple(required),
    )


def run_generalized_constraint_demo(
    graph: TopologyGraph,
    source_host,
    destination_host,
    intent: CanonicalIntent,
    planned_snapshot: TopologySnapshot,
    *,
    fresh_snapshot_provider: Callable[[], TopologySnapshot],
    base_url: str = ofctl_client.DEFAULT_BASE_URL,
    candidate_limit: int = 64,
    max_snapshot_age: timedelta = timedelta(seconds=30),
    measurement_max_age: timedelta = timedelta(minutes=5),
    ping_count: int = 10,
    ping_timeout_s: int | None = None,
    throughput_duration_s: int = 5,
    execution_id: str | None = None,
) -> GeneralizedConstraintResult:
    """Measure all candidates, evaluate all constraints, then deploy the selected path.

    `source_host` and `destination_host` must be the live Mininet host objects
    for the intent endpoints. No route is selected from configured capacity.
    """
    if execution_id is None:
        execution_id = uuid.uuid4().hex
    elif not re.fullmatch(r"[0-9a-f]{32}", execution_id):
        raise ValueError("execution_id must be a lowercase UUID hex string")
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    state = _RunState()
    if ping_timeout_s is None and type(ping_count) is int and ping_count > 0:
        ping_timeout_s = max(10, ping_count + 1)
    try:
        result = _run(
            graph,
            source_host,
            destination_host,
            intent,
            planned_snapshot,
            fresh_snapshot_provider=fresh_snapshot_provider,
            base_url=base_url,
            candidate_limit=candidate_limit,
            max_snapshot_age=max_snapshot_age,
            measurement_max_age=measurement_max_age,
            ping_count=ping_count,
            ping_timeout_s=ping_timeout_s,
            throughput_duration_s=throughput_duration_s,
            run_id=run_id,
            state=state,
        )
    except Exception as exc:
        completed_at = datetime.now(timezone.utc)
        error = f"{type(exc).__name__}: {exc}"
        record = state.partial(run_id, error)
        _persist(
            record,
            execution_id,
            started_at,
            completed_at,
            graph,
            intent,
            error,
            candidate_limit,
            ping_count,
            ping_timeout_s,
            throughput_duration_s,
            max_snapshot_age,
            measurement_max_age,
        )
        raise

    completed_at = datetime.now(timezone.utc)
    result = replace(
        result,
        execution_id=execution_id,
        execution_started_at=started_at,
        execution_completed_at=completed_at,
    )
    json_path, markdown_path = _persist(
        result,
        execution_id,
        started_at,
        completed_at,
        graph,
        intent,
        result.error,
        candidate_limit,
        ping_count,
        ping_timeout_s,
        throughput_duration_s,
        max_snapshot_age,
        measurement_max_age,
    )
    return replace(
        result,
        evidence_json_path=str(json_path),
        evidence_markdown_path=str(markdown_path),
    )


def _persist(
    result,
    execution_id,
    started_at,
    completed_at,
    graph,
    intent,
    error,
    candidate_limit,
    ping_count,
    ping_timeout_s,
    throughput_duration_s,
    max_snapshot_age,
    measurement_max_age,
):
    scope = getattr(intent, "scope", None)
    return persist_latency_execution(
        result,
        execution_id=execution_id,
        started_at=started_at,
        completed_at=completed_at,
        error=error,
        graph=graph,
        source=getattr(scope, "source", "unknown"),
        destination=getattr(scope, "destination", "unknown"),
        filename_prefix="generalized_constraints",
        configuration={
            "candidate_limit": (
                candidate_limit if type(candidate_limit) is int else None
            ),
            "ping_count": ping_count if type(ping_count) is int else None,
            "ping_timeout_s": (
                ping_timeout_s if type(ping_timeout_s) is int else None
            ),
            "throughput_duration_s": (
                throughput_duration_s
                if type(throughput_duration_s) is int
                else None
            ),
            "max_snapshot_age_seconds": _timedelta_seconds(max_snapshot_age),
            "measurement_max_age_seconds": _timedelta_seconds(
                measurement_max_age
            ),
        },
    )


def _run(
    graph,
    source_host,
    destination_host,
    intent,
    planned_snapshot,
    *,
    fresh_snapshot_provider,
    base_url,
    candidate_limit,
    max_snapshot_age,
    measurement_max_age,
    ping_count,
    ping_timeout_s,
    throughput_duration_s,
    run_id,
    state,
):
    if not isinstance(graph, TopologyGraph):
        raise ValueError("graph must be a TopologyGraph")
    if not isinstance(intent, CanonicalIntent):
        raise ValueError("intent must be a CanonicalIntent")
    if not isinstance(planned_snapshot, TopologySnapshot):
        raise ValueError("planned_snapshot must be a TopologySnapshot")
    if intent.requested_actions:
        raise ValueError("This orchestration does not dispatch requested actions.")
    if not intent.constraints and intent.optimization is None:
        raise ValueError("Intent must contain a hard constraint or optimization.")
    source_host_name = getattr(source_host, "name", None)
    if source_host_name != intent.scope.source:
        raise ValueError(
            f"source_host must identify intent source {intent.scope.source!r}"
        )
    if "bandwidth" in {
        constraint.metric for constraint in intent.constraints
    } or (
        intent.optimization is not None
        and intent.optimization.metric == "bandwidth"
    ):
        if getattr(destination_host, "name", None) != intent.scope.destination:
            raise ValueError(
                f"destination_host must identify intent destination {intent.scope.destination!r} for iperf3"
            )
    if type(ping_count) is not int or ping_count <= 0:
        raise ValueError("ping_count must be a positive integer")
    if ping_timeout_s is None:
        ping_timeout_s = max(10, ping_count + 1)
    if type(ping_timeout_s) is not int or ping_timeout_s <= 0:
        raise ValueError("ping_timeout_s must be a positive integer")
    if type(throughput_duration_s) is not int or throughput_duration_s <= 0:
        raise ValueError("throughput_duration_s must be a positive integer")
    if not isinstance(max_snapshot_age, timedelta) or max_snapshot_age < timedelta(0):
        raise ValueError("max_snapshot_age must be a non-negative timedelta")
    if (
        not isinstance(measurement_max_age, timedelta)
        or measurement_max_age < timedelta(0)
    ):
        raise ValueError("measurement_max_age must be a non-negative timedelta")

    plan = build_generalized_plan(graph, intent)
    state.plan = plan
    enumeration = enumerate_candidate_paths(
        graph,
        intent.scope.source,
        intent.scope.destination,
        candidate_limit=candidate_limit,
    )
    state.enumeration = enumeration
    if not enumeration.paths or enumeration.truncated:
        return _result(
            GeneralizedConstraintStatus.INSUFFICIENT_EVIDENCE,
            run_id,
            state,
            "Candidate enumeration is empty or truncated; global selection is not justified.",
        )

    feasibility_by_candidate = {
        physical_candidate_id(plan, path): assess_path_feasibility(plan, path)
        for path in enumeration.paths
    }
    has_potentially_feasible_candidate = any(
        assessment.feasibility != CandidateFeasibility.PROVEN_INFEASIBLE
        for assessment in feasibility_by_candidate.values()
    )
    supported = {
        item.requirement_id: item
        for item in plan.request.capabilities.constraints
    }
    if plan.request.capabilities.optimization is not None:
        item = plan.request.capabilities.optimization
        supported[item.requirement_id] = item
    unsupported = []
    for requirement in plan.required_observations:
        resolution = supported.get(requirement.requirement_id)
        if (
            requirement.metric not in MEASUREMENT_STRATEGIES
            or not _metric_measurable(requirement.metric, supported, requirement)
        ):
            reasons = (
                "; ".join(resolution.measurable.reasons)
                if resolution is not None and resolution.measurable is not None
                else "no measurement capability"
            )
            unsupported.append(f"{requirement.requirement_id}: {reasons}")
    if unsupported and has_potentially_feasible_candidate:
        return _result(
            GeneralizedConstraintStatus.INSUFFICIENT_EVIDENCE,
            run_id,
            state,
            "Unsupported or unmeasurable requirements: " + "; ".join(unsupported),
        )

    metric_names = {
        item.metric
        for item in plan.required_observations
    }
    freshness = FreshnessPolicy(
        limits=tuple(
            MetricFreshnessLimit(metric=metric, max_age=measurement_max_age)
            for metric in sorted(metric_names)
        )
    )
    request_fingerprint = planning_request_fingerprint(plan.request)
    plan_fingerprint = model_fingerprint(plan)
    operation_cookies: set[int] = set()
    observations: list[MetricObservation] = []
    objective_observations: list[ObjectiveObservation] = []
    metric_to_measure = sorted(metric_names)

    for path in enumeration.paths:
        candidate_id = physical_candidate_id(plan, path)
        stages = {"candidate_discovered_at": _now()}
        preflight = None
        snapshot = None
        rules: tuple[FlowRule, ...] = ()
        deployment = None
        cleanup = None
        measurements: dict[str, LatencyResult | ThroughputResult] = {}
        measurement_run_ids: dict[str, str] = {}
        measurement_timestamps: dict[str, datetime] = {}
        candidate_observations: list[MetricObservation] = []
        objective_observation = None
        error = None
        skip_reason = None
        operation_id = ""
        try:
            stages["preflight_started_at"] = _now()
            snapshot = fresh_snapshot_provider()
            preflight = validate_probe_preflight(
                plan,
                enumeration,
                path,
                planned_snapshot,
                snapshot,
                checked_at=datetime.now(timezone.utc),
                max_snapshot_age=max_snapshot_age,
            )
            stages["preflight_completed_at"] = _now()
            if preflight.proven_infeasible:
                skip_reason = (
                    "Candidate is statically infeasible: "
                    + "; ".join(preflight.reasons)
                )
                stages["probe_completed_at"] = _now()
                state.probes.append(
                    GeneralizedConstraintProbe(
                        candidate_id=candidate_id,
                        path=path,
                        preflight=preflight,
                        preflight_snapshot=snapshot,
                        skip_reason=skip_reason,
                        stage_timestamps=stages,
                    )
                )
                continue
            if not preflight.passed:
                error = "Probe preflight rejected candidate: " + "; ".join(
                    preflight.reasons
                )
            else:
                rules = tuple(compile_physical_path(snapshot.configured_topology, path))
                stages["compilation_completed_at"] = _now()
                stages["deployment_started_at"] = _now()
                operation_id = str(uuid.uuid4())
                try:
                    deployment = deploy_physical_path_rules(
                        list(rules), base_url=base_url
                    )
                except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
                    error = (
                        "Temporary deployment raised before ownership evidence "
                        f"returned; installation is uncertain: {exc}"
                    )
                stages["deployment_completed_at"] = _now()
                if deployment is not None and deployment.operation_cookie is None:
                    error = (
                        "Temporary deployment has no operation cookie; safe "
                        "cleanup cannot be established."
                    )
                elif deployment is not None and deployment.operation_cookie in operation_cookies:
                    error = "Temporary deployment reused an operation cookie."
                elif deployment is not None and not deployment.success:
                    error = (
                        f"Temporary deployment was not fully verified: "
                        f"{deployment.state.value}; {'; '.join(deployment.errors)}"
                    )
                elif deployment is not None:
                    operation_cookies.add(deployment.operation_cookie)
                    stages["measurement_started_at"] = _now()
                    measurements_by_group: dict[
                        str, tuple[str, LatencyResult | ThroughputResult, datetime]
                    ] = {}
                    context = _MeasurementContext(
                        source_host=source_host,
                        destination_host=destination_host,
                        destination_ip=snapshot.configured_topology.hosts[
                            intent.scope.destination
                        ].ip,
                        ping_count=ping_count,
                        ping_timeout_s=ping_timeout_s,
                        throughput_duration_s=throughput_duration_s,
                    )
                    for metric in metric_to_measure:
                        strategy = MEASUREMENT_STRATEGIES[metric]
                        if strategy.measurement_group not in measurements_by_group:
                            measurement_run_id = str(uuid.uuid4())
                            measurement = strategy.collect(context)
                            collected_at = datetime.now(timezone.utc)
                            measurements_by_group[strategy.measurement_group] = (
                                measurement_run_id,
                                measurement,
                                collected_at,
                            )
                        (
                            measurement_run_id,
                            measurement,
                            collected_at,
                        ) = measurements_by_group[strategy.measurement_group]
                        measurement_run_ids[metric] = measurement_run_id
                        measurement_timestamps[metric] = collected_at
                        measurements[metric] = measurement
                    stages["measurement_completed_at"] = _now()
        except (OSError, RuntimeError, TimeoutError, ValueError, TypeError) as exc:
            error = f"Candidate probe failed: {exc}"
            stages.setdefault("probe_completed_at", _now())
        finally:
            if deployment is not None and deployment.operation_cookie is not None:
                stages["cleanup_started_at"] = _now()
                try:
                    cleanup = cleanup_physical_path_deployment(
                        deployment, base_url=base_url
                    )
                except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
                    error = _join_error(error, f"Probe cleanup raised: {exc}")
                else:
                    if not cleanup.success:
                        error = _join_error(
                            error,
                            "Probe cleanup failed or is uncertain: "
                            f"{cleanup.state.value}; {'; '.join(cleanup.errors)}",
                        )
                stages["cleanup_completed_at"] = _now()

        if deployment is not None and deployment.operation_cookie is None and (
            deployment.accepted_count or deployment.verified_count
        ):
            error = _join_error(
                error,
                "Temporary deployment may have written flows but has no cleanup cookie.",
            )

        if snapshot is not None and preflight is not None and preflight.passed:
            for index, requirement in enumerate(plan.hard_constraints):
                metric = requirement.constraint.metric
                value, valid = _measurement_value(metric, measurements.get(metric))
                measured_at = measurement_timestamps.get(
                    metric, _measurement_time(stages)
                )
                observation = MetricObservation(
                    target=EvaluationTarget(
                        candidate_id=candidate_id,
                        request_fingerprint=request_fingerprint,
                        path_fingerprint=physical_path_fingerprint(path),
                        requirement_id=requirement.requirement_id,
                    ),
                    metric=metric,
                    unit=requirement.constraint.unit,
                    value=value if valid else None,
                    status=ObservationStatus.VALID if valid else ObservationStatus.FAILED,
                    collected_at=measured_at,
                    source=_measurement_source(metric),
                    evaluation_run_id=run_id,
                )
                candidate_observations.append(observation)
            if plan.optimization is not None:
                objective = plan.optimization
                value, valid = _measurement_value(
                    objective.metric, measurements.get(objective.metric)
                )
                required = next(
                    item
                    for item in plan.required_observations
                    if item.purpose == MetricObservationPurpose.OPTIMIZATION
                )
                measured = measurements.get(objective.metric)
                timestamp = measurement_timestamps.get(
                    objective.metric, _measurement_time(stages)
                )
                strategy = MEASUREMENT_STRATEGIES[objective.metric]
                if strategy.uses_ping_packet_counts and isinstance(measured, LatencyResult):
                    objective_observation = ObjectiveObservation.from_ping_result(
                        measured,
                        candidate_id=candidate_id,
                        request_fingerprint=request_fingerprint,
                        plan_fingerprint=plan_fingerprint,
                        path_fingerprint=physical_path_fingerprint(path),
                        observation_id=required.observation_id,
                        requirement_id=required.requirement_id,
                        evaluation_run_id=run_id,
                        collected_at=timestamp,
                        source="mininet-ping",
                    )
                else:
                    objective_observation = ObjectiveObservation(
                        candidate_id=candidate_id,
                        request_fingerprint=request_fingerprint,
                        plan_fingerprint=plan_fingerprint,
                        path_fingerprint=physical_path_fingerprint(path),
                        observation_id=required.observation_id,
                        requirement_id=required.requirement_id,
                        evaluation_run_id=run_id,
                        metric=objective.metric,
                        unit=objective.unit,
                        value=value if valid else None,
                        status=ObservationStatus.VALID if valid else ObservationStatus.FAILED,
                        collected_at=timestamp,
                        source=_measurement_source(objective.metric),
                    )

        probe = GeneralizedConstraintProbe(
            candidate_id=candidate_id,
            path=path,
            preflight=preflight,
            preflight_snapshot=snapshot,
            compiled_rules=rules,
            deployment=deployment,
            cleanup=cleanup,
            measurements={
                key: value
                for key, value in measurements.items()
                if key != "ping"
            },
            measurement_run_ids=measurement_run_ids,
            measurement_timestamps=measurement_timestamps,
            observations=tuple(candidate_observations),
            objective_observation=objective_observation,
            error=error,
            skip_reason=skip_reason,
            operation_id=operation_id,
            stage_timestamps=stages,
        )
        state.probes.append(probe)
        observations.extend(candidate_observations)
        if objective_observation is not None:
            objective_observations.append(objective_observation)
        if probe.skip_reason is not None:
            continue
        if error is not None and (
            cleanup is None
            and deployment is not None
            and deployment.operation_cookie is not None
        ):
            return _result(
                GeneralizedConstraintStatus.FAILED,
                run_id,
                state,
                error,
            )
        if cleanup is not None and not cleanup.success:
            return _result(
                GeneralizedConstraintStatus.FAILED,
                run_id,
                state,
                error or "Temporary deployment cleanup failed or is uncertain.",
            )
        if deployment is None or not deployment.success:
            return _result(
                GeneralizedConstraintStatus.FAILED,
                run_id,
                state,
                error or "Candidate deployment was not verified.",
            )

    evaluation_time = datetime.now(timezone.utc)
    evaluation_candidates = tuple(
        EvaluationCandidate(
            candidate_id=physical_candidate_id(plan, path),
            request_fingerprint=request_fingerprint,
            path=path,
            feasibility=feasibility_by_candidate[
                physical_candidate_id(plan, path)
            ].feasibility,
        )
        for path in enumeration.paths
    )
    evaluation: PlanEvaluation = evaluate_hard_constraints(
        plan,
        evaluation_candidates,
        observations,
        evaluated_at=evaluation_time,
        freshness_policy=freshness,
        evaluation_run_id=run_id,
    )
    state.plan_evaluation = evaluation
    missing_or_invalid_evidence = any(
        requirement.status
        in {EvaluationStatus.UNKNOWN, EvaluationStatus.UNSUPPORTED}
        for candidate in evaluation.candidates
        for requirement in candidate.requirements
    )
    if missing_or_invalid_evidence:
        return _result(
            GeneralizedConstraintStatus.INSUFFICIENT_EVIDENCE,
            run_id,
            state,
            "At least one candidate hard constraint has missing, invalid, stale, or unsupported evidence.",
        )
    if plan.optimization is not None:
        eligible_statuses = (
            {EvaluationStatus.NOT_EVALUATED}
            if not plan.hard_constraints
            else {EvaluationStatus.SATISFIED}
        )
        eligible = {
            candidate.candidate_id
            for candidate in evaluation.candidates
            if candidate.status in eligible_statuses
        }
        selection_objectives = tuple(
            item
            for item in objective_observations
            if item.candidate_id in eligible
        )
    else:
        selection_objectives = ()
    selection = select_candidate(
        plan,
        enumeration,
        evaluation,
        evaluation_run_id=run_id,
        evaluated_at=evaluation_time,
        objective_observations=selection_objectives,
        freshness_policy=freshness,
    )
    state.selection = selection
    if selection.status != SelectionStatus.SELECTED or selection.selected_candidate is None:
        status = (
            GeneralizedConstraintStatus.NO_SATISFYING_CANDIDATE
            if selection.status == SelectionStatus.NO_SATISFYING_CANDIDATE
            else GeneralizedConstraintStatus.NO_FEASIBLE_CANDIDATE
            if selection.status == SelectionStatus.NO_ELIGIBLE_CANDIDATE
            else GeneralizedConstraintStatus.INSUFFICIENT_EVIDENCE
        )
        return _result(
            status,
            run_id,
            state,
            f"Candidate selection did not select a path: {selection.status.value}",
        )

    return _deploy_selected(
        plan,
        enumeration,
        selection,
        graph,
        source_host,
        planned_snapshot,
        fresh_snapshot_provider,
        base_url,
        max_snapshot_age,
        ping_count,
        ping_timeout_s,
        run_id,
        operation_cookies,
        state,
    )


def _deploy_selected(
    plan,
    enumeration,
    selection,
    graph,
    source_host,
    planned_snapshot,
    fresh_snapshot_provider,
    base_url,
    max_snapshot_age,
    ping_count,
    ping_timeout_s,
    run_id,
    operation_cookies,
    state,
):
    stages = {"selection_completed_at": _now()}
    state.final_stage_timestamps = stages
    try:
        stages["preflight_started_at"] = _now()
        snapshot = fresh_snapshot_provider()
        state.final_snapshot = snapshot
        preflight = validate_preflight(
            selection,
            planned_snapshot,
            snapshot,
            checked_at=datetime.now(timezone.utc),
            max_snapshot_age=max_snapshot_age,
        )
        state.final_preflight = preflight
        stages["preflight_completed_at"] = _now()
    except (OSError, RuntimeError, TimeoutError, ValueError, TypeError) as exc:
        return _result(
            GeneralizedConstraintStatus.FAILED,
            run_id,
            state,
            f"Final preflight failed: {exc}",
        )
    if preflight.status.value != "PASSED":
        return _result(
            GeneralizedConstraintStatus.FAILED,
            run_id,
            state,
            "Final preflight rejected the selected candidate: "
            + "; ".join(preflight.reasons),
        )
    try:
        rules = tuple(
            compile_physical_path(
                snapshot.configured_topology,
                selection.selected_candidate.path,
            )
        )
    except (RuntimeError, ValueError, TypeError) as exc:
        return _result(
            GeneralizedConstraintStatus.FAILED,
            run_id,
            state,
            f"Final physical-path compilation failed: {exc}",
        )
    state.final_rules = rules
    stages["deployment_started_at"] = _now()
    state.final_operation_id = str(uuid.uuid4())
    try:
        deployment = deploy_physical_path_rules(list(rules), base_url=base_url)
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        return _result(
            GeneralizedConstraintStatus.FAILED,
            run_id,
            state,
            f"Final deployment returned uncertain installation state: {exc}",
        )
    state.final_deployment = deployment
    stages["deployment_completed_at"] = _now()
    if deployment.operation_cookie is None or not deployment.success:
        if deployment.operation_cookie is not None:
            try:
                state.final_cleanup = cleanup_physical_path_deployment(
                    deployment, base_url=base_url
                )
            except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
                return _result(
                    GeneralizedConstraintStatus.FAILED,
                    run_id,
                    state,
                    f"Final deployment failed and cleanup could not be confirmed: {exc}",
                )
        return _result(
            GeneralizedConstraintStatus.FAILED,
            run_id,
            state,
            "Final deployment did not pass exact readback verification."
            + (
                "; cleanup "
                + (
                    state.final_cleanup.state.value
                    if state.final_cleanup is not None
                    else "not possible"
                )
                if deployment.operation_cookie is not None
                else ""
            ),
        )
    if deployment.operation_cookie in operation_cookies:
        try:
            state.final_cleanup = cleanup_physical_path_deployment(
                deployment, base_url=base_url
            )
        except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return _result(
                GeneralizedConstraintStatus.FAILED,
                run_id,
                state,
                f"Final deployment reused a probe cookie; cleanup failed: {exc}",
            )
        return _result(
            GeneralizedConstraintStatus.FAILED,
            run_id,
            state,
            "Final deployment reused a temporary probe cookie.",
        )

    stages["connectivity_started_at"] = _now()
    try:
        measurement = measure_latency(
            source_host,
            snapshot.configured_topology.hosts[
                plan.request.intent.scope.destination
            ].ip,
            count=ping_count,
            timeout_s=ping_timeout_s,
        )
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        stages["connectivity_completed_at"] = _now()
        try:
            state.final_cleanup = cleanup_physical_path_deployment(
                deployment, base_url=base_url
            )
        except (OSError, RuntimeError, TimeoutError, ValueError) as cleanup_exc:
            return _result(
                GeneralizedConstraintStatus.FAILED,
                run_id,
                state,
                f"Final connectivity failed ({exc}); deployment cleanup failed ({cleanup_exc}).",
            )
        return _result(
            GeneralizedConstraintStatus.FAILED,
            run_id,
            state,
            f"Final connectivity measurement failed: {exc}",
        )
    state.final_measurement = measurement
    stages["connectivity_completed_at"] = _now()
    if not _valid_ping(measurement, "latency"):
        try:
            state.final_cleanup = cleanup_physical_path_deployment(
                deployment, base_url=base_url
            )
        except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
            return _result(
                GeneralizedConstraintStatus.FAILED,
                run_id,
                state,
                f"Final connectivity was not verified; cleanup failed: {exc}",
            )
        return _result(
            GeneralizedConstraintStatus.FAILED,
            run_id,
            state,
            "Final flow readback succeeded, but h1-to-destination connectivity was not verified.",
        )
    return _result(GeneralizedConstraintStatus.SUCCEEDED, run_id, state, None)


def _result(status, run_id, state, error):
    return GeneralizedConstraintResult(
        status=status,
        measurement_run_id=run_id,
        plan=state.plan,
        enumeration=state.enumeration,
        probes=tuple(state.probes),
        selection=state.selection,
        plan_evaluation=state.plan_evaluation,
        final_preflight=state.final_preflight,
        final_deployment=state.final_deployment,
        final_cleanup=state.final_cleanup,
        final_measurement=state.final_measurement,
        final_snapshot=state.final_snapshot,
        final_rules=state.final_rules,
        final_operation_id=state.final_operation_id,
        error=error,
        final_stage_timestamps=state.final_stage_timestamps,
    )


def _metric_measurable(metric, resolutions, requirement):
    resolution = resolutions.get(requirement.requirement_id)
    if (
        resolution is None
        or resolution.measurable is None
        or resolution.measurable.status.value != "SUPPORTED"
        or resolution.validated.status.value != "SUPPORTED"
    ):
        return False
    if requirement.purpose == MetricObservationPurpose.HARD_CONSTRAINT:
        return (
            resolution.plannable.status.value == "SUPPORTED"
            and resolution.executable.status.value == "SUPPORTED"
        )
    return (
        resolution.generalized_objective_ranking is not None
        and resolution.generalized_objective_ranking.status.value == "SUPPORTED"
        and resolution.plannable.status.value == "SUPPORTED"
    )


def _measurement_value(metric, result):
    strategy = MEASUREMENT_STRATEGIES.get(metric)
    if strategy is None or result is None:
        return None, False
    return strategy.normalize(result)


def _valid_ping(result, metric):
    if not isinstance(result, LatencyResult) or not result.measurement_succeeded:
        return False
    if metric == "packet_loss":
        return True
    return (
        result.packets_received > 0
        and result.rtt_avg_ms is not None
        and math.isfinite(result.rtt_avg_ms)
        and result.rtt_avg_ms >= 0
    )


def _measurement_source(metric):
    strategy = MEASUREMENT_STRATEGIES.get(metric)
    return strategy.source if strategy is not None else "unsupported"


def _measurement_time(stages):
    stamp = stages.get("measurement_completed_at")
    if stamp:
        return datetime.fromisoformat(stamp)
    return datetime.now(timezone.utc)


def _join_error(previous, current):
    return f"{previous}; {current}" if previous else current


def _timedelta_seconds(value):
    return value.total_seconds() if isinstance(value, timedelta) else None


def _now():
    return datetime.now(timezone.utc).isoformat()
