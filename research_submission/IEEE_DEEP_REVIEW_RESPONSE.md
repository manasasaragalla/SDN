# Deep Review Response Matrix

| Significant review criticism | Repository check | Action in manuscript |
|---|---|---|
| The title implied broad closed-loop capability | Generalized LIVE execution has probe, selection, final deployment, and readback, but no iterative post-deployment controller. | Reframed the title around deterministic constrained planning and evidence-aware execution in a fixed testbed. |
| The three workflows were presented too continuously | DESIGN, generalized LIVE, and legacy CLI are separate entry points and path representations. | Redesigned the architecture figure as three independent branches and removed a unified-pipeline interpretation. |
| Legacy systematic runs were attributed to generalized LIVE | The 27 completed and 14 timeout records come from `evaluation/run_evaluation.py` and `backend/pipeline/bandwidth.py`. | The abstract and methodology now attribute these counts exclusively to the legacy CLI sweep. |
| 24 planned repetitions conflict with 41 attempts | The script declares 3 repetitions per scenario-mode pair, producing 24 nominal pair-attempts. The retained raw inventory explains neither reruns nor the additional completed/timeout attempts. | Reported 24 nominal repetitions and 41 retained attempts, and explicitly disclosed that the reason for the additional rows is unverifiable. |
| Path A/Path B run counts may be unsupported | The systematic aggregate CSV does not independently identify route counts for every group. The generalized JSON contains explicit `final/selected_path` fields. | Removed systematic route-count deductions; reported the generalized count only where individual JSON fields confirm 6 Path B and 1 Path A successes. |
| The 8 generalized LIVE records were overstated | JSON records show 7 SUCCEEDED and 1 FAILED individual executions. | Described them as demonstrations, not a repeated statistical sample. |
| Host or topology details were guessed | `testbed/topology/diamond.py` declares five switches, h1/h2/h3/h4, and the two named paths. | Standardized the topology description and retained 10/50 Mbps as configured TCLink values. |
| Packet-loss and freshness claims need precision | Loss uses the configured survival-product model; live packet-loss is normalized from ping data with timestamp/freshness checks. | Added independence assumptions for configured loss and explained that live observations are measured, identity/freshness checked values. |
| The mock and external providers may be conflated with LLM evaluation | The mock uses deterministic regex/rule parsing; no LLM accuracy or latency dataset is retained. | Explicitly separated rule parsing from optional provider adapters and removed LLM-performance claims. |
| Test counts or execution claims were too broad | Retained reports support 843 backend tests and 266 focused planner tests. The frontend test inventory exists, but stale/older pass counts should not be repeated. | Included exact backend counts only and described frontend coverage without a pass-count claim. |
| Formal verification or continuous assurance was implied | The implementation readbacks exact flow rules and checks host connectivity; it has no network-wide invariant prover or post-deployment monitoring loop. | Removed these claims and retained formal verification and continuous assurance only as limitations/future work. |
| Arbitrary production deployment was implied | The worker is fixed to the repository diamond topology and fixed testbed lifecycle. | Limited live claims to the fixed Mininet/Ryu/OVS testbed and excluded arbitrary deployment as an unsupported capability. |
| Closed-loop benefits were overstated | Per-scenario satisfaction differences are zero in the legacy systematic comparison; isolated manual records show success and failure. | Removed causal/statistical benefit claims and reported the evidence as tied or mixed. |
| Related work was too sparse or non-critical | The implementation relates to intent terminology, SDN surveys, OpenFlow, verification, routing, measurement, and LLM configuration. | Expanded to 24 genuine references and added critical comparisons without claiming superiority. |

## Claims deliberately removed

- General closed-loop or congestion-control benefit.
- Statistical significance and pooled-causal improvement.
- Scalability or large-topology performance.
- Superiority over routing baselines.
- Formal network-wide verification.
- Continuous post-deployment QoS assurance.
- Generalized LIVE CLOSED_LOOP correction.
- Quantitative external-LLM intent accuracy.
- Arbitrary production network deployment.
- Repeated-trial status for eight generalized LIVE records.

## Future-work capabilities not implemented

- Integration of generalized LIVE execution with bounded feedback.
- Continuous post-deployment QoS monitoring.
- Independent shortest, widest, random, round-robin, and other baselines.
- Larger, randomized, and repeated topology studies.
- Quantitative external-provider parsing evaluation.
- Finer packet-loss measurement and repeated statistical trials.
- Deployment beyond the fixed diamond testbed.
