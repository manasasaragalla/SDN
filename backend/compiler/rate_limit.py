"""Deterministic compiler for the RATE_LIMIT primitive (brief Step 6:
"a generic, reusable rate_limit(flow, rate)-style deterministic QoS
compiler"). See docs/adr-004-bandwidth-mechanism.md for the mechanism
(OVS QoS queues, referenced from a SET_QUEUE OpenFlow action) and for why
this project applies it to the background/competing flow rather than the
primary MIN_BANDWIDTH intent's own flow.

Like backend/compiler/reroute.py, this is generic over source/destination/
path/rate -- nothing here names h1/h2/h3/h4 or any other specific host.
It reuses the same per-hop FlowRule generation reroute.py uses (forward,
reverse, and both ARP directions, at every switch on the path, so the
path is fully and correctly installed, not just its rate-limited hop) and
only changes the forward-direction rule at the FIRST switch hop (the one
directly attached to the source host) to route through a queue instead of
a bare OUTPUT.

This function is pure, exactly like compile_reroute: it takes a
TopologyGraph, a path, and a rate, and returns FlowRules plus the
QueueConfig those FlowRules depend on existing. It doesn't run
ovs-vsctl or talk to Ryu itself -- backend/deployment does that.
"""
from __future__ import annotations

from backend.compiler.reroute import ETH_TYPE_ARP, ETH_TYPE_IPV4, _port_towards
from backend.models.flow import FlowRule
from backend.models.network import TopologyGraph
from backend.models.qos import QueueConfig

BITS_PER_MBIT = 1_000_000


def compile_rate_limit(
    graph: TopologyGraph,
    path: list[str],
    src_ip: str,
    dst_ip: str,
    rate_mbps: float,
    priority: int = 100,
    queue_id: int = 0,
) -> tuple[list[FlowRule], QueueConfig]:
    """path is [source_host, switch, ..., switch, dest_host], same
    convention as compile_reroute. rate_mbps caps the source->destination
    direction only (the direction this "flow" actually names) at the
    first switch hop's egress toward the rest of the path -- shaping at
    the edge closest to the source, so one queue on one interface is
    enough regardless of how many further hops the path has.
    """
    switch_path = path[1:-1]
    if not switch_path:
        raise ValueError("path must include at least one switch")

    first_switch = switch_path[0]
    first_hop_next_node = path[2]  # path[0]=src host, path[1]=first switch
    first_hop_egress_intf = graph.link_between(first_switch, first_hop_next_node).intf_facing(first_switch) \
        if first_hop_next_node in graph.switches \
        else None
    if first_hop_egress_intf is None:
        # The path's first switch hop is directly attached to the
        # destination host (a one-switch path) -- shape the host-facing
        # port instead, using the host's own recorded interface if the
        # graph has one, otherwise fall back to the switch_port-derived
        # convention Mininet uses (see Host model / build_from_mininet).
        raise ValueError(
            "rate_limit currently requires the path's first switch to have "
            "a switch-to-switch next hop (single-switch paths aren't used "
            "by this project's topology)"
        )

    queue = QueueConfig(
        switch=first_switch,
        intf=first_hop_egress_intf,
        queue_id=queue_id,
        max_rate_bps=int(rate_mbps * BITS_PER_MBIT),
        label=f"rate-limit {src_ip}->{dst_ip} @ {first_switch} to {rate_mbps} Mbps",
    )

    rules: list[FlowRule] = []
    for i, switch in enumerate(switch_path):
        idx_in_full_path = i + 1
        prev_node = path[idx_in_full_path - 1]
        next_node = path[idx_in_full_path + 1]
        dpid = graph.switches[switch]

        out_port_forward = _port_towards(graph, switch, next_node)
        out_port_reverse = _port_towards(graph, switch, prev_node)

        forward_actions = (
            [{"type": "SET_QUEUE", "queue_id": queue_id}, {"type": "OUTPUT", "port": out_port_forward}]
            if switch == first_switch
            else [{"type": "OUTPUT", "port": out_port_forward}]
        )

        rules.append(
            FlowRule(
                dpid=dpid,
                priority=priority,
                match={"eth_type": ETH_TYPE_IPV4, "ipv4_src": src_ip, "ipv4_dst": dst_ip},
                actions=forward_actions,
                label=f"{src_ip}->{dst_ip} IP forward (rate-limited to {rate_mbps} Mbps) @ {switch}"
                if switch == first_switch
                else f"{src_ip}->{dst_ip} IP forward @ {switch}",
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

    return rules, queue
