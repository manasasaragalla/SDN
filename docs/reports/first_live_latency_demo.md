# First Live Generalized Latency Demo — Execution Evidence

## Execution summary

The operator reported that the live Mininet diamond demo completed with:

- **Status:** `SUCCEEDED`
- **Selected path:** `h1 → s1 → s2 → s4 → h4`
- **Final average RTT:** `1.629 ms`

This report is a read-only audit; the demo was not rerun and no controller
requests, deployments, or flow changes were made. The workspace does not
contain a serialized result for this execution. The successful terminal
summary is the only run-specific evidence provided. The `GeneralizedLatencyResult`
contains richer evidence in memory, but the previously supplied invocation
printed only status, selected path, final RTT, and error.

The result cannot be independently reproduced or fully audited from the
retained artifacts. In particular, candidate observations, deployment
cookies/readbacks, cleanup results, snapshots, and raw final ping output were
not persisted.

## Candidate discovery

The configured diamond topology contains these two `h1`-to-`h4` physical
routes. The ports below are **inferred from the topology construction order**
in `testbed/topology/diamond.py`; they were not captured in the successful
run's retained evidence. Host-side interface port numbers are not represented
by the topology model.

| Candidate | Physical route and switch-side ports | Candidate ID |
|---|---|---|
| A | `h1 — s1:1`; `s1:2 ↔ s2:2`; `s2:3 ↔ s4:3`; `s4:1 — h4` | Not retained |
| B | `h1 — s1:1`; `s1:3 ↔ s3:1`; `s3:2 ↔ s5:1`; `s5:2 ↔ s4:4`; `s4:1 — h4` | Not retained |

These are the two routes implied by the configured topology, not a saved
enumeration response from this execution. The implementation derives candidate
IDs from request and exact-path fingerprints; the fingerprints and IDs for
this run were not logged.

## Temporary measurements and probe deployments

| Candidate | Measured RTT | Packets sent / received; loss | Run and observation identity | Deployment/readback | Cleanup |
|---|---|---|---|---|---|
| A | Not retained | Not retained | Not retained | Cookie, affected DPIDs, accepted/verified rule counts not retained | Outcome and remaining-flow count not retained |
| B | Not retained | Not retained | Not retained | Cookie, affected DPIDs, accepted/verified rule counts not retained | Outcome and remaining-flow count not retained |

The orchestration source requests 10 pings by default when called with the
shown invocation, validates measured RTT and packet evidence, and cleans each
temporary deployment in a `finally` block using the deployment's operation
cookie and recorded DPIDs. These are **implementation properties**, not proof
that either probe completed or was cleaned successfully in this run.

Accordingly, this report cannot confirm that no temporary probe flows remain.
No live flow-table query was made for this audit.

## Candidate selection

- **Objective:** `MINIMIZE latency` (source-level plan configuration).
- **Reported winner:** Candidate A, `h1 → s1 → s2 → s4 → h4`.
- **Per-candidate objective values and eligibility:** Not retained.
- **Selection explanation:** The selector requires valid, fresh objective
  evidence for all eligible enumerated candidates, then minimizes latency.
  Equal objective values are resolved deterministically by path fingerprint.
  The reported `SUCCEEDED` result is consistent with the orchestration
  reaching selection and deployment, but the actual candidate values,
  eligibility records, and tie-break inputs are unavailable.

## Final preflight

The orchestration only proceeds to final deployment after final preflight
passes. Thus, if the reported `SUCCEEDED` status came from the implementation
under inspection, that control flow implies a passed final preflight.
However, the run's fresh snapshot, topology fingerprint comparison,
connected-DPID roster, port states, and `PreflightResult` were not retained.
The successful status alone does not provide their specific values.

## Final deployment and connectivity

The reported final route is Candidate A. Source inspection shows that the
physical-path compiler generates IPv4 and ARP rules in both directions, with
exact ingress and egress ports. For this three-switch route, the compiler
would generate 12 rules (four per switch). This is an **expected compiler
output inferred from source**, not a retained installation/readback record.

| Evidence | Run-specific record |
|---|---|
| Final operation cookie / ownership | Not retained |
| Affected DPIDs | Not retained |
| IPv4 and ARP flow matches/actions | Not retained |
| Requested, accepted, and readback-verified rule counts | Not retained |
| Exact flow-table readback | Not retained |
| Raw final ping output and packet counts/loss | Not retained |
| Final RTT | `1.629 ms`, as reported by the operator |
| Connectivity verification | `SUCCEEDED`, as reported by the operator |

The implementation defines deployment success as exact readback of all
requested rules and only returns overall `SUCCEEDED` after a valid final
latency measurement. Those conditions are source-level guarantees on the
success path; the individual readback and ping evidence was not persisted and
therefore cannot be independently checked here.

## Evidence sources and limitations

- Operator-provided terminal summary: status, selected path, and final RTT
  stated above.
- Source inspection: orchestration, preflight, selector, compiler, deployment
  result models, topology builder, and topology definition. Source behavior is
  identified as inferred wherever it is not direct run output.
- [`run_1793710625.json`](../../evaluation/results/run_1793710625.json) and
  [`run_1793788742.json`](../../evaluation/results/run_1793788742.json) are
  earlier legacy-pipeline records from November 3 and 4, respectively. Their
  RTTs and selected routes differ from the reported run; they are not used as
  evidence for this execution.
- No matching serialized result, execution log, or saved live snapshot was
  found in the workspace.

## Assessment

**Sufficient as a brief project demo, but not sufficiently evidenced as a
reproducible or independently auditable experiment.** The reported success,
selected physical path, and final RTT support a concise live-demo claim. For a
stronger demonstration or research record, persist the complete
`GeneralizedLatencyResult` (including candidate measurements and identities,
probe deployment/readback and cleanup results, preflight snapshots/fingerprints,
final deployment verification, and raw final ping output) as a run artifact.
