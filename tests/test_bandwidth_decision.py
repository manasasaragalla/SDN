"""Unit tests for the bandwidth decision layer, using a stub
deploy_and_measure so no mininet/root/Ryu/ovs-vsctl is needed here -- the
real callable is exercised by the CLI against the live testbed instead."""
import pytest

from backend.decision.bandwidth_decision import select_bandwidth_path
from backend.models.decision import DecisionError
from backend.models.measurement import ThroughputResult
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
            Link(node_a="s1", port_a=2, node_b="s2", port_b=1, bw_mbps=10.0),
            Link(node_a="s2", port_a=2, node_b="s4", port_b=2, bw_mbps=10.0),
            Link(node_a="s1", port_a=3, node_b="s3", port_b=1, bw_mbps=50.0),
            Link(node_a="s3", port_a=2, node_b="s4", port_b=3, bw_mbps=50.0),
        ],
    )


def _fake_throughput(received_mbps, succeeded=True):
    return ThroughputResult(sent_mbps=received_mbps, received_mbps=received_mbps, succeeded=succeeded,
                             raw_output="fake")


def test_selects_path_with_higher_measured_throughput(diamond_graph):
    measured = {
        ("h1", "s1", "s2", "s4", "h4"): _fake_throughput(6.0),   # Path A, contended
        ("h1", "s1", "s3", "s4", "h4"): _fake_throughput(22.0),  # Path B, uncontended
    }

    def deploy_and_measure(path):
        return measured[tuple(path)]

    result = select_bandwidth_path(diamond_graph, "h1", "h4", target_mbps=20.0, deploy_and_measure=deploy_and_measure)
    assert result.selected_path == ["h1", "s1", "s3", "s4", "h4"]
    assert result.selected_measurement.throughput.achieved_mbps == 22.0
    assert result.selected_measurement.static_capacity_mbps == 50.0


def test_failed_candidate_is_not_selected(diamond_graph):
    def deploy_and_measure(path):
        if path == ["h1", "s1", "s2", "s4", "h4"]:
            return _fake_throughput(None, succeeded=False)
        return _fake_throughput(15.0)

    result = select_bandwidth_path(diamond_graph, "h1", "h4", target_mbps=20.0, deploy_and_measure=deploy_and_measure)
    assert result.selected_path == ["h1", "s1", "s3", "s4", "h4"]


def test_all_candidates_failed_raises(diamond_graph):
    def deploy_and_measure(path):
        return _fake_throughput(None, succeeded=False)

    with pytest.raises(DecisionError):
        select_bandwidth_path(diamond_graph, "h1", "h4", target_mbps=20.0, deploy_and_measure=deploy_and_measure)


def test_result_carries_target_and_all_candidates(diamond_graph):
    measured = {
        ("h1", "s1", "s2", "s4", "h4"): _fake_throughput(6.0),
        ("h1", "s1", "s3", "s4", "h4"): _fake_throughput(22.0),
    }

    def deploy_and_measure(path):
        return measured[tuple(path)]

    result = select_bandwidth_path(diamond_graph, "h1", "h4", target_mbps=20.0, deploy_and_measure=deploy_and_measure)
    assert result.target_mbps == 20.0
    assert len(result.candidates) == 2


def test_prefers_cheapest_path_that_meets_target_over_a_faster_one(diamond_graph):
    """Phase 12: when more than one candidate already meets the target,
    the decision layer picks the cheapest sufficient one (frees the
    higher-capacity path for flows that actually need it), not the
    fastest one overall."""
    measured = {
        ("h1", "s1", "s2", "s4", "h4"): _fake_throughput(9.0),   # Path A, meets a 5 Mbps target
        ("h1", "s1", "s3", "s4", "h4"): _fake_throughput(45.0),  # Path B, also meets it, but far more than needed
    }

    def deploy_and_measure(path):
        return measured[tuple(path)]

    result = select_bandwidth_path(diamond_graph, "h1", "h4", target_mbps=5.0, deploy_and_measure=deploy_and_measure)
    assert result.selected_path == ["h1", "s1", "s2", "s4", "h4"]
    assert result.selected_measurement.throughput.achieved_mbps == 9.0


def test_falls_back_to_highest_throughput_when_none_meet_target(diamond_graph):
    """When nothing meets the target, still pick the best real option
    available (unchanged from the pre-Phase-12 behavior)."""
    measured = {
        ("h1", "s1", "s2", "s4", "h4"): _fake_throughput(6.0),
        ("h1", "s1", "s3", "s4", "h4"): _fake_throughput(22.0),
    }

    def deploy_and_measure(path):
        return measured[tuple(path)]

    result = select_bandwidth_path(diamond_graph, "h1", "h4", target_mbps=30.0, deploy_and_measure=deploy_and_measure)
    assert result.selected_path == ["h1", "s1", "s3", "s4", "h4"]
    assert result.selected_measurement.throughput.achieved_mbps == 22.0
