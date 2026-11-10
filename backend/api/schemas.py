from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models.canonical_intent import CanonicalIntent
from backend.models.intent import StructuredIntent
from backend.models.topology_definition import (
    ActiveTopologyResponse,
    TopologyActivationRequest,
    TopologyCatalogItem,
    TopologyDefinition,
    TopologyDefinitionInput,
    TopologyDuplicateRequest,
    TopologyRenameRequest,
    TopologyUpdateRequest,
)


class Availability(str, Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    UNKNOWN = "UNKNOWN"


class ApiHealthResponse(BaseModel):
    api_status: Literal["CONNECTED"] = "CONNECTED"
    backend_status: Availability
    ryu_status: Availability
    mininet_status: Availability
    current_execution_status: str
    checked_at: datetime
    details: dict[str, str | None] = Field(default_factory=dict)


class IntentPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    natural_language: str | None = Field(default=None, min_length=1, max_length=4000)
    structured_intent: CanonicalIntent | StructuredIntent | None = None
    source: str = Field(min_length=1, max_length=32)
    destination: str = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_request(self) -> "IntentPreviewRequest":
        if (self.natural_language is None) == (self.structured_intent is None):
            raise ValueError(
                "Provide exactly one of natural_language or structured_intent"
            )
        if self.source == self.destination:
            raise ValueError("source and destination must differ")
        return self


class IntentPreviewResponse(BaseModel):
    preview_id: UUID
    parser: str
    parser_kind: Literal["PROVIDER", "MOCK", "STRUCTURED"]
    interpretation_status: Literal["VALID"] = "VALID"
    canonical_intent: CanonicalIntent
    capability_resolution: dict[str, Any]
    planning_eligible: bool | None = None
    execution_status: Literal["AVAILABLE", "UNAVAILABLE"]
    execution_unavailable_reason: str | None = None
    execution_eligible: bool
    topology_status: Availability
    topology_identity: dict[str, Any] | None = None
    planning_result: dict[str, Any] | None = None
    unsupported_or_conditional: list[str] = Field(default_factory=list)
    explanation: list[str] = Field(default_factory=list)


class TopologyCatalogResponse(BaseModel):
    topologies: list[TopologyCatalogItem]


class TopologyVersionsResponse(BaseModel):
    versions: list[TopologyDefinition]


class TopologyExportResponse(BaseModel):
    format: Literal["intentflow-topology-v1"] = "intentflow-topology-v1"
    topology: TopologyDefinitionInput


class ExecuteIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_intent: CanonicalIntent | None = None
    preview_id: UUID | None = None

    @model_validator(mode="after")
    def validate_request(self) -> "ExecuteIntentRequest":
        if (self.canonical_intent is None) == (self.preview_id is None):
            raise ValueError("Provide exactly one of canonical_intent or preview_id")
        return self


class ExecutionAcceptedResponse(BaseModel):
    execution_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    status: Literal["RUNNING"]
    accepted_at: datetime
    events_url: str


class TopologySwitch(BaseModel):
    name: str
    dpid: int
    status: Availability


class TopologyHost(BaseModel):
    name: str
    ip: str
    mac: str
    switch: str
    switch_port: int
    attachment_capacity_mbps: float | None = None
    attachment_delay_ms: float | None = None
    attachment_packet_loss_percent: float | None = None
    attachment_admin_up: bool | None = None


class TopologyLink(BaseModel):
    node_a: str
    port_a: int | None
    node_b: str
    port_b: int
    capacity_mbps: float | None = None
    delay_ms: float | None = None
    packet_loss_percent: float | None = None
    admin_up: bool | None = None
    status: Availability


class TopologyResponse(BaseModel):
    switches: list[TopologySwitch]
    hosts: list[TopologyHost]
    links: list[TopologyLink]
    topology_fingerprint: str
    snapshot_timestamp: datetime
    snapshot_status: str
    source: str
    mode: Literal["LIVE"] = "LIVE"


class ExecutionSummary(BaseModel):
    execution_id: str
    submitted_intent: dict[str, Any] | str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: str
    selected_path: list[str] | None = None
    final_measurement: dict[str, Any] | None = None
    evidence_json: str | None = None
    evidence_markdown: str | None = None


class ExecutionDetail(ExecutionSummary):
    evidence: dict[str, Any] | None = None


class ExecutionEventName(str, Enum):
    EXECUTION_ACCEPTED = "EXECUTION_ACCEPTED"
    EXECUTION_RUNNING = "EXECUTION_RUNNING"
    EXECUTION_SUCCEEDED = "EXECUTION_SUCCEEDED"
    EXECUTION_COMPLETED = "EXECUTION_COMPLETED"
    EXECUTION_FAILED = "EXECUTION_FAILED"


class ExecutionEvent(BaseModel):
    execution_id: str
    event: ExecutionEventName
    timestamp: datetime
    detail: str | None = None


class ExecutionStatusResponse(BaseModel):
    execution_id: str
    status: str
    events: list[ExecutionEvent] = Field(default_factory=list)


class WorkerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    operation: Literal["health", "topology", "execute"]
    intent: CanonicalIntent | None = None
    execution_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")

    @model_validator(mode="after")
    def validate_operation(self) -> "WorkerRequest":
        if self.operation == "execute":
            if self.intent is None or self.execution_id is None:
                raise ValueError("execute requires an intent and execution_id")
        elif self.intent is not None or self.execution_id is not None:
            raise ValueError("health and topology requests cannot include intent data")
        return self


class WorkerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = None
