"""SQLAlchemy 2.0 ORM models for durable automation and multi-agent workflows.

Tables:
- automation_tasks: Durable workflow execution records with crash-recovery state.
- automation_schedules: Cron-based scheduled task definitions.
- idempotency_keys: Single-writer concurrency locks preventing duplicate runs.
- automation_audit_events: Append-only structured audit trail for workflows.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TaskStatus(StrEnum):
    """Lifecycle state of a durable workflow task."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


class ScheduleStatus(StrEnum):
    """Status of a scheduled automation."""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DELETED = "DELETED"


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class AutomationTask(Base, TimestampMixin):
    """Persistent durable task record enabling crash-recovery and audit replay."""

    __tablename__ = "automation_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        index=True,
    )
    # Scheduling parent link (nullable for ad-hoc tasks)
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("automation_schedules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Task definition
    task_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Logical task type identifier, e.g. 'agent_run', 'memory_consolidation'",
    )
    task_name: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    # Execution state machine
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TaskStatus.PENDING.value,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
    )

    # Timing
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Earliest time the task may be executed",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Output and errors
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Concurrency lease: worker identity that owns execution
    locked_by: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        comment="Worker instance ID that holds the execution lease",
    )
    lock_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_task_user_idempotency"),
        Index("ix_automation_tasks_status_scheduled", "status", "scheduled_at"),
    )


class AutomationSchedule(Base, TimestampMixin):
    """Cron-based recurring automation schedule definition."""

    __tablename__ = "automation_schedules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    cron_expression: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Standard 5-field cron expression, e.g. '0 9 * * 1'",
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="UTC",
        comment="IANA timezone identifier, e.g. 'America/New_York'",
    )
    task_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    task_parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ScheduleStatus.ACTIVE.value,
        index=True,
    )
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    run_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    max_runs: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Optional ceiling on total executions; None = unlimited",
    )


class IdempotencyRecord(Base):
    """Distributed idempotency lock preventing duplicate workflow triggers."""

    __tablename__ = "idempotency_records"

    key: Mapped[str] = mapped_column(
        String(512),
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Task record that was created for this idempotency key",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    response_cache: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Cached response for replayed idempotent requests",
    )


class AutomationAuditEvent(Base):
    """Immutable, append-only audit trail for all automation lifecycle events."""

    __tablename__ = "automation_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="e.g. TASK_CREATED, TASK_STARTED, TASK_COMPLETED, TASK_FAILED, SCHEDULE_TRIGGERED",
    )
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_audit_events_user_occurred", "user_id", "occurred_at"),
        Index("ix_audit_events_task_type", "task_id", "event_type"),
    )
