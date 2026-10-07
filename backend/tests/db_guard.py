"""Test-database guard (Step 15 hardening support).

Resolves the isolated test database URL and fails fast if it ever points at
the development database. Side-effect free: safe to import from tests.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse

DEV_DATABASE_NAME = "campusxolve"
TEST_DATABASE_NAME = "campusxolve_test"
DEV_DATABASE_URL = "postgresql+asyncpg://campusxolve:campusxolve@localhost:5432/campusxolve"


def _replace_database_name(url: str, name: str) -> str:
    parts = urlparse(url)
    return urlunparse(parts._replace(path=f"/{name}"))


def _database_name(url: str) -> str:
    return urlparse(url).path.lstrip("/")


def resolve_test_database_url(
    explicit: str | None = None, base: str | None = None
) -> str:
    """Return the isolated test URL or raise (fail fast) on dev-DB confusion."""
    test_url = explicit or _replace_database_name(
        base or os.environ.get("DATABASE_URL", DEV_DATABASE_URL), TEST_DATABASE_NAME
    )
    if _database_name(test_url) == DEV_DATABASE_NAME:
        raise RuntimeError(
            "Refusing to run pytest against the development database "
            f"({DEV_DATABASE_NAME!r}). Set TEST_DATABASE_URL to a dedicated "
            "test database (e.g. .../campusxolve_test)."
        )
    return test_url
