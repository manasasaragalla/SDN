"""Provider adapters share one validated objective vocabulary."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.llm.anthropic_provider import AnthropicLLM
from backend.llm.gemini_provider import GeminiLLM
from backend.llm.groq_provider import GroqLLM
from backend.llm.openai_provider import OpenAILLM
from backend.llm.schema import LLMIntentOutput
from backend.llm.mock import MockLLM
from backend.models.canonical_intent import Comparison
from backend.models.intent import Objective
from backend.models.intent_normalization import normalize_intent


class _Response:
    def __init__(self, value):
        self.value = value

    def read(self):
        return json.dumps(self.value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _payload(objective):
    payload = {
        "objective": objective,
        "source": "h1",
        "destination": "h4",
        "traffic_selector": None,
        "target": None,
        "constraints": None,
    }
    if objective == "MAXIMIZE_BANDWIDTH":
        payload["constraints"] = {
            "loss_tolerance": None,
            "metrics": [
                {
                    "metric": "BANDWIDTH",
                    "unit": "Mbps",
                    "comparison": "GTE",
                    "value": 20,
                },
                {
                    "metric": "PACKET_LOSS",
                    "unit": "%",
                    "comparison": "LT",
                    "value": 1,
                },
            ],
        }
    elif objective == "MIN_BANDWIDTH":
        payload["target"] = {"bandwidth_mbps": 200}
    elif objective is None:
        payload["constraints"] = {
            "loss_tolerance": None,
            "metrics": [
                {
                    "metric": "BANDWIDTH",
                    "unit": "Mbps",
                    "comparison": "GTE",
                    "value": 20,
                },
                {
                    "metric": "PACKET_LOSS",
                    "unit": "%",
                    "comparison": "LT",
                    "value": 1,
                },
            ],
        }
    return payload


def _parse_with_provider(provider_name, monkeypatch, payload):
    encoded = json.dumps(payload)
    if provider_name == "groq":
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=encoded)
                )
            ]
        )
        return GroqLLM(api_key="test-key", client=client).parse_intent(
            "Interpret the selected network objective."
        )

    if provider_name == "openai":
        message = SimpleNamespace(
            parsed=LLMIntentOutput.model_validate(payload),
            refusal=None,
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    parse=lambda **_kwargs: SimpleNamespace(
                        choices=[SimpleNamespace(message=message)]
                    )
                )
            )
        )
        return OpenAILLM(api_key="test-key", client=client).parse_intent(
            "Interpret the selected network objective."
        )

    if provider_name == "gemini":
        response_body = {
            "candidates": [
                {"content": {"parts": [{"text": encoded}]}}
            ]
        }
        monkeypatch.setattr(
            "backend.llm.gemini_provider.urllib.request.urlopen",
            lambda *_args, **_kwargs: _Response(response_body),
        )
        return GeminiLLM(api_key="test-key").parse_intent(
            "Interpret the selected network objective."
        )

    if provider_name == "anthropic":
        response_body = {"content": [{"text": encoded}]}
        monkeypatch.setattr(
            "backend.llm.anthropic_provider.urllib.request.urlopen",
            lambda *_args, **_kwargs: _Response(response_body),
        )
        return AnthropicLLM(api_key="test-key").parse_intent(
            "Interpret the selected network objective."
        )

    raise AssertionError(f"Unknown test provider {provider_name!r}")


@pytest.mark.parametrize(
    "provider_name",
    ["groq", "gemini", "openai", "anthropic"],
)
@pytest.mark.parametrize(
    ("objective", "expected_metric", "expected_direction", "expected_constraints"),
    [
        (
            "MINIMIZE_LATENCY",
            "latency",
            "MINIMIZE",
            [],
        ),
        (
            "MAXIMIZE_BANDWIDTH",
            "bandwidth",
            "MAXIMIZE",
            [
                ("bandwidth", Comparison.GTE, 20),
                ("packet_loss", Comparison.LT, 1),
            ],
        ),
        (
            "MIN_BANDWIDTH",
            None,
            None,
            [("bandwidth", Comparison.GTE, 200)],
        ),
        (
            None,
            None,
            None,
            [
                ("bandwidth", Comparison.GTE, 20),
                ("packet_loss", Comparison.LT, 1),
            ],
        ),
    ],
)
def test_remote_providers_normalize_objectives_and_constraints_consistently(
    provider_name,
    objective,
    expected_metric,
    expected_direction,
    expected_constraints,
    monkeypatch,
):
    parsed = _parse_with_provider(
        provider_name,
        monkeypatch,
        _payload(objective),
    )
    canonical = normalize_intent(parsed).canonical

    if expected_metric is None:
        assert canonical.optimization is None
    else:
        assert canonical.optimization.metric == expected_metric
        assert canonical.optimization.direction.value == expected_direction
    assert [
        (item.metric, item.comparison, item.value)
        for item in canonical.constraints
    ] == expected_constraints


def test_mock_provider_uses_canonical_maximize_objective_with_constraints():
    parsed = MockLLM().parse_intent(
        "Maximize bandwidth between h1 and h4 while maintaining bandwidth "
        "at least 20 Mbps and packet loss below 1 percent."
    )
    canonical = normalize_intent(parsed).canonical

    assert parsed.objective == Objective.MAXIMIZE_BANDWIDTH
    assert canonical.optimization.metric == "bandwidth"
    assert canonical.optimization.direction.value == "MAXIMIZE"
    assert [
        (item.metric, item.comparison, item.value)
        for item in canonical.constraints
    ] == [
        ("bandwidth", Comparison.GTE, 20),
        ("packet_loss", Comparison.LT, 1),
    ]
