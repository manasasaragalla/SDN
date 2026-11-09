import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.llm.base import (
    LLMParseError,
    LLMProviderResponseError,
    LLMProviderUnavailableError,
)
from backend.llm.groq_provider import DEFAULT_MODEL, GROQ_BASE_URL, GroqLLM
from backend.models.canonical_intent import Comparison
from backend.models.intent import (
    Objective,
)
from backend.models.intent_normalization import normalize_intent


def _completion(content: str):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
            )
        ]
    )


@pytest.mark.parametrize("status_code", [400, 401, 403, 404])
def test_groq_provider_classifies_rejected_model_or_request(status_code):
    client = Mock()
    error = RuntimeError(f"request rejected {status_code}")
    error.status_code = status_code
    client.chat.completions.create.side_effect = error

    with pytest.raises(LLMProviderResponseError, match=str(status_code)):
        GroqLLM(api_key="private-test-key", client=client).parse_intent(
            "Find the lowest-latency path from h1 to h4."
        )


def test_groq_provider_uses_default_model_and_validates_json(monkeypatch):
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    client = Mock()
    client.chat.completions.create.return_value = _completion(
        json.dumps(
            {
                "objective": "MINIMIZE_LATENCY",
                "source": "h1",
                "destination": "h4",
                "traffic_selector": None,
                "target": None,
                "constraints": None,
            }
        )
    )
    provider = GroqLLM(api_key="test-key", client=client)

    intent = provider.parse_intent(
        "Find the lowest-latency path.",
        source="h1",
        destination="h4",
    )

    assert provider.name == f"groq:{DEFAULT_MODEL}"
    assert intent.objective == Objective.MINIMIZE_LATENCY
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "openai/gpt-oss-120b"
    assert kwargs["response_format"] == {"type": "json_object"}
    assert "source=h1, destination=h4" in kwargs["messages"][1]["content"]
    assert "OpenFlow" in kwargs["messages"][0]["content"]


def test_groq_provider_uses_environment_configuration(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "configured-model")

    with pytest.MonkeyPatch.context() as patch:
        # Replace the constructor to verify configuration without network access.
        patch.setattr(
            "backend.llm.groq_provider.OpenAI",
            lambda **kwargs: (kwargs, GROQ_BASE_URL),
        )
        provider = GroqLLM()

    assert provider.name == "groq:configured-model"
    assert provider.client == (
        {"api_key": "test-key", "base_url": GROQ_BASE_URL},
        GROQ_BASE_URL,
    )


def test_groq_model_environment_variable_overrides_default(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "custom/groq-model")
    client = Mock()
    client.chat.completions.create.return_value = _completion(
        json.dumps(
            {
                "objective": "MINIMIZE_LATENCY",
                "source": "h1",
                "destination": "h4",
                "traffic_selector": None,
                "target": None,
                "constraints": None,
            }
        )
    )
    provider = GroqLLM(api_key="test-key", client=client)

    provider.parse_intent("Find the lowest-latency path from h1 to h4.")

    assert provider.name == "groq:custom/groq-model"
    assert client.chat.completions.create.call_args.kwargs["model"] == "custom/groq-model"


def test_groq_provider_requires_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(LLMParseError, match="GROQ_API_KEY"):
        GroqLLM()


def test_groq_mixed_legacy_objective_and_generalized_constraint_normalize():
    client = Mock()
    client.chat.completions.create.return_value = _completion(
        json.dumps(
            {
                "objective": "MINIMIZE_LATENCY",
                "source": "h1",
                "destination": "h4",
                "traffic_selector": None,
                "target": None,
                "constraints": {
                    "loss_tolerance": None,
                    "metrics": [
                        {
                            "metric": "BANDWIDTH",
                            "unit": "Mbps",
                            "comparison": "GT",
                            "value": 20,
                            "lower_bound": None,
                            "upper_bound": None,
                            "min_value": None,
                            "max_value": None,
                            "optimization": None,
                        }
                    ],
                },
            }
        )
    )
    parsed = GroqLLM(api_key="test-key", client=client).parse_intent(
        "Minimize latency between h1 and h4 while maintaining bandwidth above 20 Mbps."
    )

    canonical = normalize_intent(parsed).canonical
    assert parsed.objective == Objective.MINIMIZE_LATENCY
    assert canonical.optimization.metric == "latency"
    assert canonical.optimization.direction.value == "MINIMIZE"
    assert len(canonical.constraints) == 1
    assert canonical.constraints[0].metric == "bandwidth"
    assert canonical.constraints[0].comparison == Comparison.GT
    assert canonical.constraints[0].value == 20


@pytest.mark.parametrize("status_code", [429, 503])
def test_groq_provider_classifies_rate_limit_and_server_errors(status_code):
    client = Mock()
    error = RuntimeError(f"request failed {status_code}")
    error.status_code = status_code
    client.chat.completions.create.side_effect = error

    with pytest.raises(LLMProviderUnavailableError, match=str(status_code)):
        GroqLLM(api_key="private-test-key", client=client).parse_intent(
            "Find the lowest-latency path from h1 to h4."
        )


def test_groq_provider_rejects_malformed_or_invalid_response():
    client = Mock()
    client.chat.completions.create.return_value = _completion('{"source":"h1"}')

    with pytest.raises(LLMParseError, match="valid intent"):
        GroqLLM(api_key="test-key", client=client).parse_intent(
            "Find the lowest-latency path from h1 to h4."
        )


def test_factory_selects_groq_provider(monkeypatch):
    from backend.llm.factory import get_llm_provider

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    provider = get_llm_provider("groq")

    assert isinstance(provider, GroqLLM)
