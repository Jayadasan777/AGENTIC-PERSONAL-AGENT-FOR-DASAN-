"""Specialist Agents for AURA Multi-Agent Orchestration.

Each specialist agent is a self-contained, focused reasoning unit that
accepts a well-typed input and returns a structured response. The Orchestrator
composes them into multi-step workflows while maintaining tenant isolation
and policy gating at every boundary.

Agents defined here:
- ResearchAgent: Synthesizes knowledge from RAG + memory for a question.
- MemoryAgent: Manages memory consolidation, deduplication, and recall.
- DocumentAgent: Extracts, summarizes, and citations from uploaded documents.
- VerificationAgent: Fact-checks or validates a claim against stored evidence.
- OrchestratorAgent: Routes tasks to specialist agents and assembles results.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.provider import (
    BaseModelProvider,
    ChatMessage,
    CompletionRequest,
    get_model_provider,
)

logger = logging.getLogger("aura.agents.specialists")


# ---------------------------------------------------------------------------
# Shared Types
# ---------------------------------------------------------------------------


class AgentRole(StrEnum):
    """Named roles for the specialist agent roster."""

    ORCHESTRATOR = "orchestrator"
    RESEARCH = "research"
    MEMORY = "memory"
    DOCUMENT = "document"
    VERIFICATION = "verification"


@dataclass
class AgentInput:
    """Typed input envelope for all specialist agents."""

    user_id: uuid.UUID
    session: AsyncSession
    task: str
    context: dict[str, Any] = field(default_factory=dict)
    conversation_history: list[ChatMessage] = field(default_factory=list)


@dataclass
class AgentOutput:
    """Typed output envelope from all specialist agents."""

    agent_role: AgentRole
    success: bool
    result: str
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# Base Specialist Agent
# ---------------------------------------------------------------------------


class BaseSpecialistAgent:
    """Abstract base for all specialist agents."""

    role: AgentRole
    system_prompt: str

    def __init__(self, model_provider: BaseModelProvider | None = None) -> None:
        self._model = model_provider or get_model_provider()

    async def _complete(
        self,
        messages: list[ChatMessage],
        max_tokens: int = 800,
        temperature: float = 0.2,
    ) -> str:
        """Run a completion request through the model provider."""
        req = CompletionRequest(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        resp = await self._model.complete(req)
        return resp.content

    async def run(self, agent_input: AgentInput) -> AgentOutput:  # pragma: no cover
        """Execute the specialist agent's task. Override in subclasses."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Research Agent
# ---------------------------------------------------------------------------


class ResearchAgent(BaseSpecialistAgent):
    """Synthesizes answers by combining RAG document context with memory recall.

    In a full deployment, this agent calls the RAG service and memory service
    to hydrate its context window. For the harness it accepts pre-fetched
    context in agent_input.context['rag_chunks'] and ['memories'].
    """

    role = AgentRole.RESEARCH

    system_prompt = (
        "You are the Research Specialist for AURA. "
        "Your job is to synthesize a precise, evidence-grounded answer from "
        "the provided document excerpts and memory facts. "
        "Always cite your sources using [Doc: <filename>] or [Mem: <id>] notation. "
        "If you cannot find evidence, explicitly state that."
    )

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        started = datetime.now(UTC)
        rag_chunks: list[dict[str, Any]] = agent_input.context.get("rag_chunks", [])
        memories: list[dict[str, Any]] = agent_input.context.get("memories", [])

        context_block = ""
        if rag_chunks:
            context_block += "DOCUMENT EXCERPTS:\n"
            for chunk in rag_chunks:
                filename = chunk.get("filename", "unknown")
                page = chunk.get("page_number", "?")
                text = chunk.get("text", "")
                context_block += f"[Doc: {filename}, Page: {page}]\n{text}\n\n"

        if memories:
            context_block += "MEMORY FACTS:\n"
            for mem in memories:
                mem_id = mem.get("id", "?")
                content = mem.get("content", "")
                context_block += f"[Mem: {mem_id}] {content}\n"

        messages = [
            ChatMessage(role="system", content=self.system_prompt),
            ChatMessage(
                role="user",
                content=(f"CONTEXT:\n{context_block}\n\nQUESTION: {agent_input.task}"),
            ),
        ]

        try:
            answer = await self._complete(messages, max_tokens=1000)
            duration = (datetime.now(UTC) - started).total_seconds() * 1000
            return AgentOutput(
                agent_role=self.role,
                success=True,
                result=answer,
                metadata={"rag_chunks_used": len(rag_chunks), "memories_used": len(memories)},
                duration_ms=duration,
            )
        except Exception as exc:
            logger.exception("ResearchAgent failed: %s", exc)
            duration = (datetime.now(UTC) - started).total_seconds() * 1000
            return AgentOutput(
                agent_role=self.role,
                success=False,
                result="",
                error=str(exc),
                duration_ms=duration,
            )


