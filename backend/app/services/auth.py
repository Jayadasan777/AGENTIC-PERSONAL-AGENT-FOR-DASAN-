"""Auth service: registration, login, token refresh, and logout business logic.

Separation of concerns:
- This module owns the auth business logic.
- The endpoint router owns HTTP concerns (request parsing, status codes).
- The security module owns cryptographic primitives (hashing, JWT creation).
- The ORM models own persistence structure.

Refresh token strategy:
- On login, a new AuthSession row is created with ``refresh_token_hash``.
- On /refresh, the incoming token is hashed and looked up in the DB.
  The old session is revoked, and a NEW session + token pair is issued.
  This is "rolling refresh" — a leaked token can only be used once.
- On /logout, the session row is revoked immediately.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    verify_password,
)
from backend.app.models.auth_session import AuthSession
from backend.app.models.user import User

logger = logging.getLogger("aura.auth.service")


# ---------------------------------------------------------------------------
# User registration
# ---------------------------------------------------------------------------


async def register_user(
    email: str,
    password: str,
    full_name: str | None,
    session: AsyncSession,
) -> User:
    """Create a new user account.

    Raises:
        409 Conflict — if the email address is already registered.
    """
    # Check uniqueness before inserting to give a clean 409 error
    existing = await session.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email address is already registered",
        )

    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        is_active=True,
        is_superuser=False,
    )
    session.add(user)
    await session.flush()  # Assign DB-generated id without full commit
    logger.info("Registered new user user_id=%s email=%s", user.id, email)
    return user


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


async def login_user(
    email: str,
    password: str,
    user_agent: str | None,
    ip_address: str | None,
    session: AsyncSession,
) -> tuple[str, str]:
    """Authenticate credentials and return (access_token, refresh_token).

    Uses constant-time comparison via Argon2id to resist timing attacks.
    Raises:
        401 Unauthorized — on any credential mismatch (unified error to prevent
        user enumeration via different error messages for wrong email vs password).
    """
    _invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Always run password verification even if user not found to prevent
    # timing-based user enumeration attacks
    dummy_hash = "$argon2id$v=19$m=65536,t=3,p=4$dGVzdA$dGVzdA"
    stored_hash = user.hashed_password if user else dummy_hash

    if not verify_password(password, stored_hash):
        logger.warning("Failed login attempt for email=%s", email)
        raise _invalid

    if user is None:
        raise _invalid  # Guard: user definitely None here (dummy hash path)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    # Transparently upgrade old password hashes to current Argon2id parameters
    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(password)
        logger.info("Rehashed password for user_id=%s", user.id)

    # Issue tokens
    access_token = create_access_token(subject=str(user.id))
    refresh_token = create_refresh_token(subject=str(user.id))

    # Persist refresh session
    settings = get_settings()
    session_record = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        user_agent=user_agent,
        ip_address=ip_address,
        is_revoked=False,
        expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    session.add(session_record)
    logger.info("Login successful user_id=%s session_id=%s", user.id, session_record.id)

    return access_token, refresh_token


# ---------------------------------------------------------------------------
# Token refresh (rolling rotation)
# ---------------------------------------------------------------------------


async def refresh_tokens(
    raw_refresh_token: str,
    user_agent: str | None,
    ip_address: str | None,
    session: AsyncSession,
) -> tuple[str, str]:
    """Rotate refresh token: revoke old session, issue fresh access + refresh pair.

    Raises:
        401 Unauthorized — token invalid, expired, or already revoked.
    """
    _invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_hash = hash_refresh_token(raw_refresh_token)
    result = await session.execute(
        select(AuthSession).where(AuthSession.refresh_token_hash == token_hash)
    )
    auth_session = result.scalar_one_or_none()

    if auth_session is None or auth_session.is_revoked:
        logger.warning("Refresh attempt with unknown/revoked token hash=%s...", token_hash[:8])
        raise _invalid

    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        logger.warning("Refresh attempt with expired session session_id=%s", auth_session.id)
        raise _invalid

    # Load the owning user
    user = await session.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise _invalid

    # Revoke the consumed session
    auth_session.is_revoked = True

    # Issue new token pair
    new_access = create_access_token(subject=str(user.id))
    new_refresh = create_refresh_token(subject=str(user.id))

    settings = get_settings()
    new_session = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(new_refresh),
        user_agent=user_agent,
        ip_address=ip_address,
        is_revoked=False,
        expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    session.add(new_session)
    logger.info(
        "Token rotated user_id=%s old_session=%s new_session=%s",
        user.id,
        auth_session.id,
        new_session.id,
    )
    return new_access, new_refresh


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


async def logout_user(
    raw_refresh_token: str,
    session: AsyncSession,
) -> None:
    """Revoke the session associated with the given refresh token.

    Silent success if token not found (idempotent logout).
    """
    token_hash = hash_refresh_token(raw_refresh_token)
    result = await session.execute(
        select(AuthSession).where(AuthSession.refresh_token_hash == token_hash)
    )
    auth_session = result.scalar_one_or_none()
    if auth_session and not auth_session.is_revoked:
        auth_session.is_revoked = True
        logger.info("Session revoked session_id=%s", auth_session.id)


# ---------------------------------------------------------------------------
# Revoke all user sessions (emergency kill / password change)
# ---------------------------------------------------------------------------


async def revoke_all_user_sessions(user_id: uuid.UUID, session: AsyncSession) -> int:
    """Mark all active sessions for a user as revoked.

    Returns:
        Count of sessions revoked.
    """
    result = await session.execute(
        select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.is_revoked.is_(False),
        )
    )
    active_sessions = result.scalars().all()
    for s in active_sessions:
        s.is_revoked = True
    logger.info("Revoked %d sessions for user_id=%s", len(active_sessions), user_id)
    return len(active_sessions)


__all__ = [
    "login_user",
    "logout_user",
    "refresh_tokens",
    "register_user",
    "revoke_all_user_sessions",
]
