"""Unit tests for the MIN_BANDWIDTH pre-deployment validation added in
Phase 11 (Step 7: reject infeasible targets before deployment). Pure, no
mininet."""
import pytest

from backend.models.network import Host, Link, TopologyGraph
from backend.validator.path_validator import validate_path_for_bandwidth, validate_rate_limit


@pytest.fixture
def diamond_graph() -> TopologyGraph:
    return TopologyGraph(
        switches={"s1": 1, "s2": 2, "s3": 3, "s4": 4},
        hosts={
            "h1": Host(name="h1", ip="10.0.0.1", mac="00:00:00:00:00:01", switch="s1", switch_port=1),
            "h4": Host(name="h4", ip="10.0.0.4", mac="00:00:00:00:00:04", switch="s4", switch_port=1),
        },
        links=[
            Link(node_a="s1", port_a=2, node_b="s2", port_b=1, bw_mbps=10.0),
            Link(node_a="s2", port_a=2, node_b="s4", port_b=2, bw_mbps=10.0),
            Link(node_a="s1", port_a=3, node_b="s3", port_b=1, bw_mbps=50.0),
            Link(node_a="s3", port_a=2, node_b="s4", port_b=3, bw_mbps=50.0),
        ],
    )


def test_feasible_target_on_high_capacity_path_passes(diamond_graph):
    result = validate_path_for_bandwidth(
        diamond_graph, ["h1", "s1", "s3", "s4", "h4"], "10.0.0.1", "10.0.0.4", target_mbps=20.0
    )
    assert result.valid


def test_infeasible_target_on_low_capacity_path_rejected(diamond_graph):
    """The brief's own example: requesting 50 Mbps over a 10 Mbps path."""
    result = validate_path_for_bandwidth(
        diamond_graph, ["h1", "s1", "s2", "s4", "h4"], "10.0.0.1", "10.0.0.4", target_mbps=50.0
    )
    assert not result.valid
    assert any("capacity" in r for r in result.reasons)


def test_nonpositive_target_rejected(diamond_graph):
    result = validate_path_for_bandwidth(
        diamond_graph, ["h1", "s1", "s3", "s4", "h4"], "10.0.0.1", "10.0.0.4", target_mbps=0.0
    )
    assert not result.valid


def test_structural_problems_still_caught(diamond_graph):
    result = validate_path_for_bandwidth(
        diamond_graph, ["h1", "s1", "s8", "s4", "h4"], "10.0.0.1", "10.0.0.4", target_mbps=5.0
    )
    assert not result.valid
    assert any("s8" in r for r in result.reasons)


def test_validate_rate_limit_positive_rate_within_capacity_passes():
    result = validate_rate_limit(8.0, path_capacity_mbps=10.0)
    assert result.valid


def test_validate_rate_limit_rejects_nonpositive_rate():
    result = validate_rate_limit(-1.0, path_capacity_mbps=10.0)
    assert not result.valid


def test_validate_rate_limit_rejects_rate_above_capacity():
    result = validate_rate_limit(15.0, path_capacity_mbps=10.0)
    assert not result.valid
    assert any("exceeds" in r for r in result.reasons)


def test_validate_rate_limit_allows_unknown_capacity():
    result = validate_rate_limit(8.0, path_capacity_mbps=None)
    assert result.valid


def test_path_capacity_mbps_is_the_bottleneck(diamond_graph):
    assert diamond_graph.path_capacity_mbps(["h1", "s1", "s2", "s4", "h4"]) == 10.0
    assert diamond_graph.path_capacity_mbps(["h1", "s1", "s3", "s4", "h4"]) == 50.0


def test_path_capacity_mbps_none_when_unknown():
    graph = TopologyGraph(
        switches={"s1": 1, "s2": 2},
        hosts={
            "h1": Host(name="h1", ip="10.0.0.1", mac="00:00:00:00:00:01", switch="s1", switch_port=1),
            "h2": Host(name="h2", ip="10.0.0.2", mac="00:00:00:00:00:02", switch="s2", switch_port=1),
        },
        links=[Link(node_a="s1", port_a=2, node_b="s2", port_b=2)],  # no bw_mbps set
    )
    assert graph.path_capacity_mbps(["h1", "s1", "s2", "h2"]) is None