# ---------------------------------------------------------------------------
# Memory Agent
# ---------------------------------------------------------------------------


class MemoryAgent(BaseSpecialistAgent):
    """Handles memory consolidation, contradiction detection, and structured recall.

    Receives raw conversation excerpts or facts and produces a concise,
    structured memory update proposal. The actual DB write is performed by
    the Memory service; this agent only reasons about what to remember.
    """

    role = AgentRole.MEMORY

    system_prompt = (
        "You are the Memory Specialist for AURA. "
        "Your job is to extract durable, high-signal personal facts from the provided "
        "conversation or observation. Output a JSON list of memory items, each with "
        "fields: 'content' (string), 'tags' (list of strings), 'confidence' (0.0-1.0), "
        "'sensitivity' ('PUBLIC'|'PRIVATE'|'SENSITIVE'). "
        "Be conservative: only extract clear, verifiable facts."
    )

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        started = datetime.now(UTC)
        messages = [
            ChatMessage(role="system", content=self.system_prompt),
            ChatMessage(role="user", content=f"OBSERVATION:\n{agent_input.task}"),
        ]
        try:
            raw = await self._complete(messages, max_tokens=600, temperature=0.1)
            duration = (datetime.now(UTC) - started).total_seconds() * 1000
            return AgentOutput(
                agent_role=self.role,
                success=True,
                result=raw,
                metadata={"observation_chars": len(agent_input.task)},
                duration_ms=duration,
            )
        except Exception as exc:
            logger.exception("MemoryAgent failed: %s", exc)
            duration = (datetime.now(UTC) - started).total_seconds() * 1000
            return AgentOutput(
                agent_role=self.role,
                success=False,
                result="",
                error=str(exc),
                duration_ms=duration,
            )


# ---------------------------------------------------------------------------
# Document Agent
# ---------------------------------------------------------------------------


class DocumentAgent(BaseSpecialistAgent):
    """Extracts structured information and summaries from document chunks.

    Accepts pre-parsed text in agent_input.context['document_text'] and
    produces a title, summary, key entities, and key dates.
    """

    role = AgentRole.DOCUMENT

    system_prompt = (
        "You are the Document Analysis Specialist for AURA. "
        "Given the text of a document, extract: "
        "(1) A one-sentence title, "
        "(2) A 3-sentence executive summary, "
        "(3) Key named entities (people, organizations, places), "
        "(4) Key dates and deadlines. "
        "Format your output as JSON with keys: title, summary, entities, dates."
    )

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        started = datetime.now(UTC)
        document_text: str = agent_input.context.get("document_text", agent_input.task)

        messages = [
            ChatMessage(role="system", content=self.system_prompt),
            ChatMessage(
                role="user",
                content=f"DOCUMENT TEXT:\n{document_text[:8000]}\n\nTASK: {agent_input.task}",
            ),
        ]
        try:
            extraction = await self._complete(messages, max_tokens=800, temperature=0.1)
            duration = (datetime.now(UTC) - started).total_seconds() * 1000
            return AgentOutput(
                agent_role=self.role,
                success=True,
                result=extraction,
                metadata={"document_chars": len(document_text)},
                duration_ms=duration,
            )
        except Exception as exc:
            logger.exception("DocumentAgent failed: %s", exc)
            duration = (datetime.now(UTC) - started).total_seconds() * 1000
            return AgentOutput(
                agent_role=self.role,
                success=False,
                result="",
                error=str(exc),
                duration_ms=duration,
            )


# ---------------------------------------------------------------------------
# Verification Agent
# ---------------------------------------------------------------------------


