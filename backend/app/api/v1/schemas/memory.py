"""Pydantic schemas for Memory requests and responses."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MemoryCreateRequest(BaseModel):
    """Payload to create a new persistent memory item."""

    content: str = Field(
        ...,
        min_length=2,
        max_length=10000,
        description="The textual memory statement or fact to remember.",
    )
    category: str = Field(
        default="general",
        max_length=50,
        description="Category classification (e.g. preference, fact, instruction, work).",
    )
    sensitivity: Literal["public", "private", "confidential"] = Field(
        default="private",
        description="Privacy sensitivity tier.",
    )
    source: str = Field(
        default="user_explicit",
        max_length=50,
        description="Provenance source of the memory (e.g. user_explicit, conversation).",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )
    metadata_json: dict[str, Any] | None = Field(
        default=None,
        description="Optional structured context.",
    )


class MemoryUpdateRequest(BaseModel):
    """Payload to update an existing memory item."""

    content: str | None = Field(
        default=None,
        min_length=2,
        max_length=10000,
        description="Updated memory content.",
    )
    category: str | None = Field(
        default=None,
        max_length=50,
    )
    sensitivity: Literal["public", "private", "confidential"] | None = Field(
        default=None,
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    is_active: bool | None = Field(
        default=None,
        description="Active status flag. Set to false when superseded.",
    )
    metadata_json: dict[str, Any] | None = Field(
        default=None,
    )


class MemoryResponse(BaseModel):
    """Structured representation of a stored memory item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    content: str
    category: str
    sensitivity: str
    source: str
    confidence: float
    version: int
    parent_id: uuid.UUID | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] | None = None


class MemorySearchRequest(BaseModel):
    """Payload for hybrid semantic + keyword memory search."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Search query string.",
    )
    category: str | None = Field(
        default=None,
        description="Optional category filter.",
    )
    sensitivity: str | None = Field(
        default=None,
        description="Optional sensitivity filter (e.g. exclude confidential).",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Max number of memories to return.",
    )
    threshold: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Minimum hybrid similarity threshold.",
    )


class MemorySearchResult(BaseModel):
    """Single match item returned from hybrid memory retrieval."""

    memory: MemoryResponse
    score: float = Field(..., description="Hybrid relevance score [0.0 - 1.0]")
    match_type: str = Field(..., description="'hybrid', 'semantic', or 'keyword'")


class MemoryExportResponse(BaseModel):
    """GDPR-compliant export bundle of all memories for an authenticated user."""

    user_id: uuid.UUID
    exported_at: datetime
    total_count: int
    memories: list[MemoryResponse]
