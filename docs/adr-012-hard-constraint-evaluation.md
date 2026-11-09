# ADR-012: Pure hard-constraint evaluation

## Context

Phase 3A defines planner requests and unevaluated plans. Phase 3B enumerates
structurally valid physical paths, retaining parallel-link identity. Existing
measurement models are metric-specific parser outputs and do not provide a
common candidate-bound observation contract. Capability resolution separately
reports validation, measurability, plannability, and executability.

## Decision

Add a pure evaluator under `backend/planner/constraint_evaluation.py`. It
consumes a `Plan`, explicitly identified physical candidates, normalized
observations, an explicit timezone-aware `evaluated_at`, and an explicit
per-metric maximum-age policy. It does not collect measurements, use the
system clock, choose paths, rank candidates, or modify the Phase 3A plan.

Each evaluation candidate supplies a unique `candidate_id`, the fingerprint
of its originating `PlanningRequest`, a complete `EnumeratedPath`, and
topology feasibility. The evaluator verifies request binding, host endpoints,
and physical connections against the request topology. `PROVEN_INFEASIBLE`
candidates are excluded; `CANDIDATE` and `UNKNOWN` candidates are eligible.

Each observation is associated with a target containing candidate ID,
request fingerprint, full physical path fingerprint, and exact requirement
ID. The physical fingerprint hashes the complete serialized `EnumeratedPath`,
including node order, connection kind, physical link identity, endpoint
ports, and traversal orientation. Parallel links sharing node sequences
therefore remain distinct. Unmatched observation targets are rejected;
multiple observations for one target yield `UNKNOWN`.

Observations carry a metric, unit, value, collection status, timestamp, and
source. They must already be normalized; raw ping and iperf3 parser models
are not accepted. The evaluator checks identity, metric, exact unit, status,
timestamp freshness, finiteness, and the registered metric domain before
comparison. It never converts units. Future and stale observations are
`UNKNOWN`; age exactly at the configured maximum is fresh. A metric without
an explicit freshness limit is an invalid evaluation configuration.

Only requirements whose capability resolution has both `validated` and
`measurable` marked `SUPPORTED` are compared. Plannability and executability
do not gate evaluating supplied evidence. In particular, packet loss is
measurable even though generalized planning and enforcement remain
unsupported. EQ with an explicit nonnegative absolute tolerance is now
validated for evaluation; tolerance on other operators remains unsupported.

Comparisons use ordinary numeric semantics: GT/GTE/LT/LTE have their usual
strict/inclusive boundaries, BETWEEN is inclusive, and EQ is exact unless
an explicit tolerance is supplied, in which case
`abs(measured - target) <= tolerance`. No floating-point epsilon is added.

All hard constraints aggregate conjunctively. Any violated requirement
makes a candidate violated; otherwise any unknown or unsupported requirement
makes it unknown; all satisfied makes it satisfied. No constraints yields
`NOT_EVALUATED`. At plan evaluation level, any eligible satisfied candidate
makes the result satisfied. The result is violated only when every eligible
candidate is violated; mixed/unknown outcomes yield unknown. No eligible
candidates yields `NOT_EVALUATED`. These outcomes describe supplied
candidate evidence only; `Plan.satisfaction_status` remains `NOT_VERIFIED`.
Optimization is not evaluated.

## Measurement normalization boundary

This phase adds no measurement adapters and does not change legacy pipelines.
A future producer must normalize parser outputs conservatively:

- A ping result with zero packets transmitted is a failed measurement, not a
  valid 100% packet-loss observation. Packet loss requires a positive
  transmitted count; latency requires received packets and a present, finite
  RTT statistic.
- An iperf3 result must indicate successful execution and contain a present,
  finite throughput value. Preserve the existing `achieved_mbps` rule:
  prefer receiver throughput and fall back to sender throughput.
- Missing values, failed execution, and non-finite values must be represented
  as failed/invalid observations or omitted, never as valid measurements.

The evaluator checks normalized observation status and numeric validity but
cannot prove that a supplied source label is truthful or that the measured
path was deployed.

## Phase boundary

No ping/iperf execution, live statistics, Mininet, Ryu, OpenFlow, deployment,
QoS changes, CLI integration, path ranking, optimization, or Phase 3D work is
included. The Phase 3A `Plan` contract and legacy pipelines remain unchanged.

## Consequences and limitations

Candidate evidence is explicitly bound to a planning request, physical path,
and requirement. The caller must provide freshness policy values; no default
threshold is chosen. A matching fingerprint binds data to a declared path,
but does not prove deployment or continuing runtime behavior. Capability
support for evaluation does not imply planning, enforcement, or runtime
satisfaction.

Planner models are application data contracts and must be created with normal
validated constructors or `model_validate`/`model_validate_json`. Instance
validation revalidates planner-model instances. The ordinary
`model_construct()` API is explicitly blocked, and
`model_copy(update=...)` is blocked because updates would bypass validation.
Pydantic's `model_construct()` is intentionally a no-validation API; directly
invoking its unbound `BaseModel` implementation (for example,
`BaseModel.model_construct.__func__(PlanEvaluation, ...)`) is an unsupported
low-level bypass, not a validated construction path. Such an invocation can
create invalid in-process objects by design. The project does not claim
protection against malicious Python code executing arbitrary methods inside
the process.
