"""Cursor-Based Synchronization Protocol and Conflict Resolution Engine.

Implements delta synchronization with monotonic sequence numbers, Lamport
timestamp ordering, and Last-Write-Wins (LWW) conflict handling.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.sync.models import (
    SyncChangeRecord,
    SyncChangeType,
    SyncCursor,
    SyncEntityType,
)

logger = logging.getLogger("aura.sync.protocol")


@dataclass(frozen=True)
class SyncChangesResult:
    """Result payload for client delta fetch."""

    changes: list[dict[str, Any]]
    next_cursor: str
    has_more: bool
    latest_server_seq: int


@dataclass(frozen=True)
class ConflictResolution:
    """Outcome of resolving concurrent conflicting edits."""

    winner: str  # "SERVER" or "CLIENT"
    applied: bool
    resolved_payload: dict[str, Any]
    conflict_reason: str | None


async def get_next_server_seq(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Return the next monotonically increasing sequence number for this user."""
    stmt = select(func.coalesce(func.max(SyncChangeRecord.server_seq), 0)).where(
        SyncChangeRecord.user_id == user_id
    )
    result = await session.execute(stmt)
    current_max = result.scalar() or 0
    return current_max + 1


async def record_sync_change(
    session: AsyncSession,
    user_id: uuid.UUID,
    entity_type: SyncEntityType | str,
    entity_id: uuid.UUID,
    change_type: SyncChangeType | str,
    payload: dict[str, Any],
    client_mutation_id: str | None = None,
    client_timestamp: datetime | None = None,
) -> SyncChangeRecord:
    """Append a mutation to the user's synchronization changelog."""
    next_seq = await get_next_server_seq(session, user_id)
    entity_str = entity_type.value if isinstance(entity_type, SyncEntityType) else entity_type
    change_str = change_type.value if isinstance(change_type, SyncChangeType) else change_type

    now = datetime.now(UTC)
    record = SyncChangeRecord(
        user_id=user_id,
        server_seq=next_seq,
        entity_type=entity_str,
        entity_id=entity_id,
        change_type=change_str,
        payload_json=payload,
        client_mutation_id=client_mutation_id,
        client_timestamp=client_timestamp or now,
    )
    session.add(record)
    await session.flush()
    return record


async def get_changes_since(
    session: AsyncSession,
    user_id: uuid.UUID,
    cursor_str: str | None,
    limit: int = 50,
) -> SyncChangesResult:
    """Fetch delta changes committed after the given cursor."""
    after_seq = SyncCursor.decode(cursor_str)

    stmt = (
        select(SyncChangeRecord)
        .where(
            SyncChangeRecord.user_id == user_id,
            SyncChangeRecord.server_seq > after_seq,
        )
        .order_by(SyncChangeRecord.server_seq.asc())
        .limit(limit + 1)
    )
    results = (await session.execute(stmt)).scalars().all()

    has_more = len(results) > limit
    returned_records = results[:limit]

    changes_list: list[dict[str, Any]] = []
    max_seq = after_seq

    for r in returned_records:
        if r.server_seq > max_seq:
            max_seq = r.server_seq
        changes_list.append(
            {
                "id": str(r.id),
                "server_seq": r.server_seq,
                "entity_type": r.entity_type,
                "entity_id": str(r.entity_id),
                "change_type": r.change_type,
                "payload": r.payload_json,
                "client_mutation_id": r.client_mutation_id,
                "client_timestamp": r.client_timestamp.isoformat(),
                "created_at": r.created_at.isoformat(),
            }
        )

    next_cursor = SyncCursor.encode(max_seq)
    return SyncChangesResult(
        changes=changes_list,
        next_cursor=next_cursor,
        has_more=has_more,
        latest_server_seq=max_seq,
    )


def resolve_conflict_lww(
    server_record: dict[str, Any],
    client_mutation: dict[str, Any],
) -> ConflictResolution:
    """Resolve concurrent edit conflict using Last-Write-Wins (LWW) with tie-breaking.

    Args:
        server_record: The existing latest state on the server.
        client_mutation: The incoming queued mutation from the disconnected client.

    Returns:
        ConflictResolution specifying winner and resulting state.
    """
    server_time_str = server_record.get("client_timestamp") or server_record.get("created_at")
    client_time_str = client_mutation.get("client_timestamp")

    if not server_time_str or not client_time_str:
        # Default to Server-Wins on missing timestamp
        return ConflictResolution(
            winner="SERVER",
            applied=False,
            resolved_payload=server_record.get("payload", {}),
            conflict_reason="Missing timestamp metadata; defaulting to server state.",
        )

    try:
        server_dt = datetime.fromisoformat(server_time_str.replace("Z", "+00:00"))
        client_dt = datetime.fromisoformat(client_time_str.replace("Z", "+00:00"))
        if server_dt.tzinfo is None:
            server_dt = server_dt.replace(tzinfo=UTC)
        if client_dt.tzinfo is None:
            client_dt = client_dt.replace(tzinfo=UTC)
    except ValueError:
        return ConflictResolution(
            winner="SERVER",
            applied=False,
            resolved_payload=server_record.get("payload", {}),
            conflict_reason="Invalid ISO timestamp format; defaulting to server state.",
        )

    # Client timestamp is strictly newer -> Client Wins
    if client_dt > server_dt:
        return ConflictResolution(
            winner="CLIENT",
            applied=True,
            resolved_payload=client_mutation.get("payload", {}),
            conflict_reason=(
                f"Client timestamp ({client_dt.isoformat()}) "
                f"is newer than server ({server_dt.isoformat()})."
            ),
        )

    # Server timestamp is equal or newer -> Server Wins
    return ConflictResolution(
        winner="SERVER",
        applied=False,
        resolved_payload=server_record.get("payload", {}),
        conflict_reason=(
            f"Server timestamp ({server_dt.isoformat()}) "
            f"is equal or newer than client ({client_dt.isoformat()})."
        ),
    )
