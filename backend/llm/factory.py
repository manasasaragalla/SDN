"""Select an LLM provider.

Supported providers:
- mock: Offline testing and deterministic experiments.
- openai: OpenAI API.
- anthropic: Anthropic API.
- gemini: Google Gemini API.
- groq: Groq API using its OpenAI-compatible endpoint.

Environment variables are loaded from the project-root .env file when
present. Existing process environment variables take precedence.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from backend.llm.base import LLMProvider


PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Load .env from the project root.
# Existing environment variables are never overwritten.
load_dotenv(PROJECT_ROOT / ".env", override=False)

SUPPORTED_PROVIDERS = ("mock", "openai", "anthropic", "gemini", "groq")


def get_llm_provider(
    provider_name: str | None = None,
) -> LLMProvider:
    """Return the configured LLM provider.

    An explicit provider_name takes precedence over LLM_PROVIDER.
    Defaults to mock so tests and offline runs need no API key.
    """

    name = (
        provider_name
        or os.environ.get("LLM_PROVIDER")
        or "mock"
    ).strip().lower()

    if name not in SUPPORTED_PROVIDERS:
        supported = ", ".join(SUPPORTED_PROVIDERS)
        raise ValueError(
            f"Unknown LLM_PROVIDER: {name!r}. "
            f"Supported providers: {supported}"
        )

    if name == "mock":
        from backend.llm.mock import MockLLM
        return MockLLM()

    if name == "openai":
        from backend.llm.openai_provider import OpenAILLM
        return OpenAILLM()

    if name == "anthropic":
        from backend.llm.anthropic_provider import AnthropicLLM
        return AnthropicLLM()

    if name == "gemini":
        from backend.llm.gemini_provider import GeminiLLM
        return GeminiLLM()

    if name == "groq":
        from backend.llm.groq_provider import GroqLLM
        return GroqLLM()

    raise RuntimeError(f"Provider selection failed: {name!r}")