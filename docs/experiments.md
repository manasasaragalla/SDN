#!/usr/bin/env bash
# Installs the system-level networking stack this project needs: Mininet,
# Open vSwitch, iproute2, iperf3. Must run as root (the whole testbed needs
# CAP_NET_ADMIN for network namespaces/veth pairs).
#
# See docs/adr-001-environment-constraints.md for why OVS is started in
# userspace/netdev datapath mode here, and why link delay is created via
# topology structure rather than tc netem.
#
# Python environment:
# - Main project dependencies use system Python so Mininet's apt-installed
#   Python API remains accessible.
# - Ryu runs in its own isolated environment: .venv-ryu.

set -euo pipefail

echo "==> apt-get update"
DEBIAN_FRONTEND=noninteractive apt-get update -qq

echo "==> Installing networking dependencies"

DEBIAN_FRONTEND=noninteractive apt-get install -y \
    iproute2 mininet openvswitch-switch openvswitch-testcontroller \
    iperf3 net-tools iputils-ping ethtool tcpdump

echo "==> Starting Open vSwitch (ovsdb-server + ovs-vswitchd)"
/usr/share/openvswitch/scripts/ovs-ctl start || true

echo "==> Verifying Open vSwitch"
ovs-vsctl show

echo "==> System networking setup completed successfully"

echo ""
echo "Next steps:"
echo "  1. Install Ryu: bash scripts/setup_ryu_venv.sh"
echo "  2. Install main dependencies:"
echo "     sudo python3 -m pip install --break-system-packages --require-hashes --only-binary=:all: -r requirements.txt"
echo ""
echo "Note: Do not create a separate virtual environment for the main project."
echo "Ryu uses its own isolated environment at .venv-ryu."