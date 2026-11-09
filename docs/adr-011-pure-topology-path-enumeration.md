# ADR-011: Pure topology path enumeration

## Context

Phase 3A defines descriptive planning contracts but does not enumerate
topology paths. `TopologyGraph` stores hosts with one switch attachment and
switch-to-switch links in a list. Existing graph helpers return switch-name
sequences and select the first link between two switch names, which cannot
identify which physical link was used when parallel links exist. Those helpers
are used by legacy components and remain unchanged.

## Decision

Add a pure bounded enumerator under `backend/planner/`. It validates the
entire supplied topology and rejects malformed records rather than repairing
them. Host dictionary keys must match `Host.name`; host attachments and switch
links must reference declared switches and use positive switch ports. Each
physical switch port has exactly one owner across both attachment and link
endpoints. Self-links, duplicate physical links, and reversed duplicates are
invalid.

A switch-link identity is the lexicographically sorted pair of
`(switch_name, endpoint_port)` pairs. Reversing a link produces the same
identity. Interface names and bandwidth are metadata, not identity; parallel
links with distinct endpoint ports remain distinct.

Each result path contains ordered nodes and one ordered physical connection
per node transition. Host-attachment connections carry the known switch-side
port; the host-side port is absent from the topology model and remains
unspecified. Switch-link connections carry canonical identity, endpoint
ports, and traversal orientation. Path contracts require host attachments at
the first and last transitions and switch links at every intermediate
transition; same-switch host paths therefore contain two host attachments and
no switch links.

Enumeration uses deterministic DFS over a locally built multigraph index.
Adjacency is sorted by neighbor name and canonical link identity. Switches
cannot repeat within a path. Hosts on the same switch produce the direct
host-switch-host path. Results are not ranked, and enumeration order does not
represent a preference.

`candidate_limit` must be a positive integer; booleans are rejected. The
enumerator returns at most K paths and searches until exhaustion or a valid
K+1th path is found. `truncated` is true only when that additional path is
found. Exhaustion at exactly K paths is not truncated. The limit bounds
returned output, not worst-case search time; no separate search-budget
framework is introduced.

## Phase boundary

The enumerator performs no measurement, constraint evaluation, optimization,
OpenFlow compilation, Mininet/Ryu operation, deployment, OVS changes, or CLI
integration. It does not change `TopologyGraph` or its existing helpers and
does not construct or modify a `Plan`. Its paths remain structurally valid
candidates only; metric satisfaction is not inferred.

## Consequences

Parallel physical links remain distinguishable for later planning and
execution. Malformed topology is fail-closed, including conflicting switch
port ownership anywhere in the supplied graph. Disconnected but valid hosts
return an empty, complete result. Unknown hosts and malformed topology raise
distinct explicit errors.

DFS is suitable for the project's bounded candidate output and low-memory
streaming behavior, but simple-path search remains exponential in the worst
case. `candidate_limit` bounds output, not the effort required to exhaust a
large disconnected search space.
