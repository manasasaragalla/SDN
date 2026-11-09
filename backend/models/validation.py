"""Validation result model. A validator returns one of these -- never
raises for an ordinary "this configuration is invalid" outcome, since
that's an expected, common result this project needs to log and act on
(brief section 15/22), not an exceptional program error."""
from __future__ import annotations

from pydantic import BaseModel


class ValidationResult(BaseModel):
    valid: bool
    reasons: list[str] = []

    @classmethod
    def ok(cls) -> "ValidationResult":
        return cls(valid=True, reasons=[])

    @classmethod
    def fail(cls, *reasons: str) -> "ValidationResult":
        return cls(valid=False, reasons=list(reasons))
