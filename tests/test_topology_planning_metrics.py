import math

import pytest

from backend.models.canonical_intent import (
    CanonicalIntent,
    Comparison,
    MetricConstraint,
    TrafficScope,
)
from backend.models.network import Host, Link, TopologyGraph
from backend.planner.path_enumeration import enumerate_candidate_paths
from backend.planner.topology_planning import _path_facts, plan_on_topology


def _graph(*, capacity=None, delay=None, loss=None):
    return TopologyGraph(
        switches={"s1": 1},
        hosts={
            "h1": Host(
                name="h1",
                ip="10.0.0.1",
                mac="00:00:00:00:00:01",
                switch="s1",
                switch_port=1,
                attachment_capacity_mbps=capacity,
                attachment_delay_ms=delay,
                attachment_packet_loss_percent=loss,
            ),
            "h4": Host(
                name="h4",
                ip="10.0.0.4",
                mac="00:00:00:00:00:04",
                switch="s1",
                switch_port=2,
                attachment_capacity_mbps=capacity,
                attachment_delay_ms=delay,
                attachment_packet_loss_percent=loss,
            ),
        },
        links=[],
    )


def _path(graph):
    return enumerate_candidate_paths(graph, "h1", "h4", 10).paths[0]


@pytest.mark.parametrize(
    ("field", "constraint"),
    [
        (
            "bandwidth",
            MetricConstraint(
                metric="bandwidth",
                comparison=Comparison.GTE,
                value=1,
                unit="Mbps",
            ),
        ),
        (
            "latency",
            MetricConstraint(
                metric="latency",
                comparison=Comparison.LTE,
                value=100,
                unit="ms",
            ),
        ),
        (
            "packet_loss",
            MetricConstraint(
                metric="packet_loss",
                comparison=Comparison.LTE,
                value=50,
                unit="%",
            ),
        ),
    ],
)
def test_missing_host_attachment_metric_is_not_treated_as_complete(field, constraint):
    complete = {
        "bandwidth": {"capacity": 100},
        "latency": {"delay": 2},
        "packet_loss": {"loss": 1},
    }[field]
    graph = _graph(**complete)
    graph.hosts["h4"].attachment_capacity_mbps = (
        None if field == "bandwidth" else complete.get("capacity")
    )
    graph.hosts["h4"].attachment_delay_ms = (
        None if field == "latency" else complete.get("delay")
    )
    graph.hosts["h4"].attachment_packet_loss_percent = (
        None if field == "packet_loss" else complete.get("loss")
    )

    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        constraints=[constraint],
    )
    result = plan_on_topology(intent, graph)

    candidate = result["candidates"][0]
    metric_key = {
        "bandwidth": "bandwidth_mbps",
        "latency": "latency_ms",
        "packet_loss": "packet_loss_percent",
    }[field]
    assert candidate["configured_metrics"][metric_key] is None
    assert candidate["status"] == "UNKNOWN"
    assert candidate["constraints"][0]["status"] == "UNKNOWN"
    assert result["selected_candidate_id"] is None


def test_complete_host_attachment_metrics_preserve_existing_aggregates():
    graph = _graph(capacity=100, delay=2, loss=10)
    metrics, _ = _path_facts(graph, _path(graph))

    assert metrics["bandwidth_mbps"] == 100
    assert metrics["latency_ms"] == 4
    assert metrics["packet_loss_percent"] == pytest.approx(19)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("capacity", -1),
        ("capacity", 0),
        ("capacity", math.inf),
        ("capacity", math.nan),
        ("delay", -1),
        ("delay", math.inf),
        ("delay", math.nan),
        ("loss", -1),
        ("loss", 101),
        ("loss", math.inf),
        ("loss", math.nan),
    ],
)
def test_invalid_host_attachment_metrics_return_unknown(field, invalid):
    graph = _graph(
        capacity=100,
        delay=2,
        loss=10,
    )
    if field == "capacity":
        graph.hosts["h4"].attachment_capacity_mbps = invalid
    elif field == "delay":
        graph.hosts["h4"].attachment_delay_ms = invalid
    else:
        graph.hosts["h4"].attachment_packet_loss_percent = invalid

    metrics, _ = _path_facts(graph, _path(graph))

    metric_key = {
        "capacity": "bandwidth_mbps",
        "delay": "latency_ms",
        "loss": "packet_loss_percent",
    }[field]
    assert metrics[metric_key] is None


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("bw_mbps", -1),
        ("bw_mbps", 0),
        ("bw_mbps", math.inf),
        ("bw_mbps", math.nan),
        ("delay_ms", -1),
        ("delay_ms", math.inf),
        ("delay_ms", math.nan),
        ("packet_loss_percent", -1),
        ("packet_loss_percent", 101),
        ("packet_loss_percent", math.inf),
        ("packet_loss_percent", math.nan),
    ],
)
def test_invalid_switch_link_metrics_return_unknown(field, invalid):
    graph = TopologyGraph(
        switches={"s1": 1, "s2": 2},
        hosts={
            "h1": Host(
                name="h1",
                ip="10.0.0.1",
                mac="00:00:00:00:00:01",
                switch="s1",
                switch_port=1,
                attachment_capacity_mbps=100,
                attachment_delay_ms=1,
                attachment_packet_loss_percent=0,
            ),
            "h4": Host(
                name="h4",
                ip="10.0.0.4",
                mac="00:00:00:00:00:04",
                switch="s2",
                switch_port=1,
                attachment_capacity_mbps=100,
                attachment_delay_ms=1,
                attachment_packet_loss_percent=0,
            ),
        },
        links=[
            Link(
                node_a="s1",
                port_a=2,
                node_b="s2",
                port_b=2,
                bw_mbps=100,
                delay_ms=2,
                packet_loss_percent=1,
            )
        ],
    )
    setattr(graph.links[0], field, invalid)

    metrics, _ = _path_facts(graph, _path(graph))

    metric_key = {
        "bw_mbps": "bandwidth_mbps",
        "delay_ms": "latency_ms",
        "packet_loss_percent": "packet_loss_percent",
    }[field]
    assert metrics[metric_key] is None
