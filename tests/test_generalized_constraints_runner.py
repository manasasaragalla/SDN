from backend.models.canonical_intent import Comparison, OptimizationDirection
from evaluation.run_generalized_constraints import _intent


def test_minimize_latency_runner_intent_is_an_objective_only_request():
    intent = _intent("minimize-latency")

    assert intent.constraints == []
    assert intent.optimization.metric == "latency"
    assert intent.optimization.direction == OptimizationDirection.MINIMIZE
    assert intent.optimization.unit == "ms"


def test_maximize_bandwidth_runner_intent_is_an_objective_only_request():
    intent = _intent("maximize-bandwidth")

    assert intent.constraints == []
    assert intent.optimization.metric == "bandwidth"
    assert intent.optimization.direction == OptimizationDirection.MAXIMIZE
    assert intent.optimization.unit == "Mbps"


def test_constrained_latency_runner_intent_uses_bandwidth_as_hard_gate():
    intent = _intent("constrained-minimize-latency")

    assert len(intent.constraints) == 1
    assert intent.constraints[0].metric == "bandwidth"
    assert intent.constraints[0].comparison == Comparison.GTE
    assert intent.constraints[0].value == 20
    assert intent.optimization.metric == "latency"
    assert intent.optimization.direction == OptimizationDirection.MINIMIZE
