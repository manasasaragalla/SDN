"""Pure OpenFlow compiler for exact, physically enumerated paths."""

from __future__ import annotations

from ipaddress import IPv4Address, AddressValueError

from backend.compiler.reroute import ETH_TYPE_ARP, ETH_TYPE_IPV4
from backend.models.flow import FlowRule
from backend.models.network import TopologyGraph
from backend.planner.path_enumeration import (
    EnumeratedPath,
    validate_physical_path,
)


def compile_physical_path(
    graph: TopologyGraph,
    path: EnumeratedPath,
    priority: int = 100,
) -> list[FlowRule]:
    """Compile the selected physical path without inferring or changing it."""
    if type(priority) is not int or not 1 <= priority <= 65535:
        raise ValueError("priority must be an integer between 1 and 65535")
    if not isinstance(path, EnumeratedPath) or len(path.nodes) < 3:
        raise ValueError("path must contain two distinct hosts and a switch")
    if not isinstance(graph, TopologyGraph):
        raise ValueError("graph must be a TopologyGraph")

    all_dpids: set[int] = set()
    for dpid in graph.switches.values():
        if type(dpid) is not int or dpid <= 0 or dpid in all_dpids:
            raise ValueError(
                "Topology switches must have distinct positive integer DPIDs"
            )
        all_dpids.add(dpid)

    source, destination = path.nodes[0], path.nodes[-1]
    validate_physical_path(graph, path, source, destination)
    source_ip = _host_ipv4(graph, source)
    destination_ip = _host_ipv4(graph, destination)
    if source_ip == destination_ip:
        raise ValueError("Path endpoint hosts must have distinct IPv4 addresses")
    if sum(host.ip == source_ip for host in graph.hosts.values()) != 1 or sum(
        host.ip == destination_ip for host in graph.hosts.values()
    ) != 1:
        raise ValueError("Path endpoint IPv4 addresses must be unique in the topology")

    switch_path = path.nodes[1:-1]
    rules: list[FlowRule] = []
    seen_matches: set[tuple[int, int, tuple[tuple[str, object], ...]]] = set()

    for index, switch in enumerate(switch_path, start=1):
        dpid = graph.switches[switch]

        ingress_forward = path.connections[index - 1].to_port
        egress_forward = path.connections[index].from_port
        if (
            type(ingress_forward) is not int
            or type(egress_forward) is not int
            or ingress_forward <= 0
            or egress_forward <= 0
            or ingress_forward == egress_forward
        ):
            raise ValueError(f"Path has invalid ingress or egress ports at {switch!r}")

        for reverse, ingress, egress, src, dst in (
            (False, ingress_forward, egress_forward, source_ip, destination_ip),
            (True, egress_forward, ingress_forward, destination_ip, source_ip),
        ):
            direction = "reverse" if reverse else "forward"
            for eth_type, src_field, dst_field, src_value, dst_value in (
                (ETH_TYPE_IPV4, "ipv4_src", "ipv4_dst", src, dst),
                (ETH_TYPE_ARP, "arp_spa", "arp_tpa", src, dst),
            ):
                match = {
                    "in_port": ingress,
                    "eth_type": eth_type,
                    src_field: src_value,
                    dst_field: dst_value,
                }
                key = (dpid, priority, tuple(sorted(match.items())))
                if key in seen_matches:
                    raise ValueError("Physical path compilation produced duplicate rules")
                seen_matches.add(key)
                rules.append(
                    FlowRule(
                        dpid=dpid,
                        priority=priority,
                        match=match,
                        actions=[{"type": "OUTPUT", "port": egress}],
                        label=f"{src}->{dst} {direction} @ {switch}",
                    )
                )

    return rules


def _host_ipv4(graph: TopologyGraph, host_name: str) -> str:
    try:
        address = IPv4Address(graph.hosts[host_name].ip)
    except (AddressValueError, KeyError, TypeError) as exc:
        raise ValueError(f"Host {host_name!r} must have a valid IPv4 address") from exc
    return str(address)
