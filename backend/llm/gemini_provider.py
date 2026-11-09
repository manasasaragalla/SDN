"""Google Gemini provider using the generateContent REST API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
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

DEFAULT_MODEL = "gemini-3.6-flash"
DEFAULT_TIMEOUT_SECONDS = 90.0
API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiLLM(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        try:
            self.timeout_seconds = float(
                os.environ.get(
                    "GEMINI_TIMEOUT_SECONDS",
                    str(DEFAULT_TIMEOUT_SECONDS),
                )
            )
        except ValueError as exc:
            raise LLMParseError(
                "GEMINI_TIMEOUT_SECONDS must be a positive number."
            ) from exc

        if self.timeout_seconds <= 0:
            raise LLMParseError(
                "GEMINI_TIMEOUT_SECONDS must be a positive number."
            )

        if not self.api_key:
            raise LLMParseError(
                "GEMINI_API_KEY is not set; configure it in the environment."
            )

    @property
    def name(self) -> str:
        return f"gemini:{self.model}"

    def parse_intent(
        self,
        natural_language: str,
        *,
        source: str | None = None,
        destination: str | None = None,
    ) -> StructuredIntent:
        if not natural_language or not natural_language.strip():
            raise LLMParseError("Natural-language intent cannot be empty")

        model = urllib.parse.quote(self.model, safe="")
        request = urllib.request.Request(
            f"{API_URL}/{model}:generateContent",
            data=json.dumps(
                {
                    "systemInstruction": {
                        "parts": [{"text": SYSTEM_PROMPT}],
                    },
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": build_user_prompt(
                                        natural_language,
                                        source=source,
                                        destination=destination,
                                    )
                                }
                            ],
                        }
                    ],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                    },
                }
            ).encode("utf-8"),
            headers={
                "x-goog-api-key": self.api_key,
                "content-type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", "replace")
            try:
                error_data = json.loads(error_body)
                detail = error_data.get("error", {}).get("message", "")
            except (json.JSONDecodeError, AttributeError):
                detail = error_body
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
                f"Gemini API returned HTTP {exc.code}{suffix}"
            ) from exc
        except TimeoutError as exc:
            raise LLMProviderUnavailableError(
                "Gemini request timed out after "
                f"{self.timeout_seconds:g} seconds. Check API/network "
                "availability or increase GEMINI_TIMEOUT_SECONDS."
            ) from exc
        except urllib.error.URLError as exc:
            raise LLMProviderUnavailableError(
                f"Gemini request could not reach the provider: {exc.reason}"
            ) from exc
        except Exception as exc:
            raise LLMParseError(
                f"Gemini request failed: {exc}"
            ) from exc

        try:
            response_text = body["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(response_text)
            parsed = LLMIntentOutput.model_validate(data)
            return parsed.to_structured_intent()
        except LLMClarificationRequiredError:
            raise
        except Exception as exc:
            raise LLMParseError(
                f"Gemini output could not be parsed as a valid intent: {exc}"
            ) from exc
