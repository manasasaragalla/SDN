import io
import json
import urllib.error

import pytest

from backend.llm.anthropic_provider import AnthropicLLM
from backend.llm.base import LLMParseError


def _http_error(body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.anthropic.com/v1/messages",
        401,
        "Unauthorized",
        {},
        io.BytesIO(body.encode("utf-8")),
    )


def test_anthropic_http_error_redacts_api_key_and_bounds_provider_detail(monkeypatch):
    api_key = "private-test-key"
    provider = AnthropicLLM(api_key=api_key)
    detail = "invalid " + api_key + " " + ("x" * 1500)
    body = json.dumps({"error": {"message": detail}})

    def fail_request(*_args, **_kwargs):
        raise _http_error(body)

    monkeypatch.setattr(
        "backend.llm.anthropic_provider.urllib.request.urlopen",
        fail_request,
    )

    with pytest.raises(LLMParseError) as error:
        provider.parse_intent("Find the lowest-latency path from h1 to h4.")

    message = str(error.value)
    assert api_key not in message
    assert "[redacted]" in message
    assert len(message) < 1100


def test_anthropic_http_error_does_not_return_unstructured_body(monkeypatch):
    provider = AnthropicLLM(api_key="private-test-key")

    def fail_request(*_args, **_kwargs):
        raise _http_error("unexpected response containing private-test-key")

    monkeypatch.setattr(
        "backend.llm.anthropic_provider.urllib.request.urlopen",
        fail_request,
    )

    with pytest.raises(LLMParseError) as error:
        provider.parse_intent("Find the lowest-latency path from h1 to h4.")

    assert "private-test-key" not in str(error.value)
    assert "unexpected response" not in str(error.value)
