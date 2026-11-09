"""Topology graph model. Built from a live Mininet network (see
backend/decision/topology_graph.py) -- see docs/adr-002 for why this
reads the actual running topology directly rather than via LLDP
discovery. Nothing in this module talks to Mininet itself; it's a plain
data model plus pure graph algorithms, so it's testable with a hand-built
graph and no root/network privileges."""
from __future__ import annotations

import math
from typing import Optional

from pydantic import BaseModel, Field, StrictInt, field_validator


class Host(BaseModel):
    name: str
    ip: str
    mac: str
    switch: str  # name of the switch this host is directly connected to
    switch_port: int  # port on that switch facing this host
    attachment_capacity_mbps: Optional[float] = None
    attachment_delay_ms: Optional[float] = None
    attachment_packet_loss_percent: Optional[float] = None
    attachment_admin_up: bool | None = None


class Link(BaseModel):
    """A bidirectional switch-to-switch link. Port numbers are the real
    OVS ofport values on each end, not assumed sequential numbers.

    bw_mbps and the intf_* names are optional because they're only
    populated when the graph was built from a live Mininet network with
    TCLink (backend/decision/topology_graph.py) -- a hand-built graph in a
    unit test (e.g. tests/test_topology_graph.py) simply omits them, and
    anything that needs them (the bandwidth decision layer's static
    capacity check, the rate_limit compiler/deployment) is exercised
    against real topology-graph data, either from a real Mininet build or
    a test fixture that sets them explicitly."""

    node_a: str
    port_a: int
    node_b: str
    port_b: int
    bw_mbps: Optional[float] = None
    delay_ms: Optional[float] = None
    packet_loss_percent: Optional[float] = None
    admin_up: bool | None = None
    intf_a: Optional[str] = None
    intf_b: Optional[str] = None

    @field_validator("bw_mbps", mode="before")
    @classmethod
    def reject_boolean_capacity(cls, value):
        if isinstance(value, bool):
            raise ValueError("bw_mbps must be a numeric capacity, not a boolean")
        return value

    def other_end(self, node: str) -> str:
        if node == self.node_a:
            return self.node_b
        if node == self.node_b:
            return self.node_a
        raise ValueError(f"{node} is not an endpoint of this link")

    def port_facing(self, from_node: str) -> int:
        """The port ON from_node that this link uses."""
        if from_node == self.node_a:
            return self.port_a
        if from_node == self.node_b:
            return self.port_b
        raise ValueError(f"{from_node} is not an endpoint of this link")

    def intf_facing(self, from_node: str) -> str:
        """The OVS interface name ON from_node that this link uses (e.g.
        "s2-eth2") -- needed to target ovs-vsctl QoS commands at the right
        interface, since interface names aren't guaranteed to be a simple
        function of the port number."""
        if from_node == self.node_a:
            name = self.intf_a
        elif from_node == self.node_b:
            name = self.intf_b
        else:
            raise ValueError(f"{from_node} is not an endpoint of this link")
        if not name:
            raise ValueError(f"no interface name recorded for this link at {from_node} "
                              "(graph was not built from a live Mininet network)")
        return name


