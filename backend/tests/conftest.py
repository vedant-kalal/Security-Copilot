"""
Shared pytest fixtures.

Pure-logic tests (ML inference, the correlation engine's scoring rules,
MITRE mapping) run anywhere with no external dependencies.

API/integration tests need a real PostgreSQL + pgvector instance (the
same one set up in docs/INSTALLATION.md). They connect using the
`DATABASE_URL` environment variable and are automatically skipped if
that database is not reachable, so `pytest` still passes in environments
without Postgres (e.g. a bare CI runner) while running the full suite
wherever Postgres is available.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest
import pytest_asyncio

os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-do-not-use-in-production")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://sentinelai:sentinelai@localhost:5432/sentinelai_test"
)
os.environ.setdefault(
    "DATABASE_URL_SYNC", "postgresql+psycopg2://sentinelai:sentinelai@localhost:5432/sentinelai_test"
)
os.environ.setdefault("ENVIRONMENT", "test")

from app.core.database import Base, engine  # noqa: E402


async def _database_is_reachable() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True
    except Exception:
        return False


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


requires_database = pytest.mark.skipif(
    not _run(_database_is_reachable()),
    reason="PostgreSQL is not reachable at DATABASE_URL — start it per docs/INSTALLATION.md to run integration tests.",
)


@pytest_asyncio.fixture
async def db_session():
    """Provide a clean database schema for each test, backed by the real
    async engine/session factory the application uses."""
    from app.core.database import AsyncSessionLocal

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(db_session):
    """An httpx AsyncClient wired to the FastAPI app, with `get_db`
    overridden to reuse the test's transactional session."""
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.main import app

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def unique_email() -> str:
    return f"test-{uuid.uuid4().hex[:10]}@sentinelai.test"
