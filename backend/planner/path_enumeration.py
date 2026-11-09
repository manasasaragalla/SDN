"""Pure bounded enumeration of physically identified topology paths."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import TypeAlias

from pydantic import Field, model_validator

from backend.models.network import Host, Link, TopologyGraph
from backend.planner.models import _PlannerModel

SwitchEndpoint: TypeAlias = tuple[str, int]
SwitchLinkIdentity: TypeAlias = tuple[SwitchEndpoint, SwitchEndpoint]


class InvalidPathRequestError(ValueError):
    """Raised when an enumeration request is invalid."""


class InvalidTopologyError(ValueError):
    """Raised when topology metadata is malformed or ambiguous."""


class ConnectionKind(str, Enum):
    HOST_ATTACHMENT = "HOST_ATTACHMENT"
    SWITCH_LINK = "SWITCH_LINK"


class PathConnection(_PlannerModel):
    """One exact physical connection oriented in path-traversal direction.

    Host-side port numbers are absent from TopologyGraph and remain ``None``.
    The switch-side port is always represented.
    """

    kind: ConnectionKind
    from_node: str = Field(min_length=1)
    to_node: str = Field(min_length=1)
    from_port: int | None = None
    to_port: int | None = None
    link_identity: SwitchLinkIdentity | None = None

    @model_validator(mode="after")
    def validate_connection_shape(self) -> "PathConnection":
        if self.kind == ConnectionKind.SWITCH_LINK:
            if (
                self.from_port is None
                or self.to_port is None
                or self.from_node == self.to_node
                or self.from_port <= 0
                or self.to_port <= 0
                or self.link_identity is None
            ):
                raise ValueError(
                    "A switch-link connection requires two positive ports and a physical identity"
                )
            oriented_identity = tuple(
                sorted(
                    (
                        (self.from_node, self.from_port),
                        (self.to_node, self.to_port),
                    )
                )
            )
            if self.link_identity != oriented_identity:
                raise ValueError(
                    "Switch-link identity must match its endpoints and ports"
                )
        elif (
            self.from_node == self.to_node
            or self.link_identity is not None
            or (self.from_port is None) == (self.to_port is None)
            or any(
                port is not None and port <= 0
                for port in (self.from_port, self.to_port)
            )
        ):
            raise ValueError(
                "A host attachment requires exactly one positive switch port and no link identity"
            )
        return self


class EnumeratedPath(_PlannerModel):
    """A node route plus the exact physical connection used for each hop."""

    nodes: tuple[str, ...] = Field(min_length=3)
    connections: tuple[PathConnection, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def connections_follow_nodes(self) -> "EnumeratedPath":
        if len(self.connections) != len(self.nodes) - 1:
            raise ValueError("A path needs exactly one connection per node transition")
        if len(set(self.nodes)) != len(self.nodes):
            raise ValueError("Enumerated paths must not repeat nodes")
        if (
            self.connections[0].kind != ConnectionKind.HOST_ATTACHMENT
            or self.connections[-1].kind != ConnectionKind.HOST_ATTACHMENT
        ):
            raise ValueError(
                "The first and last path connections must be host attachments"
            )
        if any(
            connection.kind != ConnectionKind.SWITCH_LINK
            for connection in self.connections[1:-1]
        ):
            raise ValueError(
                "Intermediate path connections must be switch links"
            )
        for index, connection in enumerate(self.connections):
            if (
                connection.from_node != self.nodes[index]
                or connection.to_node != self.nodes[index + 1]
            ):
                raise ValueError(
                    "Path connections must follow the ordered node sequence"
                )
        return self


class PathEnumerationResult(_PlannerModel):
    """Bounded result; truncation means an additional valid path was found."""

    source: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    candidate_limit: int = Field(gt=0)
    paths: tuple[EnumeratedPath, ...] = ()
    truncated: bool

    @model_validator(mode="after")
    def respect_candidate_limit(self) -> "PathEnumerationResult":
        if len(self.paths) > self.candidate_limit:
            raise ValueError("Path result exceeds candidate_limit")
        if self.truncated and len(self.paths) != self.candidate_limit:
            raise ValueError("A truncated result must contain candidate_limit paths")
        if any(
            path.nodes[0] != self.source or path.nodes[-1] != self.destination
            for path in self.paths
        ):
            raise ValueError("Every result path must match the requested endpoints")
        return self


@dataclass(frozen=True)
class _IndexedLink:
    identity: SwitchLinkIdentity
    link: Link


def canonical_link_identity(link: Link) -> SwitchLinkIdentity:
    """Return endpoint-order-independent physical identity for a switch link."""

    if (
        not isinstance(link.node_a, str)
        or not link.node_a
        or not isinstance(link.node_b, str)
        or not link.node_b
        or link.node_a == link.node_b
        or type(link.port_a) is not int
        or link.port_a <= 0
        or type(link.port_b) is not int
        or link.port_b <= 0
    ):
        raise InvalidTopologyError("Cannot identify a malformed switch link")
    endpoints = sorted(
        (
            (link.node_a, link.port_a),
            (link.node_b, link.port_b),
        )
    )
    return endpoints[0], endpoints[1]


def physical_path_capacity_mbps(
    graph: TopologyGraph,
    path: EnumeratedPath,
) -> float | None:
    """Return bottleneck capacity for the exact physical path, if known.

    Every switch-link transition must match exactly one topology link with the
    same endpoint ports and canonical identity. Missing, invalid, or ambiguous
    topology metadata returns None. Host attachments do not contribute a
    switch-link capacity.
    """
    if not isinstance(graph, TopologyGraph) or not isinstance(path, EnumeratedPath):
        raise TypeError("graph and path must be TopologyGraph and EnumeratedPath")

    capacities: list[float] = []
    for connection in path.connections:
        if connection.kind != ConnectionKind.SWITCH_LINK:
            continue
        matching = [
            link
            for link in graph.links
            if (
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
        ]
        if len(matching) != 1:
            return None
        link = matching[0]
        try:
            identity = canonical_link_identity(link)
        except InvalidTopologyError:
            return None
        if identity != connection.link_identity:
            return None
        capacity = link.bw_mbps
        if (
            capacity is None
            or isinstance(capacity, bool)
            or not math.isfinite(capacity)
            or capacity < 0
        ):
            return None
        capacities.append(capacity)
    return min(capacities) if capacities else None


def validate_physical_path(
    graph: TopologyGraph,
    path: EnumeratedPath,
    source: str,
    destination: str,
) -> None:
    """Raise when a physical path is not an exact route in the supplied topology."""
    adjacency = _validate_topology(graph)
    if not isinstance(path, EnumeratedPath):
        raise InvalidPathRequestError("path must be an EnumeratedPath")
    if (
        not isinstance(source, str)
        or not source
        or not isinstance(destination, str)
        or not destination
        or source == destination
    ):
        raise InvalidPathRequestError("source and destination must be distinct hosts")
    if source not in graph.hosts or destination not in graph.hosts:
        raise InvalidPathRequestError("Path endpoints must be known topology hosts")
    if path.nodes[0] != source or path.nodes[-1] != destination:
        raise InvalidPathRequestError("Path does not match the requested endpoints")

    source_host = graph.hosts[source]
    destination_host = graph.hosts[destination]
    first, last = path.connections[0], path.connections[-1]
    if (
        first.kind != ConnectionKind.HOST_ATTACHMENT
        or first.from_node != source
        or first.to_node != source_host.switch
        or first.from_port is not None
        or first.to_port != source_host.switch_port
        or last.kind != ConnectionKind.HOST_ATTACHMENT
        or last.from_node != destination_host.switch
        or last.to_node != destination
        or last.from_port != destination_host.switch_port
        or last.to_port is not None
    ):
        raise InvalidPathRequestError(
            "Path host attachments do not match the topology"
        )

    for connection in path.connections[1:-1]:
        if (
            connection.from_node not in adjacency
            or connection.to_node not in adjacency
        ):
            raise InvalidPathRequestError(
                "Switch-link path references an unknown switch"
            )
        matches = [
            item
            for item in adjacency[connection.from_node]
            if item.link.other_end(connection.from_node) == connection.to_node
            and item.identity == connection.link_identity
            and (
                (
                    item.link.node_a == connection.from_node
                    and item.link.port_a == connection.from_port
                    and item.link.node_b == connection.to_node
                    and item.link.port_b == connection.to_port
                )
                or (
                    item.link.node_b == connection.from_node
                    and item.link.port_b == connection.from_port
                    and item.link.node_a == connection.to_node
                    and item.link.port_a == connection.to_port
                )
            )
        ]
        if len(matches) != 1:
            raise InvalidPathRequestError(
                "Switch-link path does not match exactly one physical topology link"
            )


def _validate_topology(graph: TopologyGraph) -> dict[str, list[_IndexedLink]]:
    if not isinstance(graph, TopologyGraph):
        raise InvalidTopologyError("graph must be a TopologyGraph")
    if (
        not isinstance(graph.switches, dict)
        or not isinstance(graph.hosts, dict)
        or not isinstance(graph.links, list)
    ):
        raise InvalidTopologyError(
            "TopologyGraph switches, hosts, and links must be dictionaries, dictionaries, and a list"
        )

    switch_names = set(graph.switches)
    if any(not isinstance(name, str) or not name for name in switch_names):
        raise InvalidTopologyError("Switch names must be non-empty strings")
    if any(not isinstance(name, str) or not name for name in graph.hosts):
        raise InvalidTopologyError("Host dictionary keys must be non-empty strings")
    if switch_names.intersection(graph.hosts):
        raise InvalidTopologyError("Host and switch names must not overlap")
    if set(graph.switch_ports) - switch_names:
        raise InvalidTopologyError(
            "Switch port inventory references an unknown switch"
        )

    port_owners: dict[tuple[str, int], str] = {}

    def claim_port(switch: str, port: object, owner: str) -> None:
        if type(port) is not int or port <= 0:
            raise InvalidTopologyError(
                f"Switch {switch!r} has a non-positive or invalid port for {owner}"
            )
        key = (switch, port)
        previous = port_owners.get(key)
        if previous is not None:
            raise InvalidTopologyError(
                f"Switch port {switch!r}:{port} is claimed by both "
                f"{previous} and {owner}"
            )
        port_owners[key] = owner

    for host_key, host in graph.hosts.items():
        if not isinstance(host, Host):
            raise InvalidTopologyError(
                f"Host entry {host_key!r} must contain a Host model"
            )
        if not isinstance(host.name, str) or not host.name or host_key != host.name:
            raise InvalidTopologyError(
                f"Host dictionary key {host_key!r} does not match Host.name {host.name!r}"
            )
        if not isinstance(host.switch, str) or not host.switch:
            raise InvalidTopologyError(
                f"Host {host.name!r} has an invalid switch attachment"
            )
        if host.switch not in graph.switches:
            raise InvalidTopologyError(
                f"Host {host.name!r} references unknown switch {host.switch!r}"
            )
        claim_port(
            host.switch,
            host.switch_port,
            f"host attachment {host.name!r}",
        )
        configured_ports = graph.switch_ports.get(host.switch)
        if configured_ports is not None and host.switch_port not in configured_ports:
            raise InvalidTopologyError(
                f"Host {host.name!r} uses a port absent from switch {host.switch!r} inventory"
            )

    for switch, ports in graph.switch_ports.items():
        if (
            not isinstance(ports, list)
            or any(type(port) is not int or port <= 0 for port in ports)
            or len(ports) != len(set(ports))
        ):
            raise InvalidTopologyError(
                f"Switch {switch!r} has an invalid port inventory"
            )

    seen_identities: set[SwitchLinkIdentity] = set()
    adjacency: dict[str, list[_IndexedLink]] = {
        switch: [] for switch in graph.switches
    }
    for index, link in enumerate(graph.links):
        if not isinstance(link, Link):
            raise InvalidTopologyError(
                f"Link entry {index} must contain a Link model"
            )
        if (
            not isinstance(link.node_a, str)
            or not link.node_a
            or not isinstance(link.node_b, str)
            or not link.node_b
        ):
            raise InvalidTopologyError(f"Link entry {index} has an invalid endpoint")
        if link.node_a == link.node_b:
            raise InvalidTopologyError(
                f"Link entry {index} is a self-link on {link.node_a!r}"
            )
        for endpoint in (link.node_a, link.node_b):
            if endpoint not in graph.switches:
                raise InvalidTopologyError(
                    f"Link entry {index} references unknown switch {endpoint!r}"
                )

        identity = canonical_link_identity(link)
        if identity in seen_identities:
            raise InvalidTopologyError(
                f"Duplicate physical switch link {identity!r}"
            )
        seen_identities.add(identity)

        claim_port(link.node_a, link.port_a, f"switch link {identity!r}")
        claim_port(link.node_b, link.port_b, f"switch link {identity!r}")

        for switch, port in (
            (link.node_a, link.port_a),
            (link.node_b, link.port_b),
        ):
            configured_ports = graph.switch_ports.get(switch)
            if configured_ports is not None and port not in configured_ports:
                raise InvalidTopologyError(
                    f"Switch port {switch!r}:{port} is absent from its configured inventory"
                )

        if link.admin_up is False:
            continue
        indexed = _IndexedLink(identity=identity, link=link)
        adjacency[link.node_a].append(indexed)
        adjacency[link.node_b].append(indexed)

    for switch in adjacency:
        adjacency[switch].sort(
            key=lambda item: (
                item.link.other_end(switch),
                item.identity,
            )
        )
    return adjacency


def _host_connection(host: Host, *, from_host: bool) -> PathConnection:
    if from_host:
        return PathConnection(
            kind=ConnectionKind.HOST_ATTACHMENT,
            from_node=host.name,
            to_node=host.switch,
            to_port=host.switch_port,
        )
    return PathConnection(
        kind=ConnectionKind.HOST_ATTACHMENT,
        from_node=host.switch,
        to_node=host.name,
        from_port=host.switch_port,
    )


def _switch_connection(
    indexed: _IndexedLink,
    from_switch: str,
) -> PathConnection:
    link = indexed.link
    if from_switch == link.node_a:
        from_port, to_port = link.port_a, link.port_b
        to_switch = link.node_b
    else:
        from_port, to_port = link.port_b, link.port_a
        to_switch = link.node_a
    return PathConnection(
        kind=ConnectionKind.SWITCH_LINK,
        from_node=from_switch,
        to_node=to_switch,
        from_port=from_port,
        to_port=to_port,
        link_identity=indexed.identity,
    )


def enumerate_candidate_paths(
    graph: TopologyGraph,
    source: str,
    destination: str,
    candidate_limit: int,
) -> PathEnumerationResult:
    """Enumerate deterministic loop-free physical paths without side effects.

    The limit bounds returned paths, not worst-case search time. Search stops
    immediately after finding a valid (K+1)th path to establish truncation.
    """

    if not isinstance(source, str) or not source:
        raise InvalidPathRequestError("source must be a non-empty host name")
    if not isinstance(destination, str) or not destination:
        raise InvalidPathRequestError("destination must be a non-empty host name")
    if source == destination:
        raise InvalidPathRequestError("source and destination hosts must differ")
    if type(candidate_limit) is not int or candidate_limit <= 0:
        raise InvalidPathRequestError(
            "candidate_limit must be a positive integer"
        )
    adjacency = _validate_topology(graph)
    if source not in graph.hosts:
        raise InvalidPathRequestError(f"Unknown source host {source!r}")
    if destination not in graph.hosts:
        raise InvalidPathRequestError(
            f"Unknown destination host {destination!r}"
        )

    source_host = graph.hosts[source]
    destination_host = graph.hosts[destination]
    paths: list[EnumeratedPath] = []
    truncated = False
    if (
        source_host.attachment_admin_up is False
        or destination_host.attachment_admin_up is False
    ):
        return PathEnumerationResult(
            source=source,
            destination=destination,
            candidate_limit=candidate_limit,
            paths=(),
            truncated=False,
        )

    def emit(switch_nodes: list[str], switch_connections: list[PathConnection]) -> bool:
        nonlocal truncated
        nodes = (source, *switch_nodes, destination)
        connections = (
            _host_connection(source_host, from_host=True),
            *switch_connections,
            _host_connection(destination_host, from_host=False),
        )
        candidate = EnumeratedPath(nodes=nodes, connections=connections)
        if len(paths) == candidate_limit:
            truncated = True
            return True
        paths.append(candidate)
        return False

    start = source_host.switch
    target = destination_host.switch
    if start == target:
        emit([start], [])
    else:
        def dfs(
            current: str,
            visited: set[str],
            switch_nodes: list[str],
            switch_connections: list[PathConnection],
        ) -> bool:
            for indexed in adjacency[current]:
                neighbor = indexed.link.other_end(current)
                if neighbor in visited:
                    continue
                edge = _switch_connection(indexed, current)
                next_nodes = [*switch_nodes, neighbor]
                next_connections = [*switch_connections, edge]
                if neighbor == target:
                    if emit(next_nodes, next_connections):
                        return True
                    continue
                if dfs(
                    neighbor,
                    visited | {neighbor},
                    next_nodes,
                    next_connections,
                ):
                    return True
            return False

        dfs(start, {start}, [start], [])

    return PathEnumerationResult(
        source=source,
        destination=destination,
        candidate_limit=candidate_limit,
        paths=tuple(paths),
        truncated=truncated,
    )
