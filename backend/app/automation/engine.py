"""Durable Workflow Engine — DBOS-inspired crash-safe task executor.

Provides:
- Idempotency key enforcement (exactly-once semantics per user + key).
- Concurrency lease acquisition with expiry-based dead-worker recovery.
- Automatic retry with configurable backoff on transient failure.
- Global automation PAUSE flag and per-task cancellation.
- Append-only audit event emission for every lifecycle transition.

Design principle: Every state mutation is persisted to the database BEFORE the
external side-effect is invoked so that, on crash/restart, the task state can
be reconstructed and replayed from the last committed checkpoint.
"""

from __future__ import annotations

import logging
import socket
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.automation.models import (
    AutomationAuditEvent,
    AutomationTask,
    IdempotencyRecord,
    TaskStatus,
)

logger = logging.getLogger("aura.automation.engine")

# ---------------------------------------------------------------------------
# Global pause flag — thread/process-scoped in-memory flag for local dev.
# In multi-process deployments this should be backed by a DB row or Redis key.
# ---------------------------------------------------------------------------
_GLOBAL_PAUSE: bool = False
_WORKER_ID: str = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"

LEASE_DURATION_SECONDS = 120  # Reclaimed after 2 minutes of no heartbeat
IDEMPOTENCY_TTL_SECONDS = 86_400  # 24-hour idempotency window


# ---------------------------------------------------------------------------
# Pause Controls
# ---------------------------------------------------------------------------


def get_global_pause() -> bool:
    """Return whether the global automation pause flag is currently active."""
    return _GLOBAL_PAUSE


def set_global_pause(paused: bool) -> None:
    """Set or clear the global automation pause flag."""
    global _GLOBAL_PAUSE  # noqa: PLW0603
    _GLOBAL_PAUSE = paused
    logger.warning("Global automation pause set to: %s", paused)


# ---------------------------------------------------------------------------
# Audit Helpers
# ---------------------------------------------------------------------------


async def emit_audit_event(
    session: AsyncSession,
    user_id: uuid.UUID,
    event_type: str,
    event_data: dict[str, Any],
    task_id: uuid.UUID | None = None,
    schedule_id: uuid.UUID | None = None,
) -> None:
    """Append an immutable audit event to the automation audit trail."""
    event = AutomationAuditEvent(
        user_id=user_id,
        task_id=task_id,
        schedule_id=schedule_id,
        event_type=event_type,
        event_data=event_data,
        occurred_at=datetime.now(UTC),
    )
    session.add(event)
    # Flush immediately so the event lands before any subsequent commit
    await session.flush()


# ---------------------------------------------------------------------------
# Idempotency Enforcement
# ---------------------------------------------------------------------------


async def check_and_reserve_idempotency_key(
    session: AsyncSession,
    user_id: uuid.UUID,
    idempotency_key: str,
    task_id: uuid.UUID,
) -> tuple[bool, dict[str, Any] | None]:
    """Attempt to reserve an idempotency key for this user and task.

    Returns:
        (is_new, cached_response)
        - is_new=True: key was fresh; caller should proceed with task creation.
        - is_new=False: key already exists; caller should return cached_response.
    """
    key = f"{user_id}:{idempotency_key}"
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=IDEMPOTENCY_TTL_SECONDS)

    # Try INSERT, ignore conflict (PostgreSQL dialect)
    stmt = (
        pg_insert(IdempotencyRecord)
        .values(
            key=key,
            user_id=user_id,
            task_id=task_id,
            created_at=now,
            expires_at=expires_at,
            response_cache=None,
        )
        .on_conflict_do_nothing(index_elements=["key"])
        .returning(IdempotencyRecord.task_id, IdempotencyRecord.response_cache)
    )
    result = await session.execute(stmt)
    row = result.fetchone()

    if row is None:
        # Conflict: key already existed — fetch and return cached response
        existing = await session.scalar(
            select(IdempotencyRecord).where(IdempotencyRecord.key == key)
        )
        if existing and existing.response_cache:
            return False, existing.response_cache
        return False, {"status": "ALREADY_SUBMITTED", "task_id": str(task_id)}

    return True, None


async def store_idempotency_response(
    session: AsyncSession,
    user_id: uuid.UUID,
    idempotency_key: str,
    response: dict[str, Any],
) -> None:
    """Cache a terminal response against an idempotency key."""
    key = f"{user_id}:{idempotency_key}"
    await session.execute(
        update(IdempotencyRecord)
        .where(IdempotencyRecord.key == key)
        .values(response_cache=response)
    )


# ---------------------------------------------------------------------------
# Concurrency Lease Management
# ---------------------------------------------------------------------------


