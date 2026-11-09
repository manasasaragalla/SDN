"""Deployment result model. "Success" here means what Step 6 of the brief
demands: the rule was actually read back from the switch's flow table
after being pushed, not merely that the HTTP POST returned 200."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PhysicalDeploymentState(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"


class PhysicalDeploymentResult(BaseModel):
    operation_cookie: int | None
    dpids: tuple[int, ...]
    requested_count: int
    accepted_count: int
    verified_count: int
    reconciled_count: int = 0
    state: PhysicalDeploymentState
    errors: list[str] = Field(default_factory=list)

    @property
    def success(self) -> bool:
        return (
            self.state == PhysicalDeploymentState.SUCCEEDED
            and self.requested_count > 0
            and self.verified_count == self.requested_count
        )


class PhysicalCleanupState(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"


class PhysicalCleanupResult(BaseModel):
    operation_cookie: int
    requested_dpids: tuple[int, ...]
    accepted_delete_count: int
    remaining_flow_count: int | None
    state: PhysicalCleanupState
    errors: list[str] = Field(default_factory=list)

    @property
    def success(self) -> bool:
        return (
            self.state == PhysicalCleanupState.SUCCEEDED
            and self.remaining_flow_count == 0
        )


class DeploymentResult(BaseModel):
    requested_count: int
    accepted_count: int  # ofctl_rest returned success for the POST
    verified_count: int  # rule was actually found in a subsequent flow-table read
    errors: list[str] = []

    @property
    def success(self) -> bool:
        return self.requested_count > 0 and self.verified_count == self.requested_count and not self.errors
