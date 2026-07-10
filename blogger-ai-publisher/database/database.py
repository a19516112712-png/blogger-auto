"""SQLite database connection and session management.

Uses :mod:`sqlite3` directly (no ORM) for simplicity — this is a
single-user, single-process application.  All paths are built with
:mod:`pathlib`.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from config.logging import get_logger
from config.settings import DATABASE_PATH

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Thread-local storage — each thread gets its own connection.
# ---------------------------------------------------------------------------
_local = threading.local()


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------
def get_connection() -> sqlite3.Connection:
    """Return the thread-local SQLite connection, creating it if needed.

    The connection has ``row_factory`` set to :class:`sqlite3.Row` so that
    rows can be accessed by column name.  Foreign keys are enforced via
    ``PRAGMA foreign_keys = ON``.

    Returns:
        An open :class:`~sqlite3.Connection`.
    """
    conn: sqlite3.Connection | None = getattr(_local, "connection", None)
    if conn is None:
        log.debug("Opening database connection: %s", DATABASE_PATH)
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DATABASE_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        _local.connection = conn
    return conn


def close_connection() -> None:
    """Close the thread-local database connection if it is open."""
    conn: sqlite3.Connection | None = getattr(_local, "connection", None)
    if conn is not None:
        log.debug("Closing database connection")
        conn.close()
        _local.connection = None


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager that yields a database connection and commits
    on success / rolls back on error.

    Yields:
        An open :class:`~sqlite3.Connection`.
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        log.exception("Database transaction rolled back")
        raise


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------
def execute(
    sql: str,
    params: tuple[Any, ...] = (),
    *,
    commit: bool = False,
) -> sqlite3.Cursor:
    """Execute a single SQL statement.

    Args:
        sql:    SQL statement (may contain ``?`` placeholders).
        params: Parameters for the placeholders.
        commit: If ``True``, commit immediately after execution.

    Returns:
        The :class:`~sqlite3.Cursor`.
    """
    conn = get_connection()
    cursor = conn.execute(sql, params)
    if commit:
        conn.commit()
    return cursor


def fetch_one(
    sql: str,
    params: tuple[Any, ...] = (),
) -> sqlite3.Row | None:
    """Fetch a single row.

    Args:
        sql:    SELECT statement.
        params: Query parameters.

    Returns:
        A :class:`~sqlite3.Row` or ``None``.
    """
    cursor = execute(sql, params)
    return cursor.fetchone()


def fetch_all(
    sql: str,
    params: tuple[Any, ...] = (),
) -> list[sqlite3.Row]:
    """Fetch all matching rows.

    Args:
        sql:    SELECT statement.
        params: Query parameters.

    Returns:
        List of :class:`~sqlite3.Row` objects.
    """
    cursor = execute(sql, params)
    return cursor.fetchall()


def last_insert_rowid() -> int:
    """Return the ``ROWID`` of the last INSERT.

    Returns:
        The integer rowid.
    """
    return get_connection().execute("SELECT last_insert_rowid()").fetchone()[0]
