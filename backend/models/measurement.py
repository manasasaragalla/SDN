"""Measurement result models. These carry only measured values -- never a
value the system assumed or configured (section 18: "do NOT assume
configured == achieved"; section 26: "do not invent results")."""
from __future__ import annotations

import math
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class LatencyResult(BaseModel):
    """Parsed result of a `ping` run between two hosts."""

    packets_sent: int
    packets_received: int
    packet_loss_pct: float
    packets_requested: int | None = Field(default=None, ge=0)
    rtt_min_ms: Optional[float] = None
    rtt_avg_ms: Optional[float] = None
    rtt_max_ms: Optional[float] = None
    rtt_mdev_ms: Optional[float] = None
    raw_output: str

    @field_validator("packets_sent", "packets_received", "packets_requested", mode="before")
    @classmethod
    def reject_boolean_packet_count(cls, value):
        if isinstance(value, bool):
            raise ValueError("Packet counts must be integers, not booleans.")
        return value

    @field_validator("packet_loss_pct", mode="before")
    @classmethod
    def reject_boolean_packet_loss(cls, value):
        if isinstance(value, bool):
            raise ValueError("Packet-loss percentage must be numeric, not boolean.")
        return value

    @property
    def reachable(self) -> bool:
        return self.packets_received > 0

    @property
    def measurement_succeeded(self) -> bool:
        """Whether this ping result contains usable packet-loss evidence."""
        if (
            type(self.packets_sent) is not int
            or type(self.packets_received) is not int
            or type(self.packets_requested) is not int
            or self.packets_requested <= 0
            or self.packets_sent != self.packets_requested
            or self.packets_sent <= 0
            or self.packets_received < 0
            or self.packets_received > self.packets_sent
            or not math.isfinite(self.packet_loss_pct)
            or not 0 <= self.packet_loss_pct <= 100
        ):
            return False
        expected_loss = (
            100.0
            * (self.packets_sent - self.packets_received)
            / self.packets_sent
        )
        return math.isclose(
            self.packet_loss_pct,
            expected_loss,
            rel_tol=0,
            abs_tol=0.5,
        )


class ThroughputResult(BaseModel):
    """Parsed result of an `iperf3 -J` run between two hosts."""

    sent_mbps: Optional[float] = None
    received_mbps: Optional[float] = None
    retransmits: Optional[int] = None
    duration_s: Optional[float] = None
    succeeded: bool
    error: Optional[str] = None
    raw_output: str

    @property
    def achieved_mbps(self) -> Optional[float]:
        """The throughput figure to compare against a target: the
        receiver's measured rate, since that's what the application on the
        other end actually got (not just what the sender pushed onto the
        wire)."""
        return self.received_mbps if self.received_mbps is not None else self.sent_mbps
