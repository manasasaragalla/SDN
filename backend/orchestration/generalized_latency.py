"""Generalized MINIMIZE-latency measurement and deployment orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
import math
import uuid
from typing import Callable

from backend.capabilities import ExecutionMode, resolve_capabilities
from backend.compiler.physical_path import compile_physical_path
from backend.deployment import ofctl_client
from backend.deployment.physical_path_executor import (
    cleanup_physical_path_deployment,
    deploy_physical_path_rules,
)
from backend.execution.models import (
    PortOperationalState,
    PreflightResult,
    PreflightStatus,
    SnapshotStatus,
    TopologySnapshot,
)
from backend.execution.preflight import validate_preflight
from backend.execution.probe_preflight import (
    ProbePreflightResult,
    validate_probe_preflight,
)
from backend.measurement.latency import measure_latency
from backend.models.canonical_intent import (
    CanonicalIntent,
    OptimizationDirection,
    OptimizationObjective,
    TrafficScope,
)
from backend.models.deployment import (
    PhysicalCleanupResult,
    PhysicalDeploymentResult,
)
from backend.models.fingerprints import model_fingerprint
from backend.models.flow import FlowRule
from backend.models.measurement import LatencyResult
from backend.models.network import TopologyGraph
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
    FreshnessPolicy,
    MetricFreshnessLimit,
    ObservationStatus,
    physical_path_fingerprint,
    planning_request_fingerprint,
    evaluate_hard_constraints,
)
from backend.planner.models import (
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
from backend.orchestration.latency_evidence import persist_latency_execution


class GeneralizedLatencyStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class LatencyProbe:
    candidate_id: str
    path: EnumeratedPath
    preflight: ProbePreflightResult | None
    deployment: PhysicalDeploymentResult | None
    measurement: LatencyResult | None
    cleanup: PhysicalCleanupResult | None
    observation: ObjectiveObservation | None
    error: str | None = None
    measurement_run_id: str = ""
    operation_id: str = ""
    preflight_snapshot: TopologySnapshot | None = None
    compiled_rules: tuple[FlowRule, ...] = ()
    stage_timestamps: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class GeneralizedLatencyResult:
    status: GeneralizedLatencyStatus
    measurement_run_id: str
    plan: Plan
    enumeration: PathEnumerationResult
    probes: tuple[LatencyProbe, ...]
    selection: CandidateSelectionResult | None = None
    final_preflight: PreflightResult | None = None
    final_deployment: PhysicalDeploymentResult | None = None
    final_cleanup: PhysicalCleanupResult | None = None
    final_measurement: LatencyResult | None = None
    error: str | None = None
    execution_id: str = ""
    execution_started_at: datetime | None = None
    execution_completed_at: datetime | None = None
    evidence_json_path: str | None = None
    evidence_markdown_path: str | None = None
    final_snapshot: TopologySnapshot | None = None
    final_rules: tuple[FlowRule, ...] = ()
    final_operation_id: str | None = None
    final_stage_timestamps: dict[str, str] = field(default_factory=dict)


@dataclass
class _LatencyRunContext:
    plan: Plan | None = None
    enumeration: PathEnumerationResult | None = None
    measurement_run_id: str = ""
    probes: list[LatencyProbe] = field(default_factory=list)
    selection: CandidateSelectionResult | None = None
    final_preflight: PreflightResult | None = None
    final_deployment: PhysicalDeploymentResult | None = None
    final_cleanup: PhysicalCleanupResult | None = None
    final_measurement: LatencyResult | None = None
    final_snapshot: TopologySnapshot | None = None
    final_rules: tuple[FlowRule, ...] = ()
    final_operation_id: str | None = None
    final_stage_timestamps: dict[str, str] = field(default_factory=dict)

    def partial_result(self, error: str) -> GeneralizedLatencyResult | None:
        if self.plan is None or self.enumeration is None:
            return None
        return GeneralizedLatencyResult(
            status=GeneralizedLatencyStatus.FAILED,
            measurement_run_id=self.measurement_run_id or "execution-failed",
            plan=self.plan,
            enumeration=self.enumeration,
            probes=tuple(self.probes),
            selection=self.selection,
            final_preflight=self.final_preflight,
            final_deployment=self.final_deployment,
            final_cleanup=self.final_cleanup,
            final_measurement=self.final_measurement,
            error=error,
            final_snapshot=self.final_snapshot,
            final_rules=self.final_rules,
            final_operation_id=self.final_operation_id,
            final_stage_timestamps=self.final_stage_timestamps,
        )


class LiveSnapshotError(RuntimeError):
    """Raised when Ryu cannot provide complete operational topology evidence."""


def build_latency_plan(
    graph: TopologyGraph,
    source: str = "h1",
    destination: str = "h4",
) -> Plan:
    """Build the canonical generalized MINIMIZE-latency planning request."""
    intent = CanonicalIntent(
        scope=TrafficScope(source=source, destination=destination),
        optimization=OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        ),
    )
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
    return Plan(
        request=request,
        capability_readiness=capabilities.eligibility,
        planning_readiness=PlanningReadiness.CONDITIONAL,
        optimization=intent.optimization,
        required_observations=(
            RequiredMetricObservation(
                observation_id="latency-objective-observation",
                requirement_id="latency-objective",
                purpose=MetricObservationPurpose.OPTIMIZATION,
                metric="latency",
                unit="ms",
            ),
        ),
    )


def read_live_topology_snapshot(
    graph: TopologyGraph,
    base_url: str = ofctl_client.DEFAULT_BASE_URL,
) -> TopologySnapshot:
    """Read connected DPIDs and controller port descriptions for every data port."""
    status, payload = ofctl_client._get_json(f"{base_url}/stats/switches")
    if status != 200 or not isinstance(payload, list):
        raise LiveSnapshotError(
            f"Ryu datapath roster failed: HTTP/status {status} {payload!r}"
        )
    if any(type(dpid) is not int or dpid <= 0 for dpid in payload):
        raise LiveSnapshotError("Ryu returned invalid datapath identifiers")
    connected = tuple(sorted(payload))
    expected_dpids = set(graph.switches.values())
    if len(connected) != len(set(connected)) or set(connected) != expected_dpids:
        raise LiveSnapshotError(
            f"Connected DPIDs {connected!r} do not match topology {sorted(expected_dpids)!r}"
        )

    expected_ports = _expected_ports(graph)
    observed: dict[tuple[int, int], PortOperationalState] = {}
    for dpid in sorted(expected_dpids):
        status, response = ofctl_client._get_json(
            f"{base_url}/stats/portdesc/{dpid}"
        )
        entries = response.get(str(dpid)) if isinstance(response, dict) else None
        if status != 200 or not isinstance(entries, list):
            raise LiveSnapshotError(
                f"Port descriptions for DPID {dpid} failed: HTTP/status {status} {response!r}"
            )
        for entry in entries:
            if not isinstance(entry, dict):
                raise LiveSnapshotError(
                    f"Malformed port description for DPID {dpid}: {entry!r}"
                )
            port_no = entry.get("port_no")
            if isinstance(port_no, str) and port_no.isdecimal():
                port_no = int(port_no)
            if type(port_no) is not int or (dpid, port_no) not in expected_ports:
                continue
            config = entry.get("config")
            state = entry.get("state")
            if type(config) is not int or type(state) is not int:
                raise LiveSnapshotError(
                    f"Port {dpid}:{port_no} has unknown config/state flags"
                )
            key = (dpid, port_no)
            if key in observed:
                raise LiveSnapshotError(f"Duplicate port description for {key!r}")
            observed[key] = PortOperationalState(
                dpid=dpid,
                port_no=port_no,
                present=True,
                admin_up=(config & 1) == 0,
                link_up=(state & 1) == 0 and (state & 4) != 0,
            )
    if set(observed) != expected_ports:
        missing = sorted(expected_ports - set(observed))
        raise LiveSnapshotError(f"Ryu omitted configured data ports: {missing!r}")

    return TopologySnapshot(
        configured_topology=graph,
        captured_at=datetime.now(timezone.utc),
        status=SnapshotStatus.COMPLETE,
        connected_switch_dpids=connected,
        port_states=tuple(observed[key] for key in sorted(observed)),
    )


def select_latency_candidates(
    plan: Plan,
    enumeration: PathEnumerationResult,
    observations: tuple[ObjectiveObservation, ...],
    *,
    evaluation_run_id: str,
    evaluated_at: datetime,
    freshness_policy: FreshnessPolicy,
) -> CandidateSelectionResult:
    """Create the empty-hard-constraint Phase 3C result and use the selector."""
    request_fingerprint = planning_request_fingerprint(plan.request)
    candidates = []
    for path in enumeration.paths:
        assessment = assess_path_feasibility(plan, path)
        candidates.append(
            EvaluationCandidate(
                candidate_id=assessment.candidate_id,
                request_fingerprint=request_fingerprint,
                path=path,
                feasibility=assessment.feasibility,
            )
        )
    evaluation: PlanEvaluation = evaluate_hard_constraints(
        plan,
        candidates,
        (),
        evaluated_at=evaluated_at,
        freshness_policy=freshness_policy,
        evaluation_run_id=evaluation_run_id,
    )
    return select_candidate(
        plan,
        enumeration,
        evaluation,
        evaluation_run_id=evaluation_run_id,
        evaluated_at=evaluated_at,
        objective_observations=observations,
        freshness_policy=freshness_policy,
    )


def run_generalized_latency_demo(
    graph: TopologyGraph,
    source_host,
    planned_snapshot: TopologySnapshot,
    *,
    fresh_snapshot_provider: Callable[[], TopologySnapshot],
    base_url: str = ofctl_client.DEFAULT_BASE_URL,
    source: str = "h1",
    destination: str = "h4",
    candidate_limit: int = 64,
    max_snapshot_age: timedelta = timedelta(seconds=30),
    objective_max_age: timedelta = timedelta(minutes=5),
    ping_count: int = 10,
) -> GeneralizedLatencyResult:
    """Run the latency workflow and persist JSON and Markdown evidence."""
    execution_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc)
    context = _LatencyRunContext()
    try:
        result = _run_generalized_latency_demo(
            graph,
            source_host,
            planned_snapshot,
            fresh_snapshot_provider=fresh_snapshot_provider,
            base_url=base_url,
            source=source,
            destination=destination,
            candidate_limit=candidate_limit,
            max_snapshot_age=max_snapshot_age,
            objective_max_age=objective_max_age,
            ping_count=ping_count,
            _context=context,
        )
    except Exception as exc:
        completed_at = datetime.now(timezone.utc)
        error = f"{type(exc).__name__}: {exc}"
        persist_latency_execution(
            context.partial_result(error),
            execution_id=execution_id,
            started_at=started_at,
            completed_at=completed_at,
            error=error,
            graph=graph if isinstance(graph, TopologyGraph) else None,
            source=source,
            destination=destination,
            configuration=_evidence_configuration(
                candidate_limit,
                ping_count,
                max_snapshot_age,
                objective_max_age,
            ),
        )
        raise

    completed_at = datetime.now(timezone.utc)
    result = replace(
        result,
        execution_id=execution_id,
        execution_started_at=started_at,
        execution_completed_at=completed_at,
    )
    json_path, markdown_path = persist_latency_execution(
        result,
        execution_id=execution_id,
        started_at=started_at,
        completed_at=completed_at,
        graph=graph,
        source=source,
        destination=destination,
        configuration=_evidence_configuration(
            candidate_limit,
            ping_count,
            max_snapshot_age,
            objective_max_age,
        ),
    )
    return replace(
        result,
        evidence_json_path=str(json_path),
        evidence_markdown_path=str(markdown_path),
    )


def _evidence_configuration(
    candidate_limit: int,
    ping_count: int,
    max_snapshot_age: timedelta,
    objective_max_age: timedelta,
) -> dict[str, int | float | None]:
    return {
        "candidate_limit": candidate_limit if type(candidate_limit) is int else None,
        "ping_count": ping_count if type(ping_count) is int else None,
        "max_snapshot_age_seconds": (
            max_snapshot_age.total_seconds()
            if isinstance(max_snapshot_age, timedelta)
            else None
        ),
        "objective_max_age_seconds": (
            objective_max_age.total_seconds()
            if isinstance(objective_max_age, timedelta)
            else None
        ),
    }


def _run_generalized_latency_demo(
    graph: TopologyGraph,
    source_host,
    planned_snapshot: TopologySnapshot,
    *,
    fresh_snapshot_provider: Callable[[], TopologySnapshot],
    base_url: str = ofctl_client.DEFAULT_BASE_URL,
    source: str = "h1",
    destination: str = "h4",
    candidate_limit: int = 64,
    max_snapshot_age: timedelta = timedelta(seconds=30),
    objective_max_age: timedelta = timedelta(minutes=5),
    ping_count: int = 10,
    _context: _LatencyRunContext,
) -> GeneralizedLatencyResult:
    """Measure every enumerated candidate, select by real RTT, preflight, deploy."""
    if not isinstance(graph, TopologyGraph):
        raise ValueError("graph must be a TopologyGraph")
    if not isinstance(planned_snapshot, TopologySnapshot):
        raise ValueError("planned_snapshot must be a TopologySnapshot")
    if type(ping_count) is not int or ping_count <= 0:
        raise ValueError("ping_count must be a positive integer")
    plan = build_latency_plan(graph, source, destination)
    _context.plan = plan
    enumeration = enumerate_candidate_paths(
        graph, source, destination, candidate_limit=candidate_limit
    )
    _context.enumeration = enumeration
    run_id = str(uuid.uuid4())
    _context.measurement_run_id = run_id
    freshness = FreshnessPolicy(
        limits=(
            MetricFreshnessLimit(
                metric="latency",
                max_age=objective_max_age,
            ),
        )
    )
    if enumeration.truncated or not enumeration.paths:
        return GeneralizedLatencyResult(
            status=GeneralizedLatencyStatus.INSUFFICIENT_EVIDENCE,
            measurement_run_id=run_id,
            plan=plan,
            enumeration=enumeration,
            probes=(),
            error=(
                "Candidate enumeration is truncated or empty; global latency "
                "ranking is not justified."
            ),
        )

    request_id = planning_request_fingerprint(plan.request)
    plan_id = model_fingerprint(plan)
    required_observation = plan.required_observations[0]
    probes = _context.probes
    observations: list[ObjectiveObservation] = []
    operation_cookies: set[int] = set()

    for path in enumeration.paths:
        candidate_id = physical_candidate_id(plan, path)
        candidate_measurement_run_id = ""
        probe_operation_id = ""
        stage_timestamps = {
            "candidate_discovered_at": datetime.now(timezone.utc).isoformat()
        }
        fresh_snapshot = None
        probe_check = None
        try:
            stage_timestamps["preflight_started_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            fresh_snapshot = fresh_snapshot_provider()
            checked_at = datetime.now(timezone.utc)
            probe_check = validate_probe_preflight(
                plan,
                enumeration,
                path,
                planned_snapshot,
                fresh_snapshot,
                checked_at=checked_at,
                max_snapshot_age=max_snapshot_age,
            )
            stage_timestamps["preflight_completed_at"] = datetime.now(
                timezone.utc
            ).isoformat()
        except (RuntimeError, ValueError, TypeError) as exc:
            stage_timestamps["preflight_completed_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            probes.append(
                LatencyProbe(
                    candidate_id=candidate_id,
                    path=path,
                    preflight=None,
                    deployment=None,
                    measurement=None,
                    cleanup=None,
                    observation=None,
                    error=f"Probe preflight failed: {exc}",
                    measurement_run_id=candidate_measurement_run_id,
                    operation_id=probe_operation_id,
                    preflight_snapshot=fresh_snapshot,
                    stage_timestamps=stage_timestamps,
                )
            )
            return _failed_result(
                run_id, plan, enumeration, probes, str(exc)
            )
        if not probe_check.passed:
            probes.append(
                LatencyProbe(
                    candidate_id=candidate_id,
                    path=path,
                    preflight=probe_check,
                    deployment=None,
                    measurement=None,
                    cleanup=None,
                    observation=None,
                    error="; ".join(probe_check.reasons),
                    measurement_run_id=candidate_measurement_run_id,
                    operation_id=probe_operation_id,
                    preflight_snapshot=fresh_snapshot,
                    stage_timestamps=stage_timestamps,
                )
            )
            return _failed_result(
                run_id, plan, enumeration, probes, "; ".join(probe_check.reasons)
            )

        deployment = None
        cleanup = None
        measurement = None
        error = None
        stage_timestamps["compilation_started_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        try:
            rules = compile_physical_path(fresh_snapshot.configured_topology, path)
        except (RuntimeError, ValueError, TypeError) as exc:
            stage_timestamps["compilation_completed_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            probes.append(
                LatencyProbe(
                    candidate_id=candidate_id,
                    path=path,
                    preflight=probe_check,
                    deployment=None,
                    measurement=None,
                    cleanup=None,
                    observation=None,
                    error=f"Physical path compilation failed: {exc}",
                    measurement_run_id=candidate_measurement_run_id,
                    operation_id=probe_operation_id,
                    preflight_snapshot=fresh_snapshot,
                    stage_timestamps=stage_timestamps,
                )
            )
            return _failed_result(
                run_id, plan, enumeration, probes, f"Physical path compilation failed: {exc}"
            )
        stage_timestamps["compilation_completed_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        stage_timestamps["deployment_started_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        probe_operation_id = str(uuid.uuid4())
        try:
            try:
                deployment = deploy_physical_path_rules(rules, base_url=base_url)
            except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
                error = (
                    "Temporary deployment raised before returning ownership evidence; "
                    f"installation state is uncertain: {exc}"
                )
            stage_timestamps["deployment_completed_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            if deployment is None:
                pass
            elif deployment.operation_cookie is None:
                error = (
                    "Temporary deployment has no operation cookie; ownership and "
                    "safe cleanup cannot be established."
                )
            elif deployment.operation_cookie in operation_cookies:
                error = "Temporary deployment reused an operation cookie."
            elif not deployment.success:
                error = (
                    f"Temporary deployment was not fully verified: "
                    f"{deployment.state.value}; {'; '.join(deployment.errors)}"
                )
            else:
                operation_cookies.add(deployment.operation_cookie)
                try:
                    candidate_measurement_run_id = str(uuid.uuid4())
                    stage_timestamps["measurement_started_at"] = datetime.now(
                        timezone.utc
                    ).isoformat()
                    measurement = measure_latency(
                        source_host,
                        fresh_snapshot.configured_topology.hosts[destination].ip,
                        count=ping_count,
                    )
                    stage_timestamps["measurement_completed_at"] = datetime.now(
                        timezone.utc
                    ).isoformat()
                except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
                    stage_timestamps["measurement_completed_at"] = datetime.now(
                        timezone.utc
                    ).isoformat()
                    error = f"Temporary latency measurement failed: {exc}"
        finally:
            if deployment is not None and deployment.operation_cookie is not None:
                stage_timestamps["cleanup_started_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
                try:
                    cleanup = cleanup_physical_path_deployment(
                        deployment,
                        base_url=base_url,
                    )
                except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
                    stage_timestamps["cleanup_completed_at"] = datetime.now(
                        timezone.utc
                    ).isoformat()
                    cleanup_error = f"Temporary deployment cleanup raised: {exc}"
                    error = "; ".join(part for part in (error, cleanup_error) if part)
                else:
                    stage_timestamps["cleanup_completed_at"] = datetime.now(
                        timezone.utc
                    ).isoformat()
                    if not cleanup.success:
                        cleanup_error = (
                            f"Temporary deployment cleanup failed or is uncertain: "
                            f"{cleanup.state.value}; {'; '.join(cleanup.errors)}"
                        )
                        error = "; ".join(part for part in (error, cleanup_error) if part)

        if (
            deployment is not None
            and deployment.operation_cookie is None
            and (deployment.accepted_count or deployment.verified_count)
        ):
            error = "Temporary deployment may have written flows but has no cleanup cookie."

        observation = None
        if error is None and measurement is not None:
            observation = _latency_observation(
                plan,
                path,
                measurement,
                request_id=request_id,
                plan_id=plan_id,
                run_id=run_id,
                observation_id=required_observation.observation_id,
                requirement_id=required_observation.requirement_id,
            )
            if observation.status != ObservationStatus.VALID:
                error = (
                    "Ping did not produce a valid finite RTT with successful "
                    "transmission and at least one reply."
                )
        probes.append(
            LatencyProbe(
                candidate_id=candidate_id,
                path=path,
                preflight=probe_check,
                deployment=deployment,
                measurement=measurement,
                cleanup=cleanup,
                observation=observation,
                error=error,
                measurement_run_id=candidate_measurement_run_id,
                operation_id=probe_operation_id,
                preflight_snapshot=fresh_snapshot,
                compiled_rules=tuple(rules),
                stage_timestamps=stage_timestamps,
            )
        )
        if error is not None:
            return _failed_result(run_id, plan, enumeration, probes, error)
        observations.append(observation)

    evaluated_at = datetime.now(timezone.utc)
    selection = select_latency_candidates(
        plan,
        enumeration,
        tuple(observations),
        evaluation_run_id=run_id,
        evaluated_at=evaluated_at,
        freshness_policy=freshness,
    )
    _context.selection = selection
    if selection.status != SelectionStatus.SELECTED or selection.selected_candidate is None:
        return GeneralizedLatencyResult(
            status=GeneralizedLatencyStatus.INSUFFICIENT_EVIDENCE,
            measurement_run_id=run_id,
            plan=plan,
            enumeration=enumeration,
            probes=tuple(probes),
            selection=selection,
            error=f"Candidate selection did not select a path: {selection.status.value}",
        )

    final_stage_timestamps = {
        "selection_completed_at": evaluated_at.isoformat()
    }
    _context.final_stage_timestamps = final_stage_timestamps
    final_snapshot = None
    try:
        final_stage_timestamps["preflight_started_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        final_snapshot = fresh_snapshot_provider()
        _context.final_snapshot = final_snapshot
        final_preflight_checked_at = datetime.now(timezone.utc)
        final_preflight = validate_preflight(
            selection,
            planned_snapshot,
            final_snapshot,
            checked_at=final_preflight_checked_at,
            max_snapshot_age=max_snapshot_age,
        )
        _context.final_preflight = final_preflight
        final_stage_timestamps["preflight_completed_at"] = datetime.now(
            timezone.utc
        ).isoformat()
    except (RuntimeError, ValueError, TypeError) as exc:
        final_stage_timestamps["preflight_completed_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        return GeneralizedLatencyResult(
            status=GeneralizedLatencyStatus.FAILED,
            measurement_run_id=run_id,
            plan=plan,
            enumeration=enumeration,
            probes=tuple(probes),
            selection=selection,
            final_snapshot=final_snapshot,
            final_stage_timestamps=final_stage_timestamps,
            error=f"Final preflight failed: {exc}",
        )
    if final_preflight.status != PreflightStatus.PASSED:
        return GeneralizedLatencyResult(
            status=GeneralizedLatencyStatus.FAILED,
            measurement_run_id=run_id,
            plan=plan,
            enumeration=enumeration,
            probes=tuple(probes),
            selection=selection,
            final_preflight=final_preflight,
            final_snapshot=final_snapshot,
            final_stage_timestamps=final_stage_timestamps,
            error="Final preflight rejected the selected path: "
            + "; ".join(final_preflight.reasons),
        )

    final_stage_timestamps["compilation_started_at"] = datetime.now(
        timezone.utc
    ).isoformat()
    try:
        final_rules = compile_physical_path(
            final_snapshot.configured_topology,
            selection.selected_candidate.path,
        )
        _context.final_rules = tuple(final_rules)
    except (RuntimeError, ValueError, TypeError) as exc:
        final_stage_timestamps["compilation_completed_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        return GeneralizedLatencyResult(
            status=GeneralizedLatencyStatus.FAILED,
            measurement_run_id=run_id,
            plan=plan,
            enumeration=enumeration,
            probes=tuple(probes),
            selection=selection,
            final_preflight=final_preflight,
            final_snapshot=final_snapshot,
            final_stage_timestamps=final_stage_timestamps,
            error=f"Final physical path compilation failed: {exc}",
        )
    final_stage_timestamps["compilation_completed_at"] = datetime.now(
        timezone.utc
    ).isoformat()
    final_operation_id = str(uuid.uuid4())
    _context.final_operation_id = final_operation_id
    final_stage_timestamps["deployment_started_at"] = datetime.now(
        timezone.utc
    ).isoformat()
    try:
        final_deployment = deploy_physical_path_rules(
            final_rules,
            base_url=base_url,
        )
        _context.final_deployment = final_deployment
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        final_stage_timestamps["deployment_completed_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        return GeneralizedLatencyResult(
            status=GeneralizedLatencyStatus.FAILED,
            measurement_run_id=run_id,
            plan=plan,
            enumeration=enumeration,
            probes=tuple(probes),
            selection=selection,
            final_preflight=final_preflight,
            final_snapshot=final_snapshot,
            final_rules=tuple(final_rules),
            final_operation_id=final_operation_id,
            final_stage_timestamps=final_stage_timestamps,
            error=(
                "Final deployment raised before returning ownership evidence; "
                f"installation state is uncertain: {exc}"
            ),
        )
    final_stage_timestamps["deployment_completed_at"] = datetime.now(
        timezone.utc
    ).isoformat()
    if final_deployment.operation_cookie is None:
        return GeneralizedLatencyResult(
            status=GeneralizedLatencyStatus.FAILED,
            measurement_run_id=run_id,
            plan=plan,
            enumeration=enumeration,
            probes=tuple(probes),
            selection=selection,
            final_preflight=final_preflight,
            final_deployment=final_deployment,
            final_snapshot=final_snapshot,
            final_rules=tuple(final_rules),
            final_operation_id=final_operation_id,
            final_stage_timestamps=final_stage_timestamps,
            error=(
                "Final deployment has no operation cookie; ownership and safe "
                "cleanup cannot be established."
            ),
        )
    if final_deployment.operation_cookie in operation_cookies:
        final_stage_timestamps["cleanup_started_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        try:
            final_cleanup = cleanup_physical_path_deployment(
                final_deployment,
                base_url=base_url,
            )
            _context.final_cleanup = final_cleanup
            cleanup_error = None
        except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
            final_cleanup = None
            _context.final_cleanup = None
            cleanup_error = f"Final cleanup raised: {exc}"
        finally:
            final_stage_timestamps["cleanup_completed_at"] = datetime.now(
                timezone.utc
            ).isoformat()
        return GeneralizedLatencyResult(
            status=GeneralizedLatencyStatus.FAILED,
            measurement_run_id=run_id,
            plan=plan,
            enumeration=enumeration,
            probes=tuple(probes),
            selection=selection,
            final_preflight=final_preflight,
            final_deployment=final_deployment,
            final_cleanup=final_cleanup,
            final_snapshot=final_snapshot,
            final_rules=tuple(final_rules),
            final_operation_id=final_operation_id,
            final_stage_timestamps=final_stage_timestamps,
            error=(
                "Final deployment reused a temporary probe operation cookie."
                + (f" {cleanup_error}" if cleanup_error else "")
            ),
        )
    operation_cookies.add(final_deployment.operation_cookie)
    if not final_deployment.success:
        if final_deployment.operation_cookie is not None:
            final_stage_timestamps["cleanup_started_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            try:
                final_cleanup = cleanup_physical_path_deployment(
                    final_deployment,
                    base_url=base_url,
                )
                _context.final_cleanup = final_cleanup
            except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
                final_cleanup = None
                _context.final_cleanup = None
                cleanup_error = f"Cleanup raised: {exc}"
            else:
                cleanup_error = None
            finally:
                final_stage_timestamps["cleanup_completed_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
        suffix = (
            f"; cleanup {final_cleanup.state.value}"
            if final_cleanup is not None
            else f"; {cleanup_error}"
            if cleanup_error
            else ""
        )
        return GeneralizedLatencyResult(
            status=GeneralizedLatencyStatus.FAILED,
            measurement_run_id=run_id,
            plan=plan,
            enumeration=enumeration,
            probes=tuple(probes),
            selection=selection,
            final_preflight=final_preflight,
            final_deployment=final_deployment,
            final_cleanup=final_cleanup,
            final_snapshot=final_snapshot,
            final_rules=tuple(final_rules),
            final_operation_id=final_operation_id,
            final_stage_timestamps=final_stage_timestamps,
            error=(
                f"Final deployment was not fully verified: "
                f"{final_deployment.state.value}{suffix}"
            ),
        )

    final_cleanup = None
    _context.final_cleanup = None
    final_measurement = None
    measurement_error = None
    measurement_completed = False
    final_stage_timestamps["connectivity_started_at"] = datetime.now(
        timezone.utc
    ).isoformat()
    try:
        try:
            final_measurement = measure_latency(
                source_host,
                final_snapshot.configured_topology.hosts[destination].ip,
                count=ping_count,
            )
            _context.final_measurement = final_measurement
            measurement_completed = True
            final_stage_timestamps["connectivity_completed_at"] = datetime.now(
                timezone.utc
            ).isoformat()
        except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
            measurement_error = f"Final latency measurement failed: {exc}"
            final_stage_timestamps["connectivity_completed_at"] = datetime.now(
                timezone.utc
            ).isoformat()
    finally:
        if not measurement_completed:
            final_stage_timestamps["cleanup_started_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            try:
                final_cleanup = cleanup_physical_path_deployment(
                    final_deployment,
                    base_url=base_url,
                )
                _context.final_cleanup = final_cleanup
            except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
                _context.final_cleanup = None
                cleanup_error = f"Final cleanup raised: {exc}"
                measurement_error = (
                    f"{measurement_error}; {cleanup_error}"
                    if measurement_error
                    else cleanup_error
                )
            finally:
                final_stage_timestamps["cleanup_completed_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
    if measurement_error is not None or not _valid_latency(final_measurement):
        if final_cleanup is None:
            final_stage_timestamps["cleanup_started_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            try:
                final_cleanup = cleanup_physical_path_deployment(
                    final_deployment,
                    base_url=base_url,
                )
                _context.final_cleanup = final_cleanup
            except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
                _context.final_cleanup = None
                measurement_error = (
                    f"{measurement_error}; final cleanup raised: {exc}"
                    if measurement_error
                    else f"Final cleanup raised: {exc}"
                )
            finally:
                final_stage_timestamps["cleanup_completed_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
        if final_cleanup is not None and not final_cleanup.success:
            cleanup_detail = (
                f"final cleanup is {final_cleanup.state.value}; "
                f"{'; '.join(final_cleanup.errors)}"
            )
            measurement_error = (
                f"{measurement_error}; {cleanup_detail}"
                if measurement_error
                else cleanup_detail
            )
        return GeneralizedLatencyResult(
            status=GeneralizedLatencyStatus.FAILED,
            measurement_run_id=run_id,
            plan=plan,
            enumeration=enumeration,
            probes=tuple(probes),
            selection=selection,
            final_preflight=final_preflight,
            final_deployment=final_deployment,
            final_cleanup=final_cleanup,
            final_measurement=final_measurement,
            final_snapshot=final_snapshot,
            final_rules=tuple(final_rules),
            final_operation_id=final_operation_id,
            final_stage_timestamps=final_stage_timestamps,
            error=measurement_error
            or (
                "Final path deployment read back, but connectivity/RTT validation "
                f"failed; operation cleanup is {final_cleanup.state.value}."
            ),
        )
    return GeneralizedLatencyResult(
        status=GeneralizedLatencyStatus.SUCCEEDED,
        measurement_run_id=run_id,
        plan=plan,
        enumeration=enumeration,
        probes=tuple(probes),
        selection=selection,
        final_preflight=final_preflight,
        final_deployment=final_deployment,
        final_measurement=final_measurement,
        final_snapshot=final_snapshot,
        final_rules=tuple(final_rules),
        final_operation_id=final_operation_id,
        final_stage_timestamps=final_stage_timestamps,
    )


def _latency_observation(
    plan: Plan,
    path: EnumeratedPath,
    measurement: LatencyResult,
    *,
    request_id: str,
    plan_id: str,
    run_id: str,
    observation_id: str,
    requirement_id: str,
) -> ObjectiveObservation:
    valid = _valid_latency(measurement)
    return ObjectiveObservation(
        candidate_id=physical_candidate_id(plan, path),
        request_fingerprint=request_id,
        plan_fingerprint=plan_id,
        path_fingerprint=physical_path_fingerprint(path),
        observation_id=observation_id,
        requirement_id=requirement_id,
        evaluation_run_id=run_id,
        metric="latency",
        unit="ms",
        value=measurement.rtt_avg_ms if valid else None,
        status=ObservationStatus.VALID if valid else ObservationStatus.FAILED,
        collected_at=datetime.now(timezone.utc),
        source="mininet-ping",
    )


def _valid_latency(result: LatencyResult) -> bool:
    return (
        result.measurement_succeeded
        and result.packets_received > 0
        and result.rtt_avg_ms is not None
        and math.isfinite(result.rtt_avg_ms)
        and result.rtt_avg_ms >= 0
    )


def _failed_result(
    run_id: str,
    plan: Plan,
    enumeration: PathEnumerationResult,
    probes: list[LatencyProbe],
    error: str,
) -> GeneralizedLatencyResult:
    return GeneralizedLatencyResult(
        status=GeneralizedLatencyStatus.INSUFFICIENT_EVIDENCE,
        measurement_run_id=run_id,
        plan=plan,
        enumeration=enumeration,
        probes=tuple(probes),
        error=error,
    )


def _expected_ports(graph: TopologyGraph) -> set[tuple[int, int]]:
    ports = {
        (graph.switches[host.switch], host.switch_port)
        for host in graph.hosts.values()
    }
    ports.update(
        (graph.switches[link.node_a], link.port_a) for link in graph.links
    )
    ports.update(
        (graph.switches[link.node_b], link.port_b) for link in graph.links
    )
    return ports
