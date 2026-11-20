# IntentFlow: IEEE Research Dossier

## 1. Evidence Status and Scope

This dossier is based on source inspection, tests, experiment scripts, CSV/JSON
records, Markdown reports, and the existing audit material. It does not invent
or rerun live-network results. Implemented means visible in source; retained
result means a repository artifact exists; measured means ping or iperf3
collected a value; configured means a topology or TCLink value was supplied.

The implementation is frozen. No project implementation, test, dependency,
configuration, or experiment file was changed for this paper revision.

## 2. Implementation Summary

IntentFlow has four main boundaries:

1. **Interpretation:** mock and external provider adapters parse structured
   intent. The mock is deterministic regex/rule parsing.
2. **Planning:** canonical intent, topology, exact physical path, constraint,
   objective, and candidate-selection modules operate on typed models.
3. **Execution:** a restricted worker starts Ryu/Mininet, compiles OpenFlow,
   probes/deploys routes, measures traffic, checks readback, and persists evidence.
4. **Presentation:** Next.js and FastAPI expose topology, preview, execution,
   and evidence views.

## 3. Three Distinct Workflows

### 3.1 DESIGN deterministic planning

`plan_on_topology()` in `backend/planner/topology_planning.py` enumerates exact
paths and compares configured metric aggregates against constraints. It has no
live measurement or side effect. `tests/test_topology_catalog.py` covers
catalog and preview behavior.

Host attachment and link facts are optional. A complete end-to-end bandwidth,
delay, or loss aggregate requires complete valid values. Missing or invalid
required values produce UNKNOWN and cannot establish constraint satisfaction.

### 3.2 Generalized LIVE SDN execution

`run_generalized_constraint_demo()` in
`backend/orchestration/generalized_constraints.py`:

1. validates a topology snapshot and candidate/request identity;
2. enumerates exact physical paths with a default limit of 64;
3. assesses static feasibility;
4. preflights, compiles, deploys, and readbacks each candidate probe;
5. measures ping or iperf3;
6. cleans probe flows;
7. selects the candidate;
8. preflights and deploys the final path;
9. verifies final connectivity and persists evidence.

The privileged worker builds the fixed Mininet diamond and not arbitrary active
DESIGN graphs. `backend/api/worker.py` is the execution boundary.

### 3.3 Legacy CLI ONE_SHOT/CLOSED_LOOP

`backend/pipeline/bandwidth.py`, `backend/decision/bandwidth_decision.py`, and
`evaluation/run_evaluation.py` implement the legacy bandwidth experiment.
ONE_SHOT performs one post-deployment measurement. CLOSED_LOOP reduces the
known h2-h3 competing-flow QoS cap and remeasures up to three iterations.

This mechanism does not belong to the generalized live orchestrator. It is not
general congestion control and is not evidence of a generalized SDN feedback
system.

## 4. Architecture

The implementation-aligned request sequence is:

```text
frontend
  -> FastAPI preview or execution
  -> LLM/mock -> structured intent -> canonical intent
  -> active DESIGN topology or privileged-worker LIVE snapshot
  -> exact physical path enumeration
  -> constraint and objective evaluation
  -> physical OpenFlow compilation
  -> Ryu REST / OpenFlow / OVS
  -> ping or iperf3
  -> flow readback, connectivity check, JSON/Markdown evidence
```

FastAPI is intended to run unprivileged and bind locally. The worker accepts
only `health`, `topology`, and `execute` operations and starts/stops Ryu and
Mininet. Production systemd files exist but target-host installation was not
verified.

## 5. Mathematical Model

For exact path $p$, switch links $E(p)$, and attachments $a_s,a_d$, the
DESIGN configured values are:

\[
B(p)=\min(\{B_e:e\in E(p)\}\cup\{B_{a_s},B_{a_d}\})
\]
\[
D(p)=\sum_{e\in E(p)}D_e+D_{a_s}+D_{a_d}
\]
\[
L(p)=100\left(1-\prod_{e\in E(p)\cup\{a_s,a_d\}}(1-L_e/100)\right)
\]

When required values are missing or invalid, the result is UNKNOWN. Hard
constraints are conjunctive. Objective ranking and SHA-256 fingerprint
tie-breaking are deterministic.

The live graph omits host attachment delay/loss/capacity and some link delay/
loss fields even though the Mininet graph can provide capacity for TCLinks.
Therefore live generalized execution should use measured observations rather
than complete-path configured values.

## 6. Fixed Diamond Testbed

