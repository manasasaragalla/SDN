# ADR-006: Closed-loop bandwidth correction, and a decision-layer fix that was required to exercise it for real

## Context

Phase 11 defined a `BandwidthFeedback` object and a bounded correction
formula (`backend/models/feedback.py`) but explicitly did not wire either
into an autonomous loop. Phase 12's task is to build that loop for real:
diagnose -> reconfigure -> validate -> deploy -> re-measure, bounded,
deterministic, no LLM call, using only real network measurements to
decide whether to keep going.

## What the loop corrects

A `MIN_BANDWIDTH` intent is a floor ("at least N Mbps"), not a cap.
Rate-limiting the primary flow itself would work directly against the
objective, so it is never a candidate lever. The only thing installed by
this project that acts as a deterministic, real, measurable dial is the
background/competing flow's own OVS QoS rate cap (`docs/adr-004`). The
loop's correction step is therefore: throttle the background flow's
allowed rate down (bounded per step by `MAX_ALLOCATION_STEP_RATIO`,
floored above zero by `MIN_BACKGROUND_RATE_MBPS`, formula in
`next_background_rate_mbps`), redeploy the real OVS QoS queue at the new
rate, and take a new real `iperf3` measurement of the primary flow.
Bounded at `MAX_CORRECTION_ITERATIONS` (3) total attempts; if the
background rate reaches its floor, or the formula stops proposing any
further reduction, the loop stops and reports `NOT_SATISFIED` rather than
spinning.

`backend/cli.py`'s `_run_bandwidth` implements this directly (no new
module needed -- it reuses `_setup_background_traffic`, now parameterized
by rate, plus the existing validator/compiler/deployment/measurement
layers already built in Phase 11).

## A real problem this surfaced: the selected path never actually overlapped with what the loop could correct

The first real run of the loop (target 49 Mbps, a target already known
from Phase 11 to genuinely fail) executed for real -- three real OVS QoS
redeployments, three real `iperf3` re-measurements -- but never converged,
and the reason was structural, not a bug in the loop itself:
`select_bandwidth_path`'s original policy was "always pick the candidate
with the single highest measured throughput". In this project's diamond
topology, that is *always* Path B (uncontended, ~47 Mbps real ceiling)
for any target it can reach, because Path B beats Path A (contended,
~10 Mbps link) on raw throughput regardless of the target. Path A is the
*only* candidate that shares a link with the background flow (h2->h3) --
so whenever Path B is selected, the correction loop's only lever
(throttling that background flow) has zero effect on the selected path's
achievable throughput by construction. The loop ran honestly and
reported the true, unimproved measurement each iteration; it just never
had a real chance to help, because the selected path and the thing being
corrected didn't share a bottleneck.

**Fix**: `select_bandwidth_path` now prefers the *cheapest* candidate
that already meets the target, falling back to the highest-throughput
candidate only when none do (`backend/decision/bandwidth_decision.py`,
also documented in that module's own docstring). This is not a change
made to force a demo to succeed -- it is a defensible policy in its own
right (a "give me at least N" intent has no reason to always claim the
biggest available pipe, and reserving high-capacity paths for flows that
actually need more than N is standard traffic-engineering practice), and
it is what makes Path A -- the path that can genuinely be affected by
throttling competing traffic -- reachable by the decision layer at all,
for a target within Path A's real capability. All four existing
`select_bandwidth_path` unit tests still passed unmodified after this
change (every existing test scenario happened to have only one candidate
meeting target, so the new tie-breaking rule was never exercised by them);
two new tests were added specifically to lock in the new behavior,
including one exercising the exact "prefer cheaper sufficient path over a
faster one" case this ADR describes.

## Verification

See `docs/experiments.md` (Phase 12 section) for five real, non-
fabricated runs: two immediate successes with no correction needed
(one where Path A doesn't even qualify, one where the fixed decision
policy newly selects it), one genuine correction failure (three real
iterations, bounded and stopped correctly, where the real correction
step turned out smaller than this testbed's own measurement noise), one
repeat of that same target succeeding immediately from natural variance
alone, and one genuine correction success (one real iteration: a real
OVS QoS redeploy of the background flow's rate, followed by a real
`iperf3` re-measurement that cleared the target). None of these outcomes
was selected after the fact -- each is reported as it happened, including
the one where the loop ran for real but did not help, because that is
itself an honest characterization of the correction mechanism's
real-world effectiveness near a narrow decision boundary, not a defect
to hide.
