"""LangGraph Stateful Agent Execution Graph for AURA.

Constructs an explicit state graph:
- Nodes:
  1. `reason`: Model proposes thought and structured tool action or final answer.
  2. `policy_check`: PolicyEngine evaluates permissions, risk tier, and kill switch.
  3. `execute_tool`: Runs the approved tool in an isolated ToolContext.
  4. `verify_outcome`: Independent verification of tool outputs.
- Conditional branches:
  - If final answer -> END
  - If policy says DENY -> END (with block reason)
  - If policy says REQUIRE_APPROVAL -> pauses for human-in-the-loop token
  - If policy says ALLOW -> execute_tool -> verify_outcome -> reason
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.approvals import approval_manager
from backend.app.agent.kill_switch import kill_switch
from backend.app.agent.policy import PolicyDecision, PolicyEngine
from backend.app.agent.tools.base import ToolContext
from backend.app.agent.tools.registry import get_tool_registry
from backend.app.agent.verifier import outcome_verifier
from backend.app.models.provider import (
    ChatMessage,
    CompletionRequest,
    get_model_provider,
)

logger = logging.getLogger("aura.agent.graph")


class AgentState(TypedDict):
    """Execution state passed through the LangGraph agent graph."""

    user_id: str
    session_id: str
    messages: Annotated[list[dict[str, Any]], add_messages]
    current_thought: str | None
    current_tool: str | None
    current_args: dict[str, Any] | None
    policy_decision: str | None
    policy_reason: str | None
    approval_id: str | None
    approval_token: str | None
    tool_result: dict[str, Any] | None
    outcome_verified: bool | None
    verification_reason: str | None
    final_answer: str | None
    is_blocked: bool
    step_count: int


def create_agent_graph(session: AsyncSession) -> Any:
    """Build and compile the LangGraph execution graph."""
    model_provider = get_model_provider()
    tool_registry = get_tool_registry()
    policy_engine = PolicyEngine(tool_registry)

    # 1. Reason Node
    async def reason_node(state: AgentState) -> dict[str, Any]:
        kill_switch.check()
        state_messages = [
            ChatMessage(role=m.get("role", "user"), content=m.get("content", ""))
            for m in state["messages"]
        ]
        completion_req = CompletionRequest(
            messages=state_messages,
            temperature=0.2,
            max_tokens=1000,
        )
        resp = await model_provider.complete(completion_req)
        content = resp.content

        # Check for tool call
        from backend.app.agent.harness import extract_tool_call_from_llm

        thought, tool_name, tool_args = extract_tool_call_from_llm(content)
        step_count = state.get("step_count", 0) + 1

        if not tool_name or tool_args is None:
            return {
                "final_answer": content,
                "step_count": step_count,
            }

        return {
            "current_thought": thought,
            "current_tool": tool_name,
            "current_args": tool_args,
            "step_count": step_count,
        }

    # 2. Policy Check Node
    async def policy_check_node(state: AgentState) -> dict[str, Any]:
        kill_switch.check()
        tool_name = state["current_tool"]
        tool_args = state["current_args"] or {}
        user_uuid = __import__("uuid").UUID(state["user_id"])

        policy_res = policy_engine.evaluate(
            user_id=user_uuid,
            tool_name=tool_name,  # type: ignore[arg-type]
            args=tool_args,
            approval_token=state.get("approval_token"),
        )

        if policy_res.decision == PolicyDecision.REQUIRE_APPROVAL:
            pending = approval_manager.create_request(
                approval_id=policy_res.approval_id or str(__import__("uuid").uuid4()),
                user_id=user_uuid,
                tool_name=tool_name,  # type: ignore[arg-type]
                args=tool_args,
                risk_tier=policy_res.risk_tier.value if policy_res.risk_tier else "MUTATING",
                reason=policy_res.reason,
                approval_token=policy_res.approval_token or "",
                expires_at=policy_res.expires_at or datetime.now(UTC),
            )
            return {
                "policy_decision": policy_res.decision.value,
                "policy_reason": policy_res.reason,
                "approval_id": pending.approval_id,
                "approval_token": pending.approval_token,
            }

        if policy_res.decision == PolicyDecision.DENY:
            return {
                "policy_decision": policy_res.decision.value,
                "policy_reason": policy_res.reason,
                "is_blocked": True,
            }

        return {
            "policy_decision": policy_res.decision.value,
            "policy_reason": policy_res.reason,
        }

    # 3. Tool Execution Node
    async def execute_tool_node(state: AgentState) -> dict[str, Any]:
        kill_switch.check()
        tool_name = state["current_tool"]
        tool_args = state["current_args"] or {}
        user_uuid = __import__("uuid").UUID(state["user_id"])
        context = ToolContext(user_id=user_uuid, session=session)

        tool = tool_registry.get(tool_name)  # type: ignore[arg-type]
        if not tool:
            return {
                "tool_result": {"success": False, "error": f"Tool '{tool_name}' not found"},
            }

        result = await tool.execute(context, **tool_args)
        return {"tool_result": result.model_dump()}

    # 4. Outcome Verification Node
    async def verify_outcome_node(state: AgentState) -> dict[str, Any]:
        tool_name = state["current_tool"]
        tool_args = state["current_args"] or {}
        tool_result = state["tool_result"] or {}
        user_uuid = __import__("uuid").UUID(state["user_id"])
        context = ToolContext(user_id=user_uuid, session=session)

        from backend.app.agent.tools.base import ToolResult

        t_res = ToolResult(**tool_result)
        v_res = await outcome_verifier.verify(
            tool_name=tool_name,  # type: ignore[arg-type]
            args=tool_args,
            result=t_res,
            context=context,
        )

        # Append observation to message thread
        obs_msg = {
            "role": "user",
            "content": f"Tool '{tool_name}' execution result: {tool_result.get('data')}",
        }
        return {
            "outcome_verified": v_res.verified,
            "verification_reason": v_res.reason,
            "messages": [obs_msg],
        }

    # Conditional Routers
    def route_after_reason(state: AgentState) -> str:
        if state.get("final_answer") is not None or state.get("step_count", 0) >= 6:
            return END
        return "policy_check"

    def route_after_policy(state: AgentState) -> str:
        decision = state.get("policy_decision")
        if decision == PolicyDecision.ALLOW.value:
            return "execute_tool"
        # REQUIRE_APPROVAL and DENY end this turn
        return END

    workflow = StateGraph(AgentState)
    workflow.add_node("reason", reason_node)
    workflow.add_node("policy_check", policy_check_node)
    workflow.add_node("execute_tool", execute_tool_node)
    workflow.add_node("verify_outcome", verify_outcome_node)

    workflow.set_entry_point("reason")
    workflow.add_conditional_edges("reason", route_after_reason)
    workflow.add_conditional_edges("policy_check", route_after_policy)
    workflow.add_edge("execute_tool", "verify_outcome")
    workflow.add_edge("verify_outcome", "reason")

    return workflow.compile()