class VerificationAgent(BaseSpecialistAgent):
    """Fact-checks a claim against provided evidence, returning a verdict.

    Verdicts: SUPPORTED, REFUTED, INSUFFICIENT_EVIDENCE, UNCERTAIN.
    """

    role = AgentRole.VERIFICATION

    system_prompt = (
        "You are the Fact Verification Specialist for AURA. "
        "Given a CLAIM and supporting EVIDENCE, evaluate whether the claim is: "
        "SUPPORTED (evidence clearly confirms it), "
        "REFUTED (evidence clearly contradicts it), "
        "INSUFFICIENT_EVIDENCE (not enough information to judge), or "
        "UNCERTAIN (mixed or ambiguous signals). "
        "Output JSON with fields: verdict, confidence (0.0-1.0), reasoning, "
        "and supporting_citations (list of source references)."
    )

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        started = datetime.now(UTC)
        evidence: list[str] = agent_input.context.get("evidence", [])
        if evidence:
            evidence_block = "\n".join(f"- {e}" for e in evidence)
        else:
            evidence_block = "No evidence provided."

        messages = [
            ChatMessage(role="system", content=self.system_prompt),
            ChatMessage(
                role="user",
                content=(f"CLAIM: {agent_input.task}\n\nEVIDENCE:\n{evidence_block}"),
            ),
        ]
        try:
            verdict = await self._complete(messages, max_tokens=500, temperature=0.0)
            duration = (datetime.now(UTC) - started).total_seconds() * 1000
            return AgentOutput(
                agent_role=self.role,
                success=True,
                result=verdict,
                metadata={"evidence_items": len(evidence)},
                duration_ms=duration,
            )
        except Exception as exc:
            logger.exception("VerificationAgent failed: %s", exc)
            duration = (datetime.now(UTC) - started).total_seconds() * 1000
            return AgentOutput(
                agent_role=self.role,
                success=False,
                result="",
                error=str(exc),
                duration_ms=duration,
            )


# ---------------------------------------------------------------------------
# Orchestrator Agent
# ---------------------------------------------------------------------------


@dataclass
class OrchestrationPlan:
    """Parsed execution plan produced by the Orchestrator."""

    steps: list[dict[str, Any]] = field(default_factory=list)
    rationale: str = ""


