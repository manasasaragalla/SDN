"""OVS QoS queue configuration model (brief Step 3/6 -- see
docs/adr-004-bandwidth-mechanism.md for why OVS QoS queues, not OpenFlow
meters, are this project's per-flow rate-limiting mechanism).

Deliberately shaped to match exactly what
backend/deployment/ovs_qos_client.py needs to run its `ovs-vsctl` commands
-- the same "compiler output is the literal deployable configuration"
principle backend/models/flow.py documents for FlowRule."""
from __future__ import annotations

from pydantic import BaseModel, Field


class QueueConfig(BaseModel):
    switch: str
    intf: str  # OVS interface name, e.g. "s2-eth2" (see Link.intf_facing)
    queue_id: int = Field(default=0, ge=0)
    max_rate_bps: int = Field(gt=0)
    label: str = ""
