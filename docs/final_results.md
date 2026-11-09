# Final results: ONE_SHOT vs CLOSED_LOOP intent satisfaction

This document is the final research write-up for the closed-loop
bandwidth-correction mechanism, built entirely from measured data already
in this repository. It draws on two disjoint sources: the Phase 13
systematic evaluation sweep (`evaluation/run_evaluation.py`, aggregated by
`backend/evaluation/aggregate.py`) and the Phase 11/12 manual `backend/cli.py`
demonstration runs. Both are described in full in `docs/experiments.md`;
this document is the consolidated report, and every number in it is
reproduced from `evaluation/results/final/comparison_tables.json`,
`systematic_runs.csv`, `infra_error_runs.csv`, and `manual_demo_runs.csv`
(all built by `evaluation/build_final_report.py`, which takes no new
measurements of its own). Nothing here is fabricated, smoothed, rounded up,
or excluded to change a conclusion.

## Methodology

The system under test is the closed-loop MIN_BANDWIDTH pipeline
(`backend/pipeline/bandwidth.py`), shared unmodified between the CLI demo
and the evaluation harness. Two configuration strategies are compared:

- **ONE_SHOT**: decision -> validation -> deployment -> one real
  `iperf3` measurement -> stop, whatever it shows.
- **CLOSED_LOOP**: the same, then, only if that first measurement falls
  short of the target, a bounded real correction loop (up to
  `MAX_CORRECTION_ITERATIONS = 3`): diagnose the shortfall, throttle the
  real competing background flow's OVS QoS rate cap down by a bounded,
  shortfall-proportional amount (`next_background_rate_mbps`), redeploy,
  and re-measure with real `iperf3`.

Both strategies run against the same live testbed (Mininet + Open vSwitch
userspace datapath + patched Ryu 4.34, diamond topology: contended Path A,
`h1-s1-s2-s4-h4`, 10 Mbps link, sharing its `s2-s4` hop with a background
`h2->h3` flow; uncontended Path B, `h1-s1-s3-s5-s4-h4`, 50 Mbps link).
Nothing is simulated: every throughput number in every result file is a
real `iperf3` measurement, and every background-rate change is a real
`ovs-vsctl` QoS queue redeploy.

Four scenarios, chosen to cover the interesting regions of the decision
space (see `docs/experiments.md` for the full rationale):

| scenario | target | why this target |
|---|---|---|
| `feasible` | 20 Mbps | Comfortably within Path B's uncontended capacity -- trivial case. |
| `boundary` | 5.15 Mbps | Right at Path A's real measured ceiling under contention -- genuinely noisy. |
| `correctable` | 5.05 Mbps | The exact target that produced both a genuine correction success and a genuine correction failure in the manual Phase 12 runs. |
| `infeasible` | 49 Mbps | Above even Path B's ceiling; no candidate can ever satisfy it, with or without correction. |

The Phase 13 sweep ran each (scenario, mode) combination for multiple
repetitions (`evaluation/run_evaluation.py --repetitions 3`, run in several
invocations across one long session -- a long sweep can exceed the shell's
own invocation time limit, so `evaluation_runs_*.json` files were combined
after the fact, never re-run to replace or discard an earlier result).

## Experimental setup

- Topology: `testbed/topology/diamond.py`, 6 switches, 4 hosts, real
  `TCLink` bandwidth caps, checksum offload disabled on every host veth
  (`docs/adr-005-checksum-offload.md`).
- Controller: Ryu 4.34 (patched, `.venv-ryu/`), `ofctl_rest` REST API,
  OpenFlow 1.3.
- Background traffic: `h2->h3`, real, continuous, rate-limited via OVS QoS
  (`type=linux-htb`), starting at 8 Mbps and only ever throttled downward
  by the correction loop, never by the ONE_SHOT strategy (which never
  touches it after initial setup).
- Measurement: real `iperf3` TCP throughput, `client_host.cmd(...)`
  through Mininet, parsed from real client output.
