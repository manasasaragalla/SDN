"""Unit tests for the RATE_LIMIT/QoS compiler (Phase 11, Step 6). Pure
logic, no ovs-vsctl/mininet/root needed -- mirrors
tests/test_compiler_reroute.py's style, using a hand-built graph with
bw_mbps/interface names set (as backend/decision/topology_graph.py would
populate them from a real Mininet build)."""
import pytest

from backend.compiler.rate_limit import compile_rate_limit
from backend.models.network import Host, Link, TopologyGraph


@pytest.fixture
def diamond_graph() -> TopologyGraph:
    return TopologyGraph(
        switches={"s1": 1, "s2": 2, "s3": 3, "s4": 4},
        hosts={
            "h2": Host(name="h2", ip="10.0.0.2", mac="00:00:00:00:00:02", switch="s2", switch_port=3),
            "h3": Host(name="h3", ip="10.0.0.3", mac="00:00:00:00:00:03", switch="s4", switch_port=4),
        },
        links=[
            Link(node_a="s1", port_a=2, node_b="s2", port_b=1, bw_mbps=10.0, intf_a="s1-eth2", intf_b="s2-eth1"),
            Link(node_a="s2", port_a=2, node_b="s4", port_b=2, bw_mbps=10.0, intf_a="s2-eth2", intf_b="s4-eth2"),
            Link(node_a="s1", port_a=3, node_b="s3", port_b=1, bw_mbps=50.0, intf_a="s1-eth3", intf_b="s3-eth1"),
            Link(node_a="s3", port_a=2, node_b="s4", port_b=3, bw_mbps=50.0, intf_a="s3-eth2", intf_b="s4-eth3"),
        ],
    )


def test_compile_rate_limit_rule_count(diamond_graph):
    path = ["h2", "s2", "s4", "h3"]
    rules, queue = compile_rate_limit(diamond_graph, path, "10.0.0.2", "10.0.0.3", rate_mbps=8.0)
    # 2 switches on the path * 4 rules each (fwd IP, rev IP, fwd ARP, rev ARP)
    assert len(rules) == 8
    assert {r.dpid for r in rules} == {2, 4}


def test_first_hop_forward_rule_uses_set_queue(diamond_graph):
    path = ["h2", "s2", "s4", "h3"]
    rules, queue = compile_rate_limit(diamond_graph, path, "10.0.0.2", "10.0.0.3", rate_mbps=8.0)
    fwd_at_s2 = [r for r in rules if r.dpid == 2 and r.match.get("ipv4_src") == "10.0.0.2"
                 and r.match.get("eth_type") == 0x0800][0]
    assert fwd_at_s2.actions == [{"type": "SET_QUEUE", "queue_id": 0}, {"type": "OUTPUT", "port": 2}]


def test_other_hops_use_plain_output(diamond_graph):
    path = ["h2", "s2", "s4", "h3"]
    rules, queue = compile_rate_limit(diamond_graph, path, "10.0.0.2", "10.0.0.3", rate_mbps=8.0)
    fwd_at_s4 = [r for r in rules if r.dpid == 4 and r.match.get("ipv4_src") == "10.0.0.2"
                 and r.match.get("eth_type") == 0x0800][0]
    assert fwd_at_s4.actions == [{"type": "OUTPUT", "port": 4}]


def test_queue_config_targets_first_hop_egress_interface(diamond_graph):
    path = ["h2", "s2", "s4", "h3"]
    rules, queue = compile_rate_limit(diamond_graph, path, "10.0.0.2", "10.0.0.3", rate_mbps=8.0)
    assert queue.switch == "s2"
    assert queue.intf == "s2-eth2"  # s2's port facing s4, i.e. the egress towards the rest of the path
    assert queue.max_rate_bps == 8_000_000


def test_rate_limit_is_generic_over_reversed_flow(diamond_graph):
    """Same compiler, different source/destination/path -- not hardcoded."""
    path = ["h3", "s4", "s2", "h2"]
    rules, queue = compile_rate_limit(diamond_graph, path, "10.0.0.3", "10.0.0.2", rate_mbps=5.0)
    assert queue.switch == "s4"
    assert queue.max_rate_bps == 5_000_000


def test_compile_rate_limit_raises_without_switch_hop():
    graph = TopologyGraph(
        switches={"s1": 1},
        hosts={
            "h1": Host(name="h1", ip="10.0.0.1", mac="00:00:00:00:00:01", switch="s1", switch_port=1),
            "h2": Host(name="h2", ip="10.0.0.2", mac="00:00:00:00:00:02", switch="s1", switch_port=2),
        },
        links=[],
    )
    with pytest.raises(ValueError):
        compile_rate_limit(graph, ["h1", "s1", "h2"], "10.0.0.1", "10.0.0.2", rate_mbps=5.0)
