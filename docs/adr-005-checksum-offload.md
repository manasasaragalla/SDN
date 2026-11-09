# ADR-005: TCP fails through this environment's OVS netdev datapath unless veth checksum/segmentation offload is disabled

## Context

Implementing MIN_BANDWIDTH (Phase 11) was the first time this project
actually exercised TCP (`iperf3`) end to end against the real testbed --
every prior demonstration (MINIMIZE_LATENCY) only used `ping` (ICMP). The
very first bandwidth CLI run failed: one candidate path was correctly
rejected by the new pre-deployment feasibility check (as designed), but
the other -- topologically valid, and reachable by `ping` -- reported its
`iperf3` measurement as "unreachable".

## Root cause (independently reproduced, twice, outside this project's own code)

1. `curl`/`socket.create_connection()`-based plain TCP connect attempts
   between two Mininet hosts failed with `No route to host` or connection
   timeouts, while `ping` between the same two hosts succeeded at 100%
   (`net.pingAll()`).
2. `tcpdump` on both the sending and receiving host's veth interface
   during a failed connect captured **zero packets on either side** --
   the SYN never left the sending interface at all.
3. To rule out anything specific to this project's topology, controller,
   or compiler/deployment code, the same failure was reproduced with a
   **bare OVS bridge built directly with `ovs-vsctl`, entirely outside
   Mininet and outside this project's code**: two Linux network
   namespaces connected only by a `datapath_type=netdev` OVS bridge.
   `ping` between the namespaces succeeded; a raw Python
   `socket.create_connection()` timed out.
4. Disabling checksum and segmentation offload (`ethtool -K <intf> tx off
   rx off tso off gso off gro off sg off`) on the two namespaces' veth
   interfaces in that same bare-bridge reproduction made the TCP connect
   succeed immediately.

This is a known category of issue with Linux veth pairs and *software*
(non-hardware) forwarding: a veth's default `tx-checksumming: on` means
the kernel does not compute a real TCP/IP checksum before handing the
packet off -- it marks the packet `CHECKSUM_PARTIAL` and defers the actual
computation to whatever's "downstream" (normally real NIC hardware, which
does the math without any additional kernel involvement). OVS's `netdev`
(userspace) datapath, which is what this project already knows it has to
use for OpenFlow itself (`ADR-001` Deviation 3, no kernel module support),
just forwards the raw bytes between veth ends in software -- there is no
hardware to finish the checksum. The receiving TCP stack then verifies a
checksum that was never actually computed, and silently drops the packet.
ICMP is unaffected because `ping`'s checksum is computed by `ping` itself
in userspace regardless of any NIC offload setting.

## Resolution

`testbed/topology/diamond.py`'s `start()` now calls a new
`_disable_checksum_offload()` step immediately after the switches connect
to the controller: for every host's non-loopback interface, it runs
`ethtool -K <intf> tx off rx off tso off gso off gro off sg off`. This
applies uniformly to both objectives (harmless for the already-working
`ping`-based latency pipeline) and needs no change to any compiler,
validator, decision, or deployment code -- it is a topology/environment
setup step, in the same place the topology module already documents its
other environment-specific adjustments.

`scripts/setup_system.sh` now also installs `ethtool` (needed to run this
fix) and `tcpdump` (used to diagnose this, kept for any future debugging
of this kind).

## Verification

Re-running the exact same bare-OVS-bridge reproduction from item 3 above,
with the `ethtool -K` commands from item 4 applied to both namespaces'
veth interfaces, produces a real, successful `socket.create_connection()`
(`OK` printed by the client, no exception) where it previously timed out.
The full MIN_BANDWIDTH CLI run afterwards (see `docs/experiments.md`)
completes real, non-fabricated `iperf3` measurements on both candidate
paths.
