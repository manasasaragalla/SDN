# Recommended IEEE Paper Outline

## Suggested title

**IntentFlow: A Verifiable Intent-to-Path Framework with Deterministic Constrained Planning and Closed-Loop Network Execution**

Keep the title narrower until new experiments establish generality.

## Abstract

Summarize the problem, architecture, deterministic planner, one live testbed and one controlled bandwidth result. Do not claim general SDN performance or statistically significant closed-loop improvement.

## I. Introduction

- ambiguity and implementation risk in intent-based networking;
- gap between LLM language understanding and safe configuration;
- distinction between intent interpretation, topology planning, and network execution;
- research questions:
  1. can a deterministic planner safely enumerate and rank exact paths;
  2. can hard constraints be separated from objectives;
  3. can a bounded closed-loop controller improve bandwidth intent satisfaction;
  4. what evidence is required before success is reported.

## II. Related Work

Topics to verify with academic references:

- intent-based networking;
- SDN programming and OpenFlow;
- QoS-aware constrained routing;
- multi-constraint path selection;
- network intent compilers and verification;
- LLM-assisted network management;
- closed-loop automation and feedback control;
- reproducible network testbeds.

Do not invent a literature comparison until sources are verified.

## III. System Architecture

Include a figure:

Frontend -> API -> provider/structured intent -> canonical intent -> active topology -> enumeration -> constraints/objective ranking -> preflight -> compiler -> worker/Ryu/OVS -> measurement -> evidence.

Explain:

- LLM has no command-writing authority;
- mock provider is deterministic;
- design and live topologies are separate;
- plan and execution statuses are separate.

## IV. Mathematical Formulation

Define exact candidate path, bottleneck bandwidth, summed latency, independent-link packet-loss aggregation, hard constraint operators, objective ranking, and fingerprint tie-break. Explicitly label values as configured or measured.

Known implementation issue: missing host-attachment values must be unknown in the final formulation until the implementation is corrected and retested.

## V. Proposed Methodology and Algorithm

Present bounded simple-path DFS:

1. validate topology;
2. enumerate exact physical paths;
3. aggregate configured facts;
4. reject violated constraints;
5. rank eligible candidates;
6. terminate with incomplete search if truncated;
7. preflight a live candidate;
8. compile and deploy;
9. measure and verify;
10. cleanup and publish evidence.

Include CLOSED_LOOP bandwidth correction separately and state that it is one testbed-specific lever.

## VI. Baseline and Experimental Setup

Proposed baselines:

- ONE_SHOT;
- shortest hop;
- widest/maximum bottleneck;
- lowest-configured latency;
- lowest-configured loss;
- random seeded path;
- round-robin.

Do not present a baseline as evaluated until a run exists.

Describe:

- Linux host;
- kernel/Mininet/OVS/Ryu versions;
- topology and TCLink values;
- iperf3/ping settings;
- repetition count;
- timeout and infrastructure-error handling;
- random seeds;
- anti-colliding test order;
- statistics and exclusions.

## VII. Results

Only include actual retained data:

- 27 completed systematic bandwidth rows;
- 14 explicit infrastructure errors;
- satisfaction rates;
- throughput distributions;
- correction iterations;
- manual evidence for correction success/failure.

Recommended tables:

- scenario/mode/valid-n/satisfaction;
- throughput mean/median/range;
- infrastructure errors;
- baseline comparisons after new runs;
- test and build validation.

Recommended figures:

- satisfaction rate;
- throughput vs target;
- correction iteration;
- topology and path diagram;
- framework workflow.

## VIII. Discussion

- bottleneck and measured-throughput distinction;
- bounded search limitations;
- correction lever limitations;
- infrastructure failures and measurement noise;
- source of 5 Mbps and 47 Mbps outcomes;
- no general performance claim.

## IX. Limitations

- small unequal sample sizes;
- fixed testbed;
- userspace OVS and sandbox environment;
- no randomized topology results;
- no packet-loss/loss repeated study;
- no completed baseline comparison;
- missing complete latency report artifact;
- missing raw source sweep files.

## X. Conclusion and Future Work

Conclude with implemented and demonstrated behavior only. Future work should include larger baselines, broader topology distributions, packet loss and combined constraints, and correction alternatives.