class OrchestratorAgent(BaseSpecialistAgent):
    """Routes complex tasks to specialist agents and assembles final results.

    Workflow:
    1. Generates a structured plan (which specialists to invoke in what order).
    2. Executes each specialist in sequence, passing prior outputs as context.
    3. Compiles a final synthesized response.
    """

    role = AgentRole.ORCHESTRATOR

    PLANNING_PROMPT = (
        "You are the Orchestrator for AURA's multi-agent system. "
        "Given the user task, produce a JSON execution plan with a 'steps' list. "
        "Each step has: 'agent' (one of: research, memory, document, verification), "
        "'task' (specific sub-task instruction), 'rationale' (why this agent). "
        "Also include a top-level 'rationale' field explaining the overall plan. "
        "Only include agents that are necessary. Keep plans concise (≤ 4 steps)."
    )

    SYNTHESIS_PROMPT = (
        "You are the Orchestrator for AURA. "
        "Synthesize the outputs from the specialist agents into a final, coherent, "
        "actionable response for the user. Be concise and structured. "
        "Cite specialist agent outputs where appropriate."
    )

    def __init__(self, model_provider: BaseModelProvider | None = None) -> None:
        super().__init__(model_provider)
        self._specialists: dict[AgentRole, BaseSpecialistAgent] = {
            AgentRole.RESEARCH: ResearchAgent(model_provider),
            AgentRole.MEMORY: MemoryAgent(model_provider),
            AgentRole.DOCUMENT: DocumentAgent(model_provider),
            AgentRole.VERIFICATION: VerificationAgent(model_provider),
        }

    async def _plan(self, task: str) -> OrchestrationPlan:
        """Generate a step-by-step execution plan for the task."""
        import json

        messages = [
            ChatMessage(role="system", content=self.PLANNING_PROMPT),
            ChatMessage(role="user", content=f"TASK: {task}"),
        ]
        raw = await self._complete(messages, max_tokens=600, temperature=0.1)

        # Extract JSON block
        try:
            # Try to find JSON object in the response
            import re

            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                plan_data = json.loads(match.group(0))
                return OrchestrationPlan(
                    steps=plan_data.get("steps", []),
                    rationale=plan_data.get("rationale", ""),
                )
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "Orchestrator planning produced non-JSON output; using single-step fallback"
            )

        # Fallback: single research step
        return OrchestrationPlan(
            steps=[{"agent": "research", "task": task, "rationale": "Direct research fallback"}],
            rationale="Fallback plan: delegate directly to research agent.",
        )

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        """Execute the full orchestration workflow."""
        started = datetime.now(UTC)
        plan = await self._plan(agent_input.task)
        logger.info(
            "Orchestrator plan for user %s: %d steps — %s",
            agent_input.user_id,
            len(plan.steps),
            plan.rationale,
        )

        step_outputs: list[dict[str, Any]] = []
        accumulated_context = dict(agent_input.context)

        for i, step in enumerate(plan.steps):
            agent_name = step.get("agent", "research")
            sub_task = step.get("task", agent_input.task)
            step_rationale = step.get("rationale", "")

            try:
                role = AgentRole(agent_name)
            except ValueError:
                logger.warning("Unknown agent role '%s' in plan step %d — skipping", agent_name, i)
                continue

            specialist = self._specialists.get(role)
            if specialist is None:
                logger.warning("No specialist registered for role '%s' — skipping", role)
                continue

            step_input = AgentInput(
                user_id=agent_input.user_id,
                session=agent_input.session,
                task=sub_task,
                context=accumulated_context,
                conversation_history=agent_input.conversation_history,
            )

            logger.info("Orchestrator dispatching step %d to %s", i + 1, role)
            output = await specialist.run(step_input)

            step_outputs.append(
                {
                    "step": i + 1,
                    "agent": role.value,
                    "rationale": step_rationale,
                    "success": output.success,
                    "result": output.result,
                    "error": output.error,
                    "duration_ms": output.duration_ms,
                }
            )

            # Feed this step's result into context for subsequent steps
            if output.success:
                accumulated_context[f"{role.value}_output"] = output.result

        # Synthesize final answer
        step_lines = []
        for s in step_outputs:
            step_header = f"[{s['agent'].upper()} STEP {s['step']}]:"
            step_body = s["result"] if s["success"] else f"ERROR: {s['error']}"
            step_lines.append(f"{step_header}\n{step_body}")
        step_summary = "\n\n".join(step_lines)

        synthesis_messages = [
            ChatMessage(role="system", content=self.SYNTHESIS_PROMPT),
            ChatMessage(
                role="user",
                content=(
                    f"ORIGINAL TASK: {agent_input.task}\n\nSPECIALIST OUTPUTS:\n{step_summary}"
                ),
            ),
        ]

        try:
            final_answer = await self._complete(
                synthesis_messages, max_tokens=1000, temperature=0.2
            )
            duration = (datetime.now(UTC) - started).total_seconds() * 1000
            return AgentOutput(
                agent_role=self.role,
                success=True,
                result=final_answer,
                metadata={
                    "plan_rationale": plan.rationale,
                    "steps_executed": len(step_outputs),
                    "step_outputs": step_outputs,
                },
                duration_ms=duration,
            )
        except Exception as exc:
            logger.exception("Orchestrator synthesis failed: %s", exc)
            duration = (datetime.now(UTC) - started).total_seconds() * 1000
            return AgentOutput(
                agent_role=self.role,
                success=False,
                result="",
                error=str(exc),
                metadata={"step_outputs": step_outputs},
                duration_ms=duration,
            )


# ---------------------------------------------------------------------------
# Singleton Accessors
# ---------------------------------------------------------------------------

_orchestrator_instance: OrchestratorAgent | None = None


def get_orchestrator(model_provider: BaseModelProvider | None = None) -> OrchestratorAgent:
    """Return (or create) the module-level OrchestratorAgent singleton."""
    global _orchestrator_instance  # noqa: PLW0603
    if _orchestrator_instance is None:
        _orchestrator_instance = OrchestratorAgent(model_provider)
    return _orchestrator_instance
