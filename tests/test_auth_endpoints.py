"""Integration tests for the auth HTTP endpoints.

These tests use FastAPI's TestClient (synchronous HTTPX wrapper) and an
in-memory SQLite database so they run with NO PostgreSQL dependency.

Test strategy:
- Each test class gets a fresh isolated database to avoid cross-test state pollution.
- We override the ``get_async_session`` dependency to inject a SQLite session.
- We verify HTTP status codes, response schemas, and security invariants.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.session import get_async_session
from backend.app.main import create_application

# ---------------------------------------------------------------------------
# In-memory SQLite test fixture
# ---------------------------------------------------------------------------

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def test_app_and_client():
    """Create isolated FastAPI app with in-memory SQLite DB for each test."""
    # Create engine and tables
    engine = create_async_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    # Override DB dependency
    async def override_get_async_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_application()
    app.dependency_overrides[get_async_session] = override_get_async_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    await engine.dispose()


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestRegister:
    @pytest.mark.asyncio
    async def test_register_new_user_returns_201(self, test_app_and_client: AsyncClient) -> None:
        client = test_app_and_client
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "test@example.com", "password": "securepassword123"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "test@example.com"
        assert "id" in data
        # hashed_password must NEVER appear in any response
        assert "hashed_password" not in data
        assert "password" not in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email_returns_409(
        self, test_app_and_client: AsyncClient
    ) -> None:
        client = test_app_and_client
        payload = {"email": "dup@example.com", "password": "securepassword123"}
        await client.post("/api/v1/auth/register", json=payload)
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_register_short_password_returns_422(
        self, test_app_and_client: AsyncClient
    ) -> None:
        client = test_app_and_client
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "x@example.com", "password": "short"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_email_returns_422(
        self, test_app_and_client: AsyncClient
    ) -> None:
        client = test_app_and_client
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "securepassword123"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_with_full_name(self, test_app_and_client: AsyncClient) -> None:
        client = test_app_and_client
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "named@example.com",
                "password": "securepassword123",
                "full_name": "Dasan AURA",
            },
        )
        assert response.status_code == 201
        assert response.json()["full_name"] == "Dasan AURA"


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------


class TestLogin:
    @pytest_asyncio.fixture(autouse=True)
    async def _register_user(self, test_app_and_client: AsyncClient) -> None:
        """Register a test user before each test in this class."""
        await test_app_and_client.post(
            "/api/v1/auth/register",
            json={"email": "login@example.com", "password": "mypassword123"},
        )

    @pytest.mark.asyncio
    async def test_login_valid_credentials_returns_tokens(
        self, test_app_and_client: AsyncClient
    ) -> None:
        client = test_app_and_client
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "login@example.com", "password": "mypassword123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(
        self, test_app_and_client: AsyncClient
    ) -> None:
        client = test_app_and_client
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "login@example.com", "password": "wrongpassword"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_unknown_email_returns_401(
        self, test_app_and_client: AsyncClient
    ) -> None:
        client = test_app_and_client
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "irrelevant"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_error_message_does_not_distinguish_email_vs_password(
        self, test_app_and_client: AsyncClient
    ) -> None:
        """Verify unified error message prevents user enumeration."""
        client = test_app_and_client
        wrong_email = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "mypassword123"},
        )
        wrong_pass = await client.post(
            "/api/v1/auth/login",
            json={"email": "login@example.com", "password": "wrongpassword"},
        )
        assert wrong_email.json()["detail"] == wrong_pass.json()["detail"]


# ---------------------------------------------------------------------------
# /me endpoint — tenant isolation test
# ---------------------------------------------------------------------------


class TestMe:
    @pytest.mark.asyncio
    async def test_me_requires_auth(self, test_app_and_client: AsyncClient) -> None:
        client = test_app_and_client
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401  # Unauthenticated request returns 401

    @pytest.mark.asyncio
    async def test_me_returns_own_profile(self, test_app_and_client: AsyncClient) -> None:
        client = test_app_and_client
        # Register and login
        await client.post(
            "/api/v1/auth/register",
            json={"email": "me@example.com", "password": "mypassword123"},
        )
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "me@example.com", "password": "mypassword123"},
        )
        access_token = login_resp.json()["access_token"]

        # Call /me
        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == "me@example.com"
        assert "hashed_password" not in me_resp.json()

    @pytest.mark.asyncio
    async def test_me_with_invalid_token_returns_401(
        self, test_app_and_client: AsyncClient
    ) -> None:
        client = test_app_and_client
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer this.is.not.a.valid.token"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_tenant_isolation_users_cannot_see_each_other(
        self, test_app_and_client: AsyncClient
    ) -> None:
        """Two users log in; each /me call returns only their own data."""
        client = test_app_and_client

        # Register user A
        await client.post(
            "/api/v1/auth/register",
            json={"email": "useraaa@example.com", "password": "passwordAAA123"},
        )
        # Register user B
        await client.post(
            "/api/v1/auth/register",
            json={"email": "userbbb@example.com", "password": "passwordBBB123"},
        )

        # Login as A
        login_a = await client.post(
            "/api/v1/auth/login",
            json={"email": "useraaa@example.com", "password": "passwordAAA123"},
        )
        token_a = login_a.json()["access_token"]

        # Login as B
        login_b = await client.post(
            "/api/v1/auth/login",
            json={"email": "userbbb@example.com", "password": "passwordBBB123"},
        )
        token_b = login_b.json()["access_token"]

        # A's /me should return A's email
        me_a = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"}
        )
        assert me_a.json()["email"] == "useraaa@example.com"

        # B's /me should return B's email
        me_b = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token_b}"}
        )
        assert me_b.json()["email"] == "userbbb@example.com"

        # Cross-check: B's email is NOT visible in A's response
        assert me_a.json()["email"] != me_b.json()["email"]


# ---------------------------------------------------------------------------
# Refresh and Logout
# ---------------------------------------------------------------------------


class TestRefreshAndLogout:
    @pytest_asyncio.fixture
    async def tokens(self, test_app_and_client: AsyncClient) -> dict:
        """Helper: register + login and return token pair."""
        client = test_app_and_client
        await client.post(
            "/api/v1/auth/register",
            json={"email": "refresh@example.com", "password": "refreshpass123"},
        )
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "refresh@example.com", "password": "refreshpass123"},
        )
        return resp.json()  # type: ignore[return-value]

    @pytest.mark.asyncio
    async def test_refresh_returns_new_token_pair(
        self, test_app_and_client: AsyncClient, tokens: dict
    ) -> None:
        client = test_app_and_client
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 200
        new_tokens = response.json()
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens
        # New tokens must differ from old ones
        assert new_tokens["access_token"] != tokens["access_token"]
        assert new_tokens["refresh_token"] != tokens["refresh_token"]

    @pytest.mark.asyncio
    async def test_old_refresh_token_rejected_after_rotation(
        self, test_app_and_client: AsyncClient, tokens: dict
    ) -> None:
        client = test_app_and_client
        # Rotate once
        await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        # Try to use the old token again
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_revokes_refresh_token(
        self, test_app_and_client: AsyncClient, tokens: dict
    ) -> None:
        client = test_app_and_client
        logout_resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert logout_resp.status_code == 204

        # After logout, refresh should fail
        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert refresh_resp.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_with_invalid_token_is_silent(
        self, test_app_and_client: AsyncClient
    ) -> None:
        """Logout is idempotent — invalid tokens return 204 silently."""
        client = test_app_and_client
        response = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": "completely.invalid.token"},
        )
        assert response.status_code == 204
