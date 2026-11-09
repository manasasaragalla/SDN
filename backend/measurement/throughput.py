"""Throughput measurement via `iperf3`, using JSON output (-J) so parsing
doesn't depend on iperf3's human-readable table formatting."""
from __future__ import annotations

import json
import time

from backend.models.measurement import ThroughputResult

BITS_PER_MBIT = 1_000_000


def parse_iperf3_json(raw: str) -> ThroughputResult:
    """Parse the output of `iperf3 -c ... -J`."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return ThroughputResult(succeeded=False, error="could not parse iperf3 JSON output", raw_output=raw)

    if "error" in data:
        return ThroughputResult(succeeded=False, error=data["error"], raw_output=raw)

    try:
        end = data["end"]
        sent = end["sum_sent"]
        received = end["sum_received"]
    except KeyError as exc:
        return ThroughputResult(
            succeeded=False, error=f"unexpected iperf3 JSON shape, missing {exc}", raw_output=raw
        )

    return ThroughputResult(
        sent_mbps=sent["bits_per_second"] / BITS_PER_MBIT,
        received_mbps=received["bits_per_second"] / BITS_PER_MBIT,
        retransmits=sent.get("retransmits"),
        duration_s=sent.get("seconds"),
        succeeded=True,
        raw_output=raw,
    )


def measure_throughput(
    client_host,
    server_host,
    dst_ip: str,
    duration_s: int = 5,
    port: int = 5201,
    server_startup_wait_s: float = 1.0,
) -> ThroughputResult:
    """Run an iperf3 server on server_host and a client on client_host,
    duck-typed against mininet.node.Host (anything with .cmd(str) -> str).

    The server is started with `-1` (exit after one client) so it doesn't
    linger as a background process needing separate cleanup.
    """
    server_host.cmd(f"iperf3 -s -1 -p {port} > /tmp/iperf3_server_{port}.log 2>&1 &")
    time.sleep(server_startup_wait_s)
    raw = client_host.cmd(
        f"timeout {duration_s + 10} iperf3 -c {dst_ip} -p {port} -t {duration_s} -J"
    )
    return parse_iperf3_json(raw)
