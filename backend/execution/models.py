"""Immutable contracts for non-writing execution preflight."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from backend.models.network import TopologyGraph
from backend.planner.models import Plan
from backend.planner.path_enumeration import (
    EnumeratedPath,
    InvalidPathRequestError,
    InvalidTopologyError,
    PathEnumerationResult,
    enumerate_candidate_paths,
)


class _ExecutionModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    @model_validator(mode="before")
    @classmethod
    def snapshot_input_state(cls, value: Any) -> Any:
        return deepcopy(value)

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
        if name in type(self).model_fields and isinstance(value, BaseModel):
            return deepcopy(value)
        return value

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> "_ExecutionModel":
        if update is not None:
            raise TypeError(
                "Execution models do not support model_copy(update=...); "
                "construct and validate a new model instead"
            )
        return super().model_copy(deep=deep)


class SnapshotStatus(str, Enum):
    COMPLETE = "COMPLETE"
    UNAVAILABLE = "UNAVAILABLE"
    INCOMPLETE = "INCOMPLETE"
    CONTRADICTORY = "CONTRADICTORY"


class PreflightStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class PortOperationalState(_ExecutionModel):
    """Controller-reported state for one configured data port.

    The snapshot producer obtains port presence/admin/link state from the
    controller's OpenFlow port-description response. Missing entries or
    unknown flags make a snapshot incomplete rather than implying the port
    is operational.
    """

    dpid: StrictInt = Field(gt=0)
    port_no: StrictInt = Field(gt=0)
    present: StrictBool
    admin_up: StrictBool | None
    link_up: StrictBool | None

    @model_validator(mode="after")
    def validate_presence_and_state(self) -> "PortOperationalState":
        if self.present and (self.admin_up is None or self.link_up is None):
            raise ValueError("A present port requires known administrative and link state")
        if not self.present and (self.admin_up is not None or self.link_up is not None):
            raise ValueError("An absent port cannot have operational state")
        return self


class TopologySnapshot(_ExecutionModel):
    """Injected topology evidence; this model performs no discovery.

    ``configured_topology`` is sourced from the Mininet/configuration
    inventory. ``connected_switch_dpids`` comes from the controller's
    connected-datapath roster. ``port_states`` comes from controller
    OpenFlow port descriptions. The configured inventory alone is never
    evidence of operational connectivity.
    """

    configured_topology: TopologyGraph
    captured_at: datetime
    status: SnapshotStatus
    connected_switch_dpids: tuple[StrictInt, ...] = ()
    port_states: tuple[PortOperationalState, ...] = ()

    @model_validator(mode="after")
    def validate_snapshot(self) -> "TopologySnapshot":
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        if len(self.connected_switch_dpids) != len(set(self.connected_switch_dpids)):
            raise ValueError("connected switch DPIDs must be unique")
        port_keys = [(port.dpid, port.port_no) for port in self.port_states]
        if len(port_keys) != len(set(port_keys)):
            raise ValueError("port state entries must be unique by DPID and port")

        if self.status == SnapshotStatus.COMPLETE:
            expected_ports = _expected_topology_ports(self.configured_topology)
            if set(port_keys) != expected_ports:
                raise ValueError(
                    "A complete snapshot must describe every configured topology port exactly"
                )
        return self

    @property
    def topology_fingerprint(self) -> str:
        from backend.execution.preflight import canonical_topology_fingerprint

        return canonical_topology_fingerprint(self.configured_topology)

    @property
    def snapshot_fingerprint(self) -> str:
        from backend.execution.preflight import topology_snapshot_fingerprint

        return topology_snapshot_fingerprint(self)


class PreflightResult(_ExecutionModel):
    status: PreflightStatus
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
    planned_topology_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    fresh_topology_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    planned_snapshot_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    fresh_snapshot_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    originating_plan: Plan
    enumeration: PathEnumerationResult
    selection_candidate_limit: int = Field(gt=0)
    selected_path: EnumeratedPath
    planned_snapshot: TopologySnapshot
    fresh_snapshot: TopologySnapshot
    checked_at: datetime
    max_snapshot_age: timedelta
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_result(self) -> "PreflightResult":
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("checked_at must be timezone-aware")
        if self.max_snapshot_age < timedelta(0):
            raise ValueError("max_snapshot_age must not be negative")

        from backend.execution.preflight import (
            canonical_topology_fingerprint,
            topology_snapshot_fingerprint,
        )
        from backend.models.fingerprints import model_fingerprint
        from backend.planner.candidate_selection import physical_candidate_id
        from backend.planner.constraint_evaluation import (
            physical_path_fingerprint,
            planning_request_fingerprint,
        )
        from backend.planner.path_enumeration import validate_physical_path

        plan = self.originating_plan
        if self.enumeration.candidate_limit != self.selection_candidate_limit:
            raise ValueError(
                "Preflight enumeration candidate limit does not match the originating selection"
            )
        validate_authoritative_enumeration(plan, self.enumeration)
        expected_request_fingerprint = planning_request_fingerprint(plan.request)
        expected_plan_fingerprint = model_fingerprint(plan)
        expected_path_fingerprint = physical_path_fingerprint(self.selected_path)
        expected_candidate_id = physical_candidate_id(plan, self.selected_path)
        planned_topology = canonical_topology_fingerprint(
            self.planned_snapshot.configured_topology
        )
        fresh_topology = canonical_topology_fingerprint(
            self.fresh_snapshot.configured_topology
        )
        planned_snapshot_fingerprint = topology_snapshot_fingerprint(
            self.planned_snapshot
        )
        fresh_snapshot_fingerprint = topology_snapshot_fingerprint(
            self.fresh_snapshot
        )
        scope = plan.request.intent.scope

        if self.request_fingerprint != expected_request_fingerprint:
            raise ValueError("Preflight request fingerprint does not match its plan")
        if self.plan_fingerprint != expected_plan_fingerprint:
            raise ValueError("Preflight plan fingerprint does not match its plan")
        if self.path_fingerprint != expected_path_fingerprint:
            raise ValueError("Preflight path fingerprint does not match its selected path")
        if self.candidate_id != expected_candidate_id:
            raise ValueError("Preflight candidate ID does not match its plan and path")
        if self.planned_topology_fingerprint != planned_topology:
            raise ValueError("Planned topology fingerprint does not match its snapshot")
        if self.fresh_topology_fingerprint != fresh_topology:
            raise ValueError("Fresh topology fingerprint does not match its snapshot")
        if self.planned_snapshot_fingerprint != planned_snapshot_fingerprint:
            raise ValueError("Planned snapshot fingerprint does not match its evidence")
        if self.fresh_snapshot_fingerprint != fresh_snapshot_fingerprint:
            raise ValueError("Fresh snapshot fingerprint does not match its evidence")
        if (
            self.status == PreflightStatus.PASSED
            and planned_topology
            != canonical_topology_fingerprint(plan.request.topology)
        ):
            raise ValueError("PASSED preflight planned snapshot does not match the plan")
        if (
            self.enumeration.source != scope.source
            or self.enumeration.destination != scope.destination
            or self.selected_path not in self.enumeration.paths
        ):
            raise ValueError("Selected path is not in the endpoint-bound enumeration")

        validate_physical_path(
            plan.request.topology,
            self.selected_path,
            scope.source,
            scope.destination,
        )

        if self.status == PreflightStatus.PASSED:
            if self.reasons:
                raise ValueError("PASSED preflight cannot contain failure reasons")
            if (
                self.planned_topology_fingerprint
                != self.fresh_topology_fingerprint
            ):
                raise ValueError(
                    "PASSED preflight requires matching topology fingerprints"
                )
            if (
                self.planned_snapshot.status != SnapshotStatus.COMPLETE
                or self.fresh_snapshot.status != SnapshotStatus.COMPLETE
            ):
                raise ValueError("PASSED preflight requires complete snapshots")
            if self.planned_snapshot.captured_at > self.checked_at:
                raise ValueError("PASSED preflight cannot use a future planned snapshot")
            if self.fresh_snapshot.captured_at > self.checked_at:
                raise ValueError("PASSED preflight cannot use a future snapshot")
            if self.checked_at - self.fresh_snapshot.captured_at > self.max_snapshot_age:
                raise ValueError("PASSED preflight snapshot exceeds its maximum age")
            if self.planned_snapshot.captured_at > self.fresh_snapshot.captured_at:
                raise ValueError("PASSED preflight snapshot predates the planned snapshot")

            for snapshot in (self.planned_snapshot, self.fresh_snapshot):
                expected_dpids = set(snapshot.configured_topology.switches.values())
                if set(snapshot.connected_switch_dpids) != expected_dpids:
                    raise ValueError(
                        "PASSED preflight requires all configured switches connected"
                    )
                if any(
                    not port.present or not port.admin_up or not port.link_up
                    for port in snapshot.port_states
                ):
                    raise ValueError(
                        "PASSED preflight requires every configured port operational"
                    )
            validate_physical_path(
                self.fresh_snapshot.configured_topology,
                self.selected_path,
                scope.source,
                scope.destination,
            )
        elif not self.reasons:
            raise ValueError("A non-PASSED preflight result requires an explanation")
        return self


def validate_authoritative_enumeration(
    plan: Plan,
    enumeration: PathEnumerationResult,
) -> PathEnumerationResult:
    """Recompute and compare the exact Phase 3B enumeration for a plan."""
    if not isinstance(plan, Plan) or not isinstance(enumeration, PathEnumerationResult):
        raise ValueError("A validated plan and path enumeration are required")
    scope = plan.request.intent.scope
    try:
        expected = enumerate_candidate_paths(
            plan.request.topology,
            scope.source,
            scope.destination,
            enumeration.candidate_limit,
        )
    except (InvalidPathRequestError, InvalidTopologyError, ValueError) as error:
        raise ValueError(f"Cannot recompute the plan path enumeration: {error}") from error

    if (
        enumeration.source != expected.source
        or enumeration.destination != expected.destination
        or enumeration.candidate_limit != expected.candidate_limit
        or enumeration.paths != expected.paths
        or enumeration.truncated != expected.truncated
    ):
        raise ValueError(
            "Path enumeration does not match the authoritative topology-derived enumeration"
        )
    return expected


def _expected_topology_ports(graph: TopologyGraph) -> set[tuple[int, int]]:
    """Return all configured host-facing and switch-link data ports."""
    dpids = list(graph.switches.values())
    if any(type(dpid) is not int or dpid <= 0 for dpid in dpids):
        raise ValueError("Configured switch DPIDs must be unique positive integers")
    if len(dpids) != len(set(dpids)):
        raise ValueError("Configured switch DPIDs must be unique positive integers")

    ports: list[tuple[int, int]] = []
    for name, host in graph.hosts.items():
        if host.name != name or host.switch not in graph.switches:
            raise ValueError("Configured host attachment is inconsistent")
        ports.append((graph.switches[host.switch], host.switch_port))

    for link in graph.links:
        if link.node_a not in graph.switches or link.node_b not in graph.switches:
            raise ValueError("Configured switch link references an unknown switch")
        ports.extend(
            (
                (graph.switches[link.node_a], link.port_a),
                (graph.switches[link.node_b], link.port_b),
            )
        )

    if any(type(port) is not int or port <= 0 for _, port in ports):
        raise ValueError("Configured topology ports must be positive integers")
    if len(ports) != len(set(ports)):
        raise ValueError("Configured topology reuses a switch port")
    return set(ports)
