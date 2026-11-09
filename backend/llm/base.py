"""Provider-agnostic LLM interface. The only thing any provider is allowed
to produce is a validated StructuredIntent (backend/models/intent.py) --
never OpenFlow, shell commands, or free-form configuration (brief section
11/23). A provider that returns something outside the schema raises
LLMParseError, which the caller can retry (bounded) or surface as a
"NL wasn't understood" result -- it never gets a second chance to try
something unconstrained.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.intent import StructuredIntent


class LLMParseError(Exception):
    """Raised when a provider cannot produce a StructuredIntent that
    passes schema validation for the given natural-language input."""


class LLMProviderUnavailableError(LLMParseError):
    """Raised when a configured provider cannot be reached or is unavailable."""


class LLMProviderResponseError(LLMParseError):
    """Raised when a provider rejects the configured request or model."""


class LLMClarificationRequiredError(LLMParseError):
    """Raised when a request lacks enough information for safe interpretation."""


class LLMProvider(ABC):
    @abstractmethod
    def parse_intent(
        self,
        natural_language: str,
        *,
        source: str | None = None,
        destination: str | None = None,
    ) -> StructuredIntent:
        """Translate one natural-language network objective into a
        StructuredIntent. Raises LLMParseError if it cannot."""
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for logging (brief section 27's experiment
        log records which provider/model produced each intent)."""
        raise NotImplementedError
