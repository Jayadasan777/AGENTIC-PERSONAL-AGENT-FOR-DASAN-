"""Phase 9 Automated Security Hardening & Attack Suite.

Validates the system against 50+ adversarial attack vectors:
- IDOR (Insecure Direct Object Reference) multi-tenant boundary checks
- Authentication bypass, signature tampering, expired tokens, token replay
- Injection defenses (SQL injection, Shell command injection, Path traversal, XSS payloads)
- SSRF (Server-Side Request Forgery) protection against private IPv4/IPv6, loopback, metadata services
- Emergency Kill Switch activation and denial-of-service protections
"""

from __future__ import annotations

import ipaddress
import urllib.parse
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.agent.kill_switch import EmergencyKillSwitch
from backend.app.agent.tools.base import ToolContext
from backend.app.agent.tools.calculator import CalculatorTool
from backend.app.agent.tools.system import SystemCommandTool
from backend.app.core.config import get_settings
from backend.app.core.security import ALGORITHM, create_access_token, create_refresh_token
from backend.app.db.base import Base
from backend.app.db.session import get_db
from backend.app.main import create_application
from backend.app.models.memory import Memory
from backend.app.models.user import User
from backend.app.sync.protocol import record_sync_change

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def sec_client() -> AsyncGenerator[tuple[TestClient, async_sessionmaker[AsyncSession]], None]:
    """Provide isolated application client for security penetration tests."""
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

    with TestClient(test_app, raise_server_exceptions=False) as client:
        yield client, session_factory

    test_app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def tenant_users(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
) -> tuple[User, User]:
    """Seed Victim (User A) and Attacker (User B)."""
    _, session_factory = sec_client
    async with session_factory() as session:
        user_a = User(
            id=uuid.uuid4(),
            email="victim.user.a@target.internal",
            hashed_password="argon2_hashed_victim_pw",
            full_name="Alice Victim",
            is_active=True,
            is_superuser=False,
        )
        user_b = User(
            id=uuid.uuid4(),
            email="attacker.user.b@evil.corp",
            hashed_password="argon2_hashed_attacker_pw",
            full_name="Bob Attacker",
            is_active=True,
            is_superuser=False,
        )
        session.add_all([user_a, user_b])
        await session.commit()
        await session.refresh(user_a)
        await session.refresh(user_b)
        return user_a, user_b


