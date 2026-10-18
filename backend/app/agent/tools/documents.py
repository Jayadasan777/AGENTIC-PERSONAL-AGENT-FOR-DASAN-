"""Document search and grounded RAG query tool for AURA Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.agent.tools.base import AgentTool, RiskTier, ToolContext, ToolResult
from backend.app.services.rag import RAGService

_rag_service = RAGService()


class DocumentSearchArgs(BaseModel):
    """Input parameters for searching indexed documents."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Search query or question to find in indexed documents.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Max citation chunks to retrieve.",
    )


class DocumentSearchTool(AgentTool):
    """Search uploaded user documents and return grounded citations."""

    name = "search_documents"
    description = (
        "Search through indexed PDF, DOCX, and markdown documents uploaded by the user. "
        "Returns grounded context snippets with document name and page number citations."
    )
    risk_tier = RiskTier.READ_ONLY
    args_schema = DocumentSearchArgs

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        limit = kwargs.get("limit", 5)
        try:
            chunks = await _rag_service.retrieve_relevant_chunks(
                session=context.session,
                user_id=context.user_id,
                query=query,
                limit=limit,
            )
            data = [
                {
                    "chunk_id": str(chunk.id),
                    "document_name": (chunk.document.filename if chunk.document else "Unknown"),
                    "page_number": chunk.page_number,
                    "section_heading": chunk.section_heading,
                    "content": chunk.content,
                    "score": round(score, 4),
                }
                for chunk, score in chunks
            ]
            return ToolResult(success=True, data=data)
        except Exception as err:
            return ToolResult(success=False, error=f"Document search failed: {err}")
