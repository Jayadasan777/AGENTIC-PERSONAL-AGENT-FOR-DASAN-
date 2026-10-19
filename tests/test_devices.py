"""Phase 7 Test Suite: Companion Devices, Mobile Biometric Approvals, and Android Architecture.

Tests cover:
- Companion device registration, tenant isolation, and update workflows.
- Remote device revocation with immediate invalidation.
- Push notification token management.
- Pending mobile approvals query with expiration filtering.
- Biometric approval and rejection resolution.
- Protection against IDOR and cross-user revocation attempts.
- Android project structure, Room entities, WorkManager, and Biometric prompt files.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.api.v1.dependencies.auth import get_current_user
from backend.app.core.security import create_access_token
from backend.app.db.base import Base
from backend.app.db.session import get_async_session, get_db
from backend.app.main import create_application
from backend.app.models.device import Device, DeviceType, MobileApprovalAction
from backend.app.models.user import User

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def app_client() -> AsyncGenerator[tuple[TestClient, async_sessionmaker[AsyncSession]], None]:
    """Create isolated FastAPI app with in-memory SQLite DB for device tests."""
    engine = create_async_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    test_app = create_application()
    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_async_session] = override_get_db

    with TestClient(test_app, raise_server_exceptions=False) as c:
        yield c, session_factory

    await engine.dispose()


@pytest_asyncio.fixture
async def test_user(
    app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
) -> User:
    """Create a persistent test user in DB for integration tests."""
    _, session_factory = app_client
    async with session_factory() as session:
        user = User(
            email=f"device_user_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="argon2id$mock_hash_for_test",
            full_name="Device Test User",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def other_user(
    app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
) -> User:
    """Create a secondary user to verify cross-tenant boundaries."""
    _, session_factory = app_client
    async with session_factory() as session:
        user = User(
            email=f"other_user_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="argon2id$mock_hash_for_test",
            full_name="Other User",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


def make_auth_headers(user: User) -> dict[str, str]:
    """Generate valid JWT bearer header for user."""
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. Device Registration and Lifecycle Tests
# ---------------------------------------------------------------------------


class TestDeviceRegistrationAndLifecycle:
    @pytest.mark.asyncio
    async def test_register_device_success(
        self,
        app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
        test_user: User,
    ) -> None:
        client, _ = app_client
        headers = make_auth_headers(test_user)
        payload = {
            "device_name": "Pixel 8 Pro",
            "device_type": "ANDROID",
            "device_fingerprint": f"fp_{uuid.uuid4().hex}",
            "public_key": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A...",
            "push_token": "fcm_token_xyz_123",
            "metadata": {"os_version": "14", "app_version": "1.0.0"},
        }

        resp = client.post("/api/v1/devices/register", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["device_name"] == "Pixel 8 Pro"
        assert data["device_type"] == "ANDROID"
        assert data["is_revoked"] is False
        assert data["has_push_token"] is True
        assert "id" in data

    @pytest.mark.asyncio
    async def test_re_register_updates_existing_device(
        self,
        app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
        test_user: User,
    ) -> None:
        client, _ = app_client
        headers = make_auth_headers(test_user)
        fingerprint = f"fp_static_{uuid.uuid4().hex}"
        payload1 = {
            "device_name": "Galaxy S23",
            "device_type": "ANDROID",
            "device_fingerprint": fingerprint,
            "push_token": "old_token",
        }
        resp1 = client.post("/api/v1/devices/register", json=payload1, headers=headers)
        assert resp1.status_code == 201
        device_id = resp1.json()["id"]

        # Re-register same fingerprint with new name and token
        payload2 = {
            "device_name": "Galaxy S23 Ultra",
            "device_type": "ANDROID",
            "device_fingerprint": fingerprint,
            "push_token": "new_token",
        }
        resp2 = client.post("/api/v1/devices/register", json=payload2, headers=headers)
        assert resp2.status_code == 201
        assert resp2.json()["id"] == device_id
        assert resp2.json()["device_name"] == "Galaxy S23 Ultra"

    @pytest.mark.asyncio
    async def test_list_devices_tenant_isolation(
        self,
        app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
        test_user: User,
        other_user: User,
    ) -> None:
        client, _ = app_client
        headers1 = make_auth_headers(test_user)
        headers2 = make_auth_headers(other_user)

        client.post(
            "/api/v1/devices/register",
            json={
                "device_name": "User 1 Phone",
                "device_fingerprint": f"fp_{uuid.uuid4().hex}",
            },
            headers=headers1,
        )
        client.post(
            "/api/v1/devices/register",
            json={
                "device_name": "User 2 Phone",
                "device_fingerprint": f"fp_{uuid.uuid4().hex}",
            },
            headers=headers2,
        )

        resp1 = client.get("/api/v1/devices", headers=headers1)
        resp2 = client.get("/api/v1/devices", headers=headers2)

        names1 = [d["device_name"] for d in resp1.json()]
        names2 = [d["device_name"] for d in resp2.json()]

        assert "User 1 Phone" in names1
        assert "User 2 Phone" not in names1
        assert "User 2 Phone" in names2
        assert "User 1 Phone" not in names2

    @pytest.mark.asyncio
    async def test_remote_device_revocation(
        self,
        app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
        test_user: User,
        other_user: User,
    ) -> None:
        client, _ = app_client
        headers = make_auth_headers(test_user)
        reg_resp = client.post(
            "/api/v1/devices/register",
            json={
                "device_name": "Device to Revoke",
                "device_fingerprint": f"fp_{uuid.uuid4().hex}",
                "push_token": "active_token",
            },
            headers=headers,
        )
        device_id = reg_resp.json()["id"]

        # Other user cannot revoke this device (IDOR defense)
        other_headers = make_auth_headers(other_user)
        idor_resp = client.post(f"/api/v1/devices/{device_id}/revoke", headers=other_headers)
        assert idor_resp.status_code == 404

        # Owner revokes device
        revoke_resp = client.post(f"/api/v1/devices/{device_id}/revoke", headers=headers)
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["status"] == "revoked"

        # List should not contain revoked device by default
        list_resp = client.get("/api/v1/devices", headers=headers)
        ids = [d["id"] for d in list_resp.json()]
        assert device_id not in ids

        # List with include_revoked=true shows it as revoked
        list_all = client.get("/api/v1/devices?include_revoked=true", headers=headers)
        matching = [d for d in list_all.json() if d["id"] == device_id]
        assert len(matching) == 1
        assert matching[0]["is_revoked"] is True
        assert matching[0]["has_push_token"] is False


# ---------------------------------------------------------------------------
# 2. Biometric Human-In-The-Loop Approval Tests
# ---------------------------------------------------------------------------


class TestMobileBiometricApprovals:
    @pytest.mark.asyncio
    async def test_pending_approvals_and_biometric_approve(
        self,
        app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
        test_user: User,
    ) -> None:
        client, _ = app_client
        headers = make_auth_headers(test_user)

        # Create a mock pending action
        mock_action = client.post(
            "/api/v1/devices/approvals/create-mock?tool_name=BashTool&risk_level=CRITICAL",
            headers=headers,
        )
        assert mock_action.status_code == 201
        token = mock_action.json()["approval_token"]

        # Query pending approvals
        pending_resp = client.get("/api/v1/devices/pending-approvals", headers=headers)
        assert pending_resp.status_code == 200
        tokens = [p["approval_token"] for p in pending_resp.json()]
        assert token in tokens

        # Respond with biometric approval
        respond_resp = client.post(
            f"/api/v1/devices/approvals/{token}/respond",
            json={
                "decision": "APPROVE",
                "biometric_verified": True,
                "signature": "mock_biometric_crypto_signature_xyz",
            },
            headers=headers,
        )
        assert respond_resp.status_code == 200
        data = respond_resp.json()
        assert data["status"] == "APPROVED"
        assert data["biometric_verified"] is True

        # Second response returns 409 Conflict (idempotency defense)
        dup_resp = client.post(
            f"/api/v1/devices/approvals/{token}/respond",
            json={"decision": "APPROVE", "biometric_verified": True},
            headers=headers,
        )
        assert dup_resp.status_code == 409

    @pytest.mark.asyncio
    async def test_deny_approval(
        self,
        app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
        test_user: User,
    ) -> None:
        client, _ = app_client
        headers = make_auth_headers(test_user)
        mock_action = client.post(
            "/api/v1/devices/approvals/create-mock?tool_name=DeleteUserDBTool&risk_level=CRITICAL",
            headers=headers,
        )
        token = mock_action.json()["approval_token"]

        deny_resp = client.post(
            f"/api/v1/devices/approvals/{token}/respond",
            json={"decision": "DENY", "biometric_verified": False},
            headers=headers,
        )
        assert deny_resp.status_code == 200
        assert deny_resp.json()["status"] == "REJECTED"


# ---------------------------------------------------------------------------
# 3. Android Repository Artifacts Verification
# ---------------------------------------------------------------------------


class TestAndroidArtifacts:
    def test_android_manifest_and_permissions(self) -> None:
        manifest_path = Path("android/app/src/main/AndroidManifest.xml")
        assert manifest_path.is_file(), "AndroidManifest.xml must exist"
        content = manifest_path.read_text()
        assert "android.permission.USE_BIOMETRIC" in content
        assert "android.permission.INTERNET" in content
        assert "android.permission.POST_NOTIFICATIONS" in content

    def test_room_database_and_dao(self) -> None:
        entity_path = Path("android/app/src/main/java/com/aura/companion/data/local/ApprovalEntity.kt")
        dao_path = Path("android/app/src/main/java/com/aura/companion/data/local/ApprovalDao.kt")
        db_path = Path("android/app/src/main/java/com/aura/companion/data/local/AuraDatabase.kt")

        assert entity_path.is_file()
        assert dao_path.is_file()
        assert db_path.is_file()

        assert "@Entity(tableName = \"pending_approvals\")" in entity_path.read_text()
        assert "@Dao" in dao_path.read_text()
        assert "RoomDatabase()" in db_path.read_text()

    def test_workmanager_and_biometric_manager(self) -> None:
        worker_path = Path("android/app/src/main/java/com/aura/companion/sync/AuraSyncWorker.kt")
        biometric_path = Path("android/app/src/main/java/com/aura/companion/auth/BiometricAuthManager.kt")

        assert worker_path.is_file()
        assert biometric_path.is_file()
        assert "CoroutineWorker" in worker_path.read_text()
        assert "BiometricPrompt" in biometric_path.read_text()

    def test_compose_ui_screen(self) -> None:
        ui_path = Path("android/app/src/main/java/com/aura/companion/ui/AuraCompanionApp.kt")
        assert ui_path.is_file()
        assert "@Composable" in ui_path.read_text()
        assert "AuraCompanionApp" in ui_path.read_text()
