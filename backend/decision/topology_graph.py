"""Builds a backend.models.network.TopologyGraph from a live, already-built
Mininet network. See docs/adr-002-topology-source-and-deployment.md for
why this reads Mininet directly instead of Ryu's LLDP-based topology
discovery (tried first; unreliable in this environment)."""
from __future__ import annotations

from mininet.net import Mininet
from mininet.node import Host as MininetHost
from mininet.node import Switch as MininetSwitch

from backend.models.network import Host, Link, TopologyGraph


def build_from_mininet(net: Mininet) -> TopologyGraph:
    switches: dict[str, int] = {}
    for sw in net.switches:
        # Mininet's dpid string is 16 hex chars with no separators, e.g.
        # "0000000000000001" -- this is exactly what Ryu's datapath.id is,
        # as an int, once the switch is connected.
        switches[sw.name] = int(sw.dpid, 16)

    hosts: dict[str, Host] = {}
    links: list[Link] = []

    for link in net.links:
        intf1, intf2 = link.intf1, link.intf2
        node1, node2 = intf1.node, intf2.node

        if isinstance(node1, MininetHost) or isinstance(node2, MininetHost):
            host_node, host_intf, sw_node, sw_intf = (
                (node1, intf1, node2, intf2)
                if isinstance(node1, MininetHost)
                else (node2, intf2, node1, intf1)
            )
            hosts[host_node.name] = Host(
                name=host_node.name,
                ip=host_node.IP(),
                mac=host_node.MAC(),
                switch=sw_node.name,
                switch_port=sw_node.ports[sw_intf],
            )
        elif isinstance(node1, MininetSwitch) and isinstance(node2, MininetSwitch):
            # TCLink stores the bw= value it was built with on each
            # interface's .params dict (both ends carry the same value for
            # a single bw= kwarg); absent for a plain Link with no bw=.
            bw = intf1.params.get("bw") if hasattr(intf1, "params") else None
            links.append(
                Link(
                    node_a=node1.name,
                    port_a=node1.ports[intf1],
                    node_b=node2.name,
                    port_b=node2.ports[intf2],
                    bw_mbps=float(bw) if bw is not None else None,
                    intf_a=intf1.name,
                    intf_b=intf2.name,
                )
            )
        # links directly between two hosts aren't a topology this project
        # constructs, so no other case is handled.

    return TopologyGraph(switches=switches, hosts=hosts, links=links)