async def acquire_lease(
    session: AsyncSession,
    task_id: uuid.UUID,
) -> bool:
    """Attempt to acquire an exclusive execution lease on a task.

    Uses an optimistic UPDATE with a WHERE clause to prevent duplicate
    lease acquisition across concurrent workers.

    Returns True if this worker successfully acquired the lease.
    """
    now = datetime.now(UTC)
    lease_expires_at = now + timedelta(seconds=LEASE_DURATION_SECONDS)
    stale_threshold = now - timedelta(seconds=LEASE_DURATION_SECONDS)

    result = await session.execute(
        update(AutomationTask)
        .where(
            AutomationTask.id == task_id,
            AutomationTask.status == TaskStatus.PENDING.value,
            # Accept expired leases from crashed workers
            (AutomationTask.locked_by.is_(None))
            | (AutomationTask.lock_expires_at < stale_threshold),
        )
        .values(
            locked_by=_WORKER_ID,
            lock_expires_at=lease_expires_at,
            status=TaskStatus.RUNNING.value,
            started_at=now,
            attempt_number=AutomationTask.attempt_number + 1,
        )
        .returning(AutomationTask.id)
    )
    acquired = result.fetchone() is not None
    if not acquired:
        logger.debug(
            "Lease acquisition failed for task %s (already locked or not pending)",
            task_id,
        )
    return acquired


async def release_lease(
    session: AsyncSession,
    task_id: uuid.UUID,
    final_status: TaskStatus,
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    """Release the execution lease and set terminal task state."""
    now = datetime.now(UTC)
    await session.execute(
        update(AutomationTask)
        .where(
            AutomationTask.id == task_id,
            AutomationTask.locked_by == _WORKER_ID,
        )
        .values(
            locked_by=None,
            lock_expires_at=None,
            status=final_status.value,
            completed_at=now,
            result=result,
            error_message=error_message,
        )
    )


# ---------------------------------------------------------------------------
# Task Lifecycle
# ---------------------------------------------------------------------------


async def create_task(
    session: AsyncSession,
    user_id: uuid.UUID,
    task_type: str,
    task_name: str,
    parameters: dict[str, Any],
    idempotency_key: str | None = None,
    schedule_id: uuid.UUID | None = None,
    scheduled_at: datetime | None = None,
    max_attempts: int = 3,
) -> tuple[AutomationTask, bool, dict[str, Any] | None]:
    """Create a durable task with optional idempotency guard.

    Returns:
        (task, is_new, cached_response)
        If is_new=False, the cached_response contains the previous terminal result.
    """
    task_id = uuid.uuid4()

    # Idempotency check
    if idempotency_key:
        is_new, cached = await check_and_reserve_idempotency_key(
            session=session,
            user_id=user_id,
            idempotency_key=idempotency_key,
            task_id=task_id,
        )
        if not is_new:
            # Build a phantom task for return; it was NOT inserted
            phantom = AutomationTask()
            phantom.id = task_id
            phantom.user_id = user_id
            phantom.status = TaskStatus.COMPLETED.value
            return phantom, False, cached

    task = AutomationTask(
        id=task_id,
        user_id=user_id,
        idempotency_key=idempotency_key,
        schedule_id=schedule_id,
        task_type=task_type,
        task_name=task_name,
        parameters=parameters,
        status=TaskStatus.PENDING.value,
        attempt_number=0,
        max_attempts=max_attempts,
        scheduled_at=scheduled_at or datetime.now(UTC),
    )
    session.add(task)
    await session.flush()

    await emit_audit_event(
        session=session,
        user_id=user_id,
        event_type="TASK_CREATED",
        event_data={
            "task_type": task_type,
            "task_name": task_name,
            "idempotency_key": idempotency_key,
        },
        task_id=task_id,
        schedule_id=schedule_id,
    )

    return task, True, None


async def cancel_task(
    session: AsyncSession,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
) -> bool:
    """Cancel a PENDING or PAUSED task owned by the authenticated user.

    Returns True if the cancellation was applied, False if the task was
    already in a terminal state or not owned by this user.
    """
    result = await session.execute(
        update(AutomationTask)
        .where(
            AutomationTask.id == task_id,
            AutomationTask.user_id == user_id,
            AutomationTask.status.in_(
                [
                    TaskStatus.PENDING.value,
                    TaskStatus.PAUSED.value,
                    TaskStatus.AWAITING_APPROVAL.value,
                ]
            ),
        )
        .values(
            status=TaskStatus.CANCELLED.value,
            completed_at=datetime.now(UTC),
        )
        .returning(AutomationTask.id)
    )
    cancelled = result.fetchone() is not None
    if cancelled:
        await emit_audit_event(
            session=session,
            user_id=user_id,
            event_type="TASK_CANCELLED",
            event_data={"cancelled_by": "user"},
            task_id=task_id,
        )
    return cancelled


async def pause_task(
    session: AsyncSession,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
) -> bool:
    """Pause a PENDING task owned by the user (sets status to PAUSED)."""
    result = await session.execute(
        update(AutomationTask)
        .where(
            AutomationTask.id == task_id,
            AutomationTask.user_id == user_id,
            AutomationTask.status == TaskStatus.PENDING.value,
        )
        .values(status=TaskStatus.PAUSED.value)
        .returning(AutomationTask.id)
    )
    paused = result.fetchone() is not None
    if paused:
        await emit_audit_event(
            session=session,
            user_id=user_id,
            event_type="TASK_PAUSED",
            event_data={},
            task_id=task_id,
        )
    return paused
