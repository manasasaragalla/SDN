"""Narrow preflight for authorizing one temporary physical-path probe."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from backend.execution.models import SnapshotStatus, TopologySnapshot
from backend.execution.preflight import (
    canonical_topology_fingerprint,
    topology_snapshot_fingerprint,
    validate_authoritative_enumeration,
)
from backend.models.network import TopologyGraph
from backend.planner.candidate_selection import (
    PathFeasibilityAssessment,
    assess_path_feasibility,
    physical_candidate_id,
)
from backend.planner.constraint_evaluation import physical_path_fingerprint
from backend.planner.models import CandidateFeasibility, Plan
from backend.planner.path_enumeration import (
    EnumeratedPath,
    PathEnumerationResult,
    validate_physical_path,
)


@dataclass(frozen=True)
class ProbePreflightResult:
    candidate_id: str
    path_fingerprint: str
    status: str
    planned_snapshot_fingerprint: str
    fresh_snapshot_fingerprint: str
    reasons: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == "PASSED"

    @property
    def proven_infeasible(self) -> bool:
        return self.status == "PROVEN_INFEASIBLE"


class ProbePreflightInputError(ValueError):
    """Raised when probe preflight receives malformed or unrelated inputs."""


def validate_probe_preflight(
    plan: Plan,
    enumeration: PathEnumerationResult,
    path: EnumeratedPath,
    planned_snapshot: TopologySnapshot,
    fresh_snapshot: TopologySnapshot,
    *,
    checked_at: datetime,
    max_snapshot_age: timedelta,
) -> ProbePreflightResult:
    """Authorize this enumerated candidate only; it does not select or deploy."""
    if not isinstance(plan, Plan) or not isinstance(enumeration, PathEnumerationResult):
        raise ProbePreflightInputError("A validated plan and enumeration are required")
    if not isinstance(path, EnumeratedPath):
        raise ProbePreflightInputError("path must be an EnumeratedPath")
    if not isinstance(planned_snapshot, TopologySnapshot) or not isinstance(
        fresh_snapshot, TopologySnapshot
    ):
        raise ProbePreflightInputError("Planned and fresh snapshots are required")
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ProbePreflightInputError("checked_at must be timezone-aware")
    if not isinstance(max_snapshot_age, timedelta) or max_snapshot_age < timedelta(0):
        raise ProbePreflightInputError("max_snapshot_age must be non-negative")

    scope = plan.request.intent.scope
    try:
        validate_authoritative_enumeration(plan, enumeration)
        if (
            enumeration.source != scope.source
            or enumeration.destination != scope.destination
            or path not in enumeration.paths
        ):
            raise ProbePreflightInputError(
                "Probe path is not a member of the plan's endpoint-bound enumeration"
            )
        validate_physical_path(plan.request.topology, path, scope.source, scope.destination)
        assessment: PathFeasibilityAssessment = assess_path_feasibility(plan, path)
        if assessment.feasibility == CandidateFeasibility.UNKNOWN:
            raise ProbePreflightInputError(
                f"Probe candidate is not known-feasible: {assessment.feasibility.value}"
            )
        validate_physical_path(
            fresh_snapshot.configured_topology,
            path,
            scope.source,
            scope.destination,
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ProbePreflightInputError):
            raise
        raise ProbePreflightInputError(f"Probe path validation failed: {exc}") from exc

    planned_fingerprint = canonical_topology_fingerprint(
        planned_snapshot.configured_topology
    )
    fresh_fingerprint = canonical_topology_fingerprint(
        fresh_snapshot.configured_topology
    )
    planned_snapshot_fp = topology_snapshot_fingerprint(planned_snapshot)
    fresh_snapshot_fp = topology_snapshot_fingerprint(fresh_snapshot)
    feasibility_reasons = (
        assessment.reasons
        if assessment.feasibility == CandidateFeasibility.PROVEN_INFEASIBLE
        else ()
    )
    validation_reasons: list[str] = []

    if planned_fingerprint != canonical_topology_fingerprint(plan.request.topology):
        validation_reasons.append("Planned snapshot does not match the plan topology.")
    if fresh_fingerprint != planned_fingerprint:
        validation_reasons.append("Topology changed since planning.")
    if (
        planned_snapshot.status != SnapshotStatus.COMPLETE
        or fresh_snapshot.status != SnapshotStatus.COMPLETE
    ):
        validation_reasons.append("Planned or fresh topology snapshot is not complete.")
    if planned_snapshot.captured_at > fresh_snapshot.captured_at:
        validation_reasons.append("Fresh snapshot predates the planned snapshot.")
    if fresh_snapshot.captured_at > checked_at:
        validation_reasons.append("Fresh snapshot is future-dated.")
    if checked_at - fresh_snapshot.captured_at > max_snapshot_age:
        validation_reasons.append("Fresh snapshot exceeds the permitted maximum age.")

    for snapshot in (planned_snapshot, fresh_snapshot):
        expected_dpids = set(snapshot.configured_topology.switches.values())
        if set(snapshot.connected_switch_dpids) != expected_dpids:
            validation_reasons.append(
                "Snapshot does not show exactly the configured switches connected."
            )
        if any(
            not port.present or not port.admin_up or not port.link_up
            for port in snapshot.port_states
        ):
            validation_reasons.append(
                "Snapshot contains a missing or non-operational data port."
            )

    return ProbePreflightResult(
        candidate_id=physical_candidate_id(plan, path),
        path_fingerprint=physical_path_fingerprint(path),
        status=(
            "FAILED"
            if validation_reasons
            else "PROVEN_INFEASIBLE"
            if assessment.feasibility == CandidateFeasibility.PROVEN_INFEASIBLE
            else "PASSED"
        ),
        planned_snapshot_fingerprint=planned_snapshot_fp,
        fresh_snapshot_fingerprint=fresh_snapshot_fp,
        reasons=tuple(feasibility_reasons) + tuple(validation_reasons),
    )
