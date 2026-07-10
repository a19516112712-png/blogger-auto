"""Database initialisation — creates all tables and indexes.

Safe to call multiple times; each ``CREATE TABLE IF NOT EXISTS`` is
idempotent.
"""

from __future__ import annotations

import sys
from typing import NoReturn

from config.logging import get_logger, setup_logging
from database.database import close_connection, execute, get_connection

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Schema SQL
# ---------------------------------------------------------------------------

CREATE_ARTICLES_TABLE = """
CREATE TABLE IF NOT EXISTS articles (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),

    title               TEXT NOT NULL DEFAULT '',
    slug                TEXT NOT NULL DEFAULT '',
    meta_description    TEXT NOT NULL DEFAULT '',
    content_markdown    TEXT NOT NULL DEFAULT '',
    content_html        TEXT NOT NULL DEFAULT '',
    word_count          INTEGER NOT NULL DEFAULT 0,
    labels              TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft', 'ready', 'publishing', 'published', 'failed', 'retry')),
    blogger_post_id     TEXT NOT NULL DEFAULT '',
    blogger_url         TEXT NOT NULL DEFAULT '',
    published_at        TEXT,
    is_improved         INTEGER NOT NULL DEFAULT 0,
    improvement_count   INTEGER NOT NULL DEFAULT 0,
    search_intent_type  TEXT NOT NULL DEFAULT '',
    publish_status      TEXT NOT NULL DEFAULT 'pending'
                        CHECK (publish_status IN ('pending', 'success', 'failed')),
    publish_attempts    INTEGER NOT NULL DEFAULT 0,
    last_publish_error  TEXT NOT NULL DEFAULT ''
);
"""

CREATE_GENERATED_IMAGES_TABLE = """
CREATE TABLE IF NOT EXISTS generated_images (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),

    article_id          INTEGER DEFAULT NULL
                        REFERENCES articles(id) ON DELETE CASCADE,
    prompt_text         TEXT NOT NULL DEFAULT '',
    image_path          TEXT NOT NULL DEFAULT '',
    alt_text            TEXT NOT NULL DEFAULT '',
    width               INTEGER NOT NULL DEFAULT 0,
    height              INTEGER NOT NULL DEFAULT 0,
    file_size_bytes     INTEGER NOT NULL DEFAULT 0,
    mime_type           TEXT NOT NULL DEFAULT 'image/webp',
    status              TEXT NOT NULL DEFAULT 'generated'
                        CHECK (status IN ('generated', 'uploaded', 'failed')),
    phash               TEXT NOT NULL DEFAULT '',
    provider            TEXT NOT NULL DEFAULT '',
    generation_seed     INTEGER NOT NULL DEFAULT 0,
    generation_time_ms  INTEGER NOT NULL DEFAULT 0,
    optimized           INTEGER NOT NULL DEFAULT 0,
    quality             INTEGER NOT NULL DEFAULT 90
);
"""



CREATE_PIPELINE_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    started_at          TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at         TEXT,
    status              TEXT NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running', 'success', 'failed')),
    article_id          INTEGER DEFAULT NULL,
    article_title       TEXT NOT NULL DEFAULT '',
    blogger_url         TEXT NOT NULL DEFAULT '',
    provider            TEXT NOT NULL DEFAULT '',
    image_path          TEXT NOT NULL DEFAULT '',
    elapsed_ms          INTEGER NOT NULL DEFAULT 0,
    error_message       TEXT NOT NULL DEFAULT '',
    warnings_count      INTEGER NOT NULL DEFAULT 0
);
"""


CREATE_USED_PROMPTS_TABLE = """
CREATE TABLE IF NOT EXISTS used_prompts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),

    prompt_text         TEXT NOT NULL DEFAULT '',
    response_preview    TEXT NOT NULL DEFAULT '',
    model               TEXT NOT NULL DEFAULT '',
    tokens_input        INTEGER NOT NULL DEFAULT 0,
    tokens_output       INTEGER NOT NULL DEFAULT 0,
    duration_ms         INTEGER NOT NULL DEFAULT 0,
    prompt_type         TEXT NOT NULL DEFAULT '',
    target_slug         TEXT NOT NULL DEFAULT '',
    success             INTEGER NOT NULL DEFAULT 1,
    error_message       TEXT NOT NULL DEFAULT '',
    prompt_hash         TEXT NOT NULL DEFAULT ''
);
"""

# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------
CREATE_INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_slug ON articles(slug);",
    "CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);",
    "CREATE INDEX IF NOT EXISTS idx_articles_blogger_id ON articles(blogger_post_id);",
    "CREATE INDEX IF NOT EXISTS idx_images_article ON generated_images(article_id);",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_images_phash ON generated_images(phash);",
    "CREATE INDEX IF NOT EXISTS idx_prompts_type ON used_prompts(prompt_type);",
    "CREATE INDEX IF NOT EXISTS idx_prompts_slug ON used_prompts(target_slug);",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_prompts_hash ON used_prompts(prompt_hash);",
    "CREATE INDEX IF NOT EXISTS idx_runs_status ON pipeline_runs(status);",
]

SQL_STATEMENTS: list[str] = [
    CREATE_ARTICLES_TABLE,
    CREATE_GENERATED_IMAGES_TABLE,
    CREATE_PIPELINE_RUNS_TABLE,
    CREATE_USED_PROMPTS_TABLE,
    *CREATE_INDEXES,
]


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------
def init_database() -> None:
    """Create all tables and indexes if they do not exist.

    This function is idempotent — calling it multiple times is safe.
    """
    conn = get_connection()
    for statement in SQL_STATEMENTS:
        conn.execute(statement)
    conn.commit()
    log.info("Database initialised — tables and indexes created.")


def table_exists(name: str) -> bool:
    """Check whether a table exists in the database.

    Args:
        name: Table name to check.

    Returns:
        ``True`` if the table exists.
    """
    row = get_connection().execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def get_table_row_count(name: str) -> int:
    """Return the number of rows in a table.

    Args:
        name: Table name.

    Returns:
        Row count as integer.
    """
    row = get_connection().execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> NoReturn:
    """CLI entry point: ``python -m database.init_db``."""
    setup_logging()
    init_database()

    # Verify
    from database.database import fetch_all

    with get_connection() as conn:
        tables = fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        log.info("Tables created:")
        for t in tables:
            name = t["name"]
            count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
            log.info("  - %s (%d rows)", name, count)

    close_connection()
    sys.exit(0)


if __name__ == "__main__":
    main()