- Harness reliability: an uncaught REST transport timeout and a Mininet
  host-shell hang were both found and fixed while building this harness
  (`docs/adr-007-evaluation-harness-reliability.md`) -- a bounded retry in
  `backend/deployment/ofctl_client.py`, and a 45-second per-run wall-clock
  budget in `evaluation/run_evaluation.py` that records a run exceeding it
  as an **infrastructure error**, never as a fabricated measurement.

## Baseline: ONE_SHOT

ONE_SHOT is the baseline configuration strategy: decide, deploy, measure
once, stop. It never revisits a deployment that falls short. Across the
systematic sweep it completed 10 runs (see Results below): every `feasible`,
`boundary`, and `correctable` run was satisfied on the first measurement;
every `infeasible` run was correctly `NOT SATISFIED` on the first
measurement, since no candidate path can reach 49 Mbps regardless of
background-traffic contention.

## Closed-loop approach

CLOSED_LOOP adds exactly one thing on top of the ONE_SHOT baseline: if the
final measurement falls short of the target, it runs the bounded
diagnose-reconfigure-redeploy-remeasure loop from `docs/adr-006-closed-loop-correction.md`,
up to 3 real iterations, using only the real measured shortfall to compute
the next background-rate cap. It never touches the primary flow's own
path or rate (`MIN_BANDWIDTH` is a floor, not a target to trim toward), and
it never calls an LLM. In the systematic sweep, this loop only ever had a
reason to run in the `infeasible` scenario (3 runs, each exhausting all 3
real correction iterations) -- every `feasible`, `boundary`, and
`correctable` CLOSED_LOOP run was already satisfied on the first
measurement, exactly like its ONE_SHOT counterpart, so the loop had
nothing to correct.

## Results

### Systematic sweep (27 real completed runs; `evaluation/results/final/systematic_runs.csv`)

| scenario | mode | n | initial satisfied | final satisfied | mean corrections | mean time (s) | mean final throughput (Mbps) |
|---|---|---|---|---|---|---|---|
| feasible | ONE_SHOT | 3 | 100% | 100% | 0.00 | 7.5 | 46.99 |
| feasible | CLOSED_LOOP | 2 | 100% | 100% | 0.00 | 7.5 | 46.80 |
| boundary | ONE_SHOT | 2 | 100% | 100% | 0.00 | 7.7 | 5.18 |
| boundary | CLOSED_LOOP | 4 | 100% | 100% | 0.00 | 7.6 | 26.00 |
| correctable | ONE_SHOT | 2 | 100% | 100% | 0.00 | 7.6 | 26.26 |
| correctable | CLOSED_LOOP | 8 | 100% | 100% | 0.00 | 7.6 | 31.44 |
| infeasible | ONE_SHOT | 3 | 0% | 0% | 0.00 | 7.5 | 47.17 |
| infeasible | CLOSED_LOOP | 3 | 0% | 0% | 3.00 | 30.0 | 47.05 |

(The mean-final-throughput figures for `boundary` and `correctable` mix
runs that landed on contended Path A, ~5 Mbps, with runs that landed on
uncontended Path B, ~47 Mbps -- both are genuine outcomes of the
decision layer's "cheapest candidate meeting target" policy applied to
real, noisy measurements near a decision boundary; see Failure analysis.)

### Per-scenario ablation: does closed-loop correction improve satisfaction?

| scenario | ONE_SHOT satisfied | CLOSED_LOOP satisfied | improvement | correction helped | correction ran, did not help |
|---|---|---|---|---|---|
| feasible | 100% | 100% | +0pp | 0 | 0 |
| boundary | 100% | 100% | +0pp | 0 | 0 |
| correctable | 100% | 100% | +0pp | 0 | 0 |
| infeasible | 0% | 0% | +0pp | 0 | 3 |

**Measured finding: in this dataset, closed-loop correction produced zero
percentage-point improvement in satisfaction rate in every one of the four
scenarios.** This is not a negative framing of a positive result -- it is
the direct reading of the aggregated data, and it is reported as such.