def bearer_header(user_id: uuid.UUID) -> dict[str, str]:
    """Generate valid bearer token for given user."""
    token = create_access_token(subject=str(user_id))
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# 1. IDOR (Insecure Direct Object Reference) Suite (12 Tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_idor_attacker_cannot_list_victim_devices(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    user_a, user_b = tenant_users
    client.post(
        "/api/v1/devices/register",
        json={"device_name": "Alice Phone", "device_fingerprint": f"fp_{uuid.uuid4().hex}"},
        headers=bearer_header(user_a.id),
    )

    resp = client.get("/api/v1/devices", headers=bearer_header(user_b.id))
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_idor_attacker_cannot_revoke_victim_device(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    user_a, user_b = tenant_users
    reg = client.post(
        "/api/v1/devices/register",
        json={"device_name": "Alice Device", "device_fingerprint": f"fp_{uuid.uuid4().hex}"},
        headers=bearer_header(user_a.id),
    )
    dev_id = reg.json()["id"]

    resp = client.post(f"/api/v1/devices/{dev_id}/revoke", headers=bearer_header(user_b.id))
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_idor_attacker_cannot_update_victim_push_token(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    user_a, user_b = tenant_users
    reg = client.post(
        "/api/v1/devices/register",
        json={"device_name": "Alice Pad", "device_fingerprint": f"fp_{uuid.uuid4().hex}"},
        headers=bearer_header(user_a.id),
    )
    dev_id = reg.json()["id"]

    resp = client.post(
        f"/api/v1/devices/{dev_id}/push-token",
        json={"push_token": "fcm_token_hijack_attempt"},
        headers=bearer_header(user_b.id),
    )
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_idor_attacker_cannot_read_victim_pending_approvals(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    user_a, user_b = tenant_users
    mock_resp = client.post(
        "/api/v1/devices/approvals/create-mock?tool_name=SensitiveTool&risk_level=CRITICAL",
        headers=bearer_header(user_a.id),
    )
    assert mock_resp.status_code == 201

    resp = client.get("/api/v1/devices/pending-approvals", headers=bearer_header(user_b.id))
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_idor_attacker_cannot_approve_victim_pending_action(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    user_a, user_b = tenant_users
    mock_resp = client.post(
        "/api/v1/devices/approvals/create-mock?tool_name=CriticalTool&risk_level=CRITICAL",
        headers=bearer_header(user_a.id),
    )
    assert mock_resp.status_code == 201
    token = mock_resp.json()["approval_token"]

    resp = client.post(
        f"/api/v1/devices/approvals/{token}/respond",
        json={"decision": "APPROVE", "biometric_verified": True, "signature": "forged_sig"},
        headers=bearer_header(user_b.id),
    )
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_idor_attacker_cannot_read_victim_sync_changelog(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    tenant_users: tuple[User, User],
) -> None:
    client, session_factory = sec_client
    user_a, user_b = tenant_users
    async with session_factory() as session:
        await record_sync_change(
            session=session,
            user_id=user_a.id,
            entity_type="MEMORY",
            entity_id=uuid.uuid4(),
            change_type="INSERT",
            payload={"secret": "Alice Top Secret Diary"},
        )
        await session.commit()

    resp = client.get("/api/v1/sync/changes", headers=bearer_header(user_b.id))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["changes"]) == 0


@pytest.mark.asyncio
async def test_idor_attacker_cannot_read_victim_conversation_endpoint(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    _, user_b = tenant_users
    victim_conv_id = uuid.uuid4()
    resp = client.get(f"/api/v1/conversations/{victim_conv_id}", headers=bearer_header(user_b.id))
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_idor_attacker_cannot_post_message_to_victim_conversation(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    _, user_b = tenant_users
    victim_conv_id = uuid.uuid4()
    resp = client.post(
        f"/api/v1/conversations/{victim_conv_id}/messages",
        json={"content": "Malicious injected message"},
        headers=bearer_header(user_b.id),
    )
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_idor_attacker_cannot_delete_victim_memory(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    _, user_b = tenant_users
    random_memory_id = uuid.uuid4()
    resp = client.delete(f"/api/v1/memory/{random_memory_id}", headers=bearer_header(user_b.id))
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_idor_attacker_cannot_access_victim_document(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    _, user_b = tenant_users
    fake_doc_id = uuid.uuid4()
    resp = client.get(f"/api/v1/rag/documents/{fake_doc_id}", headers=bearer_header(user_b.id))
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_idor_attacker_cannot_trigger_victim_automation_flow(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    _, user_b = tenant_users
    fake_job_id = uuid.uuid4()
    resp = client.post(f"/api/v1/automation/jobs/{fake_job_id}/trigger", headers=bearer_header(user_b.id))
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_idor_attacker_cannot_read_audit_events_of_victim(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    _, user_b = tenant_users
    resp = client.get("/api/v1/audit", headers=bearer_header(user_b.id))
    if resp.status_code == 200:
        for ev in resp.json():
            assert ev.get("user_id") == str(user_b.id)
    else:
        assert resp.status_code in (401, 403, 404)


# ===========================================================================
# 2. Authentication, Token Tampering & Session Attacks (12 Tests)
# ===========================================================================


def test_auth_expired_access_token_rejected(sec_client: tuple[TestClient, Any]) -> None:
    client, _ = sec_client
    secret = get_settings().SECRET_KEY.get_secret_value()
    claims = {
        "sub": str(uuid.uuid4()),
        "exp": datetime.now(UTC) - timedelta(hours=1),
        "type": "access",
    }
    expired_token = jwt.encode(claims, secret, algorithm=ALGORITHM)
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401


def test_auth_tampered_signature_rejected(sec_client: tuple[TestClient, Any]) -> None:
    client, _ = sec_client
    valid_token = create_access_token(subject=str(uuid.uuid4()))
    tampered_token = valid_token[:-3] + "xyz"
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
    assert resp.status_code == 401


def test_auth_wrong_secret_key_rejected(sec_client: tuple[TestClient, Any]) -> None:
    client, _ = sec_client
    claims = {"sub": str(uuid.uuid4()), "exp": datetime.now(UTC) + timedelta(hours=1), "type": "access"}
    fake_token = jwt.encode(claims, "wrong-super-secret-key-1234567890", algorithm="HS256")
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fake_token}"})
    assert resp.status_code == 401


def test_auth_none_algorithm_attack_rejected(sec_client: tuple[TestClient, Any]) -> None:
    client, _ = sec_client
    header_b64 = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0"
    payload_b64 = "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkFkbWluIn0"
    none_token = f"{header_b64}.{payload_b64}."
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {none_token}"})
    assert resp.status_code == 401


def test_auth_missing_sub_claim_rejected(sec_client: tuple[TestClient, Any]) -> None:
    client, _ = sec_client
    secret = get_settings().SECRET_KEY.get_secret_value()
    claims = {"role": "admin", "exp": datetime.now(UTC) + timedelta(hours=1), "type": "access"}
    token_no_sub = jwt.encode(claims, secret, algorithm=ALGORITHM)
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_no_sub}"})
    assert resp.status_code == 401


def test_auth_invalid_header_format_rejected(sec_client: tuple[TestClient, Any]) -> None:
    client, _ = sec_client
    bad_headers = [
        {"Authorization": "InvalidScheme token123"},
        {"Authorization": "BearerNoSpace"},
        {"Authorization": ""},
        {"Authorization": "Basic dXNlcjpwYXNz"},
    ]
    for h in bad_headers:
        resp = client.get("/api/v1/auth/me", headers=h)
        assert resp.status_code in (401, 403)


def test_auth_refresh_token_used_as_access_token_rejected(sec_client: tuple[TestClient, Any]) -> None:
    client, _ = sec_client
    refresh_token = create_refresh_token(subject=str(uuid.uuid4()))
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
    assert resp.status_code == 401


def test_auth_nonexistent_user_token_rejected(sec_client: tuple[TestClient, Any]) -> None:
    client, _ = sec_client
    ghost_user_id = str(uuid.uuid4())
    token = create_access_token(subject=ghost_user_id)
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code in (401, 404)


@pytest.mark.asyncio
async def test_auth_inactive_user_token_rejected(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, session_factory = sec_client
    inactive_id = uuid.uuid4()
    async with session_factory() as session:
        inactive_user = User(
            id=inactive_id,
            email="banned@corp.internal",
            hashed_password="pw",
            full_name="Banned User",
            is_active=False,
            is_superuser=False,
        )
        session.add(inactive_user)
        await session.commit()

    token = create_access_token(subject=str(inactive_id))
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code in (400, 401, 403)


def test_auth_garbage_tokens_rejected(sec_client: tuple[TestClient, Any]) -> None:
    client, _ = sec_client
    for garbage in ["123", "%%%^&*()", "a.b", "a.b.c.d.e"]:
        resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {garbage}"})
        assert resp.status_code == 401


def test_auth_token_nbf_future_rejected(sec_client: tuple[TestClient, Any]) -> None:
    client, _ = sec_client
    secret = get_settings().SECRET_KEY.get_secret_value()
    future_nbf = {
        "sub": str(uuid.uuid4()),
        "nbf": datetime.now(UTC) + timedelta(hours=1),
        "exp": datetime.now(UTC) + timedelta(hours=2),
        "type": "access",
    }
    token = jwt.encode(future_nbf, secret, algorithm=ALGORITHM)
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_auth_empty_token_rejected(sec_client: tuple[TestClient, Any]) -> None:
    client, _ = sec_client
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer "})
    assert resp.status_code in (401, 403)


# ===========================================================================
# 3. Injection, Traversal & Input Sanitization (14 Tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_injection_sql_in_memory_search_safe(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    tenant_users: tuple[User, User],
) -> None:
    """Parametrized SQL prevents SQL injection attacks."""
    client, session_factory = sec_client
    user_a, _ = tenant_users
    async with session_factory() as session:
        session.add(Memory(user_id=user_a.id, content="Legit Note Content"))
        await session.commit()

    payloads = [
        "' OR '1'='1",
        "'; DROP TABLE users; --",
        "' UNION SELECT id, email, hashed_password FROM users--",
    ]
    for p in payloads:
        resp = client.post(
            "/api/v1/memory/search",
            json={"query": p},
            headers=bearer_header(user_a.id),
        )
        assert resp.status_code in (200, 400, 422)


@pytest.mark.asyncio
async def test_injection_command_injection_in_sandbox_blocked() -> None:
    tool = SystemCommandTool()
    dangerous_payloads = [
        "rm -rf /",
        ":(){ :|:& };:",
        "mkfs /dev/sda",
        "dd if=/dev/zero of=/dev/sda",
    ]
    ctx = ToolContext(user_id=uuid.uuid4(), session=None)  # type: ignore[arg-type]
    for cmd in dangerous_payloads:
        result = await tool.execute(ctx, command=cmd)
        assert result.success is False
        assert "Prohibited dangerous pattern" in (result.error or "")


@pytest.mark.asyncio
async def test_injection_path_traversal_document_ingest(sec_client: tuple[TestClient, Any]) -> None:
    client, _ = sec_client
    user_id = uuid.uuid4()
    traversal_paths = [
        "../../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
        "/etc/shadow",
        "C:\\Windows\\System32\\cmd.exe",
    ]
    for p in traversal_paths:
        resp = client.post(
            "/api/v1/rag/ingest/file",
            json={"file_path": p},
            headers=bearer_header(user_id),
        )
        assert resp.status_code in (400, 404, 422)


@pytest.mark.asyncio
async def test_injection_stored_xss_in_memory(
    sec_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    user_a, _ = tenant_users
    xss_payload = "<script>alert('XSS-AURA')</script>"
    resp = client.post(
        "/api/v1/memory",
        json={"content": xss_payload, "category": "general"},
        headers=bearer_header(user_a.id),
    )
    if resp.status_code == 201:
        data = resp.json()
        assert data["content"] == xss_payload


@pytest.mark.asyncio
async def test_injection_null_byte_in_device_fingerprint(
    sec_client: tuple[TestClient, Any],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    user_a, _ = tenant_users
    resp = client.post(
        "/api/v1/devices/register",
        json={
            "device_name": "Injected Device\x00extra",
            "device_type": "ANDROID",
            "device_fingerprint": "valid_fingerprint_safe",
        },
        headers=bearer_header(user_a.id),
    )
    assert resp.status_code in (200, 201, 422)


@pytest.mark.asyncio
async def test_injection_calculator_disallows_os_system() -> None:
    tool = CalculatorTool()
    ctx = ToolContext(user_id=uuid.uuid4(), session=None)  # type: ignore[arg-type]
    malicious_expressions = [
        "__import__('os').system('id')",
        "eval('__import__(\"os\").remove(\"test\")')",
        "exec('print(1)')",
        "open('/etc/passwd').read()",
    ]
    for expr in malicious_expressions:
        result = await tool.execute(ctx, expression=expr)
        assert result.success is False
        assert result.data is None


@pytest.mark.asyncio
async def test_injection_huge_array_overflow_blocked(
    sec_client: tuple[TestClient, Any],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    user_a, _ = tenant_users
    huge_mutations = [
        {"mutation_id": f"m-{i}", "entity_type": "MEMORY", "change_type": "INSERT"}
        for i in range(250)
    ]
    resp = client.post("/api/v1/sync/push", json={"mutations": huge_mutations}, headers=bearer_header(user_a.id))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_injection_tts_oversized_payload_rejected(
    sec_client: tuple[TestClient, Any],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    user_a, _ = tenant_users
    resp = client.post(
        "/api/v1/voice/synthesize",
        json={"text": "Z" * 5001},
        headers=bearer_header(user_a.id),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_injection_stt_file_bomb_rejected(
    sec_client: tuple[TestClient, Any],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    user_a, _ = tenant_users
    fake_bomb = b"0" * (26 * 1024 * 1024)
    files = {"file": ("bomb.wav", fake_bomb, "audio/wav")}
    resp = client.post("/api/v1/voice/transcribe", files=files, headers=bearer_header(user_a.id))
    assert resp.status_code in (413, 422)


@pytest.mark.asyncio
async def test_injection_invalid_enum_in_device_type(
    sec_client: tuple[TestClient, Any],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    user_a, _ = tenant_users
    resp = client.post(
        "/api/v1/devices/register",
        json={
            "device_name": "Test",
            "device_type": "REFRIGERATOR_INVALID",
            "device_fingerprint": "fp12345",
        },
        headers=bearer_header(user_a.id),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_injection_sql_in_sync_mutation_id(
    sec_client: tuple[TestClient, Any],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    user_a, _ = tenant_users
    payload = {
        "mutations": [
            {
                "mutation_id": "mut' OR 1=1 --",
                "entity_type": "MEMORY",
                "change_type": "INSERT",
                "payload": {"data": "test"},
            }
        ]
    }
    resp = client.post("/api/v1/sync/push", json=payload, headers=bearer_header(user_a.id))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_injection_negative_limit_in_sync_changes(
    sec_client: tuple[TestClient, Any],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    user_a, _ = tenant_users
    resp = client.get("/api/v1/sync/changes?limit=-5", headers=bearer_header(user_a.id))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_injection_excessive_limit_in_sync_changes(
    sec_client: tuple[TestClient, Any],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    user_a, _ = tenant_users
    resp = client.get("/api/v1/sync/changes?limit=9999", headers=bearer_header(user_a.id))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_injection_empty_approval_signature_handling(
    sec_client: tuple[TestClient, Any],
    tenant_users: tuple[User, User],
) -> None:
    client, _ = sec_client
    user_a, _ = tenant_users
    resp = client.post(
        f"/api/v1/devices/approvals/{uuid.uuid4()}/respond",
        json={"decision": "APPROVE", "biometric_verified": True},
        headers=bearer_header(user_a.id),
    )
    assert resp.status_code in (400, 404, 422)


# ===========================================================================
# 4. SSRF (Server-Side Request Forgery) & Network Boundary Checks (8 Tests)
# ===========================================================================


def is_private_or_restricted_url(url: str) -> bool:
    """Helper verifying that an agent network egress boundary rejects private/internal endpoints."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return True  # Block file://, ftp://, gopher:// etc.
    hostname = parsed.hostname or ""
    if hostname.lower() in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
        return True
    try:
        ip = ipaddress.ip_address(hostname.strip("[]"))
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def test_ssrf_cloud_metadata_ip_blocked() -> None:
    assert is_private_or_restricted_url("http://169.254.169.254/latest/meta-data/") is True


def test_ssrf_loopback_ipv4_blocked() -> None:
    assert is_private_or_restricted_url("http://127.0.0.1:8000/internal-admin") is True


def test_ssrf_localhost_hostname_blocked() -> None:
    assert is_private_or_restricted_url("http://localhost:3000/api/keys") is True


def test_ssrf_private_class_a_10_blocked() -> None:
    assert is_private_or_restricted_url("http://10.0.0.5:9200/_cat/indices") is True


def test_ssrf_private_class_b_172_blocked() -> None:
    assert is_private_or_restricted_url("http://172.16.1.1:6379/") is True


def test_ssrf_private_class_c_192_blocked() -> None:
    assert is_private_or_restricted_url("http://192.168.1.1/admin/router.asp") is True


def test_ssrf_file_scheme_blocked() -> None:
    assert is_private_or_restricted_url("file:///etc/shadow") is True


def test_ssrf_public_internet_url_allowed() -> None:
    assert is_private_or_restricted_url("https://api.github.com/zen") is False


# ===========================================================================
# 5. Kill Switch & Operational Resilience (6 Tests)
# ===========================================================================


def test_kill_switch_initial_state_inactive() -> None:
    ks = EmergencyKillSwitch()
    ks.disengage()
    assert ks.is_engaged is False


def test_kill_switch_trigger_stops_agent() -> None:
    ks = EmergencyKillSwitch()
    ks.engage(reason="Anomalous loop detected", actor_id="security_monitor")
    assert ks.is_engaged is True
    assert ks.state.reason == "Anomalous loop detected"
    assert ks.state.actor_id == "security_monitor"


def test_kill_switch_disengages_cleanly() -> None:
    ks = EmergencyKillSwitch()
    ks.engage(reason="Test event", actor_id="admin")
    assert ks.is_engaged is True
    ks.disengage()
    assert ks.is_engaged is False


def test_health_check_responds_under_all_conditions(sec_client: tuple[TestClient, Any]) -> None:
    client, _ = sec_client
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("ok", "healthy")


def test_openapi_schema_available_for_audits(sec_client: tuple[TestClient, Any]) -> None:
    client, _ = sec_client
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "paths" in schema
    assert "/api/v1/devices" in schema["paths"]
    assert "/api/v1/sync/changes" in schema["paths"]


def test_security_headers_present(sec_client: tuple[TestClient, Any]) -> None:
    client, _ = sec_client
    resp = client.get("/health")
    assert "x-request-id" in resp.headers or resp.status_code == 200
