import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from backend.app.db.session import async_session_factory, engine
from backend.app.services.auth import register_user
from backend.app.models.user import User
from sqlalchemy import select

async def seed_user():
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.email == "dasan@aura.ai"))
        user = result.scalar_one_or_none()
        if not user:
            user = await register_user(
                email="dasan@aura.ai",
                password="aura123456",
                full_name="Jayadasan (AURA)",
                session=session
            )
            await session.commit()
            print(f"Created and committed user: {user.email} (ID: {user.id}) in Neon DB!")
        else:
            print(f"User already exists: {user.email} (ID: {user.id}) in Neon DB.")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_user())
