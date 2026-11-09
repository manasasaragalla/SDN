"""Feedback-object interface and bounded correction formulas for the
MIN_BANDWIDTH objective.

Originally (Phase 11) this only *defined* the feedback shape and a
correction formula without wiring either into an autonomous loop. Phase 12
adds the actual closed loop (backend/cli.py's `_run_bandwidth`): repeatedly
diagnose -> reconfigure -> validate -> deploy -> re-measure, bounded by
MAX_CORRECTION_ITERATIONS, using only the deterministic functions in this
module -- no LLM call is ever made to decide a numeric adjustment.

Two correction formulas live here, because there are two different
"allocations" a deterministic correction can act on for this objective:

- `next_allocation_mbps`: how much a flow's OWN reserved/requested rate
  should grow when it is under-served relative to its target. Kept as
  originally defined/tested in Phase 11.
- `next_background_rate_mbps`: this project's actual correction lever for
  MIN_BANDWIDTH (see backend/cli.py docstring on `_run_bandwidth` for why):
  since the primary flow is never itself rate-limited (a MIN_BANDWIDTH
  intent is a floor, not a cap -- rate-limiting it would work directly
  against the objective), the thing a real closed loop can deterministically
  correct is how much of the shared link the *competing* background flow is
  allowed to use. When the primary flow measures under target, throttling
  the background flow down (bounded, capped per step, floored above zero)
  frees real capacity for the primary flow -- and the next real iperf3
  measurement either confirms that helped or it didn't.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class BandwidthFeedback(BaseModel):
    """Matches the JSON shape specified in the brief exactly:
    {"objective", "target_mbps", "measured_mbps", "current_path",
    "candidate_paths", "network_state", "status"}."""

    objective: str = "MIN_BANDWIDTH"
    target_mbps: float
    measured_mbps: Optional[float]
    current_path: list[str]
    candidate_paths: list[list[str]]
    network_state: dict
    status: str  # "SATISFIED" | "NOT_SATISFIED"


# Correction is capped per iteration and bounded in total iterations, so a
# future closed loop built on this can never (a) request an unbounded
# jump in one step, chasing noise, or (b) retry forever without deciding
# the intent simply can't be met on the current topology.
MAX_ALLOCATION_STEP_RATIO = 2.0  # a single correction step never more than doubles the allocation
MAX_CORRECTION_ITERATIONS = 3
MIN_BACKGROUND_RATE_MBPS = 1.0  # floor: never throttle competing traffic to zero/negative


def next_allocation_mbps(old_allocation_mbps: float, target_mbps: float, measured_mbps: float) -> float:
    """The bounded, deterministic correction formula from the brief:
    new_allocation = old_allocation * (target / measured), capped so one
    step never more than doubles the previous allocation (protects against
    a near-zero measured_mbps producing an absurd jump) and never reduces
    it below the previous allocation when measured_mbps is already at or
    above target (nothing to correct for).

    This is a pure numeric function -- no LLM call, no network I/O -- by
    design (brief: "simple, deterministic, bounded... not repeatedly
    invoke the LLM for small numeric adjustments")."""
    if old_allocation_mbps <= 0:
        raise ValueError("old_allocation_mbps must be positive")
    if measured_mbps <= 0:
        # Nothing got through at all; the formula's ratio would be
        # infinite/undefined, so fall back to the capped max step rather
        # than dividing by zero.
        return old_allocation_mbps * MAX_ALLOCATION_STEP_RATIO

    if measured_mbps >= target_mbps:
        return old_allocation_mbps

    raw_ratio = target_mbps / measured_mbps
    capped_ratio = min(raw_ratio, MAX_ALLOCATION_STEP_RATIO)
    return old_allocation_mbps * capped_ratio


def next_background_rate_mbps(
    old_background_rate_mbps: float,
    target_mbps: float,
    measured_mbps: float,
    floor_mbps: float = MIN_BACKGROUND_RATE_MBPS,
) -> float:
    """This project's actual MIN_BANDWIDTH correction lever (see this
    module's docstring): throttles the competing background flow DOWN,
    in proportion to how far short of target the primary flow measured,
    to free real capacity for it.

    Uses the same shortfall ratio as next_allocation_mbps (target/measured,
    capped at MAX_ALLOCATION_STEP_RATIO so one step never more than halves
    the background rate) but divides instead of multiplies -- correcting
    the flow that needs to shrink, not grow -- and never goes below
    `floor_mbps` (a background flow throttled to ~0 stops being a
    meaningful competing-traffic scenario at all, and dividing by an
    ever-larger ratio as measured approaches 0 would otherwise not
    converge to anything bounded).

    Returns old_background_rate_mbps unchanged if the primary already
    meets target (nothing to correct) or if measured_mbps is invalid."""
    if old_background_rate_mbps <= 0:
        raise ValueError("old_background_rate_mbps must be positive")
    if measured_mbps is None or measured_mbps >= target_mbps:
        return old_background_rate_mbps
    if measured_mbps <= 0:
        # Primary got nothing at all -- the strongest correction step
        # this formula allows, not an undefined/infinite one.
        return max(old_background_rate_mbps / MAX_ALLOCATION_STEP_RATIO, floor_mbps)

    raw_ratio = target_mbps / measured_mbps
    capped_ratio = min(raw_ratio, MAX_ALLOCATION_STEP_RATIO)
    return max(old_background_rate_mbps / capped_ratio, floor_mbps)
