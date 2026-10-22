import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from sqlalchemy import text
from backend.app.core.config import get_settings
from backend.app.db.session import engine
from backend.app.db.base import Base
import backend.app.models  # load core models
import backend.app.automation.models  # load automation tables

async def init_tables():
    settings = get_settings()
    print(f"Connecting to Neon DB URI: {settings.async_database_uri.split('@')[-1]}")
    
    async with engine.begin() as conn:
        # Enable pgvector if available
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            print("pgvector extension ensured.")
        except Exception as e:
            print(f"Note on vector extension: {e}")

        # Create all tables defined in models
        print("Creating all tables in Neon database...")
        await conn.run_sync(Base.metadata.create_all)
        print("All tables successfully created!")

        # Verify created tables
        res = await conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """))
        tables = [r[0] for r in res.fetchall()]
        print(f"Verified tables in Neon DB ({len(tables)} tables):", tables)

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(init_tables())
