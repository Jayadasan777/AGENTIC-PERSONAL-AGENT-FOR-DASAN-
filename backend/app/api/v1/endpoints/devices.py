"""Companion Device Management and Mobile Biometric Approvals API.

Provides endpoints for:
- Registering companion Android / mobile devices.
- Querying active user devices.
- Immediate remote device revocation.
- Updating push notification tokens (FCM/APNS).
- Listing pending human-in-the-loop approvals for companion notifications.
- Submitting biometric-signed or user-authorized responses.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.dependencies.auth import get_current_user
from backend.app.db.session import get_db
from backend.app.models.device import Device, DeviceType, MobileApprovalAction
from backend.app.models.user import User

router = APIRouter(prefix="/devices", tags=["Companion Devices"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class RegisterDeviceRequest(BaseModel):
    device_name: str = Field(..., min_length=1, max_length=128)
    device_type: DeviceType = Field(default=DeviceType.ANDROID)
    device_fingerprint: str = Field(..., min_length=8, max_length=256)
    public_key: str | None = Field(default=None, max_length=2048)
    push_token: str | None = Field(default=None, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeviceResponse(BaseModel):
    id: uuid.UUID
    device_name: str
    device_type: str
    device_fingerprint: str
    is_revoked: bool
    revoked_at: datetime | None
    last_active_at: datetime
    created_at: datetime
    has_push_token: bool


class UpdatePushTokenRequest(BaseModel):
    push_token: str = Field(..., min_length=1, max_length=512)


class PendingApprovalResponse(BaseModel):
    id: uuid.UUID
    approval_token: str
    tool_name: str
    risk_level: str
    arguments: dict[str, Any]
    status: str
    created_at: datetime
    expires_at: datetime


class ApprovalResponseRequest(BaseModel):
    decision: str = Field(..., pattern="^(APPROVE|DENY)$")
    biometric_verified: bool = Field(default=False)
    signature: str | None = Field(default=None, max_length=2048)


# ---------------------------------------------------------------------------
# Device Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new companion device",
)
async def register_device(
    payload: RegisterDeviceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceResponse:
    """Register or re-activate a companion device under the authenticated tenant."""
    # Check if this fingerprint already exists for this user
    stmt = select(Device).where(
        Device.user_id == current_user.id,
        Device.device_fingerprint == payload.device_fingerprint,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()

    now = datetime.now(UTC)
    if existing:
        existing.device_name = payload.device_name
        existing.device_type = payload.device_type.value
        existing.public_key = payload.public_key
        existing.push_token = payload.push_token
        existing.is_revoked = False
        existing.revoked_at = None
        existing.last_active_at = now
        existing.metadata_json = payload.metadata
        await db.commit()
        await db.refresh(existing)
        target = existing
    else:
        target = Device(
            user_id=current_user.id,
            device_name=payload.device_name,
            device_type=payload.device_type.value,
            device_fingerprint=payload.device_fingerprint,
            public_key=payload.public_key,
            push_token=payload.push_token,
            is_revoked=False,
            last_active_at=now,
            metadata_json=payload.metadata,
        )
        db.add(target)
        await db.commit()
        await db.refresh(target)

    return DeviceResponse(
        id=target.id,
        device_name=target.device_name,
        device_type=target.device_type,
        device_fingerprint=target.device_fingerprint,
        is_revoked=target.is_revoked,
        revoked_at=target.revoked_at,
        last_active_at=target.last_active_at,
        created_at=target.created_at,
        has_push_token=bool(target.push_token),
    )


@router.get(
    "",
    response_model=list[DeviceResponse],
    summary="List registered companion devices",
)
async def list_devices(
    include_revoked: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DeviceResponse]:
    """List companion devices registered to current user."""
    stmt = select(Device).where(Device.user_id == current_user.id)
    if not include_revoked:
        stmt = stmt.where(Device.is_revoked.is_(False))
    stmt = stmt.order_by(desc(Device.last_active_at))

    devices = (await db.execute(stmt)).scalars().all()
    return [
        DeviceResponse(
            id=d.id,
            device_name=d.device_name,
            device_type=d.device_type,
            device_fingerprint=d.device_fingerprint,
            is_revoked=d.is_revoked,
            revoked_at=d.revoked_at,
            last_active_at=d.last_active_at,
            created_at=d.created_at,
            has_push_token=bool(d.push_token),
        )
        for d in devices
    ]


@router.post(
    "/{device_id}/revoke",
    response_model=dict[str, Any],
    summary="Remotely revoke a companion device",
)
async def revoke_device(
    device_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Instantly revoke access for a specific companion device."""
    now = datetime.now(UTC)
    stmt = (
        update(Device)
        .where(Device.id == device_id, Device.user_id == current_user.id)
        .values(is_revoked=True, revoked_at=now, push_token=None)
        .returning(Device.id)
    )
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found or not owned by user",
        )
    await db.commit()
    return {"status": "revoked", "device_id": str(device_id), "revoked_at": now.isoformat()}


