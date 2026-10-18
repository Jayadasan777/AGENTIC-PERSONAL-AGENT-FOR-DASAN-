"""Stateful Agent Execution Harness for AURA.

Implements a deterministic agent loop:
1. Context assembly & prompt construction.
2. Model reasoning turn proposing text answer or structured tool call.
3. Server-side Policy Engine gating (ALLOW, REQUIRE_APPROVAL, DENY).
4. Human-in-the-loop interruption upon REQUIRE_APPROVAL.
5. Isolated tool execution with bounded retries and exponential backoff.
6. Independent post-execution outcome verification.
7. Iteration limit (max_steps) preventing runaway loops.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.approvals import ApprovalManager, approval_manager
from backend.app.agent.kill_switch import kill_switch
from backend.app.agent.policy import PolicyDecision, PolicyEngine
from backend.app.agent.skills import LoadedSkill
from backend.app.agent.tools.base import ToolContext, ToolResult
from backend.app.agent.tools.registry import ToolRegistry, get_tool_registry
from backend.app.agent.verifier import OutcomeVerifier, outcome_verifier
from backend.app.models.provider import (
    BaseModelProvider,
    ChatMessage,
    CompletionRequest,
    get_model_provider,
)

logger = logging.getLogger("aura.agent.harness")


class AgentExecutionStatus(StrEnum):
    """Overall status of an agent execution turn."""

    COMPLETED = "COMPLETED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    MAX_STEPS_EXCEEDED = "MAX_STEPS_EXCEEDED"


@dataclass
class StepTrace:
    """Detailed record of an individual step in the agent execution."""

    step_index: int
    thought: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    policy_decision: str | None = None
    policy_reason: str | None = None
    tool_result: dict[str, Any] | None = None
    outcome_verified: bool | None = None
    verification_reason: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class AgentRunOutput:
    """Final output returned by the agent harness."""

    run_id: str
    status: AgentExecutionStatus
    final_answer: str | None
    traces: list[StepTrace]
    pending_approval: dict[str, Any] | None = None
    total_steps: int = 0
    error: str | None = None


def extract_tool_call_from_llm(
    content: str,
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    """Parse structured tool call proposals from LLM output.

    Looks for JSON blocks in format:
    ```tool_call
    {"tool": "calculator", "args": {"expression": "2 + 2"}}
    ```
    or
    {"tool": "calculator", "args": {...}}
    """
    pattern = r"```(?:tool_call|json)?\s*(\{.*?\})\s*```"
    match = re.search(pattern, content, re.DOTALL)
    json_str = match.group(1) if match else None

    if not json_str:
        # Try raw JSON match
        raw_match = re.search(r"(\{\s*\"tool\"\s*:\s*\"[^\"]+\".*?\})", content, re.DOTALL)
        if raw_match:
            json_str = raw_match.group(1)

    if json_str:
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict) and "tool" in parsed:
                thought = content.split("```")[0].strip() if "```" in content else None
                return thought, parsed["tool"], parsed.get("args", {})
        except json.JSONDecodeError:
            pass

    return None, None, None


class AgentHarness:
    """Orchestrates multi-step reasoning, tool execution, and safety gating."""

    def __init__(
        self,
        model_provider: BaseModelProvider | None = None,
        tool_registry: ToolRegistry | None = None,
        policy_engine: PolicyEngine | None = None,
        approvals: ApprovalManager | None = None,
        verifier: OutcomeVerifier | None = None,
        max_steps: int = 6,
    ) -> None:
        self.model_provider = model_provider or get_model_provider()
        self.tool_registry = tool_registry or get_tool_registry()
        self.policy_engine = policy_engine or PolicyEngine(self.tool_registry)
        self.approvals = approvals or approval_manager
        self.verifier = verifier or outcome_verifier
        self.max_steps = max_steps

    async def execute_tool_with_retries(
        self,
        tool_name: str,
        args: dict[str, Any],
        context: ToolContext,
        max_retries: int = 2,
    ) -> ToolResult:
        """Execute tool with bounded retries and exponential backoff."""
        tool = self.tool_registry.get(tool_name)
        if tool is None:
            return ToolResult(success=False, error=f"Tool '{tool_name}' not found.")

        last_error = ""
        for attempt in range(max_retries + 1):
            # Check kill switch before every retry attempt
            kill_switch.check()

            result = await tool.execute(context, **args)
            if result.success:
                return result

            last_error = result.error or "Unknown error"
            logger.warning("Tool %s attempt %d failed: %s", tool_name, attempt + 1, last_error)
            if attempt < max_retries:
                await asyncio.sleep(0.1 * (2**attempt))

        return ToolResult(
            success=False,
            error=f"Tool failed after {max_retries + 1} attempts: {last_error}",
        )

    async def run(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        user_prompt: str,
        history: list[ChatMessage] | None = None,
        skills: list[LoadedSkill] | None = None,
        approval_token: str | None = None,
        approved_tool: str | None = None,
        approved_args: dict[str, Any] | None = None,
    ) -> AgentRunOutput:
        """Run the autonomous agent loop up to max_steps."""
        run_id = str(uuid.uuid4())
        traces: list[StepTrace] = []
        context = ToolContext(user_id=user_id, session=session, request_id=run_id)

        # 1. Check emergency kill switch
        if kill_switch.is_engaged:
            return AgentRunOutput(
                run_id=run_id,
                status=AgentExecutionStatus.BLOCKED,
                final_answer=None,
                traces=[],
                error="Emergency kill switch is active.",
            )

        # 2. Build system instructions
        tool_schemas = self.tool_registry.get_schemas()
        skills_text = ""
        if skills:
            skills_text = "\n\nACTIVE CUSTOM SKILLS:\n" + "\n---\n".join(
                f"Skill: {s.metadata.name}\n{s.instructions}" for s in skills
            )

        system_instruction = (
            "You are AURA (Adaptive Unified Reasoning Assistant).\n"
            "You solve problems accurately using available tools when necessary.\n"
            "AVAILABLE TOOLS:\n"
            f"{json.dumps(tool_schemas, indent=2)}\n\n"
            "INSTRUCTIONS:\n"
            "1. If you need a tool, emit a JSON block in format:\n"
            "```tool_call\n"
            '{"tool": "<tool_name>", "args": {<arguments>}}\n'
            "```\n"
            "2. If no tool is needed, respond directly with the helpful, precise answer.\n"
            f"{skills_text}"
        )

        messages: list[ChatMessage] = [ChatMessage(role="system", content=system_instruction)]
        if history:
            messages.extend(history)
        messages.append(ChatMessage(role="user", content=user_prompt))

        # Handle resumed execution with pre-approved tool
        if approval_token and approved_tool and approved_args is not None:
            logger.info("Resuming execution with approved tool: %s", approved_tool)
            policy_res = self.policy_engine.evaluate(
                user_id=user_id,
                tool_name=approved_tool,
                args=approved_args,
                approval_token=approval_token,
            )
            if policy_res.decision != PolicyDecision.ALLOW:
                return AgentRunOutput(
                    run_id=run_id,
                    status=AgentExecutionStatus.BLOCKED,
                    final_answer=None,
                    traces=[],
                    error=f"Policy check failed for approved token: {policy_res.reason}",
                )

            tool_result = await self.execute_tool_with_retries(
                tool_name=approved_tool,
                args=approved_args,
                context=context,
            )
            v_res = await self.verifier.verify(
                tool_name=approved_tool,
                args=approved_args,
                result=tool_result,
                context=context,
            )
            trace = StepTrace(
                step_index=1,
                thought="Executing resumed approved action",
                tool_name=approved_tool,
                tool_args=approved_args,
                policy_decision=policy_res.decision.value,
                policy_reason=policy_res.reason,
                tool_result=tool_result.model_dump(),
                outcome_verified=v_res.verified,
                verification_reason=v_res.reason,
            )
            traces.append(trace)

            # Append observation and ask LLM for final answer
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=f"Executed tool {approved_tool} with args {approved_args}",
                )
            )
            messages.append(
                ChatMessage(
                    role="user",
                    content=f"Tool Execution Output:\n{json.dumps(tool_result.data)}",
                )
            )

        # Execution loop
        for step_idx in range(len(traces) + 1, self.max_steps + 1):
            # Check kill switch before every step
            if kill_switch.is_engaged:
                return AgentRunOutput(
                    run_id=run_id,
                    status=AgentExecutionStatus.BLOCKED,
                    final_answer=None,
                    traces=traces,
                    error="Emergency kill switch engaged during run.",
                )

            # Request LLM step proposal
            completion_req = CompletionRequest(
                messages=messages,
                temperature=0.2,
                max_tokens=1000,
            )
            resp = await self.model_provider.complete(completion_req)
            llm_text = resp.content

            thought, tool_name, tool_args = extract_tool_call_from_llm(llm_text)

            # If no tool requested, LLM has provided final answer
            if not tool_name or tool_args is None:
                return AgentRunOutput(
                    run_id=run_id,
                    status=AgentExecutionStatus.COMPLETED,
                    final_answer=llm_text,
                    traces=traces,
                    total_steps=step_idx,
                )

            # Evaluate policy
            policy_res = self.policy_engine.evaluate(
                user_id=user_id,
                tool_name=tool_name,
                args=tool_args,
            )

            # Case: REQUIRE_APPROVAL
            if policy_res.decision == PolicyDecision.REQUIRE_APPROVAL:
                pending = self.approvals.create_request(
                    approval_id=policy_res.approval_id or str(uuid.uuid4()),
                    user_id=user_id,
                    tool_name=tool_name,
                    args=tool_args,
                    risk_tier=policy_res.risk_tier.value if policy_res.risk_tier else "MUTATING",
                    reason=policy_res.reason,
                    approval_token=policy_res.approval_token or "",
                    expires_at=policy_res.expires_at or datetime.now(UTC),
                )
                trace = StepTrace(
                    step_index=step_idx,
                    thought=thought,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    policy_decision=policy_res.decision.value,
                    policy_reason=policy_res.reason,
                )
                traces.append(trace)
                return AgentRunOutput(
                    run_id=run_id,
                    status=AgentExecutionStatus.AWAITING_APPROVAL,
                    final_answer=None,
                    traces=traces,
                    pending_approval={
                        "approval_id": pending.approval_id,
                        "tool_name": pending.tool_name,
                        "args": pending.args,
                        "risk_tier": pending.risk_tier,
                        "reason": pending.reason,
                        "approval_token": pending.approval_token,
                        "expires_at": pending.expires_at.isoformat(),
                    },
                    total_steps=step_idx,
                )

            # Case: DENY
            if policy_res.decision == PolicyDecision.DENY:
                trace = StepTrace(
                    step_index=step_idx,
                    thought=thought,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    policy_decision=policy_res.decision.value,
                    policy_reason=policy_res.reason,
                )
                traces.append(trace)
                return AgentRunOutput(
                    run_id=run_id,
                    status=AgentExecutionStatus.BLOCKED,
                    final_answer=None,
                    traces=traces,
                    error=f"Tool invocation denied by policy: {policy_res.reason}",
                    total_steps=step_idx,
                )

            # Case: ALLOW -> Execute tool
            tool_result = await self.execute_tool_with_retries(
                tool_name=tool_name,
                args=tool_args,
                context=context,
            )

            # Outcome verification
            v_res = await self.verifier.verify(
                tool_name=tool_name,
                args=tool_args,
                result=tool_result,
                context=context,
            )

            trace = StepTrace(
                step_index=step_idx,
                thought=thought,
                tool_name=tool_name,
                tool_args=tool_args,
                policy_decision=policy_res.decision.value,
                policy_reason=policy_res.reason,
                tool_result=tool_result.model_dump(),
                outcome_verified=v_res.verified,
                verification_reason=v_res.reason,
            )
            traces.append(trace)

            # Update conversation history with tool result
            messages.append(ChatMessage(role="assistant", content=llm_text))
            messages.append(
                ChatMessage(
                    role="user",
                    content=(f"Tool '{tool_name}' result:\n{json.dumps(tool_result.model_dump())}"),
                )
            )

        return AgentRunOutput(
            run_id=run_id,
            status=AgentExecutionStatus.MAX_STEPS_EXCEEDED,
            final_answer=None,
            traces=traces,
            total_steps=self.max_steps,
            error=f"Agent exceeded maximum step limit of {self.max_steps}.",
        )
