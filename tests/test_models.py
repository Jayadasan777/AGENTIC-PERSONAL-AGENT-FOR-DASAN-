"""Integration tests verifying SQLAlchemy ORM models, relationships, and cascades."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.audit_event import AuditEvent
from backend.app.models.auth_session import AuthSession
from backend.app.models.conversation import Conversation
from backend.app.models.message import Message
from backend.app.models.user import User


@pytest.mark.asyncio
async def test_user_creation_and_query(db_session: AsyncSession) -> None:
    """Verify creating and retrieving a user account."""
    user = User(
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed_argon2id_password_placeholder",
        full_name="Test User",
    )
    db_session.add(user)
    await db_session.flush()

    retrieved = await db_session.get(User, user.id)
    assert retrieved is not None
    assert retrieved.email == user.email
    assert retrieved.is_active is True
    assert retrieved.is_superuser is False
    assert retrieved.created_at is not None


@pytest.mark.asyncio
async def test_conversation_and_messages_relationship(db_session: AsyncSession) -> None:
    """Verify creating conversation threads with nested messages."""
    user = User(
        email=f"chat-user-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
    )
    db_session.add(user)
    await db_session.flush()

    conv = Conversation(user_id=user.id, title="Research on AI agents")
    db_session.add(conv)
    await db_session.flush()

    msg1 = Message(conversation_id=conv.id, role="user", content="What is LangGraph?")
    msg2 = Message(conversation_id=conv.id, role="assistant", content="LangGraph is...")
    db_session.add_all([msg1, msg2])
    await db_session.flush()

    result = await db_session.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)
    )
    messages = list(result.scalars().all())
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"


@pytest.mark.asyncio
async def test_cascade_delete_user(db_session: AsyncSession) -> None:
    """Verify deleting a user cascades to conversations and messages, but preserves audit events."""
    user = User(
        email=f"cascade-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
    )
    db_session.add(user)
    await db_session.flush()

    conv = Conversation(user_id=user.id, title="Thread to be deleted")
    db_session.add(conv)
    await db_session.flush()

    msg = Message(conversation_id=conv.id, role="user", content="Will be deleted")
    audit = AuditEvent(
        user_id=user.id,
        event_type="auth.test",
        action="test",
        status="SUCCESS",
        request_id="req-test-cascade",
    )
    session = AuthSession(
        user_id=user.id,
        refresh_token_hash=uuid.uuid4().hex,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db_session.add_all([msg, audit, session])
    await db_session.flush()

    # Delete the user
    await db_session.delete(user)
    await db_session.flush()

    # Confirm user, conversation, and message are deleted
    assert await db_session.get(User, user.id) is None
    assert await db_session.get(Conversation, conv.id) is None
    assert await db_session.get(Message, msg.id) is None
    assert await db_session.get(AuthSession, session.id) is None

    # Confirm audit event is preserved with user_id set to NULL (SET NULL constraint)
    refreshed_audit = await db_session.get(AuditEvent, audit.id)
    assert refreshed_audit is not None
    assert refreshed_audit.user_id is None
