"""Phase 2 unit tests: pure parsing logic, no network/mininet required.
Fixtures were captured from real `ping`/`iperf3` runs in this environment
(see tests/fixtures/), not hand-written, so the parser is exercised
against real tool output shapes."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.measurement.latency import measure_latency, parse_ping_output
from backend.measurement.throughput import parse_iperf3_json
from backend.models.measurement import LatencyResult

FIXTURES = Path(__file__).parent / "fixtures"

REAL_PING_OUTPUT = """PING 127.0.0.1 (127.0.0.1) 56(84) bytes of data.
64 bytes from 127.0.0.1: icmp_seq=1 ttl=64 time=0.029 ms
64 bytes from 127.0.0.1: icmp_seq=2 ttl=64 time=0.033 ms
64 bytes from 127.0.0.1: icmp_seq=3 ttl=64 time=0.033 ms

--- 127.0.0.1 ping statistics ---
3 packets transmitted, 3 received, 0% packet loss, time 2036ms
rtt min/avg/max/mdev = 0.029/0.031/0.033/0.002 ms
"""

REAL_PING_OUTPUT_WITH_LOSS = """PING 10.0.0.4 (10.0.0.4) 56(84) bytes of data.
From 10.0.0.1 icmp_seq=1 Destination Host Unreachable
From 10.0.0.1 icmp_seq=2 Destination Host Unreachable

--- 10.0.0.4 ping statistics ---
5 packets transmitted, 0 received, +2 errors, 100% packet loss, time 4092ms
pipe 2
"""


def test_parse_ping_success():
    result = parse_ping_output(REAL_PING_OUTPUT)
    assert result.packets_sent == 3
    assert result.packets_received == 3
    assert result.packet_loss_pct == 0.0
    assert result.rtt_avg_ms == 0.031
    assert result.reachable


def test_parse_ping_total_loss():
    result = parse_ping_output(REAL_PING_OUTPUT_WITH_LOSS)
    assert result.packets_sent == 5
    assert result.packets_received == 0
    assert result.packet_loss_pct == 100.0
    assert result.rtt_avg_ms is None
    assert not result.reachable


def test_parse_ping_garbage_input():
    result = parse_ping_output("command not found: ping")
    assert result.packets_sent == 0
    assert result.packet_loss_pct == 100.0
    assert not result.reachable
    assert not result.measurement_succeeded


def test_packet_loss_measurement_succeeds_only_with_consistent_nonzero_counts():
    complete = parse_ping_output(REAL_PING_OUTPUT, packets_requested=3)
    complete_loss = parse_ping_output(
        REAL_PING_OUTPUT_WITH_LOSS,
        packets_requested=5,
    )
    assert complete.packets_requested == 3
    assert complete.measurement_succeeded
    assert complete_loss.measurement_succeeded


@pytest.mark.parametrize(
    "field",
    ["packets_sent", "packets_received", "packet_loss_pct"],
)
def test_latency_result_rejects_boolean_packet_loss_fields(field):
    payload = {
        "packets_sent": 5,
        "packets_received": 4,
        "packet_loss_pct": 20,
        "packets_requested": 5,
        "raw_output": "synthetic",
    }
    payload[field] = True

    with pytest.raises(ValidationError):
        LatencyResult(**payload)

    with pytest.raises(ValidationError):
        LatencyResult.model_validate_json(json.dumps(payload))


def test_latency_result_accepts_integer_counts_and_finite_numeric_percentage():
    result = LatencyResult(
        packets_sent=5,
        packets_received=4,
        packet_loss_pct=20,
        packets_requested=5,
        raw_output="synthetic",
    )

    restored = LatencyResult.model_validate_json(result.model_dump_json())
    assert restored == result
    assert restored.measurement_succeeded


def test_requested_packet_count_rejects_incomplete_ping_summaries():
    one_of_five = REAL_PING_OUTPUT.replace(
        "3 packets transmitted, 3 received, 0% packet loss",
        "1 packets transmitted, 1 received, 0% packet loss",
    )
    incomplete = parse_ping_output(one_of_five, packets_requested=5)
    assert incomplete.packets_sent == 1
    assert incomplete.packets_requested == 5
    assert not incomplete.measurement_succeeded

    zero_of_five = parse_ping_output(
        "command failed",
        packets_requested=5,
    )
    assert zero_of_five.packets_sent == 0
    assert not zero_of_five.measurement_succeeded


def test_measure_latency_binds_requested_count_to_parsed_result():
    class HostStub:
        def cmd(self, command):
            assert "ping -c 5 " in command
            return REAL_PING_OUTPUT.replace(
                "3 packets transmitted, 3 received, 0% packet loss",
                "1 packets transmitted, 1 received, 0% packet loss",
            )

    result = measure_latency(HostStub(), "10.0.0.4", count=5)

    assert result.packets_requested == 5
    assert not result.measurement_succeeded


def test_completed_and_incomplete_total_loss_are_distinguished():
    complete = parse_ping_output(
        REAL_PING_OUTPUT_WITH_LOSS,
        packets_requested=5,
    )
    incomplete = parse_ping_output(
        REAL_PING_OUTPUT_WITH_LOSS.replace(
            "5 packets transmitted, 0 received",
            "1 packets transmitted, 0 received",
        ),
        packets_requested=5,
    )

    assert complete.packet_loss_pct == 100
    assert complete.measurement_succeeded
    assert incomplete.packet_loss_pct == 100
    assert not incomplete.measurement_succeeded


def test_parse_iperf3_real_fixture():
    raw = (FIXTURES / "sample_iperf3_success.json").read_text()
    result = parse_iperf3_json(raw)
    assert result.succeeded
    assert result.sent_mbps is not None
    assert result.received_mbps is not None
    assert result.achieved_mbps == result.received_mbps


def test_parse_iperf3_error_shape():
    raw = json.dumps({"error": "unable to connect to server"})
    result = parse_iperf3_json(raw)
    assert not result.succeeded
    assert "unable to connect" in result.error


def test_parse_iperf3_garbage():
    result = parse_iperf3_json("not json at all")
    assert not result.succeeded
    assert result.error is not None
