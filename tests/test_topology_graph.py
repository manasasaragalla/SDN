"""Pure unit tests for backend.models.network.TopologyGraph, using a
hand-built graph shaped like the project's real diamond topology. No
mininet/root privileges required."""
import pytest

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


def test_finds_both_diamond_paths(diamond_graph):
    paths = diamond_graph.all_simple_paths("h1", "h4")
    path_switches = sorted(tuple(p[1:-1]) for p in paths)
    assert path_switches == [("s1", "s2", "s4"), ("s1", "s3", "s4")]


def test_all_paths_start_and_end_at_hosts(diamond_graph):
    for path in diamond_graph.all_simple_paths("h1", "h4"):
        assert path[0] == "h1"
        assert path[-1] == "h4"


def test_port_between_neighbors(diamond_graph):
    assert diamond_graph.port_between("s1", "s2") == 2
    assert diamond_graph.port_between("s2", "s1") == 1


def test_port_between_non_neighbors_raises(diamond_graph):
    with pytest.raises(ValueError):
        diamond_graph.port_between("s2", "s3")


def test_validate_valid_path(diamond_graph):
    assert diamond_graph.validate_path(["h1", "s1", "s2", "s4", "h4"]) is None


def test_validate_rejects_nonexistent_switch(diamond_graph):
    reason = diamond_graph.validate_path(["h1", "s1", "s8", "s4", "h4"])
    assert reason is not None
    assert "s8" in reason


def test_validate_rejects_discontinuous_path(diamond_graph):
    # s2 and s3 are not directly linked in the diamond
    reason = diamond_graph.validate_path(["h1", "s1", "s2", "s3", "s4", "h4"])
    assert reason is not None


def test_validate_rejects_wrong_start_switch(diamond_graph):
    reason = diamond_graph.validate_path(["h1", "s3", "s1", "h4"])
    assert reason is not None
