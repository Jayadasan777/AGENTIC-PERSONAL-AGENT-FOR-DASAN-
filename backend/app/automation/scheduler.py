"""Cron-based schedule manager with timezone-aware next-run calculation.

Features:
- 5-field cron expression parsing (minute, hour, day, month, weekday).
- IANA timezone support (e.g., 'America/New_York', 'Asia/Kolkata').
- next_run_at pre-computation stored to the DB for efficient polling.
- Global pause flag respected: no new tasks are spawned while paused.
- Per-schedule pause and deletion.
- run_count ceiling via max_runs guard.

The scheduler is designed to be called from a lightweight background loop or
an async-compatible job queue (APScheduler, Celery beat, DBOS scheduler).
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.automation.engine import (
    cancel_task,
    create_task,
    emit_audit_event,
    get_global_pause,
)
from backend.app.automation.models import (
    AutomationSchedule,
    AutomationTask,
    ScheduleStatus,
    TaskStatus,
)

logger = logging.getLogger("aura.automation.scheduler")


# ---------------------------------------------------------------------------
# Cron Expression Utilities
# ---------------------------------------------------------------------------

_CRON_FIELDS = ("minute", "hour", "day", "month", "weekday")
_FIELD_RANGES = {
    "minute": (0, 59),
    "hour": (0, 23),
    "day": (1, 31),
    "month": (1, 12),
    "weekday": (0, 7),
}


def _parse_cron_field(field: str, min_val: int, max_val: int) -> list[int]:
    """Parse a single cron field into a sorted list of matching integers."""
    values: set[int] = set()

    for part in field.split(","):
        part = part.strip()

        if part == "*":
            values.update(range(min_val, max_val + 1))

        elif part.startswith("*/"):
            try:
                step = int(part[2:])
                if step <= 0:
                    raise ValueError(f"Step must be positive, got {step}")
                values.update(range(min_val, max_val + 1, step))
            except ValueError as exc:
                raise ValueError(f"Invalid cron step '{part}': {exc}") from exc

        elif "-" in part and "/" in part:
            range_part, step_part = part.split("/", 1)
            start_str, end_str = range_part.split("-", 1)
            start, end, step = int(start_str), int(end_str), int(step_part)
            values.update(range(start, end + 1, step))

        elif "-" in part:
            start_str, end_str = part.split("-", 1)
            start, end = int(start_str), int(end_str)
            values.update(range(start, end + 1))

        else:
            values.add(int(part))

    # Validate range
    for v in values:
        if not (min_val <= v <= max_val):
            raise ValueError(f"Value {v} out of range [{min_val}, {max_val}]")

    return sorted(values)


def parse_cron_expression(cron_expr: str) -> dict[str, list[int]]:
    """Parse a 5-field cron expression string into field → matching-values dict."""
    parts = re.split(r"\s+", cron_expr.strip())
    if len(parts) != 5:
        raise ValueError(
            f"Cron expression must have exactly 5 fields (got {len(parts)}): '{cron_expr}'"
        )
    result = {}
    for field_name, part in zip(_CRON_FIELDS, parts, strict=True):
        min_v, max_v = _FIELD_RANGES[field_name]
        result[field_name] = _parse_cron_field(part, min_v, max_v)
    return result


def compute_next_run(cron_expr: str, after: datetime, tz_name: str = "UTC") -> datetime:
    """Compute the next UTC datetime when `cron_expr` fires after `after`.

    Args:
        cron_expr: Standard 5-field cron expression.
        after: Reference UTC datetime (schedule evaluates strictly after this).
        tz_name: IANA timezone name for cron evaluation (e.g. 'Asia/Kolkata').

    Returns:
        Next run time in UTC.
    """
    try:
        import zoneinfo

        tz = zoneinfo.ZoneInfo(tz_name)
    except (ImportError, KeyError):
        logger.warning("Unknown timezone '%s', falling back to UTC", tz_name)
        import zoneinfo

        tz = zoneinfo.ZoneInfo("UTC")

    fields = parse_cron_expression(cron_expr)

    # Work in the target timezone; advance by 1 minute from reference
    local_after = after.astimezone(tz)
    candidate = local_after.replace(second=0, microsecond=0) + timedelta(minutes=1)

    # Iterate at most 366 days to find the next match
    for _ in range(366 * 24 * 60):
        cron_wday = candidate.isoweekday() % 7  # 0=Sun, 1=Mon, ..., 6=Sat
        wday_matches = (cron_wday in fields["weekday"]) or (
            cron_wday == 0 and 7 in fields["weekday"]
        )
        if (
            candidate.minute in fields["minute"]
            and candidate.hour in fields["hour"]
            and candidate.day in fields["day"]
            and candidate.month in fields["month"]
            and wday_matches
        ):
            return candidate.astimezone(UTC).replace(tzinfo=UTC)

        candidate += timedelta(minutes=1)

    raise ValueError(f"Cannot find next run within 366 days for cron: '{cron_expr}'")


# ---------------------------------------------------------------------------
# Schedule CRUD
# ---------------------------------------------------------------------------


async def create_schedule(
    session: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    cron_expression: str,
    task_type: str,
    task_parameters: dict[str, Any],
    timezone: str = "UTC",
    description: str | None = None,
    max_runs: int | None = None,
) -> AutomationSchedule:
    """Create and persist a new cron schedule, pre-computing next_run_at."""
    # Validate cron expression eagerly
    parse_cron_expression(cron_expression)
    next_run = compute_next_run(cron_expression, datetime.now(UTC), timezone)

    schedule = AutomationSchedule(
        user_id=user_id,
        name=name,
        description=description,
        cron_expression=cron_expression,
        timezone=timezone,
        task_type=task_type,
        task_parameters=task_parameters,
        status=ScheduleStatus.ACTIVE.value,
        next_run_at=next_run,
        max_runs=max_runs,
        run_count=0,
    )
    session.add(schedule)
    await session.flush()

    await emit_audit_event(
        session=session,
        user_id=user_id,
        event_type="SCHEDULE_CREATED",
        event_data={
            "name": name,
            "cron": cron_expression,
            "timezone": timezone,
            "task_type": task_type,
        },
        schedule_id=schedule.id,
    )
    return schedule


async def pause_schedule(
    session: AsyncSession,
    user_id: uuid.UUID,
    schedule_id: uuid.UUID,
) -> bool:
    """Pause an active schedule (no new tasks will be spawned until resumed)."""
    result = await session.execute(
        update(AutomationSchedule)
        .where(
            AutomationSchedule.id == schedule_id,
            AutomationSchedule.user_id == user_id,
            AutomationSchedule.status == ScheduleStatus.ACTIVE.value,
        )
        .values(status=ScheduleStatus.PAUSED.value)
        .returning(AutomationSchedule.id)
    )
    paused = result.fetchone() is not None
    if paused:
        await emit_audit_event(
            session=session,
            user_id=user_id,
            event_type="SCHEDULE_PAUSED",
            event_data={},
            schedule_id=schedule_id,
        )
    return paused


async def resume_schedule(
    session: AsyncSession,
    user_id: uuid.UUID,
    schedule_id: uuid.UUID,
) -> bool:
    """Resume a paused schedule and recompute next_run_at."""
    schedule = await session.scalar(
        select(AutomationSchedule).where(
            AutomationSchedule.id == schedule_id,
            AutomationSchedule.user_id == user_id,
            AutomationSchedule.status == ScheduleStatus.PAUSED.value,
        )
    )
    if not schedule:
        return False

    next_run = compute_next_run(schedule.cron_expression, datetime.now(UTC), schedule.timezone)
    schedule.status = ScheduleStatus.ACTIVE.value
    schedule.next_run_at = next_run
    await session.flush()

    await emit_audit_event(
        session=session,
        user_id=user_id,
        event_type="SCHEDULE_RESUMED",
        event_data={"next_run_at": next_run.isoformat()},
        schedule_id=schedule_id,
    )
    return True


async def delete_schedule(
    session: AsyncSession,
    user_id: uuid.UUID,
    schedule_id: uuid.UUID,
) -> bool:
    """Soft-delete a schedule (sets status to DELETED)."""
    result = await session.execute(
        update(AutomationSchedule)
        .where(
            AutomationSchedule.id == schedule_id,
            AutomationSchedule.user_id == user_id,
            AutomationSchedule.status != ScheduleStatus.DELETED.value,
        )
        .values(status=ScheduleStatus.DELETED.value)
        .returning(AutomationSchedule.id)
    )
    deleted = result.fetchone() is not None
    if deleted:
        await emit_audit_event(
            session=session,
            user_id=user_id,
            event_type="SCHEDULE_DELETED",
            event_data={},
            schedule_id=schedule_id,
        )
    return deleted


# ---------------------------------------------------------------------------
# Schedule Tick — called from a background loop or job runner
# ---------------------------------------------------------------------------


async def tick_schedules(session: AsyncSession) -> list[uuid.UUID]:
    """Evaluate all active schedules and spawn tasks for overdue ones.

    Should be called every minute from a background process or APScheduler.
    Skipped entirely when global pause is active.

    Returns a list of task IDs that were created during this tick.
    """
    if get_global_pause():
        logger.info("Global automation pause active — schedule tick skipped")
        return []

    now = datetime.now(UTC)
    result = await session.execute(
        select(AutomationSchedule).where(
            AutomationSchedule.status == ScheduleStatus.ACTIVE.value,
            AutomationSchedule.next_run_at <= now,
        )
    )
    schedules = result.scalars().all()
    created_task_ids: list[uuid.UUID] = []

    for schedule in schedules:
        # Ceiling check
        if schedule.max_runs is not None and schedule.run_count >= schedule.max_runs:
            logger.info(
                "Schedule %s reached max_runs=%d, soft-deleting",
                schedule.id,
                schedule.max_runs,
            )
            schedule.status = ScheduleStatus.DELETED.value
            continue

        idempotency_key = f"schedule:{schedule.id}:{schedule.next_run_at.isoformat()}"

        task, is_new, _ = await create_task(
            session=session,
            user_id=schedule.user_id,
            task_type=schedule.task_type,
            task_name=f"{schedule.name} — scheduled run",
            parameters=schedule.task_parameters,
            idempotency_key=idempotency_key,
            schedule_id=schedule.id,
            scheduled_at=schedule.next_run_at,
        )

        if is_new:
            created_task_ids.append(task.id)
            logger.info("Spawned task %s from schedule %s", task.id, schedule.id)

        # Advance schedule regardless
        schedule.last_triggered_at = now
        schedule.run_count = schedule.run_count + 1  # type: ignore[assignment]
        try:
            schedule.next_run_at = compute_next_run(
                schedule.cron_expression, now, schedule.timezone
            )
        except ValueError:
            logger.error("Cannot compute next run for schedule %s — pausing", schedule.id)
            schedule.status = ScheduleStatus.PAUSED.value

        await emit_audit_event(
            session=session,
            user_id=schedule.user_id,
            event_type="SCHEDULE_TRIGGERED",
            event_data={
                "task_id": str(task.id),
                "run_count": schedule.run_count,
                "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
            },
            schedule_id=schedule.id,
            task_id=task.id,
        )

    return created_task_ids


async def cancel_pending_tasks_for_schedule(
    session: AsyncSession,
    user_id: uuid.UUID,
    schedule_id: uuid.UUID,
) -> int:
    """Cancel all PENDING tasks associated with a given schedule."""
    result = await session.execute(
        select(AutomationTask).where(
            AutomationTask.schedule_id == schedule_id,
            AutomationTask.user_id == user_id,
            AutomationTask.status == TaskStatus.PENDING.value,
        )
    )
    tasks = result.scalars().all()
    count = 0
    for task in tasks:
        cancelled = await cancel_task(session, user_id, task.id)
        if cancelled:
            count += 1
    return count
