"""Result models for the research-evaluation phase (Phase 13): comparing
ONE_SHOT configuration against CLOSED_LOOP correction for the
MIN_BANDWIDTH objective, across repeated real runs.

These are deliberately separate from ExperimentLog (backend/models/
experiment_log.py): ExperimentLog is one full record per CLI demo
invocation, including the entire raw iperf3 JSON for every candidate
(useful for a single run, too large/verbose to aggregate across dozens of
evaluation runs). BandwidthPipelineResult/EvaluationRun instead carry just
the compact, comparable fields the evaluation needs, produced by the same
real pipeline (backend/pipeline/bandwidth.py) that backend/cli.py uses --
no separate/duplicated measurement logic, only a smaller result shape.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

Mode = Literal["ONE_SHOT", "CLOSED_LOOP"]


class BandwidthPipelineResult(BaseModel):
    """What actually happened running one MIN_BANDWIDTH intent through the
    shared pipeline (backend/pipeline/bandwidth.run_bandwidth_pipeline),
    in either mode. Every *_mbps and *_satisfied field here comes from a
    real iperf3 measurement or a real validation/deployment call -- never
    estimated or assumed."""

    mode: Mode
    target_mbps: float
    selected_path: list[str]

    # The first real measurement taken on the selected path, before any
    # correction is attempted (in ONE_SHOT mode, this is also the final
    # measurement -- the pipeline stops here by definition).
    initial_throughput_mbps: Optional[float] = None
    initial_satisfied: bool

    # Only ever non-zero/non-empty in CLOSED_LOOP mode when the initial
    # measurement fell short; ONE_SHOT never attempts a correction.
    correction_iterations: int = 0
    correction_history: list[dict] = Field(default_factory=list)
    background_rate_changes_mbps: list[float] = Field(default_factory=list)

    final_throughput_mbps: Optional[float] = None
    final_satisfied: bool
    final_validation_valid: bool
    final_deployment_success: bool

    execution_time_s: float
    failure_reason: Optional[str] = None


class EvaluationRun(BaseModel):
    """One row of the evaluation dataset: a labelled scenario/target,
    which mode was used, which repetition this is, and the real pipeline
    result it produced.

    `pipeline` is None, and `error` set, only when this run never
    produced a real measurement at all -- an infrastructure-level failure
    (e.g. the Ryu REST API became unreachable) distinct from a genuine
    NOT_SATISFIED measurement outcome, which always has a populated
    `pipeline` with real numbers. Never conflate the two: an infra error
    is excluded from satisfaction-rate statistics (backend/evaluation/
    aggregate.py), not silently counted as a measured failure."""

    scenario: str
    scenario_description: str
    repetition: int
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    pipeline: Optional[BandwidthPipelineResult] = None
    error: Optional[str] = None
