
"""Tests for generalized network intent extraction and validation."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.models.intent import (
    Constraints,
    Metric,
    MetricConstraint,
    MetricUnit,
    Objective,
    Operator,
    StructuredIntent,
)
from backend.models.intent_normalization import normalize_intent
from backend.models.canonical_intent import Comparison

from backend.llm.base import LLMParseError
from backend.llm.mock import MockLLM
from backend.llm.openai_provider import OpenAILLM
from backend.llm.schema import LLMIntentOutput


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def make_metric(metric, unit, minimum=None, maximum=None, optimization=None):
    return MetricConstraint(
        metric=metric,
        unit=unit,
        min_value=minimum,
        max_value=maximum,
        optimization=optimization,
    )


def make_openai_client(parsed=None, refusal=None):
    message = SimpleNamespace(
        parsed=parsed,
        refusal=refusal,
    )

    completion = SimpleNamespace(
        choices=[
            SimpleNamespace(message=message)
        ]
    )

    parse_method = lambda **kwargs: completion

    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                parse=parse_method
            )
        )
    )


# ---------------------------------------------------------
# 1. Schema validation
# ---------------------------------------------------------

def test_bandwidth_minimum_constraint():
    constraint = make_metric(
        Metric.BANDWIDTH,
        MetricUnit.MBPS,
        minimum=30,
    )

    assert constraint.min_value == 30
    assert constraint.max_value is None


def test_bandwidth_maximum_constraint():
    constraint = make_metric(
        Metric.BANDWIDTH,
        MetricUnit.MBPS,
        maximum=50,
    )

    assert constraint.min_value is None
    assert constraint.max_value == 50


def test_bandwidth_range_constraint():
    constraint = make_metric(
        Metric.BANDWIDTH,
        MetricUnit.MBPS,
        minimum=30,
        maximum=50,
    )

    assert constraint.min_value == 30
    assert constraint.max_value == 50


def test_exact_bandwidth_constraint():
    constraint = make_metric(
        Metric.BANDWIDTH,
        MetricUnit.MBPS,
        minimum=40,
        maximum=40,
    )

    assert constraint.min_value == constraint.max_value


def test_minimize_latency():
    constraint = make_metric(
        Metric.LATENCY,
        MetricUnit.MS,
        optimization=Operator.MINIMIZE,
    )

    assert constraint.optimization == Operator.MINIMIZE


def test_maximize_bandwidth():
    constraint = make_metric(
        Metric.BANDWIDTH,
        MetricUnit.MBPS,
        optimization=Operator.MAXIMIZE,
    )

    assert constraint.optimization == Operator.MAXIMIZE


def test_reject_minimum_greater_than_maximum():
    with pytest.raises(ValidationError):
        make_metric(
            Metric.BANDWIDTH,
            MetricUnit.MBPS,
            minimum=60,
            maximum=30,
        )


def test_reject_invalid_metric_unit():
    with pytest.raises(ValidationError):
        make_metric(
            Metric.LATENCY,
            MetricUnit.MBPS,
            maximum=20,
        )


def test_reject_zero_bandwidth():
    with pytest.raises(ValidationError):
        make_metric(
            Metric.BANDWIDTH,
            MetricUnit.MBPS,
            minimum=0,
        )


def test_reject_packet_loss_above_100_percent():
    with pytest.raises(ValidationError):
        make_metric(
            Metric.PACKET_LOSS,
            MetricUnit.PERCENT,
            maximum=101,
        )


def test_reject_bounds_and_optimization_together():
    with pytest.raises(ValidationError):
        make_metric(
            Metric.LATENCY,
            MetricUnit.MS,
            maximum=20,
            optimization=Operator.MINIMIZE,
        )


def test_reject_duplicate_metrics():
    with pytest.raises(ValidationError):
        Constraints(
            metrics=[
                make_metric(
                    Metric.LATENCY,
                    MetricUnit.MS,
                    maximum=20,
                ),
                make_metric(
                    Metric.LATENCY,
                    MetricUnit.MS,
                    maximum=30,
                ),
            ]
        )


def test_reject_same_source_and_destination():
    with pytest.raises(ValidationError):
        StructuredIntent(
            source="h1",
            destination="h1",
            constraints=Constraints(
                metrics=[
                    make_metric(
                        Metric.LATENCY,
                        MetricUnit.MS,
                        maximum=20,
                    )
                ]
            ),
        )


def test_reject_intent_without_objective_or_constraints():
    with pytest.raises(ValidationError):
        StructuredIntent(
            source="h1",
            destination="h4",
        )


# ---------------------------------------------------------
# 2. Multiple constraints in one intent
# ---------------------------------------------------------

def test_multiple_metrics_in_one_intent():
    intent = StructuredIntent(
        source="h1",
        destination="h4",
        constraints=Constraints(
            metrics=[
                make_metric(
                    Metric.LATENCY,
                    MetricUnit.MS,
                    maximum=30,
                ),
                make_metric(
                    Metric.BANDWIDTH,
                    MetricUnit.MBPS,
                    minimum=15,
                    maximum=50,
                ),
            ]
        ),
    )

    assert len(intent.constraints.metrics) == 2
    assert intent.constraints.metrics[0].max_value == 30
    assert intent.constraints.metrics[1].min_value == 15
    assert intent.constraints.metrics[1].max_value == 50


# ---------------------------------------------------------
# 3. LLM-facing output schema
# ---------------------------------------------------------

def test_llm_output_accepts_generalized_range():
    output = LLMIntentOutput(
        source="h1",
        destination="h4",
        constraints=Constraints(
            metrics=[
                make_metric(
                    Metric.BANDWIDTH,
                    MetricUnit.MBPS,
                    minimum=30,
                    maximum=50,
                )
            ]
        ),
    )

    assert output.constraints.metrics[0].min_value == 30
    assert output.constraints.metrics[0].max_value == 50


def test_llm_output_rejects_internal_action_field():
    with pytest.raises(ValidationError):
        LLMIntentOutput(
            source="h1",
            destination="h4",
            action="BLOCK",
            constraints=Constraints(
                metrics=[
                    make_metric(
                        Metric.LATENCY,
                        MetricUnit.MS,
                        maximum=20,
                    )
                ]
            ),
        )


def test_llm_output_accepts_legacy_objective_with_generalized_metrics():
    output = LLMIntentOutput(
        objective="MINIMIZE_LATENCY",
        source="h1",
        destination="h4",
        constraints=Constraints(
            metrics=[
                MetricConstraint(
                    metric=Metric.BANDWIDTH,
                    unit=MetricUnit.MBPS,
                    comparison=Comparison.GT,
                    value=20,
                )
            ]
        ),
    )

    intent = output.to_structured_intent()
    canonical = normalize_intent(intent).canonical
    assert canonical.optimization.metric == "latency"
    assert canonical.optimization.direction.value == "MINIMIZE"
    assert [(item.metric, item.comparison.value, item.value) for item in canonical.constraints] == [
        ("bandwidth", "GT", 20),
    ]


# ---------------------------------------------------------
# 4. Mock provider
# ---------------------------------------------------------

@pytest.fixture
def mock_llm():
    return MockLLM()


def test_mock_extracts_bandwidth_range(mock_llm):
    intent = mock_llm.parse_intent(
        "Keep bandwidth between 30 and 50 Mbps between h1 and h4."
    )

    assert intent.source == "h1"
    assert intent.destination == "h4"

    constraint = intent.constraints.metrics[0]

    assert constraint.metric == Metric.BANDWIDTH
    assert constraint.min_value == 30
    assert constraint.max_value == 50


def test_mock_extracts_minimum_bandwidth(mock_llm):
    intent = mock_llm.parse_intent(
        "Maintain at least 10 Mbps between h1 and h4."
    )

    constraint = intent.constraints.metrics[0]

    assert constraint.metric == Metric.BANDWIDTH
    assert constraint.comparison == Comparison.GTE
    assert constraint.value == 10


def test_mock_extracts_maximum_latency(mock_llm):
    intent = mock_llm.parse_intent(
        "Keep latency below 20 ms between h1 and h4."
    )

    constraint = intent.constraints.metrics[0]

    assert constraint.metric == Metric.LATENCY
    assert constraint.comparison == Comparison.LT
    assert constraint.value == 20


def test_mock_extracts_minimize_latency(mock_llm):
    intent = mock_llm.parse_intent(
        "Minimize latency between h1 and h4."
    )

    assert intent.objective == Objective.MINIMIZE_LATENCY
    canonical = normalize_intent(intent).canonical
    assert canonical.optimization.metric == "latency"
    assert canonical.optimization.direction.value == "MINIMIZE"


def test_mock_extracts_multiple_constraints(mock_llm):
    intent = mock_llm.parse_intent(
        "Keep latency below 30 ms and bandwidth at least "
        "15 Mbps between h1 and h4."
    )

    assert len(intent.constraints.metrics) == 2

    metrics = {
        item.metric: item
        for item in intent.constraints.metrics
    }

    assert metrics[Metric.LATENCY].comparison == Comparison.LT
    assert metrics[Metric.LATENCY].value == 30
    assert metrics[Metric.BANDWIDTH].comparison == Comparison.GTE
    assert metrics[Metric.BANDWIDTH].value == 15


def test_mock_rejects_missing_endpoints(mock_llm):
    with pytest.raises(LLMParseError):
        mock_llm.parse_intent(
            "Keep bandwidth between 30 and 50 Mbps."
        )


def test_mock_rejects_unsupported_request(mock_llm):
    with pytest.raises(LLMParseError):
        mock_llm.parse_intent(
            "Configure a completely unsupported network feature."
        )


# ---------------------------------------------------------
# 5. OpenAI provider with mocked responses
# ---------------------------------------------------------

def test_openai_provider_returns_structured_intent():
    parsed = LLMIntentOutput(
        source="h1",
        destination="h4",
        constraints=Constraints(
            metrics=[
                make_metric(
                    Metric.BANDWIDTH,
                    MetricUnit.MBPS,
                    minimum=30,
                    maximum=50,
                )
            ]
        ),
    )

    client = make_openai_client(parsed=parsed)

    provider = OpenAILLM(
        api_key="test-key",
        model="gpt-4o-mini",
        client=client,
    )

    intent = provider.parse_intent(
        "Keep bandwidth between 30 and 50 Mbps between h1 and h4."
    )

    assert isinstance(intent, StructuredIntent)
    assert intent.source == "h1"
    assert intent.destination == "h4"

    constraint = intent.constraints.metrics[0]

    assert constraint.min_value == 30
    assert constraint.max_value == 50


def test_openai_provider_handles_refusal():
    client = make_openai_client(
        parsed=None,
        refusal="I cannot process this request.",
    )

    provider = OpenAILLM(
        api_key="test-key",
        client=client,
    )

    with pytest.raises(LLMParseError):
        provider.parse_intent("Some request")


def test_openai_provider_handles_missing_structured_output():
    client = make_openai_client(parsed=None)

    provider = OpenAILLM(
        api_key="test-key",
        client=client,
    )

    with pytest.raises(LLMParseError):
        provider.parse_intent("Some request")


def test_openai_provider_rejects_empty_input():
    client = make_openai_client()

    provider = OpenAILLM(
        api_key="test-key",
        client=client,
    )

    with pytest.raises(LLMParseError):
        provider.parse_intent("   ")
