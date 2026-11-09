"""Unit tests for the latency decision layer, using a stub
deploy_and_measure so no mininet/root/Ryu is needed here -- the real
callable is exercised by the end-to-end integration test instead."""
import pytest

from backend.decision.latency_decision import select_latency_path
from backend.cli import _latency_satisfied
from backend.models.decision import DecisionError
from backend.models.measurement import LatencyResult
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


def _fake_latency(rtt_avg_ms, received=5):
    return LatencyResult(
        packets_sent=5, packets_received=received, packet_loss_pct=0.0 if received else 100.0,
        rtt_avg_ms=rtt_avg_ms, raw_output="fake",
    )


def test_selects_path_with_lower_measured_latency(diamond_graph):
    measured = {
        ("h1", "s1", "s2", "s4", "h4"): _fake_latency(18.0),
        ("h1", "s1", "s3", "s4", "h4"): _fake_latency(7.0),
    }

    def deploy_and_measure(path):
        return measured[tuple(path)]

    result = select_latency_path(diamond_graph, "h1", "h4", deploy_and_measure)
    assert result.selected_path == ["h1", "s1", "s3", "s4", "h4"]
    assert len(result.candidates) == 2
    assert result.selected_measurement.latency.rtt_avg_ms == 7.0


def test_unreachable_candidate_is_not_selected(diamond_graph):
    def deploy_and_measure(path):
        if path == ["h1", "s1", "s2", "s4", "h4"]:
            return _fake_latency(None, received=0)
        return _fake_latency(12.0)

    result = select_latency_path(diamond_graph, "h1", "h4", deploy_and_measure)
    assert result.selected_path == ["h1", "s1", "s3", "s4", "h4"]


def test_all_candidates_unreachable_raises(diamond_graph):
    def deploy_and_measure(path):
        return _fake_latency(None, received=0)

    with pytest.raises(DecisionError):
        select_latency_path(diamond_graph, "h1", "h4", deploy_and_measure)


def test_no_path_between_hosts_raises():
    graph = TopologyGraph(
        switches={"s1": 1, "s2": 2},
        hosts={
            "h1": Host(name="h1", ip="10.0.0.1", mac="00:00:00:00:00:01", switch="s1", switch_port=1),
            "h4": Host(name="h4", ip="10.0.0.4", mac="00:00:00:00:00:04", switch="s2", switch_port=1),
        },
        links=[],  # s1 and s2 are not connected at all
    )
    with pytest.raises(DecisionError):
        select_latency_path(graph, "h1", "h4", lambda path: _fake_latency(1.0))


def test_latency_satisfaction_requires_beating_every_reachable_alternative():
    assert not _latency_satisfied(5.0, [4.0, 7.0])
    assert _latency_satisfied(5.0, [7.0, 8.0])
    assert not _latency_satisfied(5.0, [5.0])
    assert _latency_satisfied(5.0, [])


def test_latency_satisfaction_rejects_missing_measurement():
    assert not _latency_satisfied(None, [])
    assert not _latency_satisfied(5.0, [None])
