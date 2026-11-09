# ADR-004: Bandwidth-enforcement mechanism for MIN_BANDWIDTH / RATE_LIMIT

## Context

Phase 11 (MIN_BANDWIDTH: "provide at least 20 Mbps between h1 and h4")
needs two distinct bandwidth-related capabilities, not one:

1. **Static path capacity** -- each candidate path between h1 and h4 needs a
   known, differentiated bandwidth ceiling, so a bandwidth-aware decision
   layer has something real to reason about (analogous to how the latency
   objective uses the diamond's differentiated hop count).
2. **Dynamic per-flow rate limiting** -- the brief's `Action.RATE_LIMIT` and
   its "generic, reusable `rate_limit(flow, rate)`-style compiler"
   requirement need an actual, deployable mechanism to cap one specific
   flow's rate on a live switch, independent of the link's static capacity.

Three mechanisms were available in principle: Mininet `TCLink(bw=...)`
(link-level, static, set at topology-build time), OVS QoS queues
(per-port, attached at runtime via `ovs-vsctl`, referenced from OpenFlow
via the `SET_QUEUE` action), and OpenFlow 1.3 meters (per-flow, referenced
via an `apply:meter` instruction, configured over `ofctl_rest`'s meter
endpoints).

## Decision

**Static path capacity**: `TCLink(bw=...)`, exactly as already used for the
diamond's two h1-h4 paths (`PATH_A_BW_MBPS = 10`, `PATH_B_BW_MBPS = 50`).
ADR-001 already established this works in this kernel (`htb`/`tbf` are
compiled in); no new evidence needed, and no reason to duplicate a working
mechanism with a second one for the same job.

**Dynamic per-flow rate limiting**: **OVS QoS queues** (`type=linux-htb`),
attached to the specific egress port a flow's rule outputs to, referenced
from the compiled `FlowRule` via a `SET_QUEUE` action ahead of `OUTPUT`.
Rejected OpenFlow meters for this project's scope: meters are a
per-datapath resource keyed by an integer meter-id with their own
allocate/verify lifecycle, and this Ryu/OVS combination's meter support was
not something ADR-001 or ADR-002 had already exercised and verified --
introducing it here would mean validating a second, independent
deployment path under the same time budget that already went into
verifying `ofctl_rest` flow deployment. OVS QoS queues, by contrast, are
`tc htb` under the hood on the exact interface the flow already egresses
through -- the same queueing discipline ADR-001 already confirmed is
compiled into this kernel and already verified working (for link-level
shaping). Using it again for flow-level shaping is the smaller, more
reproducible step, and it stays independently verifiable the same way
ADR-001 verified `htb`/`tbf`: `tc qdisc show`/`tc class show` on the exact
OVS-internal interface, plus `ovs-appctl qos/show <iface>`.

## What this actually deploys

`backend/compiler/rate_limit.py` (`compile_rate_limit`) compiles a path the
same way `compile_reroute` does (explicit forward/reverse/ARP rules per
hop, no flooding), except the **first** switch hop's forward-direction rule
(source host's directly-attached switch, egress port toward the next node
in the path) gets `actions=[{"type": "SET_QUEUE", "queue_id": N}, {"type":
"OUTPUT", "port": P}]` instead of a bare `OUTPUT`, and the compiler also
returns a `QueueConfig` describing the OVS queue that rule's `queue_id`
must exist in before that rule is deployed. Shaping only the first hop
(closest to the source) is a deliberate, standard "shape at the edge"
simplification -- it caps this one flow at ingress into the shared
topology, rather than requiring an independent queue (and independent
verification) on every downstream hop for the same numeric effect. This is
the mechanism this project uses for the **background/competing traffic**
(h2->h3, see `docs/adr-005-background-traffic-topology.md`... actually
folded into this ADR below), not the primary intent's own path -- see
"Why RATE_LIMIT targets the background flow" below.

`backend/deployment/ovs_qos_client.py` runs `ovs-vsctl` directly (plain
`subprocess`, not through a Mininet node object -- these OVS switches run
`inNamespace=False`, i.e. `ovs-vsctl`/`tc` against their interfaces from
this same root network namespace works exactly as it would from inside a
Mininet-attached shell) to: create a `qos` row of `type=linux-htb` on the
target interface with one queue (`other-config:max-rate=<bps>`), attach it
to the interface's `Port` table entry, and tag both OVSDB rows with
`external_ids:owner=sdn-intent-agent`. Cleanup inspects only the QoS row
attached to the target interface, refuses to replace an unowned QoS or
Queue row, and destroys the associated project-owned rows in one scoped
OVSDB transaction. It does not issue global `destroy` operations.
Previously-created untagged
rows are intentionally left untouched and may require operator cleanup
before this client can install a queue on that interface. This mirrors
`ofctl_client.py`'s deploy-then-read-back discipline: after creating the
queue, it re-reads the port's `qos` column via `ovs-vsctl` to confirm the
queue actually attached, rather than trusting a zero exit code alone.

## Why RATE_LIMIT targets the background flow, not the primary intent

A `MIN_BANDWIDTH` intent asks for *at least* N Mbps -- a floor, not a cap.
Rate-limiting the primary h1->h4 flow itself would work against that
directly. The natural place a deterministic `rate_limit` action is useful
for *this* objective is capping the **competing** traffic (h2->h3) that
would otherwise be free to consume the entire shared link's capacity,
which is exactly what turns "does h1->h4 get 20 Mbps" from a trivial
question (nothing else is using the network) into a genuine one (a real
30-40% of Path A's capacity is being taken by another real flow at the
same time). The primary flow's own path is still installed with the
existing, unmodified `compile_reroute` (Step 1's "do not duplicate
existing functionality") -- `RATE_LIMIT` is the background flow's action,
`REROUTE` is still the primary intent's.

## Verification plan

Once `testbed/topology/diamond.py` has h2/h3 attached (see the topology
module's own docstring for the exact attachment points and why), this
mechanism is verified the same way every other deployment in this project
is: `ovs-vsctl list qos` / `ovs-vsctl list queue` on the live switch after
deployment (not just a successful HTTP-equivalent call), a real `iperf3`
run for h2->h3 confirming its achieved throughput is actually capped near
the configured rate (not just "configured", per the brief's repeated
"never conflate configured with achieved" instruction), and a real
`iperf3` run for h1->h4 under that real background load.
