"""Cross-Device Synchronization REST API Endpoints.

Provides:
- GET  /sync/changes — Fetch delta changes since an opaque cursor token.
- POST /sync/push    — Submit queued offline mutations with conflict resolution.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.dependencies.auth import get_current_user
from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.sync.protocol import get_changes_since
from backend.app.sync.queue import process_offline_batch

router = APIRouter(prefix="/sync", tags=["Synchronization"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class SyncChangesResponse(BaseModel):
    changes: list[dict[str, Any]]
    next_cursor: str
    has_more: bool
    latest_server_seq: int


class OfflineMutationItem(BaseModel):
    mutation_id: str = Field(..., min_length=4, max_length=128)
    entity_type: str = Field(..., max_length=32)
    entity_id: str | None = Field(default=None)
    change_type: str = Field(..., pattern="^(INSERT|UPDATE|DELETE)$")
    payload: dict[str, Any] = Field(default_factory=dict)
    client_timestamp: str | None = Field(default=None)
    base_cursor: str | None = Field(default=None)


class BatchSyncRequest(BaseModel):
    mutations: list[OfflineMutationItem] = Field(..., max_length=200)


class BatchSyncResponseModel(BaseModel):
    applied_count: int
    conflicted_count: int
    skipped_count: int
    latest_cursor: str
    results: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/changes",
    response_model=SyncChangesResponse,
    summary="Fetch delta changes since cursor",
)
async def fetch_changes(
    cursor: str | None = Query(None, description="Opaque cursor token from previous sync"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SyncChangesResponse:
    """Return all server mutations occurring after cursor for the authenticated user."""
    res = await get_changes_since(
        session=db,
        user_id=current_user.id,
        cursor_str=cursor,
        limit=limit,
    )
    return SyncChangesResponse(
        changes=res.changes,
        next_cursor=res.next_cursor,
        has_more=res.has_more,
        latest_server_seq=res.latest_server_seq,
    )


@router.post(
    "/push",
    response_model=BatchSyncResponseModel,
    status_code=status.HTTP_200_OK,
    summary="Push queued offline mutations to server",
)
async def push_offline_mutations(
    payload: BatchSyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BatchSyncResponseModel:
    """Replay a batch of client mutations accumulated while offline."""
    mutations_dicts = [m.model_dump() for m in payload.mutations]
    res = await process_offline_batch(
        session=db,
        user_id=current_user.id,
        mutations=mutations_dicts,
    )
    await db.commit()
    return BatchSyncResponseModel(
        applied_count=res.applied_count,
        conflicted_count=res.conflicted_count,
        skipped_count=res.skipped_count,
        latest_cursor=res.latest_cursor,
        results=res.results,
    )
