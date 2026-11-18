# IntentFlow Comprehensive Research-Readiness Audit

**Audit date:** 2026-11-18

**Scope:** repository inspection, mathematical verification, test execution, and existing evaluation artifacts only. This audit does not claim any new experiment, deployment, or live-network result.

## Executive assessment

IntentFlow has a substantial research implementation and a well-separated deterministic planning core. It is close to being research-paper ready for a **design/planner and controlled live-testbed** contribution, but is not yet ready for an IEEE submission in which broad or statistically strong claims are required.

The strongest evidence is:

- deterministic topology enumeration and ranking source;
- 42 backend test modules;
- 9 passing frontend Node tests;
- 27 valid rows in the retained systematic live-bandwidth sweep, plus 14 retained infrastructure-error rows;
- 11 retained manual CLI demonstration rows;
- live diamond-topology bandwidth and latency experiment code and artifacts.

The main gaps are missing source-result artifacts for the first live generalized-latency demo, incomplete and unequal systematic samples, 34% retained infrastructure-error rate, no reproducible randomized-topology experiment data, no independent baseline comparisons, and an environment mismatch that prevented some local tests.

## A. Architecture

### Components and responsible files

| Component | Responsible files | Evidence |
|---|---|---|
| Frontend UI | `frontend/src/app/page.tsx`, `frontend/src/components/intents/intent-page.tsx`, topology/planning/executions/metrics/settings components | Next.js App Router; natural-language or structured-intent submission; active-topology and execution polling |
| Frontend API boundary | `frontend/src/lib/api-client.ts`, `frontend/src/lib/intent-preview-status.mjs` | Configures FastAPI URL and derives presentation statuses |
| Seeded topology editor | `frontend/src/lib/topology-generator.ts`, `frontend/src/components/topology/topology-page.tsx`, `frontend/tests/topology-generator.test.mjs` | Deterministic STAR, RING, TREE, MESH, and RANDOM DESIGN graphs |
| FastAPI backend | `backend/api/main.py`, `backend/api/schemas.py`, `backend/api/auth.py` | Preview, topology catalog, execution, evidence, health, and WebSocket routes |
| LLM integration | `backend/llm/factory.py`, `backend/llm/base.py`, provider modules | Mock and configured OpenAI/Anthropic/Gemini/Groq parsing |
| Intent normalization | `backend/models/intent.py`, `backend/models/intent_normalization.py`, `backend/models/canonical_intent.py` | Legacy/generalized StructuredIntent to CanonicalIntent |
| Topology model | `backend/models/network.py`, `backend/models/topology_definition.py` | Hosts, links, ports, DPIDs, attachment and link attributes |
| DESIGN catalog | `backend/api/services/topology_catalog.py` | SQLite versioned topology storage and activation |
| Pure path planner | `backend/planner/path_enumeration.py`, `topology_planning.py`, `constraint_evaluation.py`, `candidate_selection.py` | DFS enumeration, metric aggregation, constraint evaluation, ranking |
| Capability resolution | `backend/capabilities.py` | Declares supported/unsupported/conditional intent capabilities |
| Live graph acquisition | `backend/decision/topology_graph.py` | Builds TopologyGraph from a live Mininet object |
| Mininet testbed | `testbed/topology/diamond.py` | Fixed diamond testbed and host/background configuration |
| Compilation/deployment | `backend/compiler/`, `backend/deployment/`, `backend/api/services/worker_client.py`, `backend/api/worker.py` | Physical-path compilation and privileged/restricted worker operations |
| Measurement | `backend/measurement/latency.py`, `throughput.py` | Ping RTT and iperf3 throughput |
| Orchestration/evidence | `backend/orchestration/`, `backend/models/evaluation.py`, `backend/models/experiment_log.py` | Generalized probes, final execution, JSON/Markdown evidence |

### Request-to-planning workflow

1. The frontend collects source, destination, and a natural-language or structured intent.
2. `POST /api/v1/intents/preview` receives the request.
3. If natural language is supplied, `get_llm_provider()` selects `mock`, OpenAI, Anthropic, Gemini, or Groq. The mock provider is deterministic regex parsing, not an LLM model call.
4. The provider's `StructuredIntent` or a supplied `CanonicalIntent` is validated and normalized through `normalize_intent()`.
5. The API verifies parsed endpoints against the selected topology hosts.
6. It loads the active DESIGN topology, or asks the privileged worker for a complete LIVE snapshot.
7. `resolve_capabilities()` determines whether recognition, measurement, planning, and execution are ready.
8. `plan_on_topology()` uses bounded DFS enumeration.
9. For each exact path, configured bandwidth, delay, and loss are aggregated.
10. Hard constraints are evaluated.
11. Eligible candidates are ranked by the requested objective.
12. The API returns interpretation, planning, topology identity, and execution eligibility status separately.
13. DESIGN planning is never executable.
14. Live execution uses preview eligibility, a worker allowlist, physical-path compilation, Ryu REST flow operations, exact readback, measurement, cleanup, and persisted evidence.

