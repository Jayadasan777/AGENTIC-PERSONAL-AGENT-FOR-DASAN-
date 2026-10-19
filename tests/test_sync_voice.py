"""Phase 8 Test Suite: Cross-Device Synchronization Protocol and Local Voice Intelligence.

Tests cover:
- Monotonic sequence numbering and delta pagination with opaque cursor tokens.
- Multi-device tenant isolation for sync change log.
- Offline mutation batch push, deduplication, and replay idempotency.
- Last-Write-Wins (LWW) conflict resolution between server and offline client edits.
- Voice transcription (STT) endpoint with payload validation and audio size limit.
- Voice synthesis (TTS) endpoint returning compliant WAV audio streams and headers.
"""

from __future__ import annotations

import io
import uuid
import wave
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.core.security import create_access_token
from backend.app.db.base import Base
from backend.app.db.session import get_db
from backend.app.main import create_application
from backend.app.models.user import User
from backend.app.sync.protocol import record_sync_change

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def app_client() -> AsyncGenerator[tuple[TestClient, async_sessionmaker[AsyncSession]], None]:
    """Create isolated FastAPI app with in-memory SQLite DB for sync & voice tests."""
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

    with TestClient(test_app, raise_server_exceptions=True) as client:
        yield client, session_factory

    test_app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def test_users(
    app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
) -> tuple[User, User]:
    """Seed two distinct tenant users."""
    _, session_factory = app_client
    async with session_factory() as session:
        user_a = User(
            id=uuid.uuid4(),
            email="alice.sync@example.com",
            hashed_password="hashed_pw_alice",
            full_name="Alice Sync",
            is_active=True,
            is_superuser=False,
        )
        user_b = User(
            id=uuid.uuid4(),
            email="bob.sync@example.com",
            hashed_password="hashed_pw_bob",
            full_name="Bob Sync",
            is_active=True,
            is_superuser=False,
        )
        session.add_all([user_a, user_b])
        await session.commit()
        await session.refresh(user_a)
        await session.refresh(user_b)
        return user_a, user_b


def auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    """Generate JWT authorization header for user."""
    token = create_access_token(subject=str(user_id))
    return {"Authorization": f"Bearer {token}"}


