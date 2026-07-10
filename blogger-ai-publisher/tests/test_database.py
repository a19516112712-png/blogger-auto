"""Unit tests for database initialisation and table creation.

Ensures all three required tables exist with the correct columns
and that basic CRUD operations work as expected.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from database.database import (
    close_connection,
    execute,
    fetch_all,
    fetch_one,
    get_connection,
    last_insert_rowid,
)
from database.init_db import init_database, table_exists


# ======================================================================
# Table existence
# ======================================================================
class TestTableCreation:
    """Verify all three tables are created successfully."""

    def test_all_tables_exist(self) -> None:
        """``articles``, ``generated_images``, and ``used_prompts`` exist."""
        for name in ("articles", "generated_images", "used_prompts"):
            assert table_exists(name), f"Table '{name}' should exist"

    def test_table_columns(self) -> None:
        """Each table has the required base columns (id, created_at, updated_at)."""
        for table in ("articles", "generated_images", "used_prompts"):
            cols = {
                row["name"]
                for row in execute(f"PRAGMA table_info([{table}])").fetchall()
            }
            assert "id" in cols, f"{table} missing 'id'"
            assert "created_at" in cols, f"{table} missing 'created_at'"
            assert "updated_at" in cols, f"{table} missing 'updated_at'"


# ======================================================================
# Article CRUD
# ======================================================================
class TestArticles:
    """CRUD operations on the ``articles`` table."""

    def test_insert_article(self) -> None:
        """A basic INSERT produces a row with an auto-incremented id."""
        execute(
            "INSERT INTO articles (title, slug, word_count, status) "
            "VALUES (?, ?, ?, ?)",
            ("Test Article", "test-article", 1500, "draft"),
            commit=True,
        )
        row = fetch_one("SELECT * FROM articles WHERE slug = ?", ("test-article",))
        assert row is not None
        assert row["title"] == "Test Article"
        assert row["word_count"] == 1500

    def test_insert_multiple(self) -> None:
        """Multiple inserts each receive a unique id."""
        for i in range(5):
            execute(
                "INSERT INTO articles (title, slug) VALUES (?, ?)",
                (f"Article {i}", f"article-{i}"),
                commit=True,
            )
        rows = fetch_all("SELECT id FROM articles ORDER BY id")
        ids = [r["id"] for r in rows]
        assert len(ids) == 5
        assert ids == sorted(ids)

    def test_update_article(self) -> None:
        """Updating fields works correctly."""
        execute(
            "INSERT INTO articles (title, slug, status) VALUES (?, ?, ?)",
            ("Original", "original", "draft"),
            commit=True,
        )
        execute(
            "UPDATE articles SET status = ? WHERE slug = ?",
            ("published", "original"),
            commit=True,
        )
        row = fetch_one("SELECT status FROM articles WHERE slug = ?", ("original",))
        assert row is not None
        assert row["status"] == "published"

    def test_delete_article(self) -> None:
        """Deleting a row removes it from the table."""
        execute(
            "INSERT INTO articles (title, slug) VALUES (?, ?)",
            ("To Delete", "to-delete"),
            commit=True,
        )
        execute("DELETE FROM articles WHERE slug = ?", ("to-delete",), commit=True)
        row = fetch_one("SELECT * FROM articles WHERE slug = ?", ("to-delete",))
        assert row is None


# ======================================================================
# Generated images
# ======================================================================
class TestGeneratedImages:
    """CRUD operations on the ``generated_images`` table."""

    def test_insert_image(self) -> None:
        """Image record can be created and linked to an article."""
        # First create an article to reference
        execute(
            "INSERT INTO articles (title, slug) VALUES (?, ?)",
            ("Image Parent", "image-parent"),
            commit=True,
        )
        article_id = last_insert_rowid()

        execute(
            "INSERT INTO generated_images (article_id, prompt_text, image_path) "
            "VALUES (?, ?, ?)",
            (article_id, "A baby name infographic", "/images/test.png"),
            commit=True,
        )
        rows = fetch_all("SELECT * FROM generated_images")
        assert len(rows) == 1
        assert rows[0]["article_id"] == article_id

    def test_image_foreign_key(self) -> None:
        """Orphan images (article deleted) are cascaded or handled."""
        execute(
            "INSERT INTO articles (title, slug) VALUES (?, ?)",
            ("Orphan Parent", "orphan-parent"),
            commit=True,
        )
        pid = last_insert_rowid()
        execute(
            "INSERT INTO generated_images (article_id, prompt_text) VALUES (?, ?)",
            (pid, "orphan image"),
            commit=True,
        )
        execute("DELETE FROM articles WHERE id = ?", (pid,), commit=True)
        remaining = fetch_all("SELECT * FROM generated_images")
        # CASCADE should delete the image
        assert len(remaining) == 0


# ======================================================================
# Used prompts
# ======================================================================
class TestUsedPrompts:
    """CRUD operations on the ``used_prompts`` table."""

    def test_insert_prompt(self) -> None:
        """Prompt usage is tracked with token counts."""
        execute(
            "INSERT INTO used_prompts (prompt_text, model, tokens_input, tokens_output, "
            "duration_ms, prompt_type) VALUES (?, ?, ?, ?, ?, ?)",
            ("Write article about love names", "agnes-2.0-flash", 500, 1500, 12000, "article"),
            commit=True,
        )
        row = fetch_one("SELECT * FROM used_prompts WHERE prompt_type = ?", ("article",))
        assert row is not None
        assert row["tokens_input"] == 500
        assert row["tokens_output"] == 1500


# ======================================================================
# Connection lifecycle
# ======================================================================
class TestConnectionLifecycle:
    """Database connection management."""

    def test_connection_reuse(self) -> None:
        """Calling get_connection twice returns the same object."""
        c1 = get_connection()
        c2 = get_connection()
        assert c1 is c2

    def test_close_and_reopen(self) -> None:
        """After closing, get_connection creates a fresh connection."""
        c1 = get_connection()
        close_connection()
        c2 = get_connection()
        assert c1 is not c2

    def test_context_manager_commit(self) -> None:
        """``get_db`` context manager commits on exit."""
        from database.database import get_db

        with get_db() as conn:
            conn.execute(
                "INSERT INTO articles (title, slug) VALUES (?, ?)",
                ("Context Test", "context-test"),
            )
        row = fetch_one("SELECT title FROM articles WHERE slug = ?", ("context-test",))
        assert row is not None
        assert row["title"] == "Context Test"


# ======================================================================
# Idempotency
# ======================================================================
class TestInitialisation:
    """Multiple calls to init_database are safe."""

    def test_init_is_idempotent(self) -> None:
        """Running init_database multiple times does not error."""
        # init_database was already called by conftest.py
        for _ in range(3):
            init_database()  # Should not raise
        # All tables still exist
        for name in ("articles", "generated_images", "used_prompts"):
            assert table_exists(name)
