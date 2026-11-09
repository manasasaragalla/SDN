
import pytest

from backend.decision.policy_engine import build_policy_plan
from backend.models.intent import (
    Constraints,
    Metric,
    MetricConstraint,
    MetricUnit,
    StructuredIntent,
)
from backend.models.network import Host, Link, TopologyGraph


@pytest.fixture
def graph():
    return TopologyGraph(
        switches={"s1": 1, "s2": 2, "s3": 3, "s4": 4},
        hosts={
            "h1": Host(
                name="h1", ip="10.0.0.1", mac="00:00:00:00:00:01",
                switch="s1", switch_port=1,
            ),
            "h4": Host(
                name="h4", ip="10.0.0.4", mac="00:00:00:00:00:04",
                switch="s4", switch_port=1,
            ),
        },
        links=[
            Link(node_a="s1", port_a=2, node_b="s2", port_b=2, bw_mbps=100),
            Link(node_a="s2", port_a=3, node_b="s4", port_b=2, bw_mbps=40),
            Link(node_a="s1", port_a=3, node_b="s3", port_b=2, bw_mbps=100),
            Link(node_a="s3", port_a=3, node_b="s4", port_b=3, bw_mbps=20),
        ],
    )


def make_intent(minimum=30, maximum=50):
    return StructuredIntent(
        source="h1",
        destination="h4",
        constraints=Constraints(
            metrics=[
                MetricConstraint(
                    metric=Metric.BANDWIDTH,
                    unit=MetricUnit.MBPS,
                    min_value=minimum,
                    max_value=maximum,
                )
            ]
        ),
    )


def test_planner_finds_feasible_bandwidth_path(graph):
    plan = build_policy_plan(make_intent(), graph)

    assert plan.feasible
    assert len(plan.candidate_paths) == 1
    assert plan.candidate_paths[0] == ["h1", "s1", "s2", "s4", "h4"]


def test_planner_rejects_path_below_minimum(graph):
    plan = build_policy_plan(make_intent(), graph)

    rejected_paths = list(plan.rejected_paths.values())

    assert any("below the required minimum" in reason for reason in rejected_paths)


def test_planner_rejects_unknown_source(graph):
    intent = make_intent()
    intent.source = "h99"

    with pytest.raises(ValueError, match="Unknown source host"):
        build_policy_plan(intent, graph)


def test_planner_preserves_requested_range(graph):
    plan = build_policy_plan(make_intent(30, 50), graph)

    constraint = plan.constraints[0]

    assert constraint.min_value == 30
    assert constraint.max_value == 50
