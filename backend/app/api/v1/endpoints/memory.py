"""API v1 endpoints for Personal Memory operations.

Enforces strict tenant isolation: every operation requires an authenticated user,
and memory items are verified against the requester's ID before any read/write.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.dependencies.auth import get_current_active_user
from backend.app.api.v1.schemas.memory import (
    MemoryCreateRequest,
    MemoryExportResponse,
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryUpdateRequest,
)
from backend.app.db.session import get_async_session
from backend.app.models.user import User
from backend.app.services.memory import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])
_memory_service = MemoryService()


@router.post(
    "",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new personal memory",
)
async def create_memory(
    body: MemoryCreateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MemoryResponse:
    """Store a new memory item for the authenticated user."""
    memory = await _memory_service.create_memory(
        session=session,
        user_id=current_user.id,
        data=body,
    )
    await session.commit()
    await session.refresh(memory)
    return MemoryResponse.model_validate(memory)


@router.get(
    "",
    response_model=list[MemoryResponse],
    summary="List memories for the current user",
)
async def list_memories(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    category: str | None = Query(default=None, description="Filter by category"),
    sensitivity: str | None = Query(default=None, description="Filter by sensitivity"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[MemoryResponse]:
    """Retrieve all active memories belonging to the authenticated user."""
    memories = await _memory_service.list_memories(
        session=session,
        user_id=current_user.id,
        category=category,
        sensitivity=sensitivity,
        limit=limit,
        offset=offset,
    )
    return [MemoryResponse.model_validate(m) for m in memories]


@router.get(
    "/export",
    response_model=MemoryExportResponse,
    summary="GDPR data export for personal memories",
)
async def export_memories(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MemoryExportResponse:
    """Export all stored memories for the authenticated user."""
    return await _memory_service.export_all_memories(
        session=session,
        user_id=current_user.id,
    )


@router.delete(
    "/all",
    status_code=status.HTTP_200_OK,
    summary="GDPR right-to-be-forgotten cascading memory purge",
)
async def purge_memories(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> dict[str, int | str]:
    """Hard-delete all memories belonging to the authenticated user."""
    deleted_count = await _memory_service.purge_all_memories(
        session=session,
        user_id=current_user.id,
    )
    await session.commit()
    return {"message": "All memories permanently deleted", "deleted_count": deleted_count}


@router.post(
    "/search",
    response_model=list[MemorySearchResult],
    summary="Hybrid semantic and keyword memory search",
)
async def search_memories(
    body: MemorySearchRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[MemorySearchResult]:
    """Perform hybrid retrieval over the authenticated user's memories."""
    return await _memory_service.hybrid_search(
        session=session,
        user_id=current_user.id,
        query=body.query,
        limit=body.limit,
        threshold=body.threshold,
        category=body.category,
        sensitivity=body.sensitivity,
    )


@router.get(
    "/{memory_id}",
    response_model=MemoryResponse,
    summary="Get single memory by ID",
)
async def get_memory(
    memory_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MemoryResponse:
    """Retrieve a single memory item, strictly owned by the caller."""
    memory = await _memory_service.get_memory(
        session=session,
        user_id=current_user.id,
        memory_id=memory_id,
    )
    if memory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    return MemoryResponse.model_validate(memory)


@router.put(
    "/{memory_id}",
    response_model=MemoryResponse,
    summary="Update a memory item",
)
async def update_memory(
    memory_id: uuid.UUID,
    body: MemoryUpdateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MemoryResponse:
    """Update an existing memory item."""
    memory = await _memory_service.update_memory(
        session=session,
        user_id=current_user.id,
        memory_id=memory_id,
        data=body,
    )
    if memory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    await session.commit()
    await session.refresh(memory)
    return MemoryResponse.model_validate(memory)


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a memory item",
)
async def delete_memory(
    memory_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    hard: bool = Query(default=False, description="Perform hard delete if true"),
) -> None:
    """Delete a memory item (soft delete by default, hard delete if ?hard=true)."""
    deleted = await _memory_service.delete_memory(
        session=session,
        user_id=current_user.id,
        memory_id=memory_id,
        hard_delete=hard,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    await session.commit()