A naive pool of every run regardless of scenario shows ONE_SHOT at 70%
(7/10) and CLOSED_LOOP at 82% (14/17), an apparent "+12 percentage point"
improvement. **This pooled figure must not be read as evidence that
closed-loop correction helps.** It is an artifact of unequal sample sizes
across scenarios (more CLOSED_LOOP repetitions happened to complete for
`correctable`, a scenario where both modes are satisfied 100% of the time
anyway, simply because more attempts were made there while chasing a
completed correction-in-progress run before the infrastructure timeout).
The per-scenario table above is the correct answer to the ablation
question asked at the start of this evaluation, and it shows no measured
difference anywhere in this dataset.

### Manual demonstration runs (11 runs; `evaluation/results/final/manual_demo_runs.csv`)

These are hand-run, single-invocation `backend/cli.py` demonstrations from
Phase 11/12 (not repeated for statistical confidence, and not part of the
systematic sweep above), included here because they are the only runs in
the repository that show the correction loop actually changing a run's
outcome in either direction:

| run | target | corrections | outcome |
|---|---|---|---|
| `run_1790407480.json` | 49.0 Mbps | 3 | NOT SATISFIED -- 47.13 Mbps < 49.0 Mbps (the original decision-policy-bug discovery run) |
| `run_1790407821.json` | 6.0 Mbps | 0 | SATISFIED -- 46.69 Mbps (Path B selected outright) |
| `run_1790407907.json` | 5.15 Mbps | 0 | SATISFIED -- 46.71 Mbps |
| `run_1790407943.json` | 4.9 Mbps | 0 | SATISFIED -- 4.98 Mbps (Path A selected for real, first confirmation of the decision-policy fix) |
| `run_1790408000.json` | 5.0 Mbps | 3 | **NOT SATISFIED** -- 4.55 Mbps, genuine bounded correction failure |
| `run_1790408063.json` | 5.0 Mbps | 0 | SATISFIED -- 47.34 Mbps (same target re-run, natural variance selected Path B instead) |
| `run_1790408133.json` | 5.05 Mbps | 1 | **SATISFIED after correction** -- 5.18 Mbps, genuine correction success |
| `run_1790408178.json` | (MINIMIZE_LATENCY) | 0 | SATISFIED -- regression check |
| `run_1790409159.json` | 5.05 Mbps | 0 | SATISFIED -- 47.34 Mbps (regression check, Path B selected) |
| `run_1790412063.json` | (MINIMIZE_LATENCY) | 0 | SATISFIED -- regression check |
| `run_1790412088.json` | 20.0 Mbps | 0 | SATISFIED -- 46.48 Mbps (regression check) |

`run_1790408133.json` (target 5.05 Mbps) is the one run in the entire
repository, systematic or manual, where the correction loop ran and
changed the outcome from unsatisfied to satisfied: the first measurement
on Path A came in at 4.98 Mbps, one real correction iteration throttled
the background flow from 8.00 to 7.88 Mbps, and the re-measurement came in
at 5.18 Mbps, clearing the 5.05 Mbps target. `run_1790408000.json` (also
target 5.0 Mbps) is the counter-example: the loop ran all 3 permitted
iterations for real and could not converge, because the real
shortfall-proportional correction step was smaller than this testbed's
own run-to-run measurement noise near this decision boundary.

## Failure analysis

Three distinct kinds of "failure" appear in this dataset, and they are
kept separate rather than merged into one success/failure count:

1. **Genuinely infeasible targets** (`infeasible` scenario, 49 Mbps, and
   manual run `run_1790407480.json`): no candidate path can ever reach the
   target, with or without correction, because Path B (the only feasible
   candidate) never shares a link with the throttleable background flow.
   Both ONE_SHOT and CLOSED_LOOP correctly report `NOT SATISFIED` every
   time (0% satisfaction in both modes, 6/6 systematic runs plus the
   manual run). CLOSED_LOOP still runs its full 3 correction iterations
   before giving up (mean execution time 30.0s vs. 7.5s for ONE_SHOT) --
   this is the loop's real cost when correction genuinely cannot help,
   measured rather than assumed.

