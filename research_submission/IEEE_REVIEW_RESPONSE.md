# IEEE Review Response

The review response below addresses the Deep Research/audit findings available
in the repository. It also identifies conclusions that could not be supported
from the implementation or retained data.

| Reviewer comment | Existing issue | Paper revision made | Evidence from implementation | Remaining limitation |
|---|---|---|---|---|
| Narrow the title and avoid claiming closed-loop generality. | “Verifiable” and “closed-loop” could imply formal verification or a generalized controller. | Changed the title to “Deterministic Constrained Path Planning with Evidence-Aware SDN Execution.” The abstract and architecture define verification narrowly. | Generalized orchestrator and legacy bandwidth pipeline are separate in `backend/orchestration/generalized_constraints.py` and `backend/pipeline/bandwidth.py`. | No formal network-wide verification or general congestion-control result is implemented. |
| State implementation status precisely. | Existing reports mixed source implementation with live evidence. | Added separate DESIGN, generalized LIVE, and legacy CLI sections throughout. | `backend/api/main.py`, `backend/api/worker.py`, `backend/cli.py`, `evaluation/run_evaluation.py`. | Arbitrary live topology execution is not implemented; worker execution remains fixed to the diamond. |
| Separate configured and measured metrics. | TCLink values can be confused with throughput or RTT. | Added explicit configured/observed equations and table labels. | 10/50 Mbps TCLinks; ping and iperf3 parsers. | Retained environment and raw run metadata are incomplete. |
| Distinguish flow readback from formal verification. | “Verified” could be interpreted as network invariant verification. | Restricted verification language to exact switch readback and host-pair connectivity. | `backend/deployment/physical_path_executor.py`, generalized evidence reports. | No Header-Space or NetKAT-style formal verifier. |
| Add genuine related work. | Prior documentation lacked a checked bibliography. | Added citations for intent terminology, OpenFlow, Header Space Analysis, constrained routing, Yen enumeration, measurement, and NetConfEval. | Repository directly relates to these concepts. | No systematic literature-comparison baseline was performed. |
| Explain mathematical semantics. | Missing host attachment facts previously omitted were especially dangerous. | Added complete physical-path equations and unknown/fail-closing semantics. | `_path_facts()` and `tests/test_topology_planning_metrics.py`. | No public separate switch-core metric semantics is defined for incomplete live graphs. |
| Explain bounded enumeration. | A candidate limit could be mistaken for global optimality. | Documented default 64-candidate limit and INCOMPLETE_SEARCH status. | `backend/planner/path_enumeration.py`, candidate selection code. | No empirical enumeration/runtime scaling study is retained. |
| Preserve the three workflow distinctions. | Documentation sometimes presented legacy and generalized paths as interchangeable. | Added a dedicated workflow distinction and architecture figure. | Three implementation entry points listed in the paper and dossier. | The generalized API does not execute legacy CLOSED_LOOP correction. |
| Separate rule-based parsing from LLM parsing. | Mock provider can be mistaken for an LLM study. | Explicitly labeled the mock as deterministic regex/rule parsing and providers as optional. | `backend/llm/mock.py`, `backend/llm/factory.py`. | No experiment measures provider accuracy, latency, or hallucination. |
| Report DESIGN evidence accurately. | DESIGN planner results can be mistaken for live experiments. | Labeled preview values configured and no side-effect-free result as network measurement. | `plan_on_topology()` and topology catalog. | No repeated or comparative DESIGN benchmark dataset is retained. |
| Report all systematic outcomes. | Unequal trial counts and infra errors could bias pooled conclusions. | Included 27 completed rows, 14 timeout rows, and all four per-scenario comparisons. | `systematic_runs.csv`, `infra_error_runs.csv`, `comparison_tables.json`. | Raw source JSON and per-run environment manifests are missing. |
| Do not claim statistical significance. | Pooled improvement could be interpreted causally. | Removed significance language and pooled claims as evidence. | Per-scenario difference is 0 pp for all four scenarios. | Small unequal groups prevent inferential analysis. |
| Do not claim correction generally improves throughput. | CLOSED_LOOP ran only against the h2-h3 competing flow. | Restricted claims to isolated correction behavior and three infeasible corrections. | `backend/models/feedback.py`, legacy pipeline. | No repeated corrected-boundary/independent-baseline study exists. |
| Include unsuccessful runs and failures. | A favorable success could hide bounded failure. | Added the 49-Mbps infeasible results and 5.0-Mbps three-iteration failure. | `manual_demo_runs.csv`, systematic infeasible rows. | No preregistered success/failure criterion or confidence interval. |
| Address infrastructure errors. | Timeout runs could disappear from aggregate statistics or be misclassified. | Added explicit error table and explained exclusion. | 14 `_RunTimedOut` rows in `infra_error_runs.csv`. | Timeout threshold may correlate with scenario, mode, or host state. |
| Separate generalized live evidence from legacy evidence. | Both use Mininet/ping/iperf3 but have different orchestration and path models. | Added separate methodology and result tables. | Generalized reports are distinct from `systematic_runs.csv`. | Generalized runs are single demonstrations, not a repeated study. |
| Preserve packet-loss semantics. | 10-packet ping observations are coarse for tight thresholds. | Kept packet-loss support but added the 10-packet/threshold caveat. | `generalized_constraints.py` ping strategy. | No repeated packet-loss benchmark or fine-grained packet-loss study. |
| Do not claim scalability or novelty. | Architectural diagrams and path planning could imply scale or comparative advantage. | Added explicit limitations and narrowed contribution language. | Unit tests and fixed two-route testbed. | Scalability and comparative novelty require future experiments. |
| State baselines accurately. | ONE_SHOT was sometimes implied to be a broad routing baseline. | Named ONE_SHOT as the only retained experiment baseline and marked proposed routes as not evaluated. | `evaluation/run_evaluation.py`, `comparison_tables.json`. | No independent shortest-hop/widest-path/random baseline. |
| Address LLM safety claims carefully. | “Closed-loop agent” could imply autonomous model write authority. | Described providers only as interpreters and deterministic code as executor. | Canonical schema, compiler, worker allowlist. | No LLM safety benchmark or external-provider live experiment. |
| Explain the fixed live topology. | “Diamond” diagrams and path descriptions had inconsistent switch counts. | Standardized five-switch, four-host description and exact routes. | `testbed/topology/diamond.py`. | No alternate topology or real-hardware validation. |
| Account for missing first latency artifact. | Operator terminal summary lacked raw candidate/deployment evidence. | Kept the 1.629-ms demo as incomplete, unrepeatable evidence. | `docs/reports/first_live_latency_demo.md`. | Cannot independently audit final deployment or candidate observations. |
| Add test evidence with no performance inflation. | Test pass counts can be mistaken for network experiment success. | Listed backend tests separately from live experiments. | WSL 843/843 backend and 266/266 focused planner tests. | Test environment differs from dedicated hardware and does not establish runtime scalability. |
| Strengthen reproducibility disclosure. | Historical setup, seed, and source data were incomplete. | Added exact commands, artifacts, missing raw inventory, and environment limits. | Setup scripts and result directories. | Exact historical run reproduction remains impossible from retained raw inputs. |

## Comments That Cannot Be Fully Resolved

1. **No repeated packet-loss or combined-constraint study:** the implementation
supports these metrics, but existing retained runs do not provide enough repeated
data for a statistically meaningful claim.
2. **No alternate routing baselines:** shortest-hop, widest-path, random,
round-robin, and lowest-loss comparisons are proposals only.
3. **No scalability experiment:** the 64-candidate bound and bounded topology
cannot establish scaling.
4. **No formal network verification:** the implementation performs exact flow
readback and host-pair probes, not formal invariant verification.
5. **No LLM benchmarking:** external providers and the mock parse requests,
but no accuracy or safety study is retained.
6. **No raw source sweep JSON or full environment manifest:** the paper cannot
reproduce or re-analyze the historical raw samples beyond retained CSV/JSON
summaries.
