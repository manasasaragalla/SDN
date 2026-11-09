import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from backend.llm.base import LLMParseError, LLMProviderUnavailableError
from backend.llm.gemini_provider import GeminiLLM
from backend.models.intent import Objective


class _FakeResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _response(intent):
    return {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json.dumps(intent)}],
                }
            }
        ]
    }


def test_gemini_provider_posts_intent_prompt_and_validates_response():
    intent = {
        "objective": "MINIMIZE_LATENCY",
        "source": "h1",
        "destination": "h4",
        "traffic_selector": None,
        "target": None,
        "constraints": None,
    }
    provider = GeminiLLM(api_key="test-key")

    def fake_urlopen(request, timeout):
        assert timeout == 90
        assert request.full_url.endswith(
            "/models/gemini-3.6-flash:generateContent"
        )
        assert request.get_header("X-goog-api-key") == "test-key"
        assert "test-key" not in request.full_url
        payload = json.loads(request.data)
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        assert "OpenFlow" in payload["systemInstruction"]["parts"][0]["text"]
        prompt = payload["contents"][0]["parts"][0]["text"]
        assert "Minimize latency." in prompt
        assert "source=h1, destination=h4" in prompt
        return _FakeResponse(_response(intent))

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = provider.parse_intent(
            "Minimize latency.",
            source="h1",
            destination="h4",
        )

    assert result.objective == Objective.MINIMIZE_LATENCY
    assert result.source == "h1"
    assert result.destination == "h4"


def test_gemini_provider_rejects_malformed_or_invalid_model_output():
    provider = GeminiLLM(api_key="test-key")
    with patch(
        "urllib.request.urlopen",
        return_value=_FakeResponse(
            {"candidates": [{"content": {"parts": [{"text": '{"source": "h1"}'}]}}]}
        ),
    ):
        with pytest.raises(LLMParseError, match="valid intent"):
            provider.parse_intent("Give h1 to h4 the lowest-latency path.")


def test_gemini_provider_reports_http_status_without_exposing_key():
    key = "test-key-that-must-not-leak"
    provider = GeminiLLM(api_key=key)
    error_body = json.dumps(
        {"error": {"message": f"Service unavailable (token {key})"}}
    ).encode()
    error = urllib.error.HTTPError(
        "https://generativelanguage.googleapis.com/test",
        403,
        "Forbidden",
        hdrs=None,
        fp=io.BytesIO(error_body),
    )

    with patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(LLMParseError) as exc_info:
            provider.parse_intent("Give h1 to h4 the lowest-latency path.")

    assert "HTTP 403" in str(exc_info.value)
    assert "[redacted]" in str(exc_info.value)
    assert key not in str(exc_info.value)


def test_gemini_provider_includes_google_service_error_message():
    body = json.dumps(
        {"error": {"message": "The model is overloaded. Please try again later."}}
    ).encode()
    error = urllib.error.HTTPError(
        "https://generativelanguage.googleapis.com/test",
        503,
        "Service Unavailable",
        hdrs=None,
        fp=io.BytesIO(body),
    )

    with patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(LLMProviderUnavailableError) as exc_info:
            GeminiLLM(api_key="test-key").parse_intent(
                "Give h1 to h4 the lowest-latency path."
            )

    assert "HTTP 503" in str(exc_info.value)
    assert "model is overloaded" in str(exc_info.value)


def test_gemini_provider_timeout_is_configurable_and_reported(monkeypatch):
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "120")
    provider = GeminiLLM(api_key="test-key")

    with patch(
        "urllib.request.urlopen",
        side_effect=TimeoutError("read timed out"),
    ) as urlopen:
        with pytest.raises(LLMParseError, match="timed out after 120 seconds"):
            provider.parse_intent("Give h1 to h4 the lowest-latency path.")

    assert urlopen.call_args.kwargs["timeout"] == 120


@pytest.mark.parametrize("value", ["0", "-1", "invalid"])
def test_gemini_provider_rejects_invalid_timeout(monkeypatch, value):
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", value)

    with pytest.raises(LLMParseError, match="must be a positive number"):
        GeminiLLM(api_key="test-key")
