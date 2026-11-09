# ADR-002: Topology source and deployment mechanism for the decision/compiler/deployment pipeline

## Context

Sections 13-14 of the brief require the decision layer to reason over
"actual topology/network-state information" and the compiler to generate
Ryu/OpenFlow configuration "dynamically" from source/destination/path/
topology, not a hardcoded table. Two implementation questions had to be
resolved before any of that could be built: where does the topology graph
(which switch ports connect to which neighbor, which port each host sits
behind) come from, and how does compiled configuration actually reach Ryu.

## Deployment mechanism: Ryu's `ryu.app.ofctl_rest`

Rather than writing a bespoke Ryu controller app with a custom control
channel back to the Python backend, this project uses Ryu's own bundled
`ofctl_rest` app, which exposes flow-table read/write as plain HTTP+JSON
(`POST /stats/flowentry/add`, `POST /stats/flowentry/delete`,
`GET /stats/flow/<dpid>`). This was verified working end-to-end in this
environment's patched Ryu 4.34 (see ADR-001): `ryu-manager
ryu.app.ofctl_rest --wsapi-port 8080` starts, and `GET /stats/switches`
returns a real (empty, no switches attached yet) `200 application/json`
response.

This keeps the "compiler" honest to the brief: `backend/compiler/reroute.py`
produces exactly the JSON body `ofctl_rest` accepts (`dpid`, `priority`,
`match`, `actions`), so the compiler's output *is* the literal deployable
configuration, not an abstraction one step removed from it. The
`backend/deployment/` layer is a thin HTTP client plus the verification
step the brief explicitly asks for (Step 6): after POSTing a flow, it
reads the flow table back with `GET /stats/flow/<dpid>` and confirms the
installed rule has the requested match, priority, and ordered actions
(including `SET_QUEUE` for rate-limited rules), rather than trusting that
the POST returning 200 means anything actually landed in the switch.

## Topology source: the live Mininet object, not LLDP-based discovery

Ryu ships `ryu.app.rest_topology` (built on `ryu.topology.switches`),
which discovers switches and inter-switch links dynamically via LLDP and
exposes them over REST (`/v1.0/topology/switches`, `/v1.0/topology/links`).
This was tried first, as the more "real" option matching "network-aware
decision" in spirit -- discovered links rather than an assumed graph.

It was tested against the actual diamond topology (`ryu-manager
ryu.app.ofctl_rest ryu.app.rest_topology --observe-links`): all four
switches connected to the controller and Ryu installed the LLDP-handling
flow into each of them (confirmed in `ovs-vswitchd.log`: `1 flow_mods ...
(1 adds)` for every switch), but `/v1.0/topology/switches` and
`/v1.0/topology/links` kept returning `[]` well after the switches had
connected, with no exception anywhere in Ryu's log. This looks like an
internal event round-trip issue between `ryu.app.rest_topology`'s
`get_switch()`/`get_link()` calls and the `Switches` app's registry,
possibly interacting with the eventlet-related patches ADR-001 already
had to apply -- not something worth an open-ended debugging session for a
capability this project can get more simply and just as validly another
way.

**Resolution**: `backend/decision/topology_graph.py` builds its graph
directly from the live `mininet.net.Mininet` object -- the same process
that constructed the topology already holds exact dpids, host IPs/MACs,
and (crucially) the real OVS port number for every link end, via each
switch's `.ports` mapping. This is not a step backward to "assumed"
topology: it is still the actual, currently-running network's state, read
from the one place in this project that is guaranteed to have it exactly
right (the code that built the network), rather than re-discovering
through a second, independently-verified-but-currently-unreliable channel
what this process already knows for certain.

**Trade-off being made explicitly**: this ties the decision layer to
being invoked from the same orchestrating process that built the Mininet
network (see `backend/cli.py`), rather than as a standalone service that
could attach to an arbitrary already-running network. For this project's
scope (one controlled testbed, one orchestrating script per experiment
run, per the brief's own repository layout and phase plan) that is the
right amount of engineering, not a shortcut around a requirement. If a
later phase needs the decision layer to run detached from topology
construction, `ryu.app.rest_topology` is the documented path back to
LLDP-based discovery -- the flaky part observed was the REST query layer
around it, not OpenFlow/LLDP itself, so it is worth retrying rather than
rebuilding differently.
