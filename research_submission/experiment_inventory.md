# IntentFlow Experiment Inventory

## Experiment classes

| ID | Experiment | Implementation | Retained evidence | Reproduction status |
|---|---|---|---|---|
| E1 | ONE_SHOT vs CLOSED_LOOP bandwidth | `evaluation/run_evaluation.py`, `backend/pipeline/bandwidth.py` | 27 valid systematic rows; 14 infrastructure-error rows; plots; comparison JSON | Reproducible on a Linux/Mininet/OVS/Ryu host, but not in the current Windows audit environment |
| E2 | Manual bandwidth and latency CLI demos | `backend/cli.py` | 11 JSON rows in `evaluation/results/final/manual_demo_runs.csv` | Source is runnable; evidence is hand-selected, not a controlled repeated study |
| E3 | Generalized constraint/latency scenarios | `evaluation/run_generalized_constraints.py`, `backend/orchestration/` | Several JSON and Markdown report files | Scenario source exists; live rerun needs Linux privileges and Ryu/Mininet |
| E4 | First live generalized latency demo | operator invocation plus terminal summary | Terminal summary and nonmatching legacy records; no complete run artifact | Not independently reproducible or auditable |
| E5 | Random topology DESIGN generation | `frontend/src/lib/topology-generator.ts` | 9 passing frontend tests; no experiment result data | Graph reproducible with a supplied seed |

## E1: systematic bandwidth study

### Scenarios

| Scenario | Target | Purpose |
|---|---|---|
| feasible | 20 Mbps | comfortable Path B case |
| boundary | 5.15 Mbps | near contended Path A measurement ceiling |
| correctable | 5.05 Mbps | reachable boundary target |
| infeasible | 49 Mbps | above retained Path B throughput |

Modes: `ONE_SHOT`, `CLOSED_LOOP`. Default planned repetitions: 3 per scenario/mode.

### Retained counts

From `evaluation/results/final/comparison_tables.json`:

- ONE_SHOT: 10 completed measured runs;
- CLOSED_LOOP: 17 completed measured runs;
- infrastructure errors: 14;
- total systematic attempts: 41.

Counts are unequal because infrastructure failures were excluded after timeout/recovery.

### Reproduction command

```bash
sudo mn -c
sudo PYTHONPATH=. python3 evaluation/run_evaluation.py --repetitions 3
PYTHONPATH=. python3 evaluation/summarize.py
PYTHONPATH=. python3 evaluation/build_final_report.py
```

The original `evaluation_runs_*.json` source files used to form the final CSV are not currently present in `evaluation/results/`. Preserve those source files on every rerun before final aggregation.

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

- bandwidth;
- latency;
- combined;
- minimize-latency;
- maximize-bandwidth;
- constrained-minimize-latency.

Each scenario starts Ryu and Mininet and performs a live orchestration. No repetition flags or randomized trial design are implemented.

## E4: first generalized-latency report

The report `docs/reports/first_live_latency_demo.md` confirms evidence-poor status:

- no JSON execution result;
- no snapshot/fingerprint;
- no per-candidate packet or RTT records;
- no cookie/readback/cleanup record;
- no raw ping output;
- only the terminal status, selected path, and 1.629-ms final RTT.

Treat it as a manual demo, not a complete experiment.

## Topology configurations

### Live diamond

Five switches and four hosts are in the fixed topology module, with h2/h3 background hosts.

Path A: `h1-s1-s2-s4-h4`, 10 Mbps links.

Path B: `h1-s1-s3-s5-s4-h4`, 50 Mbps links.

Design/measured distinction:

- 10/50 Mbps TCLink values are configured link properties;
- 5.0/47.0 Mbps iperf3 values are measured outcomes;
- 0.879/0.949 ms manual latency values are measured or reported observations, not configured design values;
- no packet-loss topology measurements are retained from a repeated study.

### Random DESIGN topologies

The frontend supports 2-32 switches, 1-128 hosts, bandwidth 0.01-100000 Mbps, delay 0-10000 ms, packet loss 0-100%, and patterns STAR, RING, TREE, MESH, and RANDOM.

The PRNG is deterministic for a supplied string seed. Blank seeds generate nondeterministic random values and are not reproducible unless the returned seed is retained. No random topology seed is associated with the live Mininet sweep.

## Missing experimental data

1. complete raw systematic sweep source JSON;
2. repeated latency and packet-loss observations;
3. corrected and repeated boundary experiments;
4. randomized seeded topology benchmark results;
5. baseline-policy comparison runs;
6. per-candidate observations and run IDs for generalized latency;
7. candidate enumeration/truncation benchmark;
8. confidence intervals and statistical test records.
