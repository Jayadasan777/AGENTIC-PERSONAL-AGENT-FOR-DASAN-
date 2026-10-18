"""Pydantic schemas for Document intelligence and RAG endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    """Metadata response for an uploaded and processed document."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    mime_type: str
    file_size_bytes: int
    sha256_hash: str
    status: str
    total_chunks: int
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentChunkResponse(BaseModel):
    """Individual chunk extracted from a document with citation coordinates."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    token_count: int
    page_number: int | None = None
    section_heading: str | None = None
    created_at: datetime


class RAGQueryRequest(BaseModel):
    """Payload for RAG question answering over user's indexed documents."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The question to be answered from document knowledge.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Max citation chunks to retrieve.",
    )
    threshold: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score.",
    )


class CitationItem(BaseModel):
    """Citation pointing directly to the source document and page/section."""

    chunk_id: str
    document_id: str
    document_name: str
    page_number: int | None = None
    section_heading: str | None = None
    score: float


class RAGQueryResponse(BaseModel):
    """Grounded RAG answer accompanied by strict citation evidence."""

    answer: str
    citations: list[CitationItem]
    query: str
