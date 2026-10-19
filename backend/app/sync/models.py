"""Database Models and Schema for Cursor-Based Synchronization."""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin


class SyncChangeType(StrEnum):
    """Operation types captured in synchronization changelog."""

    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class SyncEntityType(StrEnum):
    """Domain entities participating in cross-device synchronization."""

    MEMORY = "MEMORY"
    CONVERSATION = "CONVERSATION"
    MESSAGE = "MESSAGE"
    DOCUMENT = "DOCUMENT"
    TASK = "TASK"


class SyncChangeRecord(Base, TimestampMixin):
    """Append-only audit changelog recording mutations across all synced entities.

    Enables clients to request delta streams starting from an arbitrary cursor.
    """

    __tablename__ = "sync_change_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    server_seq: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    client_mutation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    client_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "server_seq", name="uq_user_server_seq"),
        Index("ix_sync_cursor_lookup", "user_id", "server_seq"),
    )


class SyncCursor:
    """Opaque cursor representation encoding user sequence checkpoint."""

    @staticmethod
    def encode(server_seq: int, timestamp: datetime | None = None) -> str:
        ts_str = (timestamp or datetime.now(UTC)).isoformat()
        payload = f"{server_seq}:{ts_str}"
        return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")

    @staticmethod
    def decode(cursor_str: str | None) -> int:
        if not cursor_str:
            return 0
        try:
            decoded = base64.urlsafe_b64decode(cursor_str.encode("utf-8")).decode("utf-8")
            seq_part = decoded.split(":", 1)[0]
            return int(seq_part)
        except Exception:
            return 0
