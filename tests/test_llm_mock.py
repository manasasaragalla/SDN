"""Unit tests for the deterministic MockLLM and the provider factory."""
import os

import pytest

from backend.llm.base import LLMParseError
from backend.llm.factory import get_llm_provider
from backend.llm.mock import MockLLM
from backend.models.canonical_intent import Comparison
from backend.models.intent import LossTolerance, Objective
from backend.models.intent_normalization import normalize_intent


def test_latency_intent_matches_brief_example():
    llm = MockLLM()
    intent = llm.parse_intent("Give h1 to h4 the lowest-latency path.")
    assert intent.objective == Objective.MINIMIZE_LATENCY
    assert intent.source == "h1"
    assert intent.destination == "h4"
    assert intent.target is None


def test_bandwidth_intent_matches_brief_example():
    llm = MockLLM()
    intent = llm.parse_intent("Provide at least 20 Mbps between h1 and h4.")
    assert intent.objective == Objective.MIN_BANDWIDTH
    assert intent.source == "h1"
    assert intent.destination == "h4"
    assert intent.target.bandwidth_mbps == 20


def test_mock_uses_explicit_ui_scope_when_request_omits_hosts():
    intent = MockLLM().parse_intent(
        "Ensure bandwidth is at least 20 Mbps.",
        source="h1",
        destination="h4",
    )
    canonical = normalize_intent(intent).canonical

    assert canonical.scope.source == "h1"
    assert canonical.scope.destination == "h4"
    assert canonical.constraints[0].metric == "bandwidth"
    assert canonical.constraints[0].value == 20


def test_latency_with_loss_tolerance_constraint():
    llm = MockLLM()
    intent = llm.parse_intent("Give h1 to h4 the lowest-latency path and tolerate some packet loss.")
    assert intent.constraints.loss_tolerance == LossTolerance.MEDIUM


def test_unsupported_phrasing_raises_llm_parse_error():
    llm = MockLLM()
    with pytest.raises(LLMParseError):
        llm.parse_intent("Optimize energy consumption between h1 and h4.")


@pytest.mark.parametrize(
    ("text", "metric", "comparison", "value"),
    [
        ("latency < 50 ms between h1 and h4", "latency", Comparison.LT, 50),
        ("latency <= 50 ms between h1 and h4", "latency", Comparison.LTE, 50),
        ("bandwidth > 20 Mbps between h1 and h4", "bandwidth", Comparison.GT, 20),
        ("bandwidth >= 20 Mbps between h1 and h4", "bandwidth", Comparison.GTE, 20),
        ("packet_loss < 1% between h1 and h4", "packet_loss", Comparison.LT, 1),
        ("packet_loss <= 1% between h1 and h4", "packet_loss", Comparison.LTE, 1),
        ("latency exactly 50 ms between h1 and h4", "latency", Comparison.EQ, 50),
        ("latency less than 50 ms between h1 and h4", "latency", Comparison.LT, 50),
        ("latency below 50 ms between h1 and h4", "latency", Comparison.LT, 50),
        ("latency at most 50 ms between h1 and h4", "latency", Comparison.LTE, 50),
        ("bandwidth at least 20 Mbps between h1 and h4", "bandwidth", Comparison.GTE, 20),
        ("packet loss less than or equal to 1 percent between h1 and h4", "packet_loss", Comparison.LTE, 1),
        ("bandwidth no less than 20 Mbps between h1 and h4", "bandwidth", Comparison.GTE, 20),
        ("latency under 50 ms between h1 and h4", "latency", Comparison.LT, 50),
        ("bandwidth over 20 Mbps between h1 and h4", "bandwidth", Comparison.GT, 20),
        ("packet loss below 1 percent between h1 and h4", "packet_loss", Comparison.LT, 1),
        ("packet loss at most 1 percent between h1 and h4", "packet_loss", Comparison.LTE, 1),
        ("bandwidth more than 20 Mbps between h1 and h4", "bandwidth", Comparison.GT, 20),
        ("bandwidth at least 20 Mbps between h1 and h4", "bandwidth", Comparison.GTE, 20),
    ],
)
def test_mock_preserves_strict_and_inclusive_comparisons(
    text, metric, comparison, value
):
    normalized = normalize_intent(MockLLM().parse_intent(text))

    assert len(normalized.canonical.constraints) == 1
    actual = normalized.canonical.constraints[0]
    assert actual.metric == metric
    assert actual.comparison == comparison
    assert actual.value == value