def create_dummy_wav(duration_sec: float = 0.5, sample_rate: int = 16000) -> bytes:
    """Create a minimal valid in-memory PCM WAV audio clip."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_frames = int(duration_sec * sample_rate)
        # 0.5s of silence / low noise PCM 16-bit
        wf.writeframes(b"\x00\x00" * num_frames)
    return buffer.getvalue()


# ===========================================================================
# 1. Delta Changes and Pagination
# ===========================================================================


@pytest.mark.asyncio
async def test_sync_changes_pagination_and_tenant_isolation(
    app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    test_users: tuple[User, User],
) -> None:
    """Test delta pagination with cursors and confirm complete tenant isolation."""
    client, session_factory = app_client
    user_a, user_b = test_users

    # Record 3 changes for User A and 1 for User B
    async with session_factory() as session:
        for i in range(1, 4):
            await record_sync_change(
                session=session,
                user_id=user_a.id,
                entity_type="MEMORY",
                entity_id=uuid.uuid4(),
                change_type="INSERT",
                payload={"title": f"Memory {i}", "priority": i},
            )
        await record_sync_change(
            session=session,
            user_id=user_b.id,
            entity_type="CONVERSATION",
            entity_id=uuid.uuid4(),
            change_type="INSERT",
            payload={"title": "Bob's private conversation"},
        )
        await session.commit()

    # User A requests all changes (limit=2 to test pagination)
    headers_a = auth_headers(user_a.id)
    resp = client.get("/api/v1/sync/changes?limit=2", headers=headers_a)
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["changes"]) == 2
    assert data["has_more"] is True
    assert data["latest_server_seq"] == 2
    cursor_page_1 = data["next_cursor"]
    assert cursor_page_1 is not None

    # Fetch page 2 using cursor
    resp_page_2 = client.get(f"/api/v1/sync/changes?cursor={cursor_page_1}&limit=2", headers=headers_a)
    assert resp_page_2.status_code == 200
    data_page_2 = resp_page_2.json()

    assert len(data_page_2["changes"]) == 1
    assert data_page_2["has_more"] is False
    assert data_page_2["changes"][0]["payload"]["title"] == "Memory 3"
    assert data_page_2["latest_server_seq"] == 3

    # Tenant Isolation: User B requests changes, should ONLY see Bob's 1 record
    headers_b = auth_headers(user_b.id)
    resp_b = client.get("/api/v1/sync/changes", headers=headers_b)
    assert resp_b.status_code == 200
    data_b = resp_b.json()

    assert len(data_b["changes"]) == 1
    assert data_b["changes"][0]["payload"]["title"] == "Bob's private conversation"
    assert data_b["latest_server_seq"] == 1


# ===========================================================================
# 2. Offline Queue Batch Push & Idempotency
# ===========================================================================


@pytest.mark.asyncio
async def test_offline_batch_push_and_deduplication(
    app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    test_users: tuple[User, User],
) -> None:
    """Test replaying queued offline mutations and idempotent deduplication."""
    client, _ = app_client
    user_a, _ = test_users
    headers = auth_headers(user_a.id)

    mutation_id_1 = "offline-client-mut-001"
    mutation_id_2 = "offline-client-mut-002"
    mem_id = str(uuid.uuid4())

    batch_payload = {
        "mutations": [
            {
                "mutation_id": mutation_id_1,
                "entity_type": "MEMORY",
                "entity_id": mem_id,
                "change_type": "INSERT",
                "payload": {"content": "Created offline in subway"},
                "client_timestamp": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
            },
            {
                "mutation_id": mutation_id_2,
                "entity_type": "MEMORY",
                "entity_id": mem_id,
                "change_type": "UPDATE",
                "payload": {"content": "Edited offline in subway v2"},
                "client_timestamp": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            },
        ]
    }

    # First Push
    resp = client.post("/api/v1/sync/push", json=batch_payload, headers=headers)
    assert resp.status_code == 200
    result = resp.json()
    assert result["applied_count"] == 2
    assert result["skipped_count"] == 0
    assert result["conflicted_count"] == 0

    # Second Push with same mutations (simulating network retry/duplicate packet)
    resp_dup = client.post("/api/v1/sync/push", json=batch_payload, headers=headers)
    assert resp_dup.status_code == 200
    result_dup = resp_dup.json()
    assert result_dup["applied_count"] == 0
    assert result_dup["skipped_count"] == 2
    assert result_dup["conflicted_count"] == 0
    assert result_dup["results"][0]["status"] == "SKIPPED_DUPLICATE"
    assert result_dup["results"][1]["status"] == "SKIPPED_DUPLICATE"


# ===========================================================================
# 3. Last-Write-Wins (LWW) Conflict Resolution
# ===========================================================================


@pytest.mark.asyncio
async def test_sync_conflict_resolution_lww(
    app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    test_users: tuple[User, User],
) -> None:
    """Verify that LWW conflict engine resolves concurrent edits based on timestamps."""
    client, session_factory = app_client
    user_a, _ = test_users
    headers = auth_headers(user_a.id)

    target_entity_id = uuid.uuid4()
    t_server = datetime.now(UTC)

    # Server already recorded an edit at t_server
    async with session_factory() as session:
        await record_sync_change(
            session=session,
            user_id=user_a.id,
            entity_type="MEMORY",
            entity_id=target_entity_id,
            change_type="UPDATE",
            payload={"version": "server-winner", "text": "Server updated note"},
            client_timestamp=t_server,
        )
        await session.commit()

    # Case A: Client mutation has older timestamp (t_server - 5 mins) -> SERVER WINS
    t_older_client = t_server - timedelta(minutes=5)
    stale_payload = {
        "mutations": [
            {
                "mutation_id": f"stale-mut-{uuid.uuid4()}",
                "entity_type": "MEMORY",
                "entity_id": str(target_entity_id),
                "change_type": "UPDATE",
                "payload": {"version": "client-stale", "text": "Stale offline edit"},
                "client_timestamp": t_older_client.isoformat(),
                "base_cursor": None,  # Base cursor is older than server sequence
            }
        ]
    }
    resp_stale = client.post("/api/v1/sync/push", json=stale_payload, headers=headers)
    assert resp_stale.status_code == 200
    stale_data = resp_stale.json()
    assert stale_data["conflicted_count"] == 1
    assert stale_data["applied_count"] == 0
    assert stale_data["results"][0]["status"] == "CONFLICT_SERVER_WON"
    assert stale_data["results"][0]["server_payload"]["version"] == "server-winner"

    # Case B: Client mutation has newer timestamp (t_server + 5 mins) -> CLIENT WINS
    t_newer_client = t_server + timedelta(minutes=5)
    newer_payload = {
        "mutations": [
            {
                "mutation_id": f"newer-mut-{uuid.uuid4()}",
                "entity_type": "MEMORY",
                "entity_id": str(target_entity_id),
                "change_type": "UPDATE",
                "payload": {"version": "client-newer", "text": "Brand new offline edit"},
                "client_timestamp": t_newer_client.isoformat(),
                "base_cursor": None,
            }
        ]
    }
    resp_newer = client.post("/api/v1/sync/push", json=newer_payload, headers=headers)
    assert resp_newer.status_code == 200
    newer_data = resp_newer.json()
    assert newer_data["conflicted_count"] == 0
    assert newer_data["applied_count"] == 1
    assert newer_data["results"][0]["status"] == "APPLIED"


# ===========================================================================
# 4. Voice Intelligence: Speech-to-Text (STT)
# ===========================================================================


@pytest.mark.asyncio
async def test_voice_transcription_endpoint(
    app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    test_users: tuple[User, User],
) -> None:
    """Test speech-to-text audio upload and transcription response."""
    client, _ = app_client
    user_a, _ = test_users
    headers = auth_headers(user_a.id)

    dummy_wav = create_dummy_wav(duration_sec=1.0)
    files = {"file": ("test_recording.wav", dummy_wav, "audio/wav")}

    resp = client.post("/api/v1/voice/transcribe", files=files, headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "text" in data
    assert "language" in data
    assert "duration_sec" in data
    assert "confidence_score" in data
    assert "engine_used" in data
    assert data["confidence_score"] > 0.0


@pytest.mark.asyncio
async def test_voice_transcription_oversized_file_rejected(
    app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    test_users: tuple[User, User],
) -> None:
    """Test that audio uploads exceeding 25MB are rejected with 413."""
    client, _ = app_client
    user_a, _ = test_users
    headers = auth_headers(user_a.id)

    # 26 MB dummy payload
    oversized = b"\x00" * (25 * 1024 * 1024 + 1024)
    files = {"file": ("huge_audio.wav", oversized, "audio/wav")}

    resp = client.post("/api/v1/voice/transcribe", files=files, headers=headers)
    assert resp.status_code == 413
    assert "exceeds 25MB" in resp.json()["detail"]


# ===========================================================================
# 5. Voice Intelligence: Text-to-Speech (TTS)
# ===========================================================================


@pytest.mark.asyncio
async def test_voice_synthesis_endpoint(
    app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    test_users: tuple[User, User],
) -> None:
    """Test text-to-speech synthesis generating compliant WAV audio stream."""
    client, _ = app_client
    user_a, _ = test_users
    headers = auth_headers(user_a.id)

    payload = {"text": "Hello Dasan, your personal agent is active and synchronized."}
    resp = client.post("/api/v1/voice/synthesize", json=payload, headers=headers)

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert "X-Audio-Duration" in resp.headers
    assert "X-Audio-Sample-Rate" in resp.headers
    assert "X-TTS-Engine" in resp.headers

    # Validate binary WAV signature: starts with b"RIFF" and format is b"WAVE"
    audio_bytes = resp.content
    assert len(audio_bytes) > 44
    assert audio_bytes[:4] == b"RIFF"
    assert audio_bytes[8:12] == b"WAVE"


@pytest.mark.asyncio
async def test_voice_synthesis_input_validation(
    app_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    test_users: tuple[User, User],
) -> None:
    """Test synthesis input validation for empty or excessively long text."""
    client, _ = app_client
    user_a, _ = test_users
    headers = auth_headers(user_a.id)

    # Empty text -> 422
    resp_empty = client.post("/api/v1/voice/synthesize", json={"text": ""}, headers=headers)
    assert resp_empty.status_code == 422

    # Text > 5000 characters -> 422
    resp_huge = client.post("/api/v1/voice/synthesize", json={"text": "A" * 5001}, headers=headers)
    assert resp_huge.status_code == 422
