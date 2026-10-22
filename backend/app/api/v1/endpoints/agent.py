"""API v1 endpoints for Agent Harness execution, human approvals, and kill switch."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.approvals import approval_manager
from backend.app.agent.harness import AgentHarness
from backend.app.agent.kill_switch import kill_switch
from backend.app.agent.tools.registry import get_tool_registry
from backend.app.api.v1.dependencies.auth import get_current_active_user
from backend.app.api.v1.schemas.agent import (
    AgentRunRequest,
    AgentRunResponse,
    ApprovalDecisionRequest,
    KillSwitchRequest,
    KillSwitchResponse,
    PendingApprovalResponse,
    ToolInfoResponse,
)
from backend.app.db.session import get_async_session
from backend.app.models.provider import BaseModelProvider, get_model_provider
from backend.app.models.user import User

router = APIRouter(prefix="/agent", tags=["agent"])
_tool_registry = get_tool_registry()


@router.post(
    "/run",
    response_model=AgentRunResponse,
    summary="Execute an autonomous agent reasoning turn",
)
async def run_agent(
    body: AgentRunRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    model_provider: Annotated[BaseModelProvider, Depends(get_model_provider)],
) -> AgentRunResponse:
    """Run autonomous agent loop, enforcing policy gating and outcome verification."""
    harness = AgentHarness(model_provider=model_provider)
    output = await harness.run(
        session=session,
        user_id=current_user.id,
        user_prompt=body.prompt,
        approval_token=body.approval_token,
        approved_tool=body.approved_tool,
        approved_args=body.approved_args,
    )

    pending_model = None
    if output.pending_approval:
        pending_model = PendingApprovalResponse(**output.pending_approval)

    return AgentRunResponse(
        run_id=output.run_id,
        status=output.status.value,
        final_answer=output.final_answer,
        traces=[
            {
                "step_index": t.step_index,
                "thought": t.thought,
                "tool_name": t.tool_name,
                "tool_args": t.tool_args,
                "policy_decision": t.policy_decision,
                "policy_reason": t.policy_reason,
                "tool_result": t.tool_result,
                "outcome_verified": t.outcome_verified,
                "verification_reason": t.verification_reason,
                "timestamp": t.timestamp,
            }
            for t in output.traces
        ],  # type: ignore[arg-type]
        pending_approval=pending_model,
        total_steps=output.total_steps,
        error=output.error,
    )


@router.get(
    "/approvals",
    response_model=list[PendingApprovalResponse],
    summary="List active pending human approval requests",
)
async def list_pending_approvals(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[PendingApprovalResponse]:
    """Retrieve all pending approval requests awaiting the caller's decision."""
    records = approval_manager.list_pending(current_user.id)
    return [
        PendingApprovalResponse(
            approval_id=r.approval_id,
            tool_name=r.tool_name,
            args=r.args,
            risk_tier=r.risk_tier,
            reason=r.reason,
            approval_token=r.approval_token,
            expires_at=r.expires_at.isoformat(),
        )
        for r in records
    ]


@router.post(
    "/approvals/{approval_id}/decision",
    summary="Record human decision (approve or reject) for a pending tool action",
)
async def decide_approval(
    approval_id: str,
    body: ApprovalDecisionRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict[str, str | bool]:
    """Approve or reject a suspended tool action."""
    try:
        record = approval_manager.decide(
            approval_id=approval_id,
            user_id=current_user.id,
            approved=body.approved,
            reason=body.reason,
        )
        return {
            "approval_id": record.approval_id,
            "status": record.status.value,
            "approved": body.approved,
            "approval_token": record.approval_token if body.approved else "",
        }
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.get(
    "/kill-switch",
    response_model=KillSwitchResponse,
    summary="Inspect emergency kill switch status",
)
async def get_kill_switch_status(
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> KillSwitchResponse:
    """Return whether the global emergency halt is currently active."""
    st = kill_switch.state
    return KillSwitchResponse(
        is_engaged=st.is_engaged,
        engaged_at=st.engaged_at,
        reason=st.reason,
        actor_id=st.actor_id,
    )


@router.post(
    "/kill-switch",
    response_model=KillSwitchResponse,
    summary="Engage or disengage global emergency kill switch",
)
async def toggle_kill_switch(
    body: KillSwitchRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> KillSwitchResponse:
    """Trigger emergency stop halting all agent executions, or resume normal state."""
    if body.engaged:
        kill_switch.engage(reason=body.reason, actor_id=str(current_user.id))
    else:
        kill_switch.disengage(actor_id=str(current_user.id))

    st = kill_switch.state
    return KillSwitchResponse(
        is_engaged=st.is_engaged,
        engaged_at=st.engaged_at,
        reason=st.reason,
        actor_id=st.actor_id,
    )


@router.get(
    "/tools",
    response_model=list[ToolInfoResponse],
    summary="List available agent tools and JSON schemas",
)
async def list_tools(
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[ToolInfoResponse]:
    """Inspect all registered tools and their input parameters."""
    tools = _tool_registry.list_tools()
    return [
        ToolInfoResponse(
            name=t.name,
            description=t.description,
            risk_tier=t.risk_tier.value,
            parameters=t.args_schema.model_json_schema(),
        )
        for t in tools
    ]