def test_mock_parses_multiple_comparisons_conjunctively():
    intent = MockLLM().parse_intent(
        "latency < 50 ms and bandwidth >= 20 Mbps between h1 and h4"
    )
    normalized = normalize_intent(intent)

    assert [
        (item.metric, item.comparison, item.value)
        for item in normalized.canonical.constraints
    ] == [
        ("latency", Comparison.LT, 50),
        ("bandwidth", Comparison.GTE, 20),
    ]


def test_mock_parses_reported_multiple_constraint_wording():
    canonical = normalize_intent(
        MockLLM().parse_intent(
            "Find a path from h1 to h4 with bandwidth at least 20 Mbps "
            "and latency below 50 ms."
        )
    ).canonical

    assert [
        (item.metric, item.comparison, item.value)
        for item in canonical.constraints
    ] == [
        ("bandwidth", Comparison.GTE, 20),
        ("latency", Comparison.LT, 50),
    ]


def test_mock_parses_combined_bandwidth_loss_and_latency_objective():
    canonical = normalize_intent(
        MockLLM().parse_intent(
            "Find a route from h1 to h4 that has at least 20 Mbps bandwidth "
            "and keeps packet loss below 1 percent, preferably with the "
            "lowest latency."
        )
    ).canonical

    assert canonical.optimization.metric == "latency"
    assert canonical.optimization.direction.value == "MINIMIZE"
    assert [
        (item.metric, item.comparison, item.value)
        for item in canonical.constraints
    ] == [
        ("packet_loss", Comparison.LT, 1),
        ("bandwidth", Comparison.GTE, 20),
    ]


@pytest.mark.parametrize(
    ("text", "expected_constraints", "expected_optimization"),
    [
        (
            "Find a path from h1 to h4 with bandwidth greater than 20 Mbps.",
            [("bandwidth", Comparison.GT, 20)],
            None,
        ),
        (
            "Find the lowest-latency path from h1 to h4.",
            [],
            ("latency", "MINIMIZE"),
        ),
        (
            "Minimize latency between h1 and h4 while maintaining bandwidth above 20 Mbps.",
            [("bandwidth", Comparison.GT, 20)],
            ("latency", "MINIMIZE"),
        ),
        (
            "Find a path from h1 to h4 with bandwidth above 1000 Mbps.",
            [("bandwidth", Comparison.GT, 1000)],
            None,
        ),
        (
            "Maximize bandwidth between h1 and h4.",
            [],
            ("bandwidth", "MAXIMIZE"),
        ),
    ],
)
def test_mock_parses_end_to_end_acceptance_intents(
    text, expected_constraints, expected_optimization
):
    canonical = normalize_intent(MockLLM().parse_intent(text)).canonical

    assert (canonical.scope.source, canonical.scope.destination) == ("h1", "h4")
    assert [
        (constraint.metric, constraint.comparison, constraint.value)
        for constraint in canonical.constraints
    ] == expected_constraints
    if expected_optimization is None:
        assert canonical.optimization is None
    else:
        assert (
            canonical.optimization.metric,
            canonical.optimization.direction.value,
        ) == expected_optimization


def test_mock_uses_canonical_maximize_bandwidth_objective():
    intent = MockLLM().parse_intent(
        "Maximize bandwidth between h1 and h4."
    )

    assert intent.objective == Objective.MAXIMIZE_BANDWIDTH
    canonical = normalize_intent(intent).canonical
    assert canonical.optimization.metric == "bandwidth"
    assert canonical.optimization.direction.value == "MAXIMIZE"


def test_mock_parses_between_as_an_inclusive_range():
    normalized = normalize_intent(
        MockLLM().parse_intent(
            "latency between 5 and 50 ms between h1 and h4"
        )
    )

    constraint = normalized.canonical.constraints[0]
    assert constraint.comparison == Comparison.BETWEEN
    assert constraint.lower_bound == 5
    assert constraint.upper_bound == 50


def test_garbage_input_raises_llm_parse_error():
    llm = MockLLM()
    with pytest.raises(LLMParseError):
        llm.parse_intent("do something to the network please")


def test_factory_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    provider = get_llm_provider()
    assert provider.name == "mock"


def test_factory_respects_env_var(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    provider = get_llm_provider()
    assert isinstance(provider, MockLLM)


def test_factory_anthropic_without_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMParseError):
        get_llm_provider("anthropic")


def test_factory_gemini_without_key_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(LLMParseError, match="GEMINI_API_KEY"):
        get_llm_provider("gemini")


def test_factory_selects_gemini_provider(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    provider = get_llm_provider("gemini")
    assert provider.name == "gemini:gemini-3.6-flash"


def test_factory_unknown_provider_raises():
    with pytest.raises(ValueError):
        get_llm_provider("some-other-service")