## B. Mathematical formulation verification

### Bottleneck bandwidth

The implementation's deterministic path calculation is conceptually:

\[
B(p)=\min_{(u,v)\in p} B(u,v)
\]

For exact switch paths, `physical_path_capacity_mbps()` verifies each switch-link identity, rejects missing or ambiguous links, and takes the minimum of valid capacities. This operation is implemented and source-verified.

The richer `_path_facts()` implementation in `topology_planning.py` additionally adds host attachment capacities to `link_capacities`, and takes `min(...)` only when every switch link has a value. This has the following discrepancies:

- If one or more switch links have missing capacity, the result is `None`, correctly unknown.
- If switch-link capacities are complete but a host attachment capacity is missing, the switch-link bottleneck is still returned and does not include the host attachment as unknown.
- If a host attachment capacity is known, it is included as a bottleneck even though the switch link test is unrelated.
- If a host attachment capacity is negative or invalid, topology validation should normally reject it for DESIGN graphs.

Conclusion: the core exact-switch-link bottleneck is correct. `_path_facts()` is not fully conservative for missing host-attachment capacity.

### Path delay

The intended aggregation is:

\[
D(p)=\sum_{e\in p} d_e
\]

Both switch-link delays and endpoint host attachment delays are intended to be included. `_path_facts()` sums switch-link delay values and known host attachment delays. A missing host attachment delay is silently omitted rather than making the aggregate unknown. It also makes a missing switch-link delay unknown through `all(value is not None)`.

Conclusion: delay is correct for complete switch-link and attachment data; missing attachment delay is incorrectly omitted instead of yielding `UNKNOWN`.

### Packet-loss aggregation

The implementation calculates independent-link survival:

\[
L(p)=100\left(1-\prod_e(1-l_e/100)\right)
\]

It uses Python `math.prod` across link and known host-attachment loss values. This is mathematically correct when every included edge and attachment has a value. Missing host-attachment loss is silently omitted instead of making the aggregate unknown, while missing switch-link loss makes the aggregate unknown.

### Hard-constraint operators

| Operator | Implementation |
|---|---|
| GT | `observed > threshold` |
| GTE | `observed >= threshold` |
| LT | `observed < threshold` |
| LTE | `observed <= threshold` |
| EQ | `abs(observed - threshold) <= tolerance`, default tolerance 0 |
| BETWEEN | `lower_bound <= observed <= upper_bound` |

These operators are inclusive where stated and exclusive for GT/LT. Canonical models enforce shape, unit, and finite values.

### Objective ranking and tie-breaking

For one objective:

- maximize: sort by `-observed`, then candidate fingerprint;
- minimize: sort by `observed`, then candidate fingerprint;
- missing objective facts prevent ranking;
- tie counts and fingerprint tie-breaking are explained in the result;
- hard constraints are evaluated before ranking;
- unknown/missing facts prevent eligibility;
- `candidate_limit` truncation sets status `INCOMPLETE_SEARCH` and removes the selected candidate.

Candidate fingerprint tie-breaking is deterministic. No random objective tie-break exists.

### Mathematical discrepancies requiring paper treatment

1. `_path_facts()` does not treat missing host attachment capacity/delay/loss as unknown. This should be corrected or explicitly excluded from proposed equations until fixed.
2. `CandidateLimit=128` is a bounded search, not global enumeration. The implementation makes no global-optimality claim after truncation.
3. The legacy measured bandwidth/latency pipelines use real observations and differ from the pure configured DESIGN planner. They must not be described as the same equation without distinguishing source of evidence.
4. Packet-loss measurement in the existing orchestration uses 10-packet resolution, so a 1% threshold needs sufficiently larger samples or exact loss semantics; the implementation itself does not turn a 10-packet zero-loss result into an exact 1% observation.

## C. Experimental evaluation

### Existing scripts

| Script | Purpose | Root/network dependency |
|---|---|---|
| `evaluation/run_evaluation.py` | Repeated ONE_SHOT vs CLOSED_LOOP bandwidth sweep | Root; Mininet; OVS; Ryu; iperf3 |
| `evaluation/run_generalized_constraints.py` | One generalized bandwidth/latency/combined scenario | Root; Mininet; OVS; Ryu |
| `evaluation/build_final_report.py` | Aggregate existing JSON/CSV, build plots | No live/network work |
| `evaluation/summarize.py` | Combine and aggregate systematic sweep JSON | No live/network work |

