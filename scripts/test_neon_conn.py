import asyncio
import os
import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Read .env.local
env_vars = {}
with open(".env.local", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env_vars[k.strip()] = v.strip().strip("\"'")

db_url = env_vars.get("DATABASE_URL")
print(f"DATABASE_URL found: {bool(db_url)}")

# Convert to asyncpg URI
# postgresql:// -> postgresql+asyncpg://
# Remove query params or convert sslmode to ssl
clean_url = db_url.split("?")[0]
async_sa_url = clean_url.replace("postgresql://", "postgresql+asyncpg://")

async def test_asyncpg():
    print("Testing direct asyncpg connect...")
    conn = await asyncpg.connect(clean_url, ssl="require")
    val = await conn.fetchval("SELECT version();")
    print("Direct asyncpg success! Postgres version:", val)
    await conn.close()

async def test_sqlalchemy():
    print("Testing SQLAlchemy async engine...")
    engine = create_async_engine(
        async_sa_url,
        connect_args={"ssl": "require"},
        pool_pre_ping=True
    )
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT current_database(), current_user;"))
        row = result.fetchone()
        print(f"SQLAlchemy success! Database: {row[0]}, User: {row[1]}")
    await engine.dispose()

async def main():
    await test_asyncpg()
    await test_sqlalchemy()

if __name__ == "__main__":
    asyncio.run(main())
