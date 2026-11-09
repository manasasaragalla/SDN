"""Deterministic compiler for the REROUTE primitive (brief section 14).

Given a validated path through the real topology, generates the OpenFlow
rules (as ryu.app.ofctl_rest payloads -- see backend/models/flow.py) that
make that exact path carry traffic between two hosts, and nothing else
does. No learning-switch flooding is used anywhere: every switch on the
path gets an explicit forward rule, an explicit reverse rule, and explicit
ARP handling (matched on arp_spa/arp_tpa, not flooded), so a topology with
parallel paths (this project's diamond) never loops -- only the single
selected path ever carries traffic.

This function is pure: it takes a TopologyGraph and a path and returns
FlowRule objects. It doesn't know about Ryu's REST API, HTTP, or Mininet;
that's backend/deployment's job.
"""
from __future__ import annotations

from backend.models.flow import FlowRule
from backend.models.network import TopologyGraph

ETH_TYPE_IPV4 = 0x0800
ETH_TYPE_ARP = 0x0806


def _port_towards(graph: TopologyGraph, current_switch: str, neighbor: str) -> int:
    """The port on current_switch that leads to `neighbor`, whether
    `neighbor` is a host directly attached to this switch or another
    switch."""
    host = graph.hosts.get(neighbor)
    if host is not None and host.switch == current_switch:
        return host.switch_port
    return graph.port_between(current_switch, neighbor)


def compile_reroute(
    graph: TopologyGraph,
    path: list[str],
    src_ip: str,
    dst_ip: str,
    priority: int = 100,
) -> list[FlowRule]:
    """path is [source_host, switch, switch, ..., switch, dest_host], as
    produced by TopologyGraph.all_simple_paths and checked by
    TopologyGraph.validate_path. Caller is responsible for validating the
    path first (backend/validator) -- this function does not re-validate,
    it assumes a good path and will raise (via TopologyGraph.port_between)
    if given one that isn't actually continuous.
    """
    switch_path = path[1:-1]
    rules: list[FlowRule] = []

    for i, switch in enumerate(switch_path):
        idx_in_full_path = i + 1
        prev_node = path[idx_in_full_path - 1]
        next_node = path[idx_in_full_path + 1]
        dpid = graph.switches[switch]

        out_port_forward = _port_towards(graph, switch, next_node)
        out_port_reverse = _port_towards(graph, switch, prev_node)

        rules.append(
            FlowRule(
                dpid=dpid,
                priority=priority,
                match={"eth_type": ETH_TYPE_IPV4, "ipv4_src": src_ip, "ipv4_dst": dst_ip},
                actions=[{"type": "OUTPUT", "port": out_port_forward}],
                label=f"{src_ip}->{dst_ip} IP forward @ {switch}",
            )
        )
        rules.append(
            FlowRule(
                dpid=dpid,
                priority=priority,
                match={"eth_type": ETH_TYPE_IPV4, "ipv4_src": dst_ip, "ipv4_dst": src_ip},
                actions=[{"type": "OUTPUT", "port": out_port_reverse}],
                label=f"{dst_ip}->{src_ip} IP reverse @ {switch}",
            )
        )
        rules.append(
            FlowRule(
                dpid=dpid,
                priority=priority,
                match={"eth_type": ETH_TYPE_ARP, "arp_spa": src_ip, "arp_tpa": dst_ip},
                actions=[{"type": "OUTPUT", "port": out_port_forward}],
                label=f"ARP {src_ip}->{dst_ip} @ {switch}",
            )
        )
        rules.append(
            FlowRule(
                dpid=dpid,
                priority=priority,
                match={"eth_type": ETH_TYPE_ARP, "arp_spa": dst_ip, "arp_tpa": src_ip},
                actions=[{"type": "OUTPUT", "port": out_port_reverse}],
                label=f"ARP {dst_ip}->{src_ip} @ {switch}",
            )
        )

    return rules


def compile_delete_flows(graph: TopologyGraph, path: list[str], src_ip: str, dst_ip: str) -> list[FlowRule]:
    """Match-only rules (no priority/actions needed by ofctl_rest's delete
    endpoint) describing the flows to remove before installing a new path
    for the same (src_ip, dst_ip) pair -- used when rerouting an existing
    intent onto a different path."""
    switch_path = path[1:-1]
    rules: list[FlowRule] = []
    for switch in switch_path:
        dpid = graph.switches[switch]
        for eth_type, a, b in (
            (ETH_TYPE_IPV4, "ipv4_src", "ipv4_dst"),
        ):
            rules.append(
                FlowRule(dpid=dpid, match={"eth_type": eth_type, a: src_ip, b: dst_ip}, actions=[])
            )
            rules.append(
                FlowRule(dpid=dpid, match={"eth_type": eth_type, a: dst_ip, b: src_ip}, actions=[])
            )
        rules.append(FlowRule(dpid=dpid, match={"eth_type": ETH_TYPE_ARP, "arp_spa": src_ip, "arp_tpa": dst_ip}, actions=[]))
        rules.append(FlowRule(dpid=dpid, match={"eth_type": ETH_TYPE_ARP, "arp_spa": dst_ip, "arp_tpa": src_ip}, actions=[]))
    return rules