Manual scripts `manual_phase3c*.py` exist in the repository root, but they appear as focused phase validation scripts rather than complete paper experiments; they were not used as primary evidence in this audit.

### Fixed topology and seeds

- The live testbed is the fixed diamond in `testbed/topology/diamond.py`.
- Path A: `h1-s1-s2-s4-h4`, links 10 Mbps.
- Path B: `h1-s1-s3-s5-s4-h4`, 50 Mbps on three links.
- Background traffic: `h2-s2-s4-h3`, initial 8 Mbps.
- No experiment seed is recorded for the live iperf3/ping sweeps.
- The frontend random topology generator uses seeded deterministic JavaScript PRNGs. One test seed is `repeatable-seed`; no paper experiment seed is recorded.
- Random topology generation, when explicitly seeded, reproduces graph structure and attributes. Blank seeds generate nondeterministic random values and are not reproducible without retaining the returned seed.

### Three previously demonstrated experiment classes

1. **ONE_SHOT/CLOSED_LOOP bandwidth sweep:** can be rerun only on a suitable Linux/Mininet/Ryu host using `evaluation/run_evaluation.py`; source files and live environment are needed. Existing 27 valid rows and 14 infrastructure-error rows are retained. Missing raw source sweep JSON means the final CSV can be reproduced as an aggregation output, but the original run inventory should be preserved first.
2. **Manual bandwidth/latency CLI demonstrations:** live scripts and eleven manual JSON rows support capability demonstrations. The source run JSON exists, but hand selection, nonuniform repetitions, and no statistical design prevent using these as a main repeated study.
3. **Generalized live latency/constraints:** source scripts and several generalized result JSON/Markdown artifacts exist. The one specifically documented "first live generalized latency demo" is only operator-supplied terminal evidence: no complete serialized run, snapshot, candidate observations, readback, or cleanup record exists.

The three previously demonstrated experiments are therefore **not uniformly reproducible**:

- systematic bandwidth: rerunnable, with caveat of 14 infrastructure errors;
- manual CLI demonstrations: source rerunnable but samples are hand-selected and should not be claimed as controlled repetitions;
- first live generalized-latency demo: not independently reproducible from retained artifacts.

### Suitable baselines

- ONE_SHOT is the existing direct baseline.
- Shortest-hop routing is a suitable baseline but is not implemented as a paper baseline experiment.
- Highest-bandwidth-path selection is a legacy policy concept and could be reproduced as a baseline.
- Random path selection is suitable and easy to control with a seed.
- Round-robin routing is suitable for fairness but needs implementation.
- Static configured-capacity ranking is suitable for comparing design planning against live measured outcomes.
- Min-hop/lowest-delay and lowest-loss baselines require explicit implementations or experiment harness controls.

No claim should state that these baselines are already experimentally evaluated.

### Missing experiments

- larger repeated sweep with no/low infrastructure failures and predeclared repetitions;
- independent per-scenario seeds and confidence intervals;
- randomized topologies across many seeds;
- comparison against shortest-hop, widest-bandwidth, lowest-configured-delay, random, and round-robin baselines;
- packet-loss repeated experiments;
- combined latency/bandwidth/loss constraints;
- scalability versus switch count and candidate limit;
- candidate enumeration truncation scenarios;
- objective ranking and tie-breaking tests with multiple metrics;
- host-attachment missing-metric tests;
- correction-convergence experiment on a boundary where correction is actually exercised;
- same-environment hardware/kernel datapath sensitivity;
- rerun of the first generalized-latency demo with complete evidence.

## D. Testing

### Existing test suites

The repository has 42 backend `test_*.py` modules and 2 frontend `.test.mjs` modules.

Covered areas include:

- canonical intent and normalization;
- mock and external provider parsing;
- topology graph and catalog;
- path enumeration and candidate selection;
- constraint evaluation and objective ranking;
- planner contract;
- bandwidth and latency decisions;
- compilation, deployment, retry, preflight, reroute, and evidence;
- frontend seeded topology generation;
- frontend preview status presentation.

### Actual commands and outcomes

