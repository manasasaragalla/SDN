"""Decision layer result models."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from backend.models.intent import Action
from backend.models.measurement import LatencyResult, ThroughputResult


class CandidateMeasurement(BaseModel):
    """One candidate path and what was actually measured on it -- not a
    theoretical hop-count estimate (brief section 13/19: "use actual
    measurements rather than only theoretical path length")."""

    path: list[str]
    latency: LatencyResult


class DecisionError(Exception):
    """Raised when no candidate path could be selected (e.g. every
    candidate was unreachable)."""


class LatencyDecisionResult(BaseModel):
    objective: str = "MINIMIZE_LATENCY"
    candidates: list[CandidateMeasurement]
    selected_path: list[str]
    action: Action = Action.REROUTE

    @property
    def selected_measurement(self) -> Optional[CandidateMeasurement]:
        for c in self.candidates:
            if c.path == self.selected_path:
                return c
        return None


class CandidateThroughputMeasurement(BaseModel):
    """One candidate path and what was actually measured on it with
    iperf3 -- the bandwidth-objective analogue of CandidateMeasurement.
    Also carries the path's static capacity (from real TCLink bw=
    values), purely for reporting/logging -- selection and satisfaction
    are always decided from `throughput`, the real measurement, never
    from `static_capacity_mbps` alone."""

    path: list[str]
    throughput: ThroughputResult
    static_capacity_mbps: Optional[float] = None


class BandwidthDecisionResult(BaseModel):
    objective: str = "MIN_BANDWIDTH"
    target_mbps: float
    candidates: list[CandidateThroughputMeasurement]
    selected_path: list[str]
    action: Action = Action.REROUTE

    @property
    def selected_measurement(self) -> Optional[CandidateThroughputMeasurement]:
        for c in self.candidates:
            if c.path == self.selected_path:
                return c
        return None
