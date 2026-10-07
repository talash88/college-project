"""Pytest bootstrap: isolate the suite on its own PostgreSQL database.

Design (see docs/AUDIT_STABILIZATION_FIXES.md):
- The suite NEVER touches the development database (``campusxolve``).
- ``TEST_DATABASE_URL`` env wins; otherwise the database name of
  ``DATABASE_URL`` (or its default) is replaced with ``campusxolve_test``.
- If the resolved test URL still points at the development database,
  collection fails fast instead of polluting dev data.
- The test database is created on demand and migrated to ``head`` once per
  pytest process, before any app module is imported.

This module must run before ``app.*`` imports so the app engine binds to the
test database for the whole pytest process.
"""

import os
import subprocess
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests.db_guard import (
    TEST_DATABASE_NAME,
    resolve_test_database_url,
)

TEST_DATABASE_URL = resolve_test_database_url()

# Point every app import in this process at the isolated test database.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("ENVIRONMENT", "test")

# Ensure backend is importable when pytest is invoked from elsewhere.
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.core.config import settings  # noqa: E402
from app.db.session import engine as app_engine  # noqa: E402


def _psycopg_dsn(async_url: str, dbname: str) -> str:
    """Convert an asyncpg URL into a psycopg/asyncpg-connectable DSN."""
    parts = urlparse(async_url)
    scheme = "postgresql://"
    netloc = parts.hostname or "localhost"
    if parts.port:
        netloc += f":{parts.port}"
    if parts.username:
        auth = parts.username
        if parts.password:
            auth += f":{parts.password}"
        netloc = f"{auth}@{netloc}"
    return f"{scheme}{netloc}/{dbname}"


def _ensure_test_database() -> None:
    """Recreate the test database from scratch (once per pytest process).

    Drop + migrate + seed every run so the suite is hermetic: no dependence
    on leftovers from previous runs and never on development records.
    """
    import asyncio

    import asyncpg

    async def _recreate() -> None:
        maintenance = _psycopg_dsn(TEST_DATABASE_URL, "postgres")
        conn = await asyncpg.connect(maintenance)
        try:
            await conn.execute(
                f'DROP DATABASE IF EXISTS "{TEST_DATABASE_NAME}" WITH (FORCE)'
            )
            await conn.execute(f'CREATE DATABASE "{TEST_DATABASE_NAME}"')
        finally:
            await conn.close()

    asyncio.run(_recreate())
    test_env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL, "ENVIRONMENT": "test"}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(backend_path),
        env=test_env,
        check=True,
        capture_output=True,
        text=True,
    )
    # Seed reference data so tests never depend on development records:
    # skill taxonomy + embeddings (skill extraction/duplicates/recommendations)
    # and the 7 official development accounts (recommendation/assignment flows
    # assert against these known solvers/mentors). All scripts are idempotent.
    for script in (
        "scripts/seed_skills.py",
        "scripts/build_skill_embeddings.py",
        "scripts/seed_users.py",
    ):
        subprocess.run(
            [sys.executable, script],
            cwd=str(backend_path),
            env=test_env,
            check=True,
            capture_output=True,
            text=True,
        )


_ensure_test_database()

assert settings.DATABASE_URL == TEST_DATABASE_URL, (
    "Test isolation broken: settings.DATABASE_URL does not point at the test DB."
)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db_pool() -> AsyncGenerator[None, None]:
    """Dispose the app-wide engine around each test.

    pytest-asyncio runs every async test on its own event loop while the
    app engine (created at import time) pools connections bound to whatever
    loop first used them. Disposing forces fresh connections on the current
    loop and avoids "attached to a different loop" failures.
    """
    await app_engine.dispose()
    yield
    await app_engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Function-scoped session on its own NullPool engine (loop-safe)."""
    test_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with factory() as session:
        yield session
        await session.rollback()
    await test_engine.dispose()
