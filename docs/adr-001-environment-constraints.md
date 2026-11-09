# ADR-001: Testbed environment and two deviations from the original design

## Context

The development and execution environment for this project is a sandboxed Linux
container (kernel `6.18.44-fc-v37`, no loadable kernel module support, root
inside the container). The user's own machine is Windows, which cannot host
Mininet/Open vSwitch/Ryu natively, so the container is the only place the
testbed can run; code is mirrored to the user's machine for storage and
version control but is not executed there.

Two aspects of the brief could not be implemented as originally specified,
for concrete, verified technical reasons. Both are documented here rather
than silently worked around.

## Deviation 1: Ryu's packaged dependencies do not install on a current
Python/setuptools toolchain

`pip install ryu` fails outright: Ryu's `setup.py` calls
`ryu.hooks.save_orig()`, which reads `setuptools.command.easy_install.get_script_args`,
an attribute removed from setuptools years ago. With build isolation
disabled and an older setuptools pinned, pip additionally backtracks all
the way to `ryu==2.2`, a Python-2-only release (invalid Python 3 syntax) --
not usable.

Once installing the real, current release (`ryu==4.34`) from source with
the hook patched (see below), two further breaks appear, both from Ryu
being unmaintained since ~2021 while its dependencies kept moving:

- `from oslo.config import cfg` fails because modern `oslo.config` /
  `oslo.i18n` distribute as flat `oslo_config` / `oslo_i18n` modules, not
  the legacy `oslo.*` namespace package Ryu's code imports.
- `ryu/app/wsgi.py` imports `eventlet.wsgi.ALREADY_HANDLED`, a sentinel
  recent eventlet releases dropped.

**Resolution**: Ryu is installed in its own virtualenv (`.venv-ryu/`),
isolated from the rest of the project's dependencies, with three small,
documented compatibility shims applied on top of the unmodified upstream
4.34 source:

1. `ryu/hooks.py` patched so `save_orig()`/`setup_hook()` degrade to a
   no-op when `easy_install.get_script_args` doesn't exist, instead of
   raising at `setup.py` import time. This only affects how the
   `ryu-manager` console script is generated at install time; it has no
   effect on the controller's runtime behavior.
2. A compatibility package `oslo/config/__init__.py` (one line:
   `from oslo_config import cfg`) is added to the venv's `site-packages`
   so `from oslo.config import cfg` keeps working against the current
   `oslo.config` distribution.
3. `ryu/app/wsgi.py`'s `_AlreadyHandledResponse` falls back to a local
   sentinel object when `eventlet.wsgi.ALREADY_HANDLED` is unavailable.
   This only affects one edge case in Ryu's optional REST/WSGI app
   framework (in-place "already handled" websocket responses); it does
   not touch OpenFlow control-plane logic, which is what this project
   uses Ryu for.

Verified: `ryu-manager` starts, binds the OpenFlow listener, and a real
Mininet/OVS switch connects to it and forwards traffic under its control
(see the Phase 1 smoke test).

The setup script that installs and patches Ryu lives at
`scripts/setup_ryu_venv.sh` (Phase 1) and is idempotent; re-running it
re-applies the patches to a fresh venv rather than assuming a pip package
will ever install cleanly for this Ryu release. Run it as an unprivileged
user with write access only to the Ryu virtual environment. Its Python
dependencies are exact-version and SHA-256 locked in
`scripts/ryu-requirements.txt`; the Ryu source archive is checked against the
reviewed digest in `scripts/ryu-4.34.sha256`, and its temporary verification
controller binds both OpenFlow and REST listeners to loopback.

## Deviation 2: no `NET_SCH_NETEM` in this kernel -- link delay cannot be
injected with Linux `tc`

Mininet's `TCLink` (the standard way to give links distinct bandwidth and
latency characteristics, called for in the brief's testbed design) shapes
traffic with the kernel's `tc` queueing disciplines: `htb`/`tbf` for
bandwidth, `netem` for delay/jitter/loss.

This kernel has no loadable modules at all (`Kernel has no loadable module
support`), so every `tc` queueing discipline has to be compiled directly
into the kernel image. Checking `/proc/config.gz` confirms `htb` and `tbf`
are built in (`CONFIG_NET_SCH_HTB=y`, `CONFIG_NET_SCH_TBF=y`), but `netem`
is not (`# CONFIG_NET_SCH_NETEM is not set`). This was verified directly:
`tc qdisc add ... htb` and `... tbf` succeed; `tc qdisc add ... netem
delay 5ms` fails with "Specified qdisc kind is unknown", and so does any
Mininet link that combines a `bw=` and `delay=` argument together (Mininet
issues them as one combined `tc` command, so the `netem` failure takes the
bandwidth shaping down with it too).

**Resolution**: bandwidth differentiation between paths still uses
`TCLink(bw=...)` exactly as specified (verified working, htb-only).
Latency differentiation between paths uses **topology structure**
(hop count and switch placement) instead of injected delay: the
low-latency path is the physically shorter path through fewer
software-forwarding hops, and the high-latency path is longer. Because
every hop in this testbed is a real userspace-OVS forwarding step (see
Deviation 3 below) with genuine, non-zero processing latency, the
resulting RTT difference between paths is real and independently
measurable with `ping` -- it is not simulated or hard-coded. This keeps
faith with the brief's requirement (section 19) to "use actual
measurements rather than only theoretical path length": the measurement
is still real, only the mechanism used to make the paths differ is
structural rather than an artificial delay knob.

If a later stage of the project needs more pronounced or more precisely
controllable latency differences than hop count alone provides, the
fallback is application-level delay (a small proxy/shim on the path)
rather than `tc`, since the kernel-level route is closed in this
environment.

## Deviation 3 (informational, not a functional gap): OVS runs in
userspace/`netdev` datapath mode, not the kernel datapath

`ovs-vswitchd`'s default "system" datapath requires the `openvswitch.ko`
kernel module, unavailable here for the same no-loadable-modules reason.
OVS bridges created with the default datapath fail outright ("failed to
enumerate system datapaths"). Every switch in this project is created
with Mininet's `datapath='user'` option, which tells OVS to use its
software (`netdev`) datapath instead -- verified with a full `pingall`
across a real Mininet/OVS/Ryu topology (0% loss). Functionally this is a
complete substitute for our purposes: the same OpenFlow protocol, the
same flow tables, the same controller API. The only real difference is
performance (software forwarding is slower than the kernel datapath),
which does not affect correctness of anything this project measures or
demonstrates, only the absolute throughput ceiling available for the
bandwidth objective's iperf3 tests.
