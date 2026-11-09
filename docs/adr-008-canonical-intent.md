# ADR-008: Canonical intent representation and legacy normalization boundary

## Context

`backend/models/intent.py` is consumed directly by the current LLM providers,
CLI, and legacy decision/planning code. Replacing that model or redirecting
those callers during the first generalization phase would risk changing the
working latency and bandwidth pipelines. The legacy schema also mixes
thresholds and optimization in one metric record, while execution support
remains objective-specific.

## Decision

Add `backend/models/canonical_intent.py` as a versioned, declarative model,
and `backend/models/intent_normalization.py` as a pure adapter from
`StructuredIntent`. The legacy model, provider interface, CLI, decision
modules, and validators remain unchanged.

The canonical intent separates:

- `scope`: source, destination, and optional protocol/port selector.
- `constraints`: zero or more metric comparisons (`GT`, `GTE`, `LT`, `LTE`,
  `EQ`, or inclusive `BETWEEN`).
- `optimization`: one independent metric and direction.
- `requested_actions`: declarative action names and scalar parameters.
- `legacy_metadata`: legacy loss-tolerance category, without assigning it a
  numeric packet-loss meaning.

Metric and unit identifiers are strings to allow new identifiers without
changing enums. Known metric units are sourced from
`backend/models/metric_definitions.py`; unknown metric and action names remain
declarative requests. Neither the model nor the normalizer marks any metric or
action executable or resolves capabilities.

The schema rejects malformed comparison shapes, non-finite numbers,
reversed ranges, invalid known-metric units, and contradictory bound
intersections expressed in the same metric and unit. It does not convert
units or infer feasibility from topology.

## Legacy compatibility

`MINIMIZE_LATENCY` normalizes to a latency `MINIMIZE` optimization and gets
the `MINIMIZE_LATENCY` legacy execution hint. `MIN_BANDWIDTH` with its
existing bandwidth target normalizes to `bandwidth GTE target Mbps` and gets
the `MIN_BANDWIDTH` hint. These hints identify the existing pipeline only;
they are not a generalized execution strategy.

Legacy loss tolerance is copied as metadata, never converted to a
packet-loss percentage. Mixed legacy objectives and generalized metric
constraints, incompatible legacy targets, and already-resolved legacy
actions are rejected instead of silently discarded. Existing `StructuredIntent`
objects are not mutated.

## Consequences

The canonical schema and normalizer are additive and independently tested.
LLM providers continue returning `StructuredIntent`, and the CLI continues
dispatching directly on its existing objective fields. Generalized intents
are not newly executable by this decision and still require separately
approved capability assessment, planning, and execution work.
