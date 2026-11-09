"""Deterministic fingerprints for immutable, validated model inputs."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def model_fingerprint(value: BaseModel | None) -> str:
    payload: Any = value.model_dump(mode="json") if value is not None else None
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
