
"""Anthropic provider using the shared generalized intent schema."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from backend.llm.base import (
    LLMClarificationRequiredError,
    LLMParseError,
    LLMProvider,
    LLMProviderResponseError,
    LLMProviderUnavailableError,
)
from backend.llm.prompt import SYSTEM_PROMPT, build_user_prompt
from backend.llm.schema import LLMIntentOutput

DEFAULT_MODEL = "claude-sonnet-4-5"
API_URL = "https://api.anthropic.com/v1/messages"


class AnthropicLLM(LLMProvider):

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model or os.environ.get(
            "ANTHROPIC_MODEL",
            DEFAULT_MODEL,
        )

        if not self.api_key:
            raise LLMParseError(
                "ANTHROPIC_API_KEY is not set; "
                "cannot use the Anthropic provider."
            )

    @property
    def name(self) -> str:
        return f"anthropic:{self.model}"

    def parse_intent(
        self,
        natural_language: str,
        *,
        source: str | None = None,
        destination: str | None = None,
    ) -> StructuredIntent:

        if not natural_language or not natural_language.strip():
            raise LLMParseError("Natural-language intent cannot be empty")

        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": build_user_prompt(
                        natural_language,
                        source=source,
                        destination=destination,
                    ),
                }
            ],
        }

        request = urllib.request.Request(
            API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))

        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", "replace")
            try:
                error_data = json.loads(error_body)
                detail = error_data.get("error", {}).get("message", "")
            except (json.JSONDecodeError, AttributeError):
                detail = ""
            if self.api_key:
                detail = detail.replace(self.api_key, "[redacted]")
            detail = " ".join(detail.split())[:1000]
            suffix = f": {detail}" if detail else ""
            error_type = (
                LLMProviderUnavailableError
                if exc.code == 429 or exc.code >= 500
                else LLMProviderResponseError
            )
            raise error_type(
                f"Anthropic API returned HTTP {exc.code}{suffix}"
            ) from exc

        except Exception as exc:
            raise LLMParseError(
                f"Anthropic request failed: {exc}"
            ) from exc

        try:
            response_text = body["content"][0]["text"]
            data = json.loads(response_text)

        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMParseError(
                f"Could not parse Anthropic response as JSON: {exc}"
            ) from exc

        if "error" in data:
            raise LLMParseError(
                f"Model reported: {data['error']}"
            )

        try:
            parsed = LLMIntentOutput.model_validate(data)

            return parsed.to_structured_intent()

        except LLMClarificationRequiredError:
            raise
        except Exception as exc:
            raise LLMParseError(
                f"Anthropic output failed schema validation: {exc}"
            ) from exc
