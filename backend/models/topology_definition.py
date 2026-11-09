"""Validated, versioned user-managed topology definitions."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import ipaddress
import math
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.models.network import TopologyGraph


class TopologyMode(str, Enum):
    DESIGN = "DESIGN"
    MININET = "MININET"
    LIVE = "LIVE"


class NodePosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=-100000, le=100000, allow_inf_nan=False)
    y: float = Field(ge=-100000, le=100000, allow_inf_nan=False)


class TopologyDefinitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    mode: Literal[TopologyMode.DESIGN] = TopologyMode.DESIGN
    graph: TopologyGraph
    positions: dict[str, NodePosition] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Topology name cannot be blank.")
        return value

    @model_validator(mode="after")
    def validate_topology(self) -> "TopologyDefinitionInput":
        _validate_design_graph(self.graph)
        node_names = set(self.graph.switches) | set(self.graph.hosts)
        if set(self.positions) - node_names:
            raise ValueError("Layout positions may only reference topology nodes.")
        if not self.positions:
            self.positions = _default_positions(node_names, self.graph.hosts)
        return self


class TopologyDefinition(TopologyDefinitionInput):
    id: UUID
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class TopologyCatalogItem(BaseModel):
    id: UUID
    name: str
    version: int
    mode: TopologyMode
    active: bool
    node_count: int
    link_count: int
    updated_at: datetime


class TopologyUpdateRequest(TopologyDefinitionInput):
    expected_version: int = Field(ge=1)


class TopologyRenameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    expected_version: int = Field(ge=1)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Topology name cannot be blank.")
        return value


class TopologyActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int | None = Field(default=None, ge=1)


class TopologyDuplicateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Topology name cannot be blank.")
        return value


class ActiveTopologyResponse(BaseModel):
    topology: TopologyDefinition | None
    active: bool


def _validate_design_graph(graph: TopologyGraph) -> None:
    if not graph.switches:
        raise ValueError("A topology must contain at least one OpenFlow switch.")
    if set(graph.switches) & set(graph.hosts):
        raise ValueError("Host and switch names must be distinct.")
    if len(set(graph.switches.values())) != len(graph.switches):
        raise ValueError("Switch DPIDs must be unique.")
    if any(not name.strip() for name in graph.switches):
        raise ValueError("Switch names cannot be blank.")
    if any(dpid <= 0 for dpid in graph.switches.values()):
        raise ValueError("Switch DPIDs must be positive integers.")

    used_ports: set[tuple[str, int]] = set()

    def claim_port(switch: str, port: int, owner: str) -> None:
        if switch not in graph.switches:
            raise ValueError(f"{owner} references unknown switch {switch!r}.")
        if type(port) is not int or port <= 0:
            raise ValueError(f"{owner} must use a positive switch port.")
        key = (switch, port)
        if key in used_ports:
            raise ValueError(f"Switch port {switch}:{port} is assigned more than once.")
        configured_ports = graph.switch_ports.get(switch)
        if configured_ports is not None and port not in configured_ports:
            raise ValueError(
                f"Switch port {switch}:{port} is not in the configured port inventory."
            )
        used_ports.add(key)

    unknown_port_lists = set(graph.switch_ports) - set(graph.switches)
    if unknown_port_lists:
        raise ValueError(
            "Port inventories reference unknown switches: "
            + ", ".join(sorted(unknown_port_lists))
        )
    for switch, ports in graph.switch_ports.items():
        if len(ports) != len(set(ports)) or any(port <= 0 for port in ports):
            raise ValueError(
                f"Switch {switch!r} ports must be unique positive integers."
            )

    host_ips: set[str] = set()
    host_macs: set[str] = set()
    for host_name, host in graph.hosts.items():
        if host_name != host.name or not _valid_node_name(host_name):
            raise ValueError(f"Invalid host name {host_name!r}.")
        try:
            normalized_ip = str(ipaddress.ip_address(host.ip))
        except ValueError as exc:
            raise ValueError(f"Host {host_name!r} has an invalid IP address.") from exc
        if normalized_ip in host_ips:
            raise ValueError(f"Host {host_name!r} has a duplicate IP address.")
        host_ips.add(normalized_ip)
        if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", host.mac):
            raise ValueError(f"Host {host_name!r} has an invalid MAC address.")
        normalized_mac = host.mac.lower()
        if normalized_mac in host_macs:
            raise ValueError(f"Host {host_name!r} has a duplicate MAC address.")
        host_macs.add(normalized_mac)
        if (
            host.attachment_capacity_mbps is not None
            and (
                not math.isfinite(host.attachment_capacity_mbps)
                or host.attachment_capacity_mbps <= 0
            )
        ):
            raise ValueError(
                f"Host {host_name!r} attachment capacity must be positive."
            )
        if (
            host.attachment_delay_ms is not None
            and (
                not math.isfinite(host.attachment_delay_ms)
                or host.attachment_delay_ms < 0
            )
        ):
            raise ValueError(
                f"Host {host_name!r} attachment delay cannot be negative."
            )
        if (
            host.attachment_packet_loss_percent is not None
            and (
                not math.isfinite(host.attachment_packet_loss_percent)
                or not 0 <= host.attachment_packet_loss_percent <= 100
            )
        ):
            raise ValueError(
                f"Host {host_name!r} attachment packet loss must be between 0 and 100 percent."
            )
        claim_port(host.switch, host.switch_port, f"Host {host_name!r}")

    for switch, dpid in graph.switches.items():
        if not _valid_node_name(switch):
            raise ValueError(f"Invalid switch name {switch!r}.")
        if type(dpid) is not int:
            raise ValueError(f"Switch {switch!r} DPID must be an integer.")

    link_identities: set[tuple[tuple[str, int], tuple[str, int]]] = set()
    for index, link in enumerate(graph.links):
        if (
            link.node_a not in graph.switches
            or link.node_b not in graph.switches
            or link.node_a == link.node_b
        ):
            raise ValueError(f"Link {index + 1} must connect two distinct known switches.")
        first = (link.node_a, link.port_a)
        second = (link.node_b, link.port_b)
        identity = tuple(sorted((first, second)))
        if identity in link_identities:
            raise ValueError(f"Duplicate physical link between {first} and {second}.")
        link_identities.add(identity)
        claim_port(link.node_a, link.port_a, f"Link {index + 1}")
        claim_port(link.node_b, link.port_b, f"Link {index + 1}")
        if link.bw_mbps is not None and (
            not math.isfinite(link.bw_mbps) or link.bw_mbps <= 0
        ):
            raise ValueError("Configured link capacity must be greater than zero.")
        if link.delay_ms is not None and (
            not math.isfinite(link.delay_ms) or link.delay_ms < 0
        ):
            raise ValueError("Configured link delay cannot be negative.")
        if (
            link.packet_loss_percent is not None
            and (
                not math.isfinite(link.packet_loss_percent)
                or not 0 <= link.packet_loss_percent <= 100
            )
        ):
            raise ValueError("Configured packet loss must be between 0 and 100 percent.")


def _valid_node_name(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", value))


def _default_positions(
    node_names: set[str],
    hosts: dict[str, object],
) -> dict[str, NodePosition]:
    positions: dict[str, NodePosition] = {}
    switches = sorted(node_names - set(hosts))
    for index, name in enumerate(switches):
        positions[name] = NodePosition(x=240 + (index % 4) * 210, y=100 + (index // 4) * 180)
    for index, name in enumerate(sorted(set(hosts))):
        positions[name] = NodePosition(x=35 + (index % 2) * 1050, y=130 + (index // 2) * 150)
    return positions
