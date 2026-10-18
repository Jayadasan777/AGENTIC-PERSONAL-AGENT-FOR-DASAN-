"""Memory ORM model representing persistent personal knowledge items.

Each memory is scoped to an authenticated user (strict multi-tenant isolation),
has associated metadata (source provenance, confidence, sensitivity, version),
and includes an embedding vector for semantic similarity search.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from backend.app.db.base import Base, TimestampMixin
from backend.app.db.types import PortableVector

if TYPE_CHECKING:
    from backend.app.models.user import User


class Memory(Base, TimestampMixin):
    """Personal memory entry belonging strictly to a single user."""

    __tablename__ = "memories"

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
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(50),
        default="general",
        nullable=False,
        index=True,
    )
    sensitivity: Mapped[str] = mapped_column(
        String(20),
        default="private",
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(50),
        default="conversation",
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memories.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        PortableVector(dim=384),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Relationships
    user: Mapped[User] = relationship(
        "User",
        back_populates="memories",
    )
    parent_memory: Mapped[Memory | None] = relationship(
        "Memory",
        remote_side=[id],
        foreign_keys=[parent_id],
        backref="child_memories",
    )
