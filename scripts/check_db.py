import asyncio
import os

# Load .env before reading DATABASE_URL
import src.config  # noqa: F401,E402

import asyncpg


def _get_database_url() -> str:
    """Read DATABASE_URL from env."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is required. "
            "Example: postgresql://user:pass@localhost:5432/cs_rag"
        )
    return url


async def main():
    url = _get_database_url()
    # asyncpg expects postgresql:// not postgresql+asyncpg://
    conn_url = url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(conn_url)
    rows = await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )
    print(f"Connected to: {conn_url.split('@')[-1].split('/')[0]}")
    for r in rows:
        print(r["table_name"])
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