class TopologyGraph(BaseModel):
    """switches: name -> dpid (as Ryu/ofctl_rest expects it, an int)."""

    switches: dict[str, StrictInt]
    hosts: dict[str, Host]
    links: list[Link]
    switch_ports: dict[str, list[StrictInt]] = Field(default_factory=dict)

    def neighbors(self, switch: str) -> list[str]:
        result = []
        for link in self.links:
            if link.node_a == switch:
                result.append(link.node_b)
            elif link.node_b == switch:
                result.append(link.node_a)
        return result

    def port_between(self, from_switch: str, to_switch: str) -> int:
        """The port number on from_switch that leads directly to to_switch."""
        for link in self.links:
            if link.node_a == from_switch and link.node_b == to_switch:
                return link.port_a
            if link.node_b == from_switch and link.node_a == to_switch:
                return link.port_b
        raise ValueError(f"no direct link between {from_switch} and {to_switch}")

    def link_between(self, from_switch: str, to_switch: str) -> Link:
        """The Link object joining two directly-connected switches (either
        order) -- used where more than just the port number is needed
        (bandwidth, interface name)."""
        for link in self.links:
            if {link.node_a, link.node_b} == {from_switch, to_switch}:
                return link
        raise ValueError(f"no direct link between {from_switch} and {to_switch}")

    def path_capacity_mbps(self, path: list[str]) -> Optional[float]:
        """Return capacity only when every node-pair hop identifies one link.

        Node-only paths cannot select among parallel physical links. In that
        case, or when any hop has missing or invalid capacity, return None.
        Use ``physical_path_capacity_mbps`` from the path enumerator when the
        exact physical candidate is available.
        """
        switch_path = path[1:-1]
        capacities: list[float] = []
        for a, b in zip(switch_path, switch_path[1:]):
            matching = [
                link
                for link in self.links
                if {link.node_a, link.node_b} == {a, b}
            ]
            if len(matching) != 1:
                return None
            capacity = matching[0].bw_mbps
            if (
                capacity is None
                or isinstance(capacity, bool)
                or not math.isfinite(capacity)
                or capacity < 0
            ):
                return None
            capacities.append(capacity)
        return min(capacities) if capacities else None

    def maximum_possible_path_capacity_mbps(
        self,
        path: list[str],
    ) -> Optional[float]:
        """Return an upper bound for any physical realization of a node path.

        For each switch hop, this uses the highest capacity among its parallel
        links, then takes the bottleneck across hops. This value is only
        suitable for existential topology checks (whether some physical
        realization could meet a lower bound); it is not the capacity of any
        candidate unless that candidate's physical links are independently
        identified. Missing or invalid metadata on any parallel link returns
        None so the upper bound cannot falsely prove infeasibility.
        """
        switch_path = path[1:-1]
        hop_upper_bounds: list[float] = []
        for a, b in zip(switch_path, switch_path[1:]):
            matching = [
                link
                for link in self.links
                if {link.node_a, link.node_b} == {a, b}
            ]
            if not matching:
                return None
            capacities = [link.bw_mbps for link in matching]
            if any(
                capacity is None
                or isinstance(capacity, bool)
                or not math.isfinite(capacity)
                or capacity < 0
                for capacity in capacities
            ):
                return None
            hop_upper_bounds.append(max(capacities))
        return min(hop_upper_bounds) if hop_upper_bounds else None

    def all_simple_paths(self, source_host: str, dest_host: str, max_hops: int = 6) -> list[list[str]]:
        """All simple (no repeated node) paths from source_host to
        dest_host, expressed as [host, switch, switch, ..., switch, host].
        Small, bounded search -- this project's topologies are a handful
        of switches, not a datacenter fabric, so plain DFS is the right
        amount of algorithm."""
        if source_host not in self.hosts or dest_host not in self.hosts:
            raise ValueError("unknown host")

        start_switch = self.hosts[source_host].switch
        end_switch = self.hosts[dest_host].switch

        paths: list[list[str]] = []

        def dfs(current: str, visited: set[str], path: list[str]) -> None:
            if len(path) - 1 > max_hops:
                return
            if current == end_switch:
                paths.append(list(path))
                return
            for neighbor in self.neighbors(current):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                path.append(neighbor)
                dfs(neighbor, visited, path)
                path.pop()
                visited.remove(neighbor)

        dfs(start_switch, {start_switch}, [start_switch])

        return [[source_host] + p + [dest_host] for p in paths]

    def validate_path(self, path: list[str]) -> Optional[str]:
        """Returns None if the path is valid (every node exists, every
        consecutive pair is actually linked/attached), or a human-readable
        reason it is not. Used by the pre-deployment validator (Step 5)."""
        if len(path) < 3:
            return "path must include at least source host, one switch, and destination host"

        source_host, *switch_path, dest_host = path

        if source_host not in self.hosts:
            return f"unknown source host: {source_host}"
        if dest_host not in self.hosts:
            return f"unknown destination host: {dest_host}"

        for node in switch_path:
            if node not in self.switches:
                return f"unknown switch in path: {node}"

        if switch_path[0] != self.hosts[source_host].switch:
            return f"path does not start at {source_host}'s attached switch ({self.hosts[source_host].switch})"
        if switch_path[-1] != self.hosts[dest_host].switch:
            return f"path does not end at {dest_host}'s attached switch ({self.hosts[dest_host].switch})"

        for a, b in zip(switch_path, switch_path[1:]):
            if b not in self.neighbors(a):
                return f"no link between {a} and {b}"

        if len(set(switch_path)) != len(switch_path):
            return "path revisits a switch"

        return None
