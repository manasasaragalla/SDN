"""Pure identity and freshness checks before a future execution attempt."""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json

from backend.execution.models import (
    PreflightResult,
    PreflightStatus,
    SnapshotStatus,
    TopologySnapshot,
    validate_authoritative_enumeration,
)
from backend.models.network import TopologyGraph
from backend.planner.candidate_selection import (
    CandidateSelectionResult,
    SelectionStatus,
    assess_path_feasibility,
    physical_candidate_id,
)
from backend.models.fingerprints import model_fingerprint
from backend.planner.constraint_evaluation import (
    physical_path_fingerprint,
    planning_request_fingerprint,
)
from backend.planner.path_enumeration import validate_physical_path


class PreflightInputError(ValueError):
    """Raised when preflight is not given one valid selected candidate."""


def canonical_topology_fingerprint(graph: TopologyGraph) -> str:
    """Fingerprint configured topology while ignoring only input ordering.

    Switch/host identities, DPIDs, host attachments and addresses, physical
    endpoint/port pairs, paired interface names, and configured capacity are
    included. Switch-link endpoint order and collection/dictionary order are
    normalized because those are representational, not semantic, differences.
    """
    if not isinstance(graph, TopologyGraph):
        raise TypeError("graph must be a TopologyGraph")

    switches = sorted(graph.switches.items())
    hosts = sorted(
        (
            name,
            host.name,
            host.ip,
            host.mac,
            host.switch,
            host.switch_port,
        )
        for name, host in graph.hosts.items()
    )

    links = []
    for link in graph.links:
        endpoints = sorted(
            (
                (link.node_a, link.port_a, link.intf_a),
                (link.node_b, link.port_b, link.intf_b),
            )
        )
        links.append(
            {
                "endpoints": endpoints,
                "bw_mbps": link.bw_mbps,
            }
        )
    links.sort(
        key=lambda item: json.dumps(
            item,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    )

    payload = {
        "switches": switches,
        "hosts": hosts,
        "links": links,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def topology_snapshot_fingerprint(snapshot: TopologySnapshot) -> str:
    """Fingerprint configured topology plus the time-bound operational view."""
    if not isinstance(snapshot, TopologySnapshot):
        raise TypeError("snapshot must be a TopologySnapshot")
    payload = {
        "topology_fingerprint": canonical_topology_fingerprint(
            snapshot.configured_topology
        ),
        "captured_at": snapshot.captured_at.isoformat(),
        "status": snapshot.status.value,
        "connected_switch_dpids": sorted(snapshot.connected_switch_dpids),
        "port_states": sorted(
            (
                port.dpid,
                port.port_no,
                port.present,
                port.admin_up,
                port.link_up,
            )
            for port in snapshot.port_states
        ),
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_preflight(
    selection: CandidateSelectionResult,
    planned_snapshot: TopologySnapshot,
    fresh_snapshot: TopologySnapshot,
    *,
    checked_at: datetime,
    max_snapshot_age: timedelta,
) -> PreflightResult:
    """Validate one selected physical candidate against injected snapshots.

    This function performs no network reads or writes and never enumerates
    paths or selects a replacement candidate. Any non-PASSED result blocks
    deployment.
    """
    if not isinstance(selection, CandidateSelectionResult):
        raise PreflightInputError("selection must be a CandidateSelectionResult")
    if (
        not isinstance(planned_snapshot, TopologySnapshot)
        or not isinstance(fresh_snapshot, TopologySnapshot)
    ):
        raise PreflightInputError("planned and fresh snapshots are required")
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise PreflightInputError("checked_at must be timezone-aware")
    if not isinstance(max_snapshot_age, timedelta) or max_snapshot_age < timedelta(0):
        raise PreflightInputError("max_snapshot_age must be a non-negative timedelta")
    if (
        selection.status != SelectionStatus.SELECTED
        or selection.selected_candidate is None
    ):
        raise PreflightInputError("preflight requires exactly one selected candidate")

    candidate = selection.selected_candidate
    if candidate not in selection.candidates:
        raise PreflightInputError("selected candidate is not in the validated candidate set")
    try:
        request_fingerprint = planning_request_fingerprint(
            selection.originating_plan.request
        )
        plan_fingerprint = model_fingerprint(selection.originating_plan)
        if (
            selection.request_fingerprint != request_fingerprint
            or selection.plan_fingerprint != plan_fingerprint
        ):
            raise PreflightInputError(
                "selection request or plan identity does not match its originating plan"
            )
        validate_authoritative_enumeration(
            selection.originating_plan,
            selection.enumeration,
        )
        expected_path_fingerprint = physical_path_fingerprint(candidate.path)
        if candidate.path_fingerprint != expected_path_fingerprint:
            raise PreflightInputError(
                "selected candidate path fingerprint does not match its physical path"
            )
        matching_candidates = [
            item
            for item in selection.candidates
            if item.candidate_id == candidate.candidate_id
        ]
        if len(matching_candidates) != 1:
            raise PreflightInputError(
                "selected candidate identity is not unique in the selection result"
            )
        candidate_entry = matching_candidates[0]
        if (
            candidate_entry != candidate
        ):
            raise PreflightInputError(
                "selected candidate does not match its complete candidate-set entry"
            )
        expected_candidate_id = physical_candidate_id(
            selection.originating_plan, candidate.path
        )
        if expected_candidate_id != candidate.candidate_id:
            raise PreflightInputError(
                "selected candidate ID does not bind its exact physical path"
            )
        if candidate.path not in selection.enumeration.paths:
            raise PreflightInputError(
                "selected physical path is not in the validated enumeration"
            )
        scope = selection.originating_plan.request.intent.scope
        if (
            selection.enumeration.source != scope.source
            or selection.enumeration.destination != scope.destination
        ):
            raise PreflightInputError(
                "validated enumeration endpoints do not match the originating request"
            )
        assessment = assess_path_feasibility(
            selection.originating_plan,
            candidate.path,
        )
        if candidate.feasibility != assessment.feasibility:
            raise PreflightInputError(
                "selected candidate feasibility does not match its physical path assessment"
            )
        evaluation_candidates = {
            item.candidate_id: item
            for item in selection.plan_evaluation.candidates
        }
        evaluated_candidate = evaluation_candidates.get(candidate.candidate_id)
        if (
            evaluated_candidate is None
            or candidate.hard_constraint_status != evaluated_candidate.status
        ):
            raise PreflightInputError(
                "selected candidate constraint status does not match its plan evaluation"
            )
        validate_physical_path(
            selection.originating_plan.request.topology,
            candidate.path,
            selection.enumeration.source,
            selection.enumeration.destination,
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, PreflightInputError):
            raise
        raise PreflightInputError(f"selected physical path is invalid: {error}") from error

    try:
        planned_fingerprint = canonical_topology_fingerprint(
            planned_snapshot.configured_topology
        )
        fresh_fingerprint = canonical_topology_fingerprint(
            fresh_snapshot.configured_topology
        )
        request_topology_fingerprint = canonical_topology_fingerprint(
            selection.originating_plan.request.topology
        )
        planned_snapshot_fingerprint = topology_snapshot_fingerprint(planned_snapshot)
        fresh_snapshot_fingerprint = topology_snapshot_fingerprint(fresh_snapshot)
    except (TypeError, ValueError) as error:
        raise PreflightInputError(f"topology snapshot is malformed: {error}") from error

    def result(status: PreflightStatus, *reasons: str) -> PreflightResult:
        return PreflightResult(
            status=status,
            candidate_id=candidate.candidate_id,
            request_fingerprint=request_fingerprint,
            plan_fingerprint=plan_fingerprint,
            path_fingerprint=expected_path_fingerprint,
            planned_topology_fingerprint=planned_fingerprint,
            fresh_topology_fingerprint=fresh_fingerprint,
            planned_snapshot_fingerprint=planned_snapshot_fingerprint,
            fresh_snapshot_fingerprint=fresh_snapshot_fingerprint,
            originating_plan=selection.originating_plan,
            enumeration=selection.enumeration,
            selection_candidate_limit=selection.enumeration.candidate_limit,
            selected_path=candidate.path,
            planned_snapshot=planned_snapshot,
            fresh_snapshot=fresh_snapshot,
            checked_at=checked_at,
            max_snapshot_age=max_snapshot_age,
            reasons=tuple(reasons),
        )

    if request_topology_fingerprint != planned_fingerprint:
        return result(
            PreflightStatus.FAILED,
            "Planned topology snapshot does not match the originating planning request.",
        )
    if (
        planned_snapshot.status != SnapshotStatus.COMPLETE
        or fresh_snapshot.status != SnapshotStatus.COMPLETE
    ):
        return result(
            PreflightStatus.UNKNOWN,
            "Planned or fresh topology snapshot is unavailable, incomplete, or contradictory.",
        )
    if fresh_snapshot.captured_at > checked_at:
        return result(
            PreflightStatus.UNKNOWN,
            "Fresh topology snapshot was captured after the preflight check time.",
        )
    if checked_at - fresh_snapshot.captured_at > max_snapshot_age:
        return result(
            PreflightStatus.UNKNOWN,
            "Fresh topology snapshot is older than the permitted maximum age.",
        )
    if planned_snapshot.captured_at > fresh_snapshot.captured_at:
        return result(
            PreflightStatus.UNKNOWN,
            "Fresh topology snapshot predates the planned topology snapshot.",
        )
    if planned_fingerprint != fresh_fingerprint:
        return result(
            PreflightStatus.FAILED,
            "Configured topology changed since planning; candidate cannot be substituted.",
        )

    expected_dpids = set(fresh_snapshot.configured_topology.switches.values())
    if set(fresh_snapshot.connected_switch_dpids) != expected_dpids:
        return result(
            PreflightStatus.FAILED,
            "Controller connectivity does not include exactly the configured switches.",
        )
    if any(
        not port.present
        or not port.admin_up
        or not port.link_up
        for port in fresh_snapshot.port_states
    ):
        return result(
            PreflightStatus.FAILED,
            "At least one configured topology port is missing, administratively down, or operationally down.",
        )
    try:
        validate_physical_path(
            fresh_snapshot.configured_topology,
            candidate.path,
            selection.enumeration.source,
            selection.enumeration.destination,
        )
    except (TypeError, ValueError) as error:
        return result(
            PreflightStatus.FAILED,
            f"Selected physical path is invalid in the fresh topology: {error}",
        )

    return result(
        PreflightStatus.PASSED,
    )
