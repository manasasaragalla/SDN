# ADR-009: Static metric capability catalogue and pure resolution

## Context

The canonical intent model describes requirements but does not establish that
the project can measure, plan, or execute them. The existing latency and
bandwidth pipelines are real, metric-specific legacy paths; the generalized
policy engine and action orchestration are not implemented. Packet loss is
present in ping results, but no packet-loss constraint planner or enforcement
exists.

## Decision

Add a small static metric-definition table in
`backend/models/metric_definitions.py`. It is the shared source for known
metric identifiers, canonical units, value domains, and unit semantics.
Canonical unit labels are required exactly; no conversion is performed.

Add `backend/capabilities.py` as a pure resolver with independent recognized,
validated, measurable, plannable, and executable assessments. Unknown metrics
and actions fail closed. Packet loss is reported measurable but not plannable
or executable. Latency and bandwidth remain conditionally available through
their exact existing legacy intent shapes; that compatibility does not assert
generalized execution support. Requested actions are assessed separately from
internal mechanisms. REROUTE and RATE_LIMIT remain conditional on their current
scope and orchestration limits.

If a topology graph is provided, resolution validates endpoint presence,
distinct IPv4 endpoint addresses, and path existence. Bandwidth lower targets
use known static link capacities only to identify proven infeasibility; absent
capacity metadata is reported as conditional/unknown, never as measured
throughput. RATE_LIMIT compares its positive finite requested rate against
known first switch-to-switch egress capacity, using the existing pure rate
validator; missing capacity remains conditional and rates above every known
candidate egress are rejected. Unsupported selectors are rejected because
current compilers do not compile them.

Node-only topology paths do not identify a physical parallel link.
`TopologyGraph.path_capacity_mbps()` therefore returns unknown when any hop
has multiple physical links, rather than using the first link in list order.
The capability resolver uses the explicitly named maximum-possible capacity
only as an existential upper bound: it can prove that some physical
realization may meet a bandwidth lower bound, or that all known realizations
cannot; it does not assign that capacity to every candidate. Exact candidate
capacity is computed only from a Phase 3B `EnumeratedPath` with physical link
identity. Missing or invalid capacity metadata remains unknown. Boolean
`bw_mbps` values are rejected during `Link` validation rather than being
coerced to numeric capacities.

The resolver performs no network, deployment, or measurement operations and is
not wired into the CLI in this phase.

`CAPABILITY_READY` means only that the supplied capability checks passed. It
does not mean execution was dispatched, deployment succeeded, or measured
network behavior satisfied the request. Resolution results explicitly report
`NOT_DISPATCHED`, `NOT_ATTEMPTED`, and `NOT_VERIFIED` for those separate
execution, deployment, and satisfaction states.

## Consequences

Capability claims are explicit and independently testable. New metrics need
an intentional metric definition and capability record; adding a name alone
cannot make it executable. The current legacy pipelines remain unchanged.
Generalized policy planning, action orchestration, and CLI integration require
separate implementation and approval.
