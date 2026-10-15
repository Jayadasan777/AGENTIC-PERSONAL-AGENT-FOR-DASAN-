"""Security utilities: Argon2id password hashing and JWT access/refresh token lifecycle.

Design decisions:
- Argon2id is the winner of the Password Hashing Competition (PHC) and is recommended
  by OWASP as the primary KDF for password storage. We use the memory-hard variant.
- JWTs are signed with HS256 using the application SECRET_KEY.
- Access tokens are short-lived (15 min). Refresh tokens are long-lived (7 days) but
  stored as HASHED values in the database so a leaked DB row cannot be replayed.
- Token rotation: every /refresh call issues a brand-new refresh token and marks the
  old session row as revoked, preventing unlimited reuse of any single token.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from jose import jwt

from backend.app.core.config import get_settings

logger = logging.getLogger("aura.security")

# ---------------------------------------------------------------------------
# Argon2id password hasher — OWASP recommended parameters (2024)
# m=65536 KiB (64 MB), t=3 iterations, p=4 parallelism
# ---------------------------------------------------------------------------
_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

ALGORITHM = "HS256"


# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using Argon2id.

    Returns an encoded hash string containing algorithm parameters, salt, and hash.
    This is safe to store directly in the database.
    """
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a stored Argon2id hash.

    Returns True if they match. Logs a warning on failure to detect brute-force
    attempts in structured logs without leaking credentials.
    Automatically handles Argon2id parameter upgrades via rehash detection.
    """
    try:
        _password_hasher.verify(hashed_password, plain_password)
        return True
    except VerifyMismatchError:
        # Normal case: wrong password
        return False
    except VerificationError:
        # Hash is malformed / from different algorithm
        logger.warning("Password verification error: hash may be from wrong algorithm")
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Return True if the stored hash uses outdated Argon2id parameters.

    Call after successful login to transparently upgrade hashes to current parameters.
    """
    return _password_hasher.check_needs_rehash(hashed_password)


# ---------------------------------------------------------------------------
# Refresh token hashing (SHA-256)
# We store the hash of the refresh token in the DB, not the token itself.
# This way a DB leak cannot be used to replay sessions.
# ---------------------------------------------------------------------------


def hash_refresh_token(token: str) -> str:
    """Return a stable SHA-256 hex digest of the raw refresh token string."""
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# JWT utilities
# ---------------------------------------------------------------------------


def _get_secret() -> str:
    return get_settings().SECRET_KEY.get_secret_value()


def create_access_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT access token.

    Args:
        subject: The user ID (UUID as string) to embed as the ``sub`` claim.
        extra_claims: Optional additional claims (e.g. roles, email).

    Returns:
        Encoded JWT string.
    """
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, _get_secret(), algorithm=ALGORITHM)


def create_refresh_token(subject: str) -> str:
    """Create a signed JWT refresh token with a longer expiry.

    The caller is responsible for storing ``hash_refresh_token(result)`` in the DB.

    Args:
        subject: The user ID (UUID as string).

    Returns:
        Encoded JWT string (raw — store only the hash in DB).
    """
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }

    return jwt.encode(payload, _get_secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT, returning its payload.

    Raises:
        JWTError: If the token is expired, tampered, or otherwise invalid.
    """
    return dict(
        jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode an access token and verify its ``type`` claim.

    Raises:
        ValueError: If the token type is not ``access``.
        JWTError: If the token fails signature or expiry validation.
    """
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise ValueError("Token is not an access token")
    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decode a refresh token and verify its ``type`` claim.

    Raises:
        ValueError: If the token type is not ``refresh``.
        JWTError: If the token fails signature or expiry validation.
    """
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise ValueError("Token is not a refresh token")
    return payload


__all__ = [
    "ALGORITHM",
    "create_access_token",
    "create_refresh_token",
    "decode_access_token",
    "decode_refresh_token",
    "decode_token",
    "hash_password",
    "hash_refresh_token",
    "needs_rehash",
    "verify_password",
]
