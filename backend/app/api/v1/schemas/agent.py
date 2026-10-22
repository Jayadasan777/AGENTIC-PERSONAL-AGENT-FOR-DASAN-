"""Pydantic schemas for Agent Harness endpoints, approvals, and kill switch."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    """Payload to trigger an agent execution turn."""

    prompt: str = Field(default="", min_length=0, max_length=4000)
    skill_names: list[str] = Field(default_factory=list)
    approval_token: str | None = Field(
        default=None,
        description="Signed token when resuming an action after user approval.",
    )
    approved_tool: str | None = None
    approved_args: dict[str, Any] | None = None


class StepTraceResponse(BaseModel):
    """Diagnostic trace of an individual execution step in the loop."""

    step_index: int
    thought: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    policy_decision: str | None = None
    policy_reason: str | None = None
    tool_result: dict[str, Any] | None = None
    outcome_verified: bool | None = None
    verification_reason: str | None = None
    timestamp: datetime


class PendingApprovalResponse(BaseModel):
    """Details of an action suspended awaiting user consent."""

    approval_id: str
    tool_name: str
    args: dict[str, Any]
    risk_tier: str
    reason: str
    approval_token: str
    expires_at: str


class AgentRunResponse(BaseModel):
    """Output summary of an agent run."""

    run_id: str
    status: str
    final_answer: str | None = None
    traces: list[StepTraceResponse] = Field(default_factory=list)
    pending_approval: PendingApprovalResponse | None = None
    total_steps: int = 0
    error: str | None = None


class ApprovalDecisionRequest(BaseModel):
    """Payload for user confirming or rejecting a suspended tool action."""

    approved: bool
    reason: str | None = None


class KillSwitchRequest(BaseModel):
    """Payload for engaging or disengaging the emergency kill switch."""

    engaged: bool
    reason: str = Field(default="Manual emergency stop")


class KillSwitchResponse(BaseModel):
    """Status record of the emergency kill switch."""

    is_engaged: bool
    engaged_at: datetime | None = None
    reason: str | None = None
    actor_id: str | None = None


class ToolInfoResponse(BaseModel):
    """Metadata schema of a registered agent tool."""

    name: str
    description: str
    risk_tier: str
    parameters: dict[str, Any]
