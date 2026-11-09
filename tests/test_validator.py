"""Unit tests for pre-deployment validation (Step 5). Pure, no mininet."""
import pytest

from backend.compiler.reroute import compile_reroute
from backend.models.flow import FlowRule
from backend.models.network import Host, Link, TopologyGraph
from backend.validator.path_validator import validate_flow_rules, validate_path_for_reroute


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


def test_valid_reroute_passes(diamond_graph):
    result = validate_path_for_reroute(
        diamond_graph, "REROUTE", ["h1", "s1", "s2", "s4", "h4"], "10.0.0.1", "10.0.0.4"
    )
    assert result.valid
    assert result.reasons == []


def test_unsupported_action_rejected(diamond_graph):
    result = validate_path_for_reroute(
        diamond_graph, "TELEPORT", ["h1", "s1", "s2", "s4", "h4"], "10.0.0.1", "10.0.0.4"
    )
    assert not result.valid
    assert "unsupported action" in result.reasons[0]


def test_nonexistent_switch_in_path_rejected(diamond_graph):
    result = validate_path_for_reroute(
        diamond_graph, "REROUTE", ["h1", "s1", "s8", "s4", "h4"], "10.0.0.1", "10.0.0.4"
    )
    assert not result.valid
    assert any("s8" in r for r in result.reasons)


def test_mismatched_ip_rejected(diamond_graph):
    result = validate_path_for_reroute(
        diamond_graph, "REROUTE", ["h1", "s1", "s2", "s4", "h4"], "10.0.0.99", "10.0.0.4"
    )
    assert not result.valid
    assert any("does not match" in r for r in result.reasons)


def test_compiled_flow_rules_pass_validation(diamond_graph):
    path = ["h1", "s1", "s2", "s4", "h4"]
    rules = compile_reroute(diamond_graph, path, "10.0.0.1", "10.0.0.4")
    result = validate_flow_rules(diamond_graph, rules)
    assert result.valid


def test_flow_rule_with_unknown_dpid_rejected(diamond_graph):
    bad_rule = FlowRule(dpid=999, priority=100, match={"eth_type": 2048}, actions=[{"type": "OUTPUT", "port": 1}])
    result = validate_flow_rules(diamond_graph, [bad_rule])
    assert not result.valid
    assert any("unknown dpid" in r for r in result.reasons)


def test_conflicting_flow_rules_rejected(diamond_graph):
    match = {"eth_type": 2048, "ipv4_src": "10.0.0.1", "ipv4_dst": "10.0.0.4"}
    rule_a = FlowRule(dpid=1, priority=100, match=match, actions=[{"type": "OUTPUT", "port": 2}])
    rule_b = FlowRule(dpid=1, priority=100, match=match, actions=[{"type": "OUTPUT", "port": 3}])
    result = validate_flow_rules(diamond_graph, [rule_a, rule_b])
    assert not result.valid
    assert any("conflicting" in r for r in result.reasons)