2. **A genuine bounded correction failure at a noisy decision boundary**
   (manual run `run_1790408000.json`, target 5.0 Mbps): the target is
   topologically reachable, the loop runs for real, and it still does not
   converge, because the real correction step (a 9.5% cumulative
   reduction in the background cap across all three iterations) is
   smaller than this testbed's own measurement noise at this boundary
   (repeated `iperf3` runs under identical configuration vary by roughly
   ±0.2-0.4 Mbps here). This is reported as a real, expected limitation
   of a shortfall-proportional correction step operating near a boundary
   this narrow, not a bug in the correction logic.

3. **Infrastructure errors, excluded from every statistic**
   (`evaluation/results/final/infra_error_runs.csv`, 14 runs, 34% of the 41
   systematic-sweep attempts): a REST call to Ryu or a Mininet host shell
   occasionally stalled past the 45-second per-run budget under the
   sustained load of a long harness session. These are a measured property
   of running this particular harness against this particular sandboxed
   environment for an extended period, not a failure of the intent-
   satisfaction system under test, and are never counted as a measured
   `NOT SATISFIED` outcome. See `docs/adr-007-evaluation-harness-reliability.md`.

## Limitations

- The systematic sweep never happened to capture a completed automated
  run of the correction loop converging or failing to converge on the
  `boundary` or `correctable` scenarios specifically -- several
  `correctable` CLOSED_LOOP runs did start down that path (measured short,
  began throttling) but were cut off by the run-timeout budget before
  their outcome was recorded, and are honestly logged as infrastructure
  errors rather than guessed at. The only evidence in this repository that
  the correction loop changes an outcome in either direction is the two
  manual Phase 12 runs (`run_1790408133.json`, `run_1790408000.json`).
- The systematic sweep's per-(scenario, mode) sample sizes are small (2 to
  8 runs) and unequal, a direct consequence of the infrastructure-error
  rate above; this is a real limitation on the statistical confidence of
  any per-scenario rate quoted here, not something the aggregation hides.
- This testbed is a single, shared, 2-vCPU sandboxed container running
  Mininet, multiple OVS userspace switches, and the Ryu controller all at
  once; the measurement noise and infrastructure-error rate documented
  here are properties of this specific environment and may not transfer
  to a testbed with dedicated hardware or a kernel datapath.
- The correction mechanism only has one lever (throttling a background
  flow that happens to share a link with the selected path); scenarios
  where no such shared link exists (`infeasible` here) are, by
  architecture, never correctable, and this dataset confirms that
  prediction rather than testing a different mechanism.

## Research findings

1. **Closed-loop correction produced zero measured improvement in
   aggregate satisfaction rate over one-shot configuration, in every
   scenario in the systematic sweep.** The one pooled statistic that
   suggests otherwise (+12pp) is a sampling artifact, not a real effect,
   and is explicitly not claimed as a finding.
2. **The correction loop does work when given the chance**: the one
   manual run where the first measurement fell short on a topologically
   reachable target and the loop got to run (`run_1790408133.json`)
   converged to `SATISFIED` in exactly one real iteration. The systematic
   sweep did not happen to capture an automated instance of this, purely
   because of the infrastructure-error rate documented above -- it is not
   evidence that the loop doesn't work, only that this particular sweep
   didn't record a completed example of it working.
3. **The correction loop correctly identifies when it cannot help**: on
   the genuinely infeasible target, it ran its full bound (3 iterations)
   and correctly reported `NOT SATISFIED` every time, in both the
   systematic sweep and the manual run, with no false positive.
4. **The correction loop can also genuinely fail to converge on a
   reachable target**, when the real correction step is smaller than
   real measurement noise near a narrow decision boundary
   (`run_1790408000.json`) -- this is reported as an honest limitation of
   a bounded, deterministic, shortfall-proportional correction strategy,
   not smoothed into a success.
5. **A real research byproduct of building the evaluation harness itself**
   was finding and fixing two infrastructure reliability bugs (an uncaught
   REST timeout, and a Mininet host-shell hang that could cascade into a
   crash) that the original single-invocation CLI demo never ran long
   enough to expose -- documented in `docs/adr-007-evaluation-harness-reliability.md`,
   with the residual ~34% infra-error rate reported rather than concealed.
