"""Flow rule model. Deliberately shaped to match ryu.app.ofctl_rest's JSON
body exactly (dpid, priority, match, actions) -- see
docs/adr-002-topology-source-and-deployment.md for why: the compiler's
output should be the literal deployable configuration, not one more
abstraction layer removed from it."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

MAX_COOKIE = (1 << 64) - 1


class FlowRule(BaseModel):
    dpid: int
    priority: int = Field(default=100, ge=1, le=65535)
    match: dict[str, Any]
    actions: list[dict[str, Any]]
    cookie: int | None = Field(default=None, ge=0, le=MAX_COOKIE)
    # A label for what this rule is for (e.g. "h1->h4 forward, hop s1"),
    # not sent to Ryu -- purely for logging/debugging.
    label: str = ""

    @field_validator("cookie", mode="before")
    @classmethod
    def reject_boolean_cookie(cls, value):
        if isinstance(value, bool):
            raise ValueError("cookie must be an integer, not a boolean")
        return value

    def to_ofctl_payload(self) -> dict[str, Any]:
        payload = {
            "dpid": self.dpid,
            "priority": self.priority,
            "match": self.match,
            "actions": self.actions,
        }
        if self.cookie is not None:
            payload["cookie"] = self.cookie
        return payload
