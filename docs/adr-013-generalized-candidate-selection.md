# ADR-013: Deterministic generalized candidate selection

## Status

Accepted for the Phase 3D implementation.

## Context

Phase 3B enumerates physical paths, including exact switch-link identities and
endpoint ports. Phase 3C evaluates hard constraints against normalized,
candidate-bound observations. Neither phase selects a path. A selector must
not collapse parallel physical links to node-only routes, infer runtime
satisfaction from topology, or turn a planning result into deployment.

## Decision

Add pure deterministic selection in
`backend/planner/candidate_selection.py`. Phase 3B `EnumeratedPath` is the
only accepted physical candidate representation. Each candidate ID is a
`physical-` digest of the originating planning-request fingerprint
and complete serialized physical-path fingerprint. The digest includes
ordered nodes, connection types, traversal orientation, endpoint ports, and
physical switch-link identities. It does not depend on enumeration position.
Parallel links with the same node sequence therefore have separate IDs.

Every enumerated path is checked against the exact request topology before
selection. Topology validation rejects duplicate/ambiguous switch-link
identities and claimed ports. Path validation checks source and destination
host attachments, switch sequence, oriented link endpoints, ports, and
physical identities. Invalid or mismatched paths raise
`SelectionInputError`; an absent or ambiguous physical realization is never
repaired by guessing.

The selector also reruns the pure Phase 3B enumerator against the originating
plan's topology and endpoints with the supplied candidate limit. It compares
the ordered `EnumeratedPath` models—including every connection and parallel
link identity—and the recomputed truncation flag. A caller-supplied
`truncated=false` or enumeration fingerprint is not evidence of completeness:
an omitted, extra, reordered, altered, or incorrectly flagged path set is
rejected. Correct K-limited truncated enumerations remain valid subsets.

`assess_path_feasibility` is a small pure topology assessment, not a generic
feasibility framework:

- A structurally valid exact physical path is `CANDIDATE` unless known
  topology capacity proves a requested bandwidth lower bound impossible.
- Exact per-path bandwidth capacity is derived using
  `physical_path_capacity_mbps`. GT, GTE, BETWEEN, and EQ lower boundaries are
  interpreted according to their comparison semantics; EQ tolerance lowers
  the minimum potentially satisfying value.
- A known per-hop capacity can prove a path infeasible even when another hop
  has missing capacity, because the known hop is an upper bound on the
  complete path. Otherwise incomplete capacity metadata produces `UNKNOWN`.
- `CANDIDATE` means only that supplied topology facts do not disprove
  feasibility. It does not mean that traffic can achieve the target or that a
  hard constraint is satisfied. Measurement evidence is never used to assign
  topology feasibility.

Phase 3C remains callable without an evaluation-run ID. When a caller supplies
one, every `MetricObservation` must carry the same non-empty ID, and
`PlanEvaluation` retains it and the plan fingerprint. Phase 3D requires both
identities and one timezone-aware timestamp shared with the Phase 3C result.
`PlanEvaluation` stores a deterministic fingerprint of the complete
`FreshnessPolicy` used during evaluation. Phase 3D requires the caller's policy
to have the identical fingerprint; a missing or different policy identity is
rejected. It also requires the exact Phase 3C `evaluated_at` timestamp and does
not claim to re-evaluate freshness because Phase 3C results do not retain raw
constraint observations.
The caller is responsible for making the opaque evaluation-run ID unique in
the evidence persistence scope; a UUID is suitable but not generated here.

The selector reuses the Phase 3C per-requirement aggregation and only allows
`CANDIDATE` paths whose every hard constraint is `SATISFIED` to rank.
`VIOLATED` retains Phase 3C's precedence over another unresolved requirement
for that candidate. An unresolved hard-constraint result that might affect
selection yields `INSUFFICIENT_EVIDENCE`.

The result-state order is:

1. Reject invalid or incomplete physical enumeration, path, identity, run,
   freshness-policy fingerprint, or mapped evidence.
2. With no constraints and no objective, return `NO_SELECTION_CRITERIA`.
3. Assess exact physical-path feasibility.
4. Return `NO_ELIGIBLE_CANDIDATE` if every enumerated candidate is
   `PROVEN_INFEASIBLE`; any `UNKNOWN` candidate blocks definitive selection.
5. Apply all hard constraints conjunctively.
6. Return `NO_SATISFYING_CANDIDATE` only when every eligible candidate
   conclusively violates at least one hard constraint. Truncation makes
   absence of a satisfying path inconclusive.
7. Return `INSUFFICIENT_EVIDENCE` when unresolved evidence could change the
   outcome.
8. For an objective, require the explicit
   `generalized_objective_ranking` capability before evaluating objective
   evidence. It is unsupported for every production metric initially.

Objective observations are separate from Phase 3C hard-constraint
observations. Each is bound to the exact candidate, request, plan, path,
objective observation and requirement IDs, and evaluation run. Duplicate or
unexpected records are rejected. Missing, invalid, stale, future-dated, or
non-finite objective values do not produce a selection. Where objective
ranking is explicitly enabled, ties are broken by the physical-path
fingerprint.

When hard constraints exist without an objective, eligible satisfying paths
are tie-broken by physical-path fingerprint and labeled
`NEUTRAL_DETERMINISTIC`; this is not optimization. With an optimization
objective and truncated enumeration, the result is always
`INSUFFICIENT_EVIDENCE`. With hard constraints only, selection from a
truncated enumerated subset is allowed only when a satisfying candidate is
present and the result reports `search_truncated=true` and
`selection_scope=ENUMERATED_SUBSET`. No-criteria results also preserve the
truncation flag and never select a path.

## Phase boundary

Selection is a pure planning result. It does not imply execution, deployment,
or runtime satisfaction. No production generalized objective metric is
enabled. There is no live network query, measurement collection, feedback,
configuration compilation, CLI integration, or change to legacy selectors.

`CandidateSelectionResult` retains the originating plan, topology-validated
enumeration, Phase 3C evaluation, freshness policy, and objective observations
as provenance. Its hard-constraint and objective criterion properties derive
from the plan, not caller-provided booleans. Result validation checks that
candidate rows exactly cover the validated enumeration, candidate paths and
IDs agree, Phase 3C identities and requirement results agree with the plan,
and any selected candidate is the deterministic eligible winner. A selected
hard-constraint candidate must have every required constraint satisfied by
its corresponding reported value. Objective selection requires an explicit
supported ranking capability and matching, valid, fresh objective
observations for all eligible candidates; a numeric score alone is not
evidence. These invariants protect ordinary construction and validated
serialization round trips, not deliberate low-level bypasses of Pydantic's
model validation.

## Consequences and limitations

The selector can reject paths disproved by known physical capacities but
cannot establish achieved throughput, latency, or other runtime metrics.
Missing relevant capacity metadata remains unknown unless a different known
hop already proves a bandwidth lower bound impossible. Objective ranking is
intentionally unusable for current production capabilities. A complete
enumeration is established by rerunning Phase 3B over the exact supplied
topology and endpoint pair, but remains limited by the enumerator's
implementation and the accuracy of topology metadata; selection never claims
deployment or operational optimality.
