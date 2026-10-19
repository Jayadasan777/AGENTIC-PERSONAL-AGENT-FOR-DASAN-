"""Companion Device and Mobile Push/Biometric Approval Models.

Enables multi-device registration, remote device revocation, and mobile
biometric human-in-the-loop approvals.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin


class DeviceType(StrEnum):
    """Supported companion client platforms."""

    ANDROID = "ANDROID"
    IOS = "IOS"
    DESKTOP = "DESKTOP"
    CLI = "CLI"


class Device(Base, TimestampMixin):
    """Registered companion device associated with an authenticated user."""

    __tablename__ = "companion_devices"

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
    device_name: Mapped[str] = mapped_column(String(128), nullable=False)
    device_type: Mapped[str] = mapped_column(String(32), default=DeviceType.ANDROID.value, nullable=False)
    device_fingerprint: Mapped[str] = mapped_column(String(256), nullable=False)
    public_key: Mapped[str | None] = mapped_column(Text, nullable=True)  # Ed25519 / RSA public key
    push_token: Mapped[str | None] = mapped_column(String(512), nullable=True)  # FCM / APNS token
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "device_fingerprint", name="uq_user_device_fingerprint"),
        Index("ix_devices_user_active", "user_id", "is_revoked"),
    )


class MobileApprovalAction(Base, TimestampMixin):
    """Approval request routed to companion devices for biometric or screen authorization."""

    __tablename__ = "mobile_approval_actions"

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
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companion_devices.id", ondelete="SET NULL"),
        nullable=True,
    )
    approval_token: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), default="CRITICAL", nullable=False)
    arguments_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)  # PENDING, APPROVED, REJECTED, EXPIRED
    biometric_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_mobile_approvals_user_status", "user_id", "status"),
    )
