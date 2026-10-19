"""Offline Operation Queue Replay and Batch Sync Processor.

Handles ordered execution of offline client mutations upon network reconnection.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.sync.models import SyncChangeRecord, SyncCursor
from backend.app.sync.protocol import (
    record_sync_change,
    resolve_conflict_lww,
)

logger = logging.getLogger("aura.sync.queue")


@dataclass(frozen=True)
class BatchSyncResponse:
    """Summary of batch offline queue processing."""

    applied_count: int
    conflicted_count: int
    skipped_count: int
    latest_cursor: str
    results: list[dict[str, Any]]


async def process_offline_batch(
    session: AsyncSession,
    user_id: uuid.UUID,
    mutations: list[dict[str, Any]],
) -> BatchSyncResponse:
    """Replay a batch of queued offline operations with conflict and idempotency checks."""
    applied = 0
    conflicted = 0
    skipped = 0
    results: list[dict[str, Any]] = []

    for mut in mutations:
        mutation_id = mut.get("mutation_id")
        entity_type = mut.get("entity_type", "MEMORY")
        entity_id_raw = mut.get("entity_id")
        change_type = mut.get("change_type", "UPDATE")
        payload = mut.get("payload", {})
        client_ts_raw = mut.get("client_timestamp")
        base_cursor = mut.get("base_cursor")

        try:
            entity_uuid = uuid.UUID(entity_id_raw) if entity_id_raw else uuid.uuid4()
        except (ValueError, TypeError):
            entity_uuid = uuid.uuid4()

        client_dt = datetime.now(UTC)
        if client_ts_raw:
            try:
                client_dt = datetime.fromisoformat(client_ts_raw.replace("Z", "+00:00"))
            except ValueError:
                pass

        # 1. Idempotency Check: Was this mutation_id already applied?
        if mutation_id:
            dup_stmt = select(SyncChangeRecord).where(
                SyncChangeRecord.user_id == user_id,
                SyncChangeRecord.client_mutation_id == mutation_id,
            )
            existing = (await session.execute(dup_stmt)).scalar_one_or_none()
            if existing:
                skipped += 1
                results.append(
                    {
                        "mutation_id": mutation_id,
                        "status": "SKIPPED_DUPLICATE",
                        "server_seq": existing.server_seq,
                    }
                )
                continue

        # 2. Conflict Check: Did another mutation happen to this entity since base_cursor?
        base_seq = SyncCursor.decode(base_cursor)
        conflict_stmt = (
            select(SyncChangeRecord)
            .where(
                SyncChangeRecord.user_id == user_id,
                SyncChangeRecord.entity_id == entity_uuid,
                SyncChangeRecord.server_seq > base_seq,
            )
            .order_by(SyncChangeRecord.server_seq.desc())
        )
        recent_server_edit = (await session.execute(conflict_stmt)).scalars().first()

        if recent_server_edit:
            # Concurrent edit detected -> run LWW resolution
            server_dict = {
                "payload": recent_server_edit.payload_json,
                "client_timestamp": recent_server_edit.client_timestamp.isoformat(),
                "created_at": recent_server_edit.created_at.isoformat(),
            }
            client_dict = {
                "payload": payload,
                "client_timestamp": client_dt.isoformat(),
            }
            resolution = resolve_conflict_lww(server_dict, client_dict)

            if not resolution.applied:
                # Server wins; reject client mutation
                conflicted += 1
                results.append(
                    {
                        "mutation_id": mutation_id,
                        "status": "CONFLICT_SERVER_WON",
                        "reason": resolution.conflict_reason,
                        "server_payload": resolution.resolved_payload,
                    }
                )
                continue

        # 3. Apply mutation into changelog
        record = await record_sync_change(
            session=session,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_uuid,
            change_type=change_type,
            payload=payload,
            client_mutation_id=mutation_id,
            client_timestamp=client_dt,
        )
        applied += 1
        results.append(
            {
                "mutation_id": mutation_id,
                "status": "APPLIED",
                "server_seq": record.server_seq,
            }
        )

    # Compute latest cursor
    latest_stmt = (
        select(SyncChangeRecord.server_seq)
        .where(SyncChangeRecord.user_id == user_id)
        .order_by(SyncChangeRecord.server_seq.desc())
        .limit(1)
    )
    max_seq = (await session.execute(latest_stmt)).scalar() or 0
    latest_cursor = SyncCursor.encode(max_seq)

    return BatchSyncResponse(
        applied_count=applied,
        conflicted_count=conflicted,
        skipped_count=skipped,
        latest_cursor=latest_cursor,
        results=results,
    )
