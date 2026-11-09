"""The project's testbed topology (brief section 16): h1 and h4 connected
through two switch-disjoint paths with different characteristics.

    h1 --- s1 --- s2 ------- s4 --- h4      (path A: 2 switch hops, low bandwidth)
            \\--- s3 --- s5 --/             (path B: 3 switch hops, high bandwidth)

Bandwidth differentiation uses Mininet's TCLink (bw=), which works
(verified) via the kernel's htb/tbf queueing disciplines. Latency
differentiation does NOT use tc netem -- this kernel has no NET_SCH_NETEM
built in and no loadable module support to add it (see
docs/adr-001-environment-constraints.md, Deviation 2). Path B has a
genuinely, structurally different hop count from path A (3 inter-switch
hops through s3+s5, vs. 2 through s2) -- an earlier version of this
topology gave both paths the same hop count (s1-s2-s4 vs s1-s3-s4), which
made the two paths' measured latency indistinguishable from software-
forwarding noise; the extra switch (s5) fixes that. The actual latency
difference the system measures still comes from real ping RTT over real
per-hop userspace-OVS forwarding, never an injected/simulated value --
only the topology's shape (not a delay parameter) is what's engineered
here.

Both paths exist simultaneously in this topology (as the brief requires:
"multiple possible paths"), which means an L2-flooding controller app
(like ryu.app.simple_switch_13) would create a forwarding loop the moment
traffic flows -- there is no spanning-tree app running here. This is
intentional: which single path actually carries traffic at any moment is
the decision layer + compiler's job (Phase 5/6), installing specific
non-flooding flow rules, not something this topology module or a generic
learning switch should paper over.

Phase 11 (MIN_BANDWIDTH) adds two background-traffic hosts, h2 and h3,
attached directly to s2 and s4 -- the two switches at either end of the
s2-s4 link, which is one of Path A's two hops (the other being s1-s2).
A real h2->h3 flow, once routed with its own explicit flow rules (the
same generic compile_reroute this module's docstring already describes,
just called again for a different host pair), travels over exactly that
s2-s4 link and so genuinely contends for its 10 Mbps capacity with any
h1->h4 traffic that is, at that moment, using Path A. This is a minimal
change (two hosts, two host-links, zero new switches, zero change to the
existing five inter-switch links) that turns "does h1->h4 get N Mbps"
from a question the network can trivially always answer yes to (nothing
else is using it) into one that can genuinely fail under real, measured
contention -- see docs/adr-004-bandwidth-mechanism.md for how that
background flow's own rate is capped (via OVS QoS, not by just trusting
its configured cap).
"""
from __future__ import annotations

from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController


# Link bandwidths (Mbps). Kept apart enough that iperf3 measurements can
# clearly distinguish "on path A" from "on path B" even with software-OVS
# overhead.
PATH_A_BW_MBPS = 10.0  # s1-s2, s2-s4
PATH_B_BW_MBPS = 50.0  # s1-s3, s3-s4


def build_diamond_topology(controller_ip: str = "127.0.0.1", controller_port: int = 6653) -> Mininet:
    net = Mininet(controller=RemoteController, switch=OVSSwitch, link=TCLink, autoSetMacs=True)
    net.addController("c0", controller=RemoteController, ip=controller_ip, port=controller_port)

    # protocols="OpenFlow13" pinned explicitly: ofctl_rest's match syntax
    # (eth_type, ipv4_src, arp_spa, ...) is OXM/OF1.2+ terminology, and
    # Mininet's OVSSwitch defaults to leaving the bridge's protocol list
    # unset, which is worth removing all doubt about rather than relying
    # on OVS/Ryu's mutual version negotiation to land on 1.3 by luck.
    s1 = net.addSwitch("s1", datapath="user", protocols="OpenFlow13", dpid="0000000000000001")
    s2 = net.addSwitch("s2", datapath="user", protocols="OpenFlow13", dpid="0000000000000002")
    s3 = net.addSwitch("s3", datapath="user", protocols="OpenFlow13", dpid="0000000000000003")
    s4 = net.addSwitch("s4", datapath="user", protocols="OpenFlow13", dpid="0000000000000004")
    s5 = net.addSwitch("s5", datapath="user", protocols="OpenFlow13", dpid="0000000000000005")

    h1 = net.addHost("h1", ip="10.0.0.1/24")
    h4 = net.addHost("h4", ip="10.0.0.4/24")
    # Background/competing-traffic hosts (Phase 11) -- see module docstring.
    h2 = net.addHost("h2", ip="10.0.0.2/24")
    h3 = net.addHost("h3", ip="10.0.0.3/24")

    net.addLink(h1, s1)
    net.addLink(s4, h4)
    net.addLink(h2, s2)
    net.addLink(h3, s4)

    # Path A: 2 switch hops (s1-s2-s4), lower bandwidth.
    net.addLink(s1, s2, bw=PATH_A_BW_MBPS)
    net.addLink(s2, s4, bw=PATH_A_BW_MBPS)

    # Path B: 3 switch hops (s1-s3-s5-s4) -- structurally longer, so its
    # real forwarding latency is expected (and, per the module docstring,
    # verified) to be higher, not just noisier -- higher bandwidth.
    net.addLink(s1, s3, bw=PATH_B_BW_MBPS)
    net.addLink(s3, s5, bw=PATH_B_BW_MBPS)
    net.addLink(s5, s4, bw=PATH_B_BW_MBPS)

    return net


def _disable_checksum_offload(net: Mininet) -> None:
    """Works around a real environment limitation found while building the
    MIN_BANDWIDTH objective (Phase 11): with checksum/segmentation offload
    left at its Linux veth default (on), TCP connections through this
    kernel's OVS *netdev* (userspace) datapath fail outright -- `ping`
    (ICMP) succeeds, but a TCP SYN never completes a handshake (confirmed
    with tcpdump: the SYN never leaves the sending veth at all once
    offload is enabled, and reproduced with a bare OVS bridge entirely
    outside Mininet, so this is not specific to this project's topology or
    controller). Disabling tx/rx checksum and all segmentation offload
    (tso/gso/gro/sg) on every host-facing veth interface fixes it --
    verified with a raw cross-namespace `socket.create_connection()"""
    for host in net.hosts:
        for intf_name in host.intfNames():
            if intf_name == "lo":
                continue
            host.cmd(f"ethtool -K {intf_name} tx off rx off tso off gso off gro off sg off")


def start(net: Mininet) -> None:
    net.build()
    net.get("c0").start()
    for switch_name in ("s1", "s2", "s3", "s4", "s5"):
        net.get(switch_name).start([net.get("c0")])
    _disable_checksum_offload(net)


if __name__ == "__main__":
    # Structural smoke test only: confirms every switch connects to the
    # controller. Does not run pingall/traffic -- see the module docstring
    # for why that would loop without Phase 5/6's path-selecting flows.
    setLogLevel("info")
    import time

    net = build_diamond_topology()
    start(net)
    try:
        time.sleep(2)  # give switches time to complete the OpenFlow handshake
        for switch_name in ("s1", "s2", "s3", "s4", "s5"):
            sw = net.get(switch_name)
            out = sw.cmd(f"ovs-vsctl get bridge {switch_name} name")
            print(f"{switch_name}: bridge present = {switch_name in out}")
        print("=== controller connections ===")
        print(net.get("s1").cmd("ovs-vsctl list Controller"))
    finally:
        net.stop()
