"""Integration tests for SQLAlchemy 2.0 asynchronous engine and database session provider."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_async_engine_connectivity(db_session: AsyncSession) -> None:
    """Verify that the async engine connects to local PostgreSQL container and executes queries."""
    result = await db_session.execute(text("SELECT 1 AS alive;"))
    scalar = result.scalar()
    assert scalar == 1


@pytest.mark.asyncio
async def test_current_database_identity(db_session: AsyncSession) -> None:
    """Verify that the active session connects to aura_db."""
    result = await db_session.execute(text("SELECT current_database();"))
    db_name = result.scalar()
    assert db_name == "aura_db"


@pytest.mark.asyncio
async def test_pgvector_extension_available_in_db(db_session: AsyncSession) -> None:
    """Verify that pgvector is installed and active in the connected database."""
    result = await db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'vector';")
    )
    extname = result.scalar()
    assert extname == "vector"
