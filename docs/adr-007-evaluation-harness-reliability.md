# ADR-007: Evaluation harness reliability -- a real Mininet/REST instability found running Phase 13, and the fixes

## Context

Phase 13 adds a research-evaluation harness (`evaluation/run_evaluation.py`)
that drives the real MIN_BANDWIDTH pipeline dozens of times in one long
process, across four scenarios and two modes (ONE_SHOT, CLOSED_LOOP),
repeated for statistical confidence. Building this surfaced a real
reliability problem the single-invocation CLI demo (`backend/cli.py`)
never hits often enough to notice, because it makes far fewer real
Mininet/OVS/Ryu calls per process lifetime.

## What went wrong, found by actually running the sweep

The first real attempt at a full sweep crashed with an uncaught
`TimeoutError` from `urllib.request.urlopen` inside
`backend/deployment/ofctl_client.py`'s `_post_json`, partway through the
4th real run in the session (first Feasible/CLOSED_LOOP run) -- a REST
call to Ryu's `ofctl_rest` API stalled past its 10-second timeout even
though Ryu and OVS were both observably healthy immediately before and
after. This is a transient transport hiccup under sustained real load,
not a rejection, and it killed the whole process outright.

Fixing that (see below) surfaced a second, distinct real problem: after
recovering from one of these stalls, subsequent runs would occasionally
hang far longer (tens of seconds to minutes) inside `mininet.node.Host.cmd()`
itself -- specifically in `backend/measurement/throughput.py`'s call to
`client_host.cmd(...)` for the real `iperf3` measurement. Mininet's `Host.cmd`
is a *synchronous* wrapper around a persistent, per-host shell it manages
with a hand-rolled read/monitor loop (`mininet.node.Node.sendCmd`/
`waitOutput`/`monitor`), not a subprocess with its own timeout. Under
sustained load (many sequential real commands across many hosts, over
tens of minutes), this loop can occasionally never see the expected
completion marker and blocks forever. This is a known category of
Mininet fragility, not a bug in this project's own decision/compiler/
validator/deployment code -- none of which changed.

Worse: interrupting that hang with a `SIGALRM`-based hard timeout (the
first fix attempted) can leave the affected `Host`'s internal `waiting`
flag stuck `True` forever, so any further `.cmd()` call on that same host
-- including the ones `mininet.net.Mininet.stop()` itself needs to tear
the topology down cleanly -- immediately raises `AssertionError` instead
of running. The first version of the recovery path called `net.stop()`
on exactly this broken object, which raised again and, since that
happened inside the sweep's own `finally` block, crashed the whole
Python process a second time -- risking the loss of every real run
result already collected in that session.

## Fixes (this project's evaluation-harness code, not its core architecture)

1. **Bounded transport retry** (`backend/deployment/ofctl_client.py`):
   `_post_json`/`_get_json` now retry a transient transport-level failure
   (`TimeoutError`, `URLError`, `ConnectionError`, `OSError`) up to
   `MAX_TRANSPORT_RETRIES` (2) times with a short delay, and return a
   clear `(0, "transport error...")` failure instead of raising when
   retries are exhausted. An HTTP-level error response (a real
   rejection, e.g. 4xx/5xx) is still returned as-is, never retried. This
   is a targeted fix to a real bug that blocks reproducible evaluation
   (the exception item 15 of the Phase 13 brief allows for exactly this
   case) -- it does not touch the decision, compiler, or validator
   layers, and is covered by `tests/test_ofctl_client_retry.py` (mocked
   transport, no real Ryu needed).

2. **Per-run wall-clock budget + honest recording, not a crash**
   (`evaluation/run_evaluation.py`): every real run is wrapped in a
   `SIGALRM`-based 45-second hard timeout. A run that never completes in
   that window (whether from a REST stall the retry above couldn't
   resolve, or a genuinely stuck Mininet host shell) is recorded as an
   **infrastructure error** -- `EvaluationRun.pipeline = None`,
   `error = "..."` -- never faked into a measured `NOT_SATISFIED`
   outcome. `backend/evaluation/aggregate.py` excludes these from every
   satisfaction-rate statistic and reports their count separately
   (`infra_errors`), so a real infrastructure hiccup can never silently
   inflate or deflate either mode's apparent success rate.

3. **Recovery via `mn -c`, never `net.stop()` on a possibly-broken net**:
   after a timeout, the harness kills the current Ryu subprocess and runs
   `mn -c` as an external `subprocess` call -- the same command this
   project's own README already tells a human operator to run between
   CLI invocations -- rather than calling `.stop()` on a Mininet net
   object that may have a permanently stuck host shell. This is the safe
   external equivalent, and it is what actually allowed the sweep to
   keep making forward progress instead of cascading into a second crash.

4. **Incremental result persistence**: `evaluation/run_evaluation.py`
   writes its `evaluation_runs_*.json` file after every single run, not
   once at the end. A run that hits an infrastructure error (or, before
   fix 3, a cascading crash) never loses the real runs already collected
   in that session.

## Honest characterization of the result

Running the full sweep for real still hit a real infrastructure-error
rate of roughly one in three runs (see `docs/experiments.md`'s Phase 13
section for the exact count) -- this is reported as a genuine, measured
property of running this particular research harness against this
particular sandboxed Mininet environment for an extended session, not
concealed or excluded from the write-up. It does not affect the validity
of the runs that did complete: every completed run in the dataset is a
real, non-fabricated measurement, exactly as in every other phase of this
project. It does mean the evaluation dataset for the "boundary" and
"correctable" scenarios ended up smaller, and in this particular
automated sweep no completed run happened to catch the closed loop
converging on those two scenarios specifically -- the earlier,
manually-run examples in `docs/experiments.md`'s Phase 12 section
(target 5.05 Mbps converging in one real correction iteration; target
5.0 Mbps exhausting all three real iterations without converging) remain
the record of that specific behavior, produced before this harness
existed, under the same real pipeline.
