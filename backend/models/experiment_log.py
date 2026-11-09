"""Experiment log record (brief section 27/Step 14). One of these per run,
written as JSON under evaluation/results/."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class ExperimentLog(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_intent: str
    llm_provider: str
    structured_intent: dict[str, Any]
    candidates: list[dict[str, Any]]
    selected_path: list[str]
    selected_action: str
    validation_result: dict[str, Any]
    deployment_result: dict[str, Any]
    final_measurement: dict[str, Any]
    intent_satisfied: bool
    satisfaction_reason: str
    llm_call_count: int
    correction_iterations: int = 0
    error: Optional[str] = None
    # Populated only for MIN_BANDWIDTH runs (Phase 11) -- kept optional so
    # the existing MINIMIZE_LATENCY logging path (and every previously
    # written run_*.json) is completely unaffected.
    background_traffic: Optional[dict[str, Any]] = None
    target_mbps: Optional[float] = None
    measured_mbps: Optional[float] = None
    # Populated only when the Phase 12 closed correction loop actually ran
    # (i.e. the first real measurement fell short of target): one entry
    # per iteration, in order, each a real diagnose->reconfigure->
    # validate->deploy->measure step -- see backend/cli.py's
    # `_run_bandwidth`. Structured diagnostic info per Step 9, not a
    # simulated/estimated trace.
    correction_history: Optional[list[dict[str, Any]]] = None
