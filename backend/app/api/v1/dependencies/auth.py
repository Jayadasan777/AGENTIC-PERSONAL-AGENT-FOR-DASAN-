"""FastAPI dependency injection functions for authentication and tenant isolation.

These dependencies are reused across all protected endpoints via:
    current_user: User = Depends(get_current_active_user)

Tenant isolation guarantee:
    Every database lookup for user-owned resources must pass the resolved
    ``current_user.id`` as a WHERE filter. The dependencies here establish
    WHICH user is authenticated; every endpoint MUST then scope its own
    DB queries to that user's ID. Never trust a user-supplied ``user_id``
    parameter in request bodies or query params for resource access.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import decode_access_token
from backend.app.db.session import get_async_session
from backend.app.models.user import User

logger = logging.getLogger("aura.auth")

# HTTPBearer reads the "Authorization: Bearer <token>" header automatically
_bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """Resolve and return the User from the JWT in the Authorization header.

    Raises:
        401 Unauthorized — if token is absent, expired, or tampered.
        401 Unauthorized — if the user ID in the token does not exist in the DB.

    Security note: We return a 401 (not 403) in all cases to avoid disclosing
    whether a given user ID exists (user enumeration protection).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(credentials.credentials)
        user_id_str: str | None = payload.get("sub")
        if not user_id_str:
            raise credentials_exception
        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError, AttributeError):
        logger.warning("Invalid token presented")
        raise credentials_exception from None

    # Hit the database to confirm the user still exists and is not deleted.
    # Avoids serving stale tokens for deleted accounts.
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        logger.warning("Token subject user_id=%s not found in DB", user_id)
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Extend get_current_user to reject deactivated accounts.

    Raises:
        403 Forbidden — if the authenticated user's account has been deactivated.
    """
    if not current_user.is_active:
        logger.warning("Inactive user user_id=%s attempted access", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )
    return current_user


async def get_current_superuser(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Gate access to superuser-only endpoints.

    Raises:
        403 Forbidden — if the authenticated active user is not a superuser.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required",
        )
    return current_user


__all__ = [
    "get_current_active_user",
    "get_current_superuser",
    "get_current_user",
]
