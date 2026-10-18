"""Memory management and retrieval service.

Implements:
- Strict multi-tenant isolation on all operations.
- Semantic vector indexing and cosine distance calculation.
- Hybrid retrieval combining semantic embeddings with keyword token matching.
- Deduplication and versioning for superseded knowledge.
- GDPR-compliant data export and cascading hard deletion.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.schemas.memory import (
    MemoryCreateRequest,
    MemoryExportResponse,
    MemoryResponse,
    MemorySearchResult,
    MemoryUpdateRequest,
)
from backend.app.models.memory import Memory
from backend.app.services.embedding import (
    BaseEmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
)

logger = logging.getLogger("aura.memory")

# Cosine similarity threshold above which two memory statements are considered identical
DEDUPLICATION_THRESHOLD = 0.95


_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "as", "in", "for", "over",
    "and", "or", "to", "at", "does", "do", "did", "which", "what", "how",
    "who", "user", "of", "by", "with", "from",
}


def _tokenize(text: str) -> set[str]:
    raw_tokens = re.findall(r"\w+", text.lower())
    tokens = set()
    for t in raw_tokens:
        if t not in _STOP_WORDS and len(t) > 2:
            if t.endswith("ing") and len(t) > 5:
                t = t[:-3]
            elif t.endswith("ed") and len(t) > 4:
                t = t[:-2]
            elif t.endswith("es") and len(t) > 4:
                t = t[:-2]
            elif t.endswith("s") and len(t) > 3:
                t = t[:-1]
            tokens.add(t)
    return tokens or set(raw_tokens)


def _compute_keyword_score(query: str, text: str) -> float:
    """Compute lexical token overlap score between query and candidate text."""
    query_tokens = _tokenize(query)
    text_tokens = _tokenize(text)
    if not query_tokens or not text_tokens:
        return 0.0
    overlap = len(query_tokens & text_tokens)
    return overlap / len(query_tokens)


class MemoryService:
    """Service layer orchestrating persistent user memories."""

    def __init__(self, embedding_provider: BaseEmbeddingProvider | None = None) -> None:
        self.embedding_provider = embedding_provider or get_embedding_provider()

    async def create_memory(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        data: MemoryCreateRequest,
    ) -> Memory:
        """Create a new memory entry for the given user, with embedding & deduplication."""
        embedding = await self.embedding_provider.embed_text(data.content)

        # Check for near-duplicates in the user's active memories
        active_memories = await self.list_memories(
            session=session,
            user_id=user_id,
            category=data.category,
            limit=100,
        )

        for existing in active_memories:
            if existing.embedding:
                sim = cosine_similarity(embedding, existing.embedding)
                if sim >= DEDUPLICATION_THRESHOLD:
                    logger.info(
                        "Deduplication triggered: new memory is duplicate of %s (sim=%.3f)",
                        existing.id,
                        sim,
                    )
                    # Refresh existing memory metadata/confidence if updated
                    existing.confidence = max(existing.confidence, data.confidence)
                    existing.updated_at = datetime.now(UTC)
                    await session.flush()
                    return existing

        new_memory = Memory(
            user_id=user_id,
            content=data.content,
            category=data.category,
            sensitivity=data.sensitivity,
            source=data.source,
            confidence=data.confidence,
            version=1,
            is_active=True,
            is_deleted=False,
            embedding=embedding,
            metadata_json=data.metadata_json,
        )
        session.add(new_memory)
        await session.flush()
        logger.info("Created memory id=%s for user_id=%s", new_memory.id, user_id)
        return new_memory

    async def get_memory(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
    ) -> Memory | None:
        """Fetch a specific memory item enforcing tenant isolation."""
        stmt = select(Memory).where(
            Memory.id == memory_id,
            Memory.user_id == user_id,
            Memory.is_deleted.is_(False),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_memories(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        category: str | None = None,
        sensitivity: str | None = None,
        is_active: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Memory]:
        """List active memories for an authenticated user with optional filtering."""
        stmt = select(Memory).where(
            Memory.user_id == user_id,
            Memory.is_deleted.is_(False),
            Memory.is_active == is_active,
        )
        if category:
            stmt = stmt.where(Memory.category == category)
        if sensitivity:
            stmt = stmt.where(Memory.sensitivity == sensitivity)

        stmt = stmt.order_by(Memory.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_memory(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        data: MemoryUpdateRequest,
    ) -> Memory | None:
        """Update a memory item, re-embedding if content modified and incrementing version."""
        memory = await self.get_memory(session, user_id, memory_id)
        if memory is None:
            return None

        if data.content is not None and data.content != memory.content:
            memory.content = data.content
            memory.embedding = await self.embedding_provider.embed_text(data.content)
            memory.version += 1

        if data.category is not None:
            memory.category = data.category
        if data.sensitivity is not None:
            memory.sensitivity = data.sensitivity
        if data.confidence is not None:
            memory.confidence = data.confidence
        if data.is_active is not None:
            memory.is_active = data.is_active
        if data.metadata_json is not None:
            memory.metadata_json = data.metadata_json

        memory.updated_at = datetime.now(UTC)
        await session.flush()
        logger.info("Updated memory id=%s version=%d", memory.id, memory.version)
        return memory

    async def delete_memory(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        hard_delete: bool = False,
    ) -> bool:
        """Delete a memory item enforcing tenant isolation."""
        memory = await self.get_memory(session, user_id, memory_id)
        if memory is None:
            return False

        if hard_delete:
            await session.delete(memory)
        else:
            memory.is_deleted = True
            memory.is_active = False
            memory.updated_at = datetime.now(UTC)

        await session.flush()
        logger.info(
            "Deleted memory id=%s (hard_delete=%s) user_id=%s",
            memory_id,
            hard_delete,
            user_id,
        )
        return True

    async def hybrid_search(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        query: str,
        limit: int = 5,
        threshold: float = 0.1,
        category: str | None = None,
        sensitivity: str | None = None,
    ) -> list[MemorySearchResult]:
        """Perform hybrid (semantic + keyword) retrieval over the user's active memories."""
        query_embedding = await self.embedding_provider.embed_text(query)

        # Retrieve active candidates for this tenant
        candidates = await self.list_memories(
            session=session,
            user_id=user_id,
            category=category,
            sensitivity=sensitivity,
            limit=200,
        )

        scored_results: list[tuple[Memory, float, str]] = []

        for mem in candidates:
            semantic_score = 0.0
            if mem.embedding:
                # Cosine similarity in range [-1.0, 1.0], normalized to [0.0, 1.0]
                cos_sim = cosine_similarity(query_embedding, mem.embedding)
                semantic_score = max(0.0, cos_sim)

            keyword_score = _compute_keyword_score(query, mem.content)

            # Hybrid weighted combination
            hybrid_score = (0.7 * semantic_score) + (0.3 * keyword_score)

            if hybrid_score >= threshold:
                match_type = "hybrid"
                if semantic_score > 0.4 and keyword_score > 0.3:
                    match_type = "hybrid"
                elif semantic_score > 0.4:
                    match_type = "semantic"
                else:
                    match_type = "keyword"

                scored_results.append((mem, hybrid_score, match_type))

        # Sort descending by hybrid score
        scored_results.sort(key=lambda x: x[1], reverse=True)

        return [
            MemorySearchResult(
                memory=MemoryResponse.model_validate(mem),
                score=round(score, 4),
                match_type=match_type,
            )
            for mem, score, match_type in scored_results[:limit]
        ]

    async def export_all_memories(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
    ) -> MemoryExportResponse:
        """Export all memories for an authenticated user (GDPR data portability)."""
        memories = await self.list_memories(
            session=session,
            user_id=user_id,
            limit=10000,
        )
        return MemoryExportResponse(
            user_id=user_id,
            exported_at=datetime.now(UTC),
            total_count=len(memories),
            memories=[MemoryResponse.model_validate(m) for m in memories],
        )

    async def purge_all_memories(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
    ) -> int:
        """Cascading hard-delete of all user memories (GDPR right-to-be-forgotten)."""
        stmt = delete(Memory).where(Memory.user_id == user_id)
        result = await session.execute(stmt)
        deleted_count = int(result.rowcount)
        await session.flush()
        logger.warning(
            "GDPR Purge executed: %d memories deleted for user_id=%s",
            deleted_count,
            user_id,
        )
        return deleted_count
