"""Document and DocumentChunk ORM entities for Document Intelligence and RAG.

Enforces strict tenant isolation: every Document and DocumentChunk is scoped
to a specific authenticated user. All chunks cascade-delete with the parent document.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from backend.app.db.base import Base, TimestampMixin
from backend.app.db.types import PortableVector

if TYPE_CHECKING:
    from backend.app.models.user import User


class Document(Base, TimestampMixin):
    """Uploaded document belonging to an authenticated user."""

    __tablename__ = "documents"

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
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    storage_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    total_chunks: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    # Relationships
    user: Mapped[User] = relationship(
        "User",
        back_populates="documents",
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )


class DocumentChunk(Base, TimestampMixin):
    """Text chunk extracted from a document with embedding and citation provenance."""

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    token_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    section_heading: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        PortableVector(dim=384),
        nullable=True,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    # Relationships
    document: Mapped[Document] = relationship(
        "Document",
        back_populates="chunks",
    )
