"""Pydantic schemas for authentication request/response payloads.

Schemas are kept separate from ORM models (backend.app.models.*) to enforce
the boundary between transport layer validation and persistence layer structure.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field

# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class UserRegisterRequest(BaseModel):
    """Payload for POST /auth/register."""

    email: EmailStr = Field(..., description="User's unique email address")
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Plain-text password (8–128 chars); hashed server-side before storage",
    )
    full_name: str | None = Field(
        default=None,
        max_length=255,
        description="Optional display name",
    )


class UserLoginRequest(BaseModel):
    """Payload for POST /auth/login."""

    email: EmailStr = Field(..., description="Registered email address")
    password: str = Field(..., description="Plain-text password for verification")


class TokenRefreshRequest(BaseModel):
    """Payload for POST /auth/refresh."""

    refresh_token: str = Field(..., description="Valid unexpired refresh JWT")


# ---------------------------------------------------------------------------
# Response bodies
# ---------------------------------------------------------------------------


class TokenResponse(BaseModel):
    """Issued access + refresh token pair returned after login or refresh."""

    access_token: str = Field(..., description="Short-lived JWT access token (15 min)")
    refresh_token: str = Field(..., description="Long-lived JWT refresh token (7 days)")
    token_type: str = Field(default="bearer")


class UserPublicResponse(BaseModel):
    """Safe public representation of a User — never includes hashed_password."""

    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    is_superuser: bool

    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    """Response for GET /auth/me — current authenticated user profile."""

    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    is_superuser: bool

    model_config = {"from_attributes": True}


__all__ = [
    "MeResponse",
    "TokenRefreshRequest",
    "TokenResponse",
    "UserLoginRequest",
    "UserPublicResponse",
    "UserRegisterRequest",
]
