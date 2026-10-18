"""Message entity representing chat turns, model responses, and tool calls."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.app.models.conversation import Conversation


class Message(Base, TimestampMixin):
    """Single message entry in a conversation thread."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    model_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    token_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
