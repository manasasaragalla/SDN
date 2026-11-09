"""Latency measurement via `ping`. Parsing is pure and unit-testable
separately from actually running ping against a live host."""
from __future__ import annotations

import re

from backend.models.measurement import LatencyResult

_SUMMARY_RE = re.compile(
    r"(?P<sent>\d+) packets transmitted, (?P<received>\d+)(?: packets)? received,"
    r"(?:\s*\+\d+ errors,)? (?P<loss>[\d.]+)% packet loss"
)
_RTT_RE = re.compile(
    r"rtt min/avg/max/mdev = "
    r"(?P<min>[\d.]+)/(?P<avg>[\d.]+)/(?P<max>[\d.]+)/(?P<mdev>[\d.]+) ms"
)


def parse_ping_output(
    output: str,
    *,
    packets_requested: int | None = None,
) -> LatencyResult:
    """Parse the text output of `ping -c N <dst>` (iputils-ping format)."""
    summary = _SUMMARY_RE.search(output)
    if not summary:
        # No summary line at all means ping itself failed to run (bad
        # interface, unresolvable host, etc.) rather than "0% received".
        return LatencyResult(
            packets_sent=0,
            packets_received=0,
            packet_loss_pct=100.0,
            packets_requested=packets_requested,
            raw_output=output,
        )

    rtt = _RTT_RE.search(output)
    return LatencyResult(
        packets_sent=int(summary.group("sent")),
        packets_received=int(summary.group("received")),
        packet_loss_pct=float(summary.group("loss")),
        packets_requested=packets_requested,
        rtt_min_ms=float(rtt.group("min")) if rtt else None,
        rtt_avg_ms=float(rtt.group("avg")) if rtt else None,
        rtt_max_ms=float(rtt.group("max")) if rtt else None,
        rtt_mdev_ms=float(rtt.group("mdev")) if rtt else None,
        raw_output=output,
    )


def measure_latency(host, dst_ip: str, count: int = 5, timeout_s: int = 10) -> LatencyResult:
    """Run ping from a Mininet host object to dst_ip and parse the result.

    `host` is a mininet.node.Host (or anything exposing .cmd(str) -> str);
    kept duck-typed so this function can be unit-tested with a stub without
    importing mininet.
    """
    output = host.cmd(f"timeout {timeout_s} ping -c {count} {dst_ip}")
    return parse_ping_output(output, packets_requested=count)
