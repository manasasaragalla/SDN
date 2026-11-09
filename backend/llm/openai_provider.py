
"""OpenAI provider using Pydantic Structured Outputs."""

from __future__ import annotations

import os

from openai import OpenAI

from backend.llm.base import (
    LLMParseError,
    LLMProvider,
    LLMProviderResponseError,
    LLMProviderUnavailableError,
)
from backend.llm.prompt import SYSTEM_PROMPT, build_user_prompt
from backend.llm.schema import LLMIntentOutput

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAILLM(LLMProvider):

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        client: OpenAI | None = None,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model or os.environ.get(
            "OPENAI_MODEL",
            DEFAULT_MODEL,
        )

        if client is None and not self.api_key:
            raise LLMParseError(
                "OPENAI_API_KEY is not set. "
                "Configure it in the environment."
            )

        self.client = client or OpenAI(api_key=self.api_key)

    @property
    def name(self) -> str:
        return f"openai:{self.model}"

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
            completion = self.client.chat.completions.parse(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": build_user_prompt(
                            natural_language,
                            source=source,
                            destination=destination,
                        ),
                    },
                ],
                response_format=LLMIntentOutput,
            )

            message = completion.choices[0].message

            if message.refusal:
                raise LLMParseError(
                    f"OpenAI refused the request: {message.refusal}"
                )

            parsed = message.parsed

            if parsed is None:
                raise LLMParseError(
                    "OpenAI did not return a structured intent"
                )

            return parsed.to_structured_intent()

        except LLMParseError:
            raise

        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code == 429 or isinstance(status_code, int) and status_code >= 500:
                raise LLMProviderUnavailableError(
                    f"OpenAI request failed (HTTP {status_code})."
                ) from exc
            if isinstance(status_code, int):
                raise LLMProviderResponseError(
                    f"OpenAI rejected the request (HTTP {status_code}): {exc}"
                ) from exc
            raise LLMParseError(
                f"OpenAI intent extraction failed: {exc}"
            ) from exc
