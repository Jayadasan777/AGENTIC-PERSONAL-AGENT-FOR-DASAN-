"""Automation Audit Dashboard API endpoints.

Provides:
- GET  /automation/tasks                  — List user's automation tasks (paginated).
- GET  /automation/tasks/{task_id}        — Get a specific task with full trace.
- POST /automation/tasks/{task_id}/cancel — Cancel a pending/paused task.
- POST /automation/tasks/{task_id}/pause  — Pause a pending task.
- GET  /automation/schedules              — List user's cron schedules.
- POST /automation/schedules              — Create a new cron schedule.
- GET  /automation/schedules/{id}         — Get schedule details.
- POST /automation/schedules/{id}/pause   — Pause a schedule.
- POST /automation/schedules/{id}/resume  — Resume a paused schedule.
- DELETE /automation/schedules/{id}       — Soft-delete a schedule.
- GET  /automation/audit                  — Paginated audit event log.
- GET  /automation/pause                  — Query global pause status.
- POST /automation/pause                  — Set global pause on/off.
- POST /automation/orchestrate            — Submit a multi-agent task.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.dependencies.auth import get_current_user
from backend.app.automation.engine import (
    cancel_task,
    create_task,
    emit_audit_event,
    get_global_pause,
    pause_task,
    set_global_pause,
)
from backend.app.automation.models import (
    AutomationAuditEvent,
    AutomationSchedule,
    AutomationTask,
    ScheduleStatus,
    TaskStatus,
)
from backend.app.automation.scheduler import (
    create_schedule,
    delete_schedule,
    pause_schedule,
    resume_schedule,
)
from backend.app.automation.specialists import AgentInput, get_orchestrator
from backend.app.db.session import get_db

router = APIRouter(prefix="/automation", tags=["Automation"])


# ---------------------------------------------------------------------------
# Pydantic I/O Schemas
# ---------------------------------------------------------------------------


class TaskSummaryResponse(BaseModel):
    id: uuid.UUID
    task_type: str
    task_name: str
    status: str
    attempt_number: int
    max_attempts: int
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    has_error: bool


class TaskDetailResponse(TaskSummaryResponse):
    parameters: dict[str, Any]
    result: dict[str, Any] | None
    error_message: str | None
    schedule_id: uuid.UUID | None
    idempotency_key: str | None


class CreateTaskRequest(BaseModel):
    task_type: str = Field(..., min_length=1, max_length=128)
    task_name: str = Field(..., min_length=1, max_length=256)
    parameters: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(None, max_length=256)
    scheduled_at: datetime | None = None
    max_attempts: int = Field(default=3, ge=1, le=10)


class CreateScheduleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    cron_expression: str = Field(..., description="5-field cron, e.g. '0 9 * * 1'")
    timezone: str = Field(default="UTC", max_length=64)
    task_type: str = Field(..., min_length=1, max_length=128)
    task_parameters: dict[str, Any] = Field(default_factory=dict)
    max_runs: int | None = Field(None, ge=1)


class ScheduleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    cron_expression: str
    timezone: str
    task_type: str
    status: str
    run_count: int
    max_runs: int | None
    next_run_at: datetime | None
    last_triggered_at: datetime | None
    created_at: datetime


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    event_data: dict[str, Any]
    task_id: uuid.UUID | None
    schedule_id: uuid.UUID | None
    occurred_at: datetime


class PauseStatusResponse(BaseModel):
    paused: bool
    message: str


class SetPauseRequest(BaseModel):
    paused: bool


class OrchestrateRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=4096)
    context: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(None, max_length=256)


class OrchestrateResponse(BaseModel):
    success: bool
    result: str
    metadata: dict[str, Any]
    duration_ms: float
    task_id: uuid.UUID | None = None


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Task Endpoints
# ---------------------------------------------------------------------------


@router.get("/tasks", response_model=PaginatedResponse, summary="List automation tasks")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all automation tasks for the authenticated user (paginated)."""
    where_clauses = [AutomationTask.user_id == current_user.id]
    if status_filter:
        where_clauses.append(AutomationTask.status == status_filter)

    total_result = await db.scalar(
        select(func.count()).select_from(AutomationTask).where(*where_clauses)
    )
    total = total_result or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        select(AutomationTask)
        .where(*where_clauses)
        .order_by(desc(AutomationTask.created_at))
        .offset(offset)
        .limit(page_size)
    )
    tasks = result.scalars().all()

    items = [
        TaskSummaryResponse(
            id=t.id,
            task_type=t.task_type,
            task_name=t.task_name,
            status=t.status,
            attempt_number=t.attempt_number,
            max_attempts=t.max_attempts,
            scheduled_at=t.scheduled_at,
            started_at=t.started_at,
            completed_at=t.completed_at,
            created_at=t.created_at,
            has_error=t.error_message is not None,
        )
        for t in tasks
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get(
    "/tasks/{task_id}",
    response_model=TaskDetailResponse,
    summary="Get task details",
)
async def get_task(
    task_id: uuid.UUID,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskDetailResponse:
    """Retrieve a specific task with full details (tenant-isolated)."""
    task = await db.scalar(
        select(AutomationTask).where(
            AutomationTask.id == task_id,
            AutomationTask.user_id == current_user.id,
        )
    )
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return TaskDetailResponse(
        id=task.id,
        task_type=task.task_type,
        task_name=task.task_name,
        status=task.status,
        attempt_number=task.attempt_number,
        max_attempts=task.max_attempts,
        scheduled_at=task.scheduled_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        created_at=task.created_at,
        has_error=task.error_message is not None,
        parameters=task.parameters,
        result=task.result,
        error_message=task.error_message,
        schedule_id=task.schedule_id,
        idempotency_key=task.idempotency_key,
    )


@router.post("/tasks", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
async def submit_task(
    body: CreateTaskRequest,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Submit a new durable automation task."""
    task, is_new, cached = await create_task(
        session=db,
        user_id=current_user.id,
        task_type=body.task_type,
        task_name=body.task_name,
        parameters=body.parameters,
        idempotency_key=body.idempotency_key,
        scheduled_at=body.scheduled_at,
        max_attempts=body.max_attempts,
    )
    await db.commit()

    if not is_new and cached:
        return {"is_new": False, "cached_response": cached, "task_id": str(task.id)}

    return {"is_new": True, "task_id": str(task.id), "status": task.status}


@router.post(
    "/tasks/{task_id}/cancel",
    response_model=dict[str, str],
    summary="Cancel a task",
)
async def cancel_task_endpoint(
    task_id: uuid.UUID,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Cancel a PENDING, PAUSED, or AWAITING_APPROVAL task."""
    cancelled = await cancel_task(db, current_user.id, task_id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task not found, already terminal, or not owned by you.",
        )
    await db.commit()
    return {"status": "cancelled", "task_id": str(task_id)}


@router.post(
    "/tasks/{task_id}/pause",
    response_model=dict[str, str],
    summary="Pause a task",
)
async def pause_task_endpoint(
    task_id: uuid.UUID,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Pause a PENDING task (halt it without cancelling)."""
    paused = await pause_task(db, current_user.id, task_id)
    if not paused:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task not found, not in PENDING state, or not owned by you.",
        )
    await db.commit()
    return {"status": "paused", "task_id": str(task_id)}


# ---------------------------------------------------------------------------
# Schedule Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/schedules",
    response_model=PaginatedResponse,
    summary="List cron schedules",
)
async def list_schedules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all active cron schedules for the authenticated user."""
    where_clauses = [
        AutomationSchedule.user_id == current_user.id,
        AutomationSchedule.status != ScheduleStatus.DELETED.value,
    ]
    total = (
        await db.scalar(select(func.count()).select_from(AutomationSchedule).where(*where_clauses))
        or 0
    )
    offset = (page - 1) * page_size
    result = await db.execute(
        select(AutomationSchedule)
        .where(*where_clauses)
        .order_by(desc(AutomationSchedule.created_at))
        .offset(offset)
        .limit(page_size)
    )
    schedules = result.scalars().all()

    items = [
        ScheduleResponse(
            id=s.id,
            name=s.name,
            description=s.description,
            cron_expression=s.cron_expression,
            timezone=s.timezone,
            task_type=s.task_type,
            status=s.status,
            run_count=s.run_count,
            max_runs=s.max_runs,
            next_run_at=s.next_run_at,
            last_triggered_at=s.last_triggered_at,
            created_at=s.created_at,
        )
        for s in schedules
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post(
    "/schedules",
    response_model=ScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a cron schedule",
)
async def create_schedule_endpoint(
    body: CreateScheduleRequest,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduleResponse:
    """Create a new recurring automation schedule with timezone support."""
    try:
        schedule = await create_schedule(
            session=db,
            user_id=current_user.id,
            name=body.name,
            cron_expression=body.cron_expression,
            task_type=body.task_type,
            task_parameters=body.task_parameters,
            timezone=body.timezone,
            description=body.description,
            max_runs=body.max_runs,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid cron expression: {exc}",
        ) from exc

    await db.commit()
    await db.refresh(schedule)
    return ScheduleResponse(
        id=schedule.id,
        name=schedule.name,
        description=schedule.description,
        cron_expression=schedule.cron_expression,
        timezone=schedule.timezone,
        task_type=schedule.task_type,
        status=schedule.status,
        run_count=schedule.run_count,
        max_runs=schedule.max_runs,
        next_run_at=schedule.next_run_at,
        last_triggered_at=schedule.last_triggered_at,
        created_at=schedule.created_at,
    )


@router.get(
    "/schedules/{schedule_id}",
    response_model=ScheduleResponse,
    summary="Get schedule details",
)
async def get_schedule(
    schedule_id: uuid.UUID,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduleResponse:
    """Get details of a specific schedule."""
    schedule = await db.scalar(
        select(AutomationSchedule).where(
            AutomationSchedule.id == schedule_id,
            AutomationSchedule.user_id == current_user.id,
            AutomationSchedule.status != ScheduleStatus.DELETED.value,
        )
    )
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    return ScheduleResponse(
        id=schedule.id,
        name=schedule.name,
        description=schedule.description,
        cron_expression=schedule.cron_expression,
        timezone=schedule.timezone,
        task_type=schedule.task_type,
        status=schedule.status,
        run_count=schedule.run_count,
        max_runs=schedule.max_runs,
        next_run_at=schedule.next_run_at,
        last_triggered_at=schedule.last_triggered_at,
        created_at=schedule.created_at,
    )


@router.post(
    "/schedules/{schedule_id}/pause",
    response_model=dict[str, str],
    summary="Pause a schedule",
)
async def pause_schedule_endpoint(
    schedule_id: uuid.UUID,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Pause an active schedule. No new tasks will be spawned while paused."""
    paused = await pause_schedule(db, current_user.id, schedule_id)
    if not paused:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found or already paused",
        )
    await db.commit()
    return {"status": "paused", "schedule_id": str(schedule_id)}


@router.post(
    "/schedules/{schedule_id}/resume",
    response_model=dict[str, str],
    summary="Resume a schedule",
)
async def resume_schedule_endpoint(
    schedule_id: uuid.UUID,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Resume a paused schedule and recompute next_run_at."""
    resumed = await resume_schedule(db, current_user.id, schedule_id)
    if not resumed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found or not paused",
        )
    await db.commit()
    return {"status": "resumed", "schedule_id": str(schedule_id)}


@router.delete(
    "/schedules/{schedule_id}",
    response_model=dict[str, str],
    summary="Delete a schedule",
)
async def delete_schedule_endpoint(
    schedule_id: uuid.UUID,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Soft-delete a schedule (status set to DELETED, data retained for audit)."""
    deleted = await delete_schedule(db, current_user.id, schedule_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    await db.commit()
    return {"status": "deleted", "schedule_id": str(schedule_id)}


# ---------------------------------------------------------------------------
# Audit Dashboard
# ---------------------------------------------------------------------------


@router.get(
    "/audit",
    response_model=PaginatedResponse,
    summary="Automation audit log",
)
async def list_audit_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    task_id: uuid.UUID | None = Query(None),
    schedule_id: uuid.UUID | None = Query(None),
    event_type: str | None = Query(None),
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Paginated, filterable automation audit event log (tenant-isolated)."""
    where_clauses = [AutomationAuditEvent.user_id == current_user.id]
    if task_id:
        where_clauses.append(AutomationAuditEvent.task_id == task_id)
    if schedule_id:
        where_clauses.append(AutomationAuditEvent.schedule_id == schedule_id)
    if event_type:
        where_clauses.append(AutomationAuditEvent.event_type == event_type)

    total = (
        await db.scalar(
            select(func.count()).select_from(AutomationAuditEvent).where(*where_clauses)
        )
        or 0
    )
    offset = (page - 1) * page_size
    result = await db.execute(
        select(AutomationAuditEvent)
        .where(*where_clauses)
        .order_by(desc(AutomationAuditEvent.occurred_at))
        .offset(offset)
        .limit(page_size)
    )
    events = result.scalars().all()

    items = [
        AuditEventResponse(
            id=e.id,
            event_type=e.event_type,
            event_data=e.event_data,
            task_id=e.task_id,
            schedule_id=e.schedule_id,
            occurred_at=e.occurred_at,
        )
        for e in events
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ---------------------------------------------------------------------------
# Global Pause Control
# ---------------------------------------------------------------------------


@router.get(
    "/pause",
    response_model=PauseStatusResponse,
    summary="Get automation pause status",
)
async def get_pause_status(
    current_user: Any = Depends(get_current_user),
) -> PauseStatusResponse:
    """Query whether global automation execution is currently paused."""
    paused = get_global_pause()
    return PauseStatusResponse(
        paused=paused,
        message="Automation is globally paused." if paused else "Automation is running normally.",
    )


@router.post(
    "/pause",
    response_model=PauseStatusResponse,
    summary="Set automation pause",
)
async def set_pause_status(
    body: SetPauseRequest,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PauseStatusResponse:
    """Set or clear the global automation execution pause flag."""
    set_global_pause(body.paused)
    action = "paused" if body.paused else "resumed"
    await emit_audit_event(
        session=db,
        user_id=current_user.id,
        event_type="GLOBAL_PAUSE_CHANGED",
        event_data={"paused": body.paused, "set_by": str(current_user.id)},
    )
    await db.commit()
    return PauseStatusResponse(
        paused=body.paused,
        message=f"Global automation {action} successfully.",
    )


# ---------------------------------------------------------------------------
# Multi-Agent Orchestration Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/orchestrate",
    response_model=OrchestrateResponse,
    summary="Run multi-agent task",
)
async def orchestrate(
    body: OrchestrateRequest,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrchestrateResponse:
    """Submit a complex task to the multi-agent Orchestrator.

    The orchestrator plans a sequence of specialist agents (Research, Memory,
    Document, Verification) to execute and assembles a final synthesized answer.

    Supports optional idempotency_key to prevent duplicate submissions.
    """
    # Track this orchestration as a durable task for audit
    task, is_new, cached = await create_task(
        session=db,
        user_id=current_user.id,
        task_type="orchestration",
        task_name=body.task[:100],
        parameters={"task": body.task, "context_keys": list(body.context.keys())},
        idempotency_key=body.idempotency_key,
    )
    await db.flush()

    if not is_new and cached:
        await db.commit()
        return OrchestrateResponse(
            success=True,
            result=cached.get("result", ""),
            metadata={"cached": True},
            duration_ms=0.0,
            task_id=task.id,
        )

    # Run the orchestrator
    agent_input = AgentInput(
        user_id=current_user.id,
        session=db,
        task=body.task,
        context=body.context,
    )

    orchestrator = get_orchestrator()
    output = await orchestrator.run(agent_input)

    # Persist result back to durable task record
    from sqlalchemy import update as sa_update

    final_status = TaskStatus.COMPLETED if output.success else TaskStatus.FAILED

    now = datetime.now(UTC)

    await db.execute(
        sa_update(AutomationTask)
        .where(AutomationTask.id == task.id)
        .values(
            status=final_status.value,
            completed_at=now,
            started_at=now,
            attempt_number=1,
            result=(
                {"result": output.result, "metadata": output.metadata} if output.success else None
            ),
            error_message=output.error if not output.success else None,
        )
    )

    await emit_audit_event(
        session=db,
        user_id=current_user.id,
        event_type="ORCHESTRATION_COMPLETED" if output.success else "ORCHESTRATION_FAILED",
        event_data={
            "success": output.success,
            "steps_executed": output.metadata.get("steps_executed", 0),
            "duration_ms": output.duration_ms,
        },
        task_id=task.id,
    )
    await db.commit()

    return OrchestrateResponse(
        success=output.success,
        result=output.result,
        metadata=output.metadata,
        duration_ms=output.duration_ms,
        task_id=task.id,
    )
