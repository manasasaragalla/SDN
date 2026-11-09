"""Groq provider using its OpenAI-compatible chat completions API."""

from __future__ import annotations

import json
import os

from openai import OpenAI

from backend.llm.base import (
    LLMClarificationRequiredError,
    LLMParseError,
    LLMProvider,
    LLMProviderResponseError,
    LLMProviderUnavailableError,
)
from backend.llm.prompt import SYSTEM_PROMPT, build_user_prompt
from backend.llm.schema import LLMIntentOutput

DEFAULT_MODEL = "openai/gpt-oss-120b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqLLM(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        client: OpenAI | None = None,
    ):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.model = model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)

        if client is None and not self.api_key:
            raise LLMParseError(
                "GROQ_API_KEY is not set; configure it in the environment."
            )

        self.client = client or OpenAI(
            api_key=self.api_key,
            base_url=GROQ_BASE_URL,
        )

    @property
    def name(self) -> str:
        return f"groq:{self.model}"

    def parse_intent(
        self,
        natural_language: str,
        *,
        source: str | None = None,
        destination: str | None = None,
    ) -> StructuredIntent:
        if not natural_language or not natural_language.strip():
            raise LLMParseError("Natural-language intent cannot be empty")

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_user_prompt(
                            natural_language,
                            source=source,
                            destination=destination,
                        ),
                    },
                ],
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            if (
                status_code == 429
                or isinstance(status_code, int) and status_code >= 500
                or type(exc).__name__ in {
                    "APIConnectionError",
                    "APITimeoutError",
                }
            ):
                message = str(exc)
                if self.api_key:
                    message = message.replace(self.api_key, "[redacted]")
                message = " ".join(message.split())[:1000]
                raise LLMProviderUnavailableError(
                    f"Groq request failed"
                    + (f" (HTTP {status_code})" if status_code else "")
                    + (f": {message}" if message else "")
                ) from exc
            if isinstance(status_code, int):
                message = str(exc)
                if self.api_key:
                    message = message.replace(self.api_key, "[redacted]")
                message = " ".join(message.split())[:1000]
                raise LLMProviderResponseError(
                    f"Groq rejected the request (HTTP {status_code})"
                    + (f": {message}" if message else "")
                ) from exc
            raise LLMParseError(f"Groq intent request failed: {exc}") from exc

        try:
            response_text = completion.choices[0].message.content
            if not response_text:
                raise ValueError("provider returned an empty response")
            data = json.loads(response_text)
            parsed = LLMIntentOutput.model_validate(data)
            return parsed.to_structured_intent()
        except LLMClarificationRequiredError:
            raise
        except Exception as exc:
            raise LLMParseError(
                f"Groq output could not be parsed as a valid intent: {exc}"
            ) from exc