| Command | Outcome |
|---|---|
| `git --no-pager status --short` | Worktree status was checked; no implementation changes were made by this audit. |
| `python -m pytest -q` | Failed during collection: `C:\msys64\ucrt64\bin\python.exe` has no `pytest` module. |
| `pytest -q` | Full collection attempted with Anaconda pytest; failed/blocked because `backend/api/worker.py` imports Unix-only `fcntl` on Windows. |
| `pytest -q <core/backend test list>` | 339 passed, 18 errors. All 18 setup errors were in `tests/test_topology_catalog.py` and showed `starlette.testclient.TestClient`/installed `httpx` incompatibility (`Client.__init__() got an unexpected keyword argument 'app'`), not assertion failures. |
| `cd frontend && npm test` | 9/9 frontend tests passed. |
| `cd frontend && npm run build` | Failed because `next` was not resolved by npm's direct script lookup in this environment. |
| `cd frontend && node node_modules/next/dist/bin/next build` | Next build reached compilation but failed: missing Windows native `lightningcss.win32-x64-msvc.node`. |

No live Mininet, Ryu, OVS, iperf3, ping, or network execution was run during this audit.

## E. Research paper readiness

### IEEE structure

1. Title
2. Abstract
3. Introduction and motivation
4. Related work
5. System architecture
6. Intent interpretation and canonical model
7. Topology and path model
8. Mathematical formulation
9. Proposed deterministic planner and closed-loop algorithm
10. Baselines
11. Experimental setup
12. Results
13. Discussion and threats to validity
14. Limitations
15. Conclusion and future work
16. References
17. Optional reproducibility appendix

### Supported claims

- a deterministic, typed intent-to-plan architecture is implemented;
- mock parsing is offline and deterministic;
- DESIGN topology values are design facts, not measured telemetry;
- exact physical paths and candidate fingerprints are represented;
- hard constraints are conjunctive;
- objective ranking and deterministic fingerprint tie-breaking exist;
- live candidate and closed-loop bandwidth code exists;
- the retained systematic sweep contains real iperf3 values and infrastructure-error records;
- ONE_SHOT and CLOSED_LOOP are compared in the retained aggregate;
- 14 of 41 sweep attempts were infrastructure errors and were excluded from aggregate statistics;
- the one manual success and one manual failure demonstrate real correction behavior in opposite directions;
- random topology generation is deterministic for a supplied seed.

### Unsupported claims

- no claim of live Mininet deployment from source alone;
- no claim of Ryu connectivity or OpenFlow installation beyond retained execution evidence;
- no claim that the 27-row sweep is statistically sufficient;
- no claim that closed-loop correction has a general improvement advantage;
- no claim that the correction algorithm converges at scale;
- no claim that packet loss, latency, or combined constraints were systematically benchmarked unless new runs persist complete evidence;
- no claim that the first live latency demo is fully reproducible;
- no claim that random topologies were used in the live experiments;
- no claim that configured delay or loss is measured RTT or live packet loss;
- no claim of general SDN performance;
- no claim of dedicated-hardware or kernel-datapath equivalence;
- no claim of LLM-driven planning because the planner is deterministic and providers only parse requests.

### Generateable figures and tables

Actual data can generate:

- satisfaction rate by scenario and mode;
- final throughput vs. target;
- correction-iteration distribution;
- infrastructure-error count by scenario;
- manual/automated run separation table;
- scenario, target, path, and measured throughput table;
- candidate enumeration and ranking table from additional deterministic runs;
- test-pass summary table.

The existing retained plots are for the bandwidth sweep and should be labeled as 27 completed measured runs plus 14 excluded infrastructure errors.

### Research topics for IEEE references

- intent-based networking;
- declarative SDN control;
- OpenFlow flow management;
- network function composition and path selection;
- constrained shortest path and multi-constraint routing;
- QoS-aware routing;
- bottleneck bandwidth and end-to-end delay/loss models;
- closed-loop networking and verification;
- digital twins and network simulation;
- LLM limitations and hallucination in network control;
- safe constrained LLM integration;
- software data planes and Mininet/OVS experimental methodology;
- reproducible network experimentation;
- candidate enumeration complexity and bounded search.

No verified bibliography is included here. References must be checked against IEEE-indexed/peer-reviewed sources before paper writing.

## F. Reproducibility inventory

See `reproducibility_inventory.md` for dependencies and commands.

*** Add File: E:\SdnProject\research_submission\experiment_inventory.md
# IntentFlow Experiment Inventory

## Experiment classes

