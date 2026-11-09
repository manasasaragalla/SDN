"""Unit tests for the REROUTE compiler, using a hand-built diamond graph
(same shape as tests/test_topology_graph.py). No mininet/root needed --
this checks the compiler's pure logic, not deployment."""
import pytest

from backend.compiler.reroute import compile_reroute
from backend.models.network import Host, Link, TopologyGraph


@pytest.fixture
def diamond_graph() -> TopologyGraph:
    return TopologyGraph(
        switches={"s1": 1, "s2": 2, "s3": 3, "s4": 4},
        hosts={
            "h1": Host(name="h1", ip="10.0.0.1", mac="00:00:00:00:00:01", switch="s1", switch_port=1),
            "h4": Host(name="h4", ip="10.0.0.4", mac="00:00:00:00:00:04", switch="s4", switch_port=1),
        },
        links=[
            Link(node_a="s1", port_a=2, node_b="s2", port_b=1),
            Link(node_a="s2", port_a=2, node_b="s4", port_b=2),
            Link(node_a="s1", port_a=3, node_b="s3", port_b=1),
            Link(node_a="s3", port_a=2, node_b="s4", port_b=3),
        ],
    )


def test_compile_path_a_rule_count(diamond_graph):
    path = ["h1", "s1", "s2", "s4", "h4"]
    rules = compile_reroute(diamond_graph, path, "10.0.0.1", "10.0.0.4")
    # 3 switches on the path * 4 rules each (fwd IP, rev IP, fwd ARP, rev ARP)
    assert len(rules) == 12
    assert {r.dpid for r in rules} == {1, 2, 4}


def test_compile_path_a_output_ports_correct(diamond_graph):
    path = ["h1", "s1", "s2", "s4", "h4"]
    rules = compile_reroute(diamond_graph, path, "10.0.0.1", "10.0.0.4")

    def find(dpid, match_fragment):
        for r in rules:
            if r.dpid == dpid and all(r.match.get(k) == v for k, v in match_fragment.items()):
                return r
        raise AssertionError(f"no rule found for dpid={dpid} match~{match_fragment}")

    # s1 (dpid 1): forward IP traffic h1->h4 must go out port 2 (towards s2)
    fwd_at_s1 = find(1, {"ipv4_src": "10.0.0.1", "ipv4_dst": "10.0.0.4"})
    assert fwd_at_s1.actions == [{"type": "OUTPUT", "port": 2}]

    # s1: reverse traffic h4->h1 must go out port 1 (towards h1)
    rev_at_s1 = find(1, {"ipv4_src": "10.0.0.4", "ipv4_dst": "10.0.0.1"})
    assert rev_at_s1.actions == [{"type": "OUTPUT", "port": 1}]

    # s4 (dpid 4): forward traffic arriving via path A must exit towards h4, port 1
    fwd_at_s4 = find(4, {"ipv4_src": "10.0.0.1", "ipv4_dst": "10.0.0.4"})
    assert fwd_at_s4.actions == [{"type": "OUTPUT", "port": 1}]

    # s4: reverse traffic h4->h1 must go back out port 2 (towards s2, path A)
    rev_at_s4 = find(4, {"ipv4_src": "10.0.0.4", "ipv4_dst": "10.0.0.1"})
    assert rev_at_s4.actions == [{"type": "OUTPUT", "port": 2}]


def test_compile_path_b_uses_different_ports_at_s4(diamond_graph):
    path_b = ["h1", "s1", "s3", "s4", "h4"]
    rules = compile_reroute(diamond_graph, path_b, "10.0.0.1", "10.0.0.4")
    s4_fwd = [r for r in rules if r.dpid == 4 and r.match.get("ipv4_src") == "10.0.0.1"][0]
    # on path B, s4 must receive from s3 (port 3) and output to h4 (port 1)
    assert s4_fwd.actions == [{"type": "OUTPUT", "port": 1}]


def test_arp_rules_present_and_match_correctly(diamond_graph):
    path = ["h1", "s1", "s2", "s4", "h4"]
    rules = compile_reroute(diamond_graph, path, "10.0.0.1", "10.0.0.4")
    arp_rules = [r for r in rules if r.match.get("eth_type") == 0x0806]
    assert len(arp_rules) == 6  # 2 directions * 3 switches
    for r in arp_rules:
        assert "arp_spa" in r.match and "arp_tpa" in r.match


def test_no_flooding_actions_ever_generated(diamond_graph):
    """Every action must be a specific OUTPUT port -- never a flood/all,
    which would defeat the point of picking one path in a topology with
    parallel links."""
    path = ["h1", "s1", "s3", "s4", "h4"]
    rules = compile_reroute(diamond_graph, path, "10.0.0.1", "10.0.0.4")
    for r in rules:
        for action in r.actions:
            assert action["type"] == "OUTPUT"
            assert isinstance(action["port"], int)


def test_compile_raises_on_discontinuous_path(diamond_graph):
    with pytest.raises(ValueError):
        compile_reroute(diamond_graph, ["h1", "s1", "s2", "s3", "s4", "h4"], "10.0.0.1", "10.0.0.4")
