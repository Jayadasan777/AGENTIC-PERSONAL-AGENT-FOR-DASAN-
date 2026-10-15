"""Unit tests for Argon2id password hashing and JWT security utilities.

These tests run entirely in-memory — no database, no network.
They cover the cryptographic primitives in backend.app.core.security.
"""

from __future__ import annotations

import pytest

from backend.app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    verify_password,
)

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self) -> None:
        hashed = hash_password("mysecretpassword")
        assert "mysecretpassword" not in hashed

    def test_argon2id_identifier_in_hash(self) -> None:
        hashed = hash_password("mysecretpassword")
        # Argon2id hashes always start with $argon2id$
        assert hashed.startswith("$argon2id$")

    def test_verify_correct_password_returns_true(self) -> None:
        hashed = hash_password("correctpassword")
        assert verify_password("correctpassword", hashed) is True

    def test_verify_wrong_password_returns_false(self) -> None:
        hashed = hash_password("correctpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_same_password_produces_different_hashes(self) -> None:
        # Argon2id uses random salts — same password must yield different hashes
        h1 = hash_password("samepassword")
        h2 = hash_password("samepassword")
        assert h1 != h2

    def test_both_hashes_verify_correctly(self) -> None:
        h1 = hash_password("samepassword")
        h2 = hash_password("samepassword")
        assert verify_password("samepassword", h1) is True
        assert verify_password("samepassword", h2) is True

    def test_needs_rehash_returns_false_for_fresh_hash(self) -> None:
        hashed = hash_password("testpassword")
        assert needs_rehash(hashed) is False


# ---------------------------------------------------------------------------
# Refresh token hashing
# ---------------------------------------------------------------------------


class TestRefreshTokenHashing:
    def test_same_token_produces_same_hash(self) -> None:
        token = "some.jwt.token"
        assert hash_refresh_token(token) == hash_refresh_token(token)

    def test_different_tokens_produce_different_hashes(self) -> None:
        h1 = hash_refresh_token("token.one")
        h2 = hash_refresh_token("token.two")
        assert h1 != h2

    def test_hash_is_hex_string(self) -> None:
        h = hash_refresh_token("anytoken")
        # SHA-256 hex is always 64 characters
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# JWT access tokens
# ---------------------------------------------------------------------------


class TestAccessTokens:
    def test_create_and_decode_access_token(self) -> None:
        token = create_access_token(subject="user-123")
        payload = decode_access_token(token)
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"

    def test_access_token_contains_exp_and_iat(self) -> None:
        token = create_access_token(subject="user-123")
        payload = decode_access_token(token)
        assert "exp" in payload
        assert "iat" in payload
        assert payload["exp"] > payload["iat"]

    def test_access_token_with_extra_claims(self) -> None:
        token = create_access_token(subject="user-123", extra_claims={"email": "a@b.com"})
        payload = decode_access_token(token)
        assert payload["email"] == "a@b.com"

    def test_tampered_access_token_raises(self) -> None:
        from jose import JWTError

        token = create_access_token(subject="user-123")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(JWTError):
            decode_access_token(tampered)

    def test_refresh_token_rejected_as_access_token(self) -> None:
        refresh = create_refresh_token(subject="user-123")
        with pytest.raises(ValueError, match="not an access token"):
            decode_access_token(refresh)


# ---------------------------------------------------------------------------
# JWT refresh tokens
# ---------------------------------------------------------------------------


class TestRefreshTokens:
    def test_create_and_decode_refresh_token(self) -> None:
        token = create_refresh_token(subject="user-456")
        payload = decode_refresh_token(token)
        assert payload["sub"] == "user-456"
        assert payload["type"] == "refresh"

    def test_refresh_token_expires_later_than_access_token(self) -> None:
        access = create_access_token(subject="user-456")
        refresh = create_refresh_token(subject="user-456")
        access_payload = decode_access_token(access)
        refresh_payload = decode_refresh_token(refresh)
        assert refresh_payload["exp"] > access_payload["exp"]

    def test_access_token_rejected_as_refresh_token(self) -> None:
        access = create_access_token(subject="user-456")
        with pytest.raises(ValueError, match="not a refresh token"):
            decode_refresh_token(access)