| ID | Experiment | Implementation | Retained evidence | Reproduction status |
|---|---|---|---|---|
| E1 | ONE_SHOT vs CLOSED_LOOP bandwidth | `evaluation/run_evaluation.py`, `backend/pipeline/bandwidth.py` | 27 valid systematic rows; 14 infra-error rows; plots; comparison JSON | Reproducible on Linux/Mininet/OVS/Ryu host, not in the current Windows audit environment |
| E2 | Manual bandwidth and latency CLI demos | `backend/cli.py` | 11 JSON rows in `evaluation/results/final/manual_demo_runs.csv` | Source runnable; not a controlled repeated study |
| E3 | Generalized constraint/latency scenarios | `evaluation/run_generalized_constraints.py`, `backend/orchestration/` | Several JSON and Markdown report files | Scenario source exists; live rerun needs Linux privileges and Ryu/Mininet |
| E4 | First live generalized latency demo | operator invocation plus terminal summary | Terminal summary and nonmatching legacy records; no complete run artifact | Not independently reproducible or auditable |
| E5 | Random topology DESIGN generation | `frontend/src/lib/topology-generator.ts` | 9 passing frontend tests; no experiment result data | Graph reproducible with supplied seed |

## E1: systematic bandwidth study

### Scenarios

| Scenario | Target | Purpose |
|---|---|---|
| feasible | 20 Mbps | comfortable Path B case |
| boundary | 5.15 Mbps | near contended Path A measurement ceiling |
| correctable | 5.05 Mbps | reachable boundary target |
| infeasible | 49 Mbps | above retained Path B throughput |

Modes: `ONE_SHOT`, `CLOSED_LOOP`.

Default planned repetitions: 3 per scenario/mode.

### Actual retained counts

From `evaluation/results/final/comparison_tables.json`:

- ONE_SHOT: 10 completed measured runs
- CLOSED_LOOP: 17 completed measured runs
- infrastructure errors: 14
- total retained systematic attempts: 41

Counts are unequal because infrastructure failures were excluded after retry/timeouts.

### Reproduction command

```bash
sudo mn -c
sudo PYTHONPATH=. python3 evaluation/run_evaluation.py --repetitions 3
PYTHONPATH=. python3 evaluation/summarize.py
PYTHONPATH=. python3 evaluation/build_final_report.py
```

The original run JSON files used to form the final CSV are not currently present in `evaluation/results/`; preserve them on a rerun before aggregation.

## E2: manual demonstrations

Retained records include:

- `run_1790408133.json`: 5.05 Mbps target, Path A first shortfall, one real correction success;
- `run_1790408000.json`: 5.0 Mbps target, first shortfall, three real correction iterations and bounded failure;
- 49 Mbps infeasible run;
- several 20/6/5.15/4.9 Mbps demonstrations;
- two latency demonstrations.

These rows are hand-run and hand-selected. They can demonstrate implementation behavior, but are not sufficient for statistical comparison.

## E3: generalized constraints

Supported scenario choices in `evaluation/run_generalized_constraints.py`:

- bandwidth
- latency
- combined
- minimize-latency
- maximize-bandwidth
- constrained-minimize-latency

Each scenario starts Ryu and Mininet and performs a live orchestration. No repetition flags or randomized trial design are implemented.

## E4: first generalized-latency report

The report `docs/reports/first_live_latency_demo.md` confirms that this run is evidence-poor:

- no JSON execution result;
- no snapshot/fingerprint;
- no per-candidate packet or RTT records;
- no cookie/readback/cleanup record;
- no raw ping output;
- only the terminal status, selected path, and 1.629-ms final RTT.

Treat it as a manual demo only.

## Topology configurations

### Live diamond

Five switches and four hosts, plus background hosts h2/h3. Path A and Path B share h1/h4 endpoints and are disjoint at the switch level.

Design distinction:

- 10/50 Mbps TCLink values are configured link properties;
- 5.0/47.0 Mbps iperf3 values are measured outcomes;
- 0.879/0.949 ms manual latency values are measured or reported observations, not configured design values;
- no packet-loss topology measurements are retained from a repeated study.

### Random DESIGN topologies

Generated ranges are user-configurable for:

- switch count 2-32;
- host count 1-128;
- bandwidth 0.01-100000 Mbps;
- delay 0-10000 ms;
- packet loss 0-100%;
- extra links 0 to remaining complete graph edges.

Patterns: STAR, RING, TREE, MESH, RANDOM.

The PRNG is seeded through FNV-1a-style seed hashing and mulberry32-like state mixing. Supplied-string seeds are repeatable. No network seed is used in the live Mininet topology.

## Missing experimental data

1. complete raw systematic sweep source JSON;
2. repeated latency and packet-loss observations;
3. corrected and repeated boundary experiments;
4. random seeded topology benchmark results;
5. baseline-policy comparison runs;
6. per-candidate observations and run IDs for generalized latency;
7. candidate enumeration/truncation benchmark;
8. confidence intervals and statistical test records.

