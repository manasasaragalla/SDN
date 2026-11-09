# ADR-010: Generalized planner contract

## Context

Canonical intent and capability resolution now describe requested requirements
and known implementation limits. The legacy latency and bandwidth pipelines
remain operational but are metric-specific and must not be duplicated as a
second generalized execution pipeline. Generalized constraint evaluation,
objective optimization, and path enumeration have not been approved in this
phase.

## Decision

Add a small typed contract under `backend/planner/`:

- `PlanningRequest` accepts the existing `CanonicalIntent`, `TopologyGraph`,
  and `CapabilityResolution` models. Capability results carry deterministic
  fingerprints of the canonical intent and topology they resolved; the
  request rejects results for different inputs. Requests and plans snapshot
  their inputs at construction. Mutable model-valued fields and `__dict__`
  access return detached copies; immutable planner values are returned
  directly to avoid repeatedly copying topology-sized state. Serialization
  returns detached data. `model_copy(update=...)` is rejected because Pydantic
  does not validate update values. `model_construct()` is also rejected for
  planner models; callers must use validated construction or `model_validate()`.
- `Plan` preserves capability readiness separately from planning readiness,
  execution dispatch, deployment, and satisfaction verification.
- Every `Plan` retains its originating `PlanningRequest`. Its hard constraints
  must exactly match the request's constraints, in order, with no omission,
  addition, or mutation; its optimization must also match the request. The
  plan owns an isolated snapshot of that request.
- Each hard constraint receives an identifier and an independent required
  observation. The aggregation is explicitly conjunctive (`ALL`).
- Every candidate path records its topology feasibility, explanations, known
  facts, unknown facts, and a separate evaluation entry for every hard
  constraint.
- Candidate feasibility is topology-only. `CANDIDATE` means not proven
  impossible; it does not mean constraints were evaluated or satisfied.
- In this contract, every candidate record has an explanatory rationale.
  `CANDIDATE` rationales explain inclusion, and `UNKNOWN` or
  `PROVEN_INFEASIBLE` rationales explain the unresolved or excluded status.
  Contract fixtures may state that their candidate is a fixture; this does not
  assert topology evidence.
- Candidate constraint results are restricted to `NOT_EVALUATED`. The plan
  remains `NOT_VERIFIED` for satisfaction; measurement or constraint
  evaluation is required before either can report satisfaction.
- The optimization objective and its required observation are represented
  independently. Optimization is `NOT_APPLIED` in this contract and cannot
  establish constraint satisfaction.

Unknown facts have their own model and explanatory reason. A `READY` plan
requires capability readiness, at least one `CANDIDATE`, and no
unknown-feasibility candidate. Readiness does not assert that hard constraints
have been measured or satisfied.

## Phase boundary

This phase defines data contracts only. It does not enumerate paths, assess
topology facts, evaluate constraints, rank objectives, compile flows, measure
network behavior, or execute changes. The legacy intent normalizer and
latency/bandwidth pipelines remain unchanged. No generalized metric is
considered executable merely because its identifier exists.

## Consequences

The planner can be implemented incrementally against explicit result types
without changing legacy dispatch. Future planning and execution work must
populate each constraint independently, preserve `ALL` semantics, leave
unknown topology facts unresolved, and rank objectives only after every hard
constraint has been verified as satisfied.

These guards cover the supported Pydantic APIs; they are not a defense against
deliberate Python-level tampering or low-level construction that bypasses the
model API.