@router.post(
    "/{device_id}/push-token",
    response_model=dict[str, str],
    summary="Update FCM / mobile push notification token",
)
async def update_push_token(
    device_id: uuid.UUID,
    payload: UpdatePushTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Update push token for an active, non-revoked device."""
    stmt = (
        update(Device)
        .where(
            Device.id == device_id,
            Device.user_id == current_user.id,
            Device.is_revoked.is_(False),
        )
        .values(push_token=payload.push_token, last_active_at=datetime.now(UTC))
        .returning(Device.id)
    )
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active device not found",
        )
    await db.commit()
    return {"status": "updated", "device_id": str(device_id)}


# ---------------------------------------------------------------------------
# Biometric Human-In-The-Loop Approval Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/pending-approvals",
    response_model=list[PendingApprovalResponse],
    summary="Query pending tool approvals for mobile companion",
)
async def list_pending_approvals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PendingApprovalResponse]:
    """List pending high-risk tool actions awaiting human decision."""
    now = datetime.now(UTC)
    stmt = (
        select(MobileApprovalAction)
        .where(
            MobileApprovalAction.user_id == current_user.id,
            MobileApprovalAction.status == "PENDING",
            MobileApprovalAction.expires_at > now,
        )
        .order_by(desc(MobileApprovalAction.created_at))
    )
    actions = (await db.execute(stmt)).scalars().all()
    return [
        PendingApprovalResponse(
            id=a.id,
            approval_token=a.approval_token,
            tool_name=a.tool_name,
            risk_level=a.risk_level,
            arguments=a.arguments_json,
            status=a.status,
            created_at=a.created_at,
            expires_at=a.expires_at,
        )
        for a in actions
    ]


@router.post(
    "/approvals/{token}/respond",
    response_model=dict[str, Any],
    summary="Respond to an approval request with biometric attestation",
)
async def respond_to_approval(
    token: str,
    payload: ApprovalResponseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Submit APPROVE or DENY decision with optional biometric signature."""
    now = datetime.now(UTC)
    stmt = select(MobileApprovalAction).where(
        MobileApprovalAction.approval_token == token,
        MobileApprovalAction.user_id == current_user.id,
    )
    action = (await db.execute(stmt)).scalar_one_or_none()
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found",
        )

    if action.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approval request already resolved with status '{action.status}'",
        )

    expires_at = (
        action.expires_at.replace(tzinfo=UTC)
        if action.expires_at.tzinfo is None
        else action.expires_at
    )
    if expires_at <= now:
        action.status = "EXPIRED"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Approval request has expired",
        )

    final_status = "APPROVED" if payload.decision == "APPROVE" else "REJECTED"
    action.status = final_status
    action.biometric_verified = payload.biometric_verified
    action.signature = payload.signature
    action.responded_at = now

    await db.commit()
    return {
        "status": final_status,
        "token": token,
        "biometric_verified": payload.biometric_verified,
        "responded_at": now.isoformat(),
    }


@router.post(
    "/approvals/create-mock",
    response_model=PendingApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an approval request (used by agent harness or test flows)",
)
async def create_mock_approval(
    tool_name: str = Query("SystemCommandTool"),
    risk_level: str = Query("CRITICAL"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PendingApprovalResponse:
    """Helper endpoint to generate an approval action for mobile push testing."""
    now = datetime.now(UTC)
    token = f"appr_{uuid.uuid4().hex}"
    action = MobileApprovalAction(
        user_id=current_user.id,
        approval_token=token,
        tool_name=tool_name,
        risk_level=risk_level,
        arguments_json={"command": "rm -rf /var/cache/temp", "confirmed": False},
        status="PENDING",
        expires_at=now + timedelta(minutes=15),
    )
    db.add(action)
    await db.commit()
    await db.refresh(action)

    return PendingApprovalResponse(
        id=action.id,
        approval_token=action.approval_token,
        tool_name=action.tool_name,
        risk_level=action.risk_level,
        arguments=action.arguments_json,
        status=action.status,
        created_at=action.created_at,
        expires_at=action.expires_at,
    )
