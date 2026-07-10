"""Shared fixtures and configuration for pytest.

Sets up an in-memory SQLite database before each test session and
configures logging to suppress noise during test runs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Generator

import pytest

from database.database import close_connection, get_connection
from database.init_db import init_database


@pytest.fixture(autouse=True)
def _silence_logging() -> Generator[None, None, None]:
    """Suppress non-critical log output during tests."""
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.fixture(scope="session", autouse=True)
def db_cleanup() -> Generator[None, None, None]:
    """Ensure a clean test database is used."""
    # Override DATABASE_PATH to in-memory *before* any imports trigger it
    import config.settings as s

    s.DATABASE_PATH = Path(":memory:")  # type: ignore[assignment]
    yield
    close_connection()


@pytest.fixture(autouse=True)
def fresh_db() -> Generator[None, None, None]:
    """Re-initialise the database before each test."""
    init_database()
    yield
    # Clean all rows after test
    conn = get_connection()
    for table in ("articles", "generated_images", "used_prompts"):
        conn.execute(f"DELETE FROM [{table}]")
    conn.commit()
