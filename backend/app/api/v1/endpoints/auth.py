"""Auth endpoint router: register, login, refresh, logout, me.

HTTP concerns only — all business logic is delegated to backend.app.services.auth.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.dependencies.auth import get_current_active_user
from backend.app.api.v1.schemas.auth import (
    MeResponse,
    TokenRefreshRequest,
    TokenResponse,
    UserLoginRequest,
    UserPublicResponse,
    UserRegisterRequest,
)
from backend.app.db.session import get_async_session
from backend.app.models.user import User
from backend.app.services.auth import (
    login_user,
    logout_user,
    refresh_tokens,
    register_user,
)

logger = logging.getLogger("aura.auth.router")

router = APIRouter(prefix="/auth", tags=["Auth"])


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=UserPublicResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    body: UserRegisterRequest,
    session: AsyncSession = Depends(get_async_session),
) -> UserPublicResponse:
    """Create a new user account.

    - **email**: Unique email address (lowercased on storage).
    - **password**: 8–128 characters; hashed with Argon2id before storage.
    - **full_name**: Optional display name.

    Returns the new user's public profile (never the hashed password).
    Raises 409 if the email is already registered.
    """
    user = await register_user(
        email=body.email.lower(),
        password=body.password,
        full_name=body.full_name,
        session=session,
    )
    await session.commit()
    return UserPublicResponse.model_validate(user)


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive access + refresh tokens",
)
async def login(
    body: UserLoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    """Exchange valid credentials for a JWT access token and refresh token.

    - Access token: short-lived (15 min), include in ``Authorization: Bearer`` header.
    - Refresh token: long-lived (7 days), use POST /auth/refresh to rotate.

    Raises 401 on any credential mismatch.
    """
    user_agent = request.headers.get("User-Agent")
    client_ip = request.client.host if request.client else None

    access_token, refresh_token = await login_user(
        email=body.email.lower(),
        password=body.password,
        user_agent=user_agent,
        ip_address=client_ip,
        session=session,
    )
    await session.commit()
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and receive a fresh token pair",
)
async def refresh(
    body: TokenRefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh token pair.

    The old refresh token is immediately revoked (rolling rotation).
    Raises 401 if the token is invalid, expired, or already consumed.
    """
    user_agent = request.headers.get("User-Agent")
    client_ip = request.client.host if request.client else None

    new_access, new_refresh = await refresh_tokens(
        raw_refresh_token=body.refresh_token,
        user_agent=user_agent,
        ip_address=client_ip,
        session=session,
    )
    await session.commit()
    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the current refresh token session",
)
async def logout(
    body: TokenRefreshRequest,
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """Invalidate the provided refresh token.

    Idempotent — calling this with an already-revoked token returns 204 silently.
    Note: Access tokens cannot be invalidated server-side (they expire in 15 min).
    Clients must discard their access token on logout.
    """
    await logout_user(raw_refresh_token=body.refresh_token, session=session)
    await session.commit()


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Return the currently authenticated user's profile",
)
async def me(
    current_user: User = Depends(get_current_active_user),
) -> MeResponse:
    """Return the profile of the authenticated user.

    Requires a valid access token in ``Authorization: Bearer <token>``.
    """
    return MeResponse.model_validate(current_user)


__all__ = ["router"]
