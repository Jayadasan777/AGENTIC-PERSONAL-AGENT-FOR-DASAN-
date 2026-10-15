"""Asynchronous database engine and session factory management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.config import get_settings

settings = get_settings()

# Asynchronous engine using asyncpg driver
# pool_pre_ping=True verifies connections are alive before handing them to requests
engine = create_async_engine(
    settings.async_database_uri,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Async sessionmaker factory
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency provider yielding an isolated asynchronous database session.

    Automatically closes the session upon request completion and rolls back on unhandled error.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Alias used by FastAPI dependency injection in auth/deps modules
get_async_session = get_db

__all__ = ["async_session_factory", "engine", "get_async_session", "get_db"]