The live testbed has five switches:

- Path A: `h1-s1-s2-s4-h4`, 10-Mbps TCLink bottleneck.
- Path B: `h1-s1-s3-s5-s4-h4`, 50-Mbps TCLink bottleneck.
- Background: `h2-s2-s4-h3`, initially 8 Mbps.

The 10/50 Mbps values are configured. Measured systematic results near 5 and
47 Mbps are iperf3 receiver throughput. Manual latency values are measured ping
RTTs and not injected netem delays.

## 7. Generalized Live Evidence

Retained reports include live candidate and final measurements with probe
cookies, deployment/readback, cleanup, snapshots, and raw tool output in some
cases. Representative retained runs include:

| Scenario | Selected path | Candidate/final evidence |
|---|---|---|
MAX bandwidth | Path B | 9.470 Mbps Path A, 45.514 Mbps Path B; probe cleanup succeeded |
Band. >=20 + latency <=50 | Path B | 46.156 Mbps, 2.601-ms ping; final 1.945 ms |
MIN latency | Path B | 2.483-ms candidate; 2.294-ms final |
Bandwidth >=20 + MIN latency | Path B | 45.141 Mbps, 2.483-ms candidate; 2.294-ms final |

These are individual demonstrations. They do not establish repeated
performance or scalability.

The operator-reported generalized latency demo with 1.629-ms RTT lacks a
serialized result and run-specific candidate/deployment evidence. It remains
an incomplete demo, not a complete experiment.

## 8. Systematic Bandwidth Evidence

The four scenarios and retained counts are:

| Scenario | ONE_SHOT | CLOSED_LOOP | ONE infra. errors | CLOSED infra. errors |
|---|---:|---:|---:|---:|
| feasible | 3 | 2 | 1 | 0 |
| boundary | 2 | 4 | 2 | 2 |
| correctable | 2 | 8 | 4 | 2 |
| infeasible | 3 | 3 | 2 | 1 |

All 14 infrastructure records are 45-second timeouts. They are infrastructure
outcomes, not measured intent failures.

Per-scenario satisfaction differences:

| Scenario | ONE_SHOT | CLOSED_LOOP | Difference |
|---|---:|---:|---:|
| feasible | 100% | 100% | 0 pp |
| boundary | 100% | 100% | 0 pp |
| correctable | 100% | 100% | 0 pp |
| infeasible | 0% | 0% | 0 pp |

The pooled 70.0% versus 82.3529% result is an unequal-sample composition
effect. It must not be called closed-loop improvement or significance.

Manual runs include:

- 5.05 Mbps: one real correction success, final 5.1787 Mbps.
- 5.0 Mbps: three iterations, bounded failure, final 4.5528 Mbps.
- 49 Mbps: bounded failure, 47.1322 Mbps final/manual result.

These opposite manual outcomes demonstrate the implementation's success and
failure paths, not a statistical benefit.

## 9. Testing and Validation

The complete WSL backend suite was retained as 843 passed. A focused planner
suite passed 266 tests. Frontend Node test files cover preview status, API
error formatting, topology version controls, and seeded topology generation.
These tests validate source behavior and fixture compatibility. They are not
live performance measurements.

## 10. Reproducibility

Live commands require Linux, root privileges, Mininet, Open vSwitch, Ryu,
iperf3, ping, and ethtool. The repository provides setup scripts and
locked/hashed Python dependencies. Missing or incomplete items are:

- original systematic sweep source JSON files;
- complete raw ping/iperf3 inventory for every run;
- exact historical Linux/kernel/datapath and Ryu build metadata;
- live run random seeds and run-order randomization;
- repeated generalized packet-loss/combined-constraint data;
- alternate routing baselines;
- hardware or repeated randomized-topology evidence.

## 11. Supported and Unsupported Claims

Supported:

- typed intent and deterministic planning;
- exact physical route and fail-closed constraint evaluation;
- generalized live probe/readback/cleanup/evidence lifecycle;
- fixed-diamond live measurements;
- legacy ONE_SHOT/CLOSED_LOOP implementation and unequal retained data;
- no per-scenario systematic satisfaction improvement.

Unsupported:

- general closed-loop benefit;
- statistical significance;
- scalability;
- general SDN performance;
- hardware equivalence;
- formal network verification;
- LLM intent accuracy or safety performance;
- arbitrary live topology execution;
- independent baseline superiority;
- repeated packet-loss evaluation;
- correction convergence under general congestion.
