"""Personal memory search and note creation tools for AURA Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.agent.tools.base import AgentTool, RiskTier, ToolContext, ToolResult
from backend.app.api.v1.schemas.memory import MemoryCreateRequest
from backend.app.services.memory import MemoryService

_memory_service = MemoryService()


class MemorySearchArgs(BaseModel):
    """Input parameters for searching personal memories."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Search query to locate relevant user memories.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Max memory items to retrieve.",
    )


class MemorySearchTool(AgentTool):
    """Search personal memories and past facts stored by the user."""

    name = "search_memory"
    description = (
        "Search through the authenticated user's personal memories, notes, and preferences. "
        "Use this tool whenever recalling user background, facts, or past details."
    )
    risk_tier = RiskTier.READ_ONLY
    args_schema = MemorySearchArgs

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        limit = kwargs.get("limit", 5)
        try:
            results = await _memory_service.hybrid_search(
                session=context.session,
                user_id=context.user_id,
                query=query,
                limit=limit,
            )
            data = [
                {
                    "id": str(r.id),
                    "content": r.content,
                    "category": r.category,
                    "score": round(r.score, 4),
                }
                for r in results
            ]
            return ToolResult(success=True, data=data)
        except Exception as err:
            return ToolResult(success=False, error=f"Memory search failed: {err}")


class CreateNoteArgs(BaseModel):
    """Input parameters for recording a new personal note or memory."""

    content: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The note or memory content to record for the user.",
    )
    category: str = Field(
        default="general",
        description="Category classification (e.g. preference, work, personal, general).",
    )


class CreateNoteTool(AgentTool):
    """Record a new persistent note or memory for the authenticated user."""

    name = "create_note"
    description = (
        "Save a persistent note or memory for the authenticated user. "
        "State mutating operation requiring user authorization."
    )
    risk_tier = RiskTier.MUTATING
    args_schema = CreateNoteArgs

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        content = kwargs.get("content", "")
        category = kwargs.get("category", "general")
        try:
            req = MemoryCreateRequest(
                content=content,
                category=category,
                sensitivity="standard",
            )
            memory = await _memory_service.create_memory(
                session=context.session,
                user_id=context.user_id,
                data=req,
                provenance="agent_action",
            )
            await context.session.commit()
            return ToolResult(
                success=True,
                data={
                    "id": str(memory.id),
                    "content": memory.content,
                    "category": memory.category,
                    "status": "created",
                },
            )
        except Exception as err:
            return ToolResult(success=False, error=f"Failed to create note: {err}")
