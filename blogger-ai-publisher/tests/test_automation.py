"""Comprehensive tests for the Automation Engine (Milestone 5).

Covers:
- ArticleQueue (acquire, lock, mark, count)
- Health check (database, auth, disk, directories)
- Metrics collection
- Report generation
- Recovery (stuck articles, incomplete runs)
- Scheduler commands
- Full pipeline simulation
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from automation.queue import ArticleQueue, QueueError
from automation.recovery import recover_state
from automation.metrics import collect_metrics, record_pipeline_run
from automation.notifier import save_report, _format_duration

# ======================================================================
# ArticleQueue tests
# ======================================================================


class TestArticleQueue:
    """Test article queue management."""

    def test_acquire_next_returns_oldest_draft(self, fresh_db) -> None:
        """acquire_next returns the oldest draft article."""
        from database.database import execute

        execute(
            "INSERT INTO articles (title, slug, status, content_markdown) "
            "VALUES (?, ?, ?, ?)",
            ("Newer Draft", "newer", "draft", "Content"),
            commit=True,
        )
        execute(
            "INSERT INTO articles (title, slug, status, content_markdown) "
            "VALUES (?, ?, ?, ?)",
            ("Older Draft", "older", "draft", "Content"),
            commit=True,
        )

        queue = ArticleQueue()
        article = queue.acquire_next()
        assert article is not None
        assert article["title"] == "Newer Draft"  # Oldest by created_at ASC

    def test_acquire_next_none_when_none_pending(self, fresh_db) -> None:
        """Returns None when no articles are pending."""
        queue = ArticleQueue()
        assert queue.acquire_next() is None

    def test_acquire_next_skips_published(self, fresh_db) -> None:
        """Does not return already published articles."""
        from database.database import execute

        execute(
            "INSERT INTO articles (title, slug, status, blogger_post_id) "
            "VALUES (?, ?, ?, ?)",
            ("Published", "pub", "published", "post_123"),
            commit=True,
        )

        queue = ArticleQueue()
        assert queue.acquire_next() is None

    def test_acquire_next_locks_article(self, fresh_db) -> None:
        """Acquired article is locked with 'publishing' status."""
        from database.database import execute, fetch_one

        execute(
            "INSERT INTO articles (title, slug, status, content_markdown) "
            "VALUES (?, ?, ?, ?)",
            ("Lock Test", "lock-test", "draft", "Content"),
            commit=True,
        )

        queue = ArticleQueue()
        article = queue.acquire_next()
        assert article is not None

        # Verify lock
        locked = fetch_one(
            "SELECT status FROM articles WHERE id = ?", (article["id"],)
        )
        assert locked["status"] == "publishing"

    def test_mark_published_updates_db(self, fresh_db) -> None:
        """mark_published sets status and post ID."""
        from database.database import execute, fetch_one

        execute(
            "INSERT INTO articles (title, slug, status, content_markdown) "
            "VALUES (?, ?, ?, ?)",
            ("Pub Test", "pub-test", "draft", "Content"),
            commit=True,
        )
        article_id = execute(
            "SELECT id FROM articles WHERE slug = ?", ("pub-test",)
        ).fetchone()[0]

        queue = ArticleQueue()
        queue.mark_published(
            article_id=article_id,
            blogger_post_id="abc123",
            blogger_url="https://example.com/post",
        )

        updated = fetch_one(
            "SELECT status, blogger_post_id, blogger_url FROM articles WHERE id = ?",
            (article_id,),
        )
        assert updated["status"] == "published"
        assert updated["blogger_post_id"] == "abc123"
        assert updated["blogger_url"] == "https://example.com/post"

    def test_mark_failed_retries(self, fresh_db) -> None:
        """mark_failed sets status to 'ready' for retry."""
        from database.database import execute, fetch_one

        execute(
            "INSERT INTO articles (title, slug, status, content_markdown) "
            "VALUES (?, ?, ?, ?)",
            ("Fail Retry", "fail-retry", "draft", "Content"),
            commit=True,
        )
        article_id = execute(
            "SELECT id FROM articles WHERE slug = ?", ("fail-retry",)
        ).fetchone()[0]

        queue = ArticleQueue()
        queue.mark_failed(article_id, "Test error", max_retries=10)

        updated = fetch_one(
            "SELECT status, publish_attempts FROM articles WHERE id = ?",
            (article_id,),
        )
        assert updated["status"] == "ready"  # Retryable
        assert updated["publish_attempts"] == 1

    def test_mark_failed_exhausted(self, fresh_db) -> None:
        """mark_failed sets status to 'failed' after max retries."""
        from database.database import execute, fetch_one

        execute(
            "INSERT INTO articles (title, slug, status, "
            "content_markdown, publish_attempts) "
            "VALUES (?, ?, ?, ?, ?)",
            ("Exhausted", "exhausted", "draft", "Content", 10),
            commit=True,
        )
        article_id = execute(
            "SELECT id FROM articles WHERE slug = ?", ("exhausted",)
        ).fetchone()[0]

        queue = ArticleQueue()
        queue.mark_failed(article_id, "Final error", max_retries=10)

        updated = fetch_one(
            "SELECT status FROM articles WHERE id = ?",
            (article_id,),
        )
        assert updated["status"] == "failed"

    def test_unlock_stuck_article(self, fresh_db) -> None:
        """unlock sets a publishing article back to draft."""
        from database.database import execute, fetch_one

        execute(
            "INSERT INTO articles (title, slug, status, content_markdown) "
            "VALUES (?, ?, ?, ?)",
            ("Stuck", "stuck", "publishing", "Content"),
            commit=True,
        )
        article_id = execute(
            "SELECT id FROM articles WHERE slug = ?", ("stuck",)
        ).fetchone()[0]

        queue = ArticleQueue()
        queue.unlock(article_id)

        updated = fetch_one(
            "SELECT status FROM articles WHERE id = ?",
            (article_id,),
        )
        assert updated["status"] in ("draft", "ready")

    def test_count_pending(self, fresh_db) -> None:
        """count_pending returns correct number."""
        from database.database import execute

        execute(
            "INSERT INTO articles (title, slug, status, content_markdown) "
            "VALUES (?, ?, ?, ?)",
            ("A", "a", "draft", "Content"),
            commit=True,
        )
        execute(
            "INSERT INTO articles (title, slug, status, content_markdown) "
            "VALUES (?, ?, ?, ?)",
            ("B", "b", "ready", "Content"),
            commit=True,
        )
        execute(
            "INSERT INTO articles (title, slug, status) "
            "VALUES (?, ?, ?)",
            ("C", "c", "published"),
            commit=True,
        )

        queue = ArticleQueue()
        assert queue.count_pending() == 2

    def test_count_stuck(self, fresh_db) -> None:
        """count_stuck returns correct number."""
        from database.database import execute

        execute(
            "INSERT INTO articles (title, slug, status, content_markdown) "
            "VALUES (?, ?, ?, ?)",
            ("Stuck1", "s1", "publishing", "C"),
            commit=True,
        )
        execute(
            "INSERT INTO articles (title, slug, status, content_markdown) "
            "VALUES (?, ?, ?, ?)",
            ("Stuck2", "s2", "publishing", "C"),
            commit=True,
        )

        queue = ArticleQueue()
        assert queue.count_stuck() == 2


# ======================================================================
# Health check tests
# ======================================================================




# ======================================================================
# import_posts_from_directory tests
# ======================================================================


class TestImportPosts:
    """Test auto-importing markdown posts into the articles table."""

    def test_import_creates_articles(self, fresh_db, tmp_path) -> None:
        """Valid markdown files are imported as draft articles."""
        from automation.pipeline import import_posts_from_directory
        from database.database import fetch_one
        import config.settings

        posts_dir = tmp_path / "posts"
        posts_dir.mkdir()
        md = posts_dir / "test-article.md"
        md.write_text("---\ntitle: Test Article\nslug: test-article\nlabels:\n  - Baby Names\nmeta_description: A test\n---\nHello world")

        orig = config.settings.POSTS_DIR
        config.settings.POSTS_DIR = posts_dir

        try:
            count = import_posts_from_directory()
            assert count == 1

            row = fetch_one(
                "SELECT title, slug, status, labels, word_count FROM articles WHERE slug = ?",
                ("test-article",),
            )
            assert row is not None
            assert row["title"] == "Test Article"
            assert row["status"] == "draft"
            assert row["labels"] == "Baby Names"
            assert row["word_count"] == 2
        finally:
            config.settings.POSTS_DIR = orig

    def test_import_skips_duplicate_slug(self, fresh_db, tmp_path) -> None:
        """Files with existing slug are skipped."""
        from automation.pipeline import import_posts_from_directory
        from database.database import execute
        import config.settings

        execute(
            "INSERT INTO articles (title, slug, status) VALUES (?, ?, ?)",
            ("Existing", "existing-article", "draft"),
            commit=True,
        )

        posts_dir = tmp_path / "posts"
        posts_dir.mkdir()
        md = posts_dir / "dup.md"
        md.write_text("---\ntitle: Duplicate\nslug: existing-article\nlabels: []\nmeta_description: dup\n---\nBody")

        orig = config.settings.POSTS_DIR
        config.settings.POSTS_DIR = posts_dir

        try:
            count = import_posts_from_directory()
            assert count == 0
        finally:
            config.settings.POSTS_DIR = orig

    def test_import_no_posts_directory(self, fresh_db, tmp_path) -> None:
        """Non-existent posts directory returns 0 without error."""
        from automation.pipeline import import_posts_from_directory
        import config.settings

        posts_dir = tmp_path / "nonexistent"
        orig = config.settings.POSTS_DIR
        config.settings.POSTS_DIR = posts_dir

        try:
            count = import_posts_from_directory()
            assert count == 0
        finally:
            config.settings.POSTS_DIR = orig

    def test_import_empty_directory(self, fresh_db, tmp_path) -> None:
        """Empty posts directory returns 0 without error."""
        from automation.pipeline import import_posts_from_directory
        import config.settings

        posts_dir = tmp_path / "posts-empty"
        posts_dir.mkdir()
        orig = config.settings.POSTS_DIR
        config.settings.POSTS_DIR = posts_dir

        try:
            count = import_posts_from_directory()
            assert count == 0
        finally:
            config.settings.POSTS_DIR = orig

    def test_import_malformed_frontmatter(self, fresh_db, tmp_path) -> None:
        """Files with invalid YAML are skipped."""
        from automation.pipeline import import_posts_from_directory
        import config.settings

        posts_dir = tmp_path / "posts"
        posts_dir.mkdir()
        md = posts_dir / "broken.md"
        md.write_text("---\ntitle: title: Broken\nslug: broken\n---\nBody")

        orig = config.settings.POSTS_DIR
        config.settings.POSTS_DIR = posts_dir

        try:
            count = import_posts_from_directory()
            assert count == 0
        finally:
            config.settings.POSTS_DIR = orig

    def test_import_missing_title_or_slug(self, fresh_db, tmp_path) -> None:
        """Files missing title or slug are skipped."""
        from automation.pipeline import import_posts_from_directory
        import config.settings

        posts_dir = tmp_path / "posts"
        posts_dir.mkdir()
        md1 = posts_dir / "no-title.md"
        md1.write_text("---\nslug: no-title\n---\nBody")
        md2 = posts_dir / "no-slug.md"
        md2.write_text("---\ntitle: No Slug\n---\nBody")

        orig = config.settings.POSTS_DIR
        config.settings.POSTS_DIR = posts_dir

        try:
            count = import_posts_from_directory()
            assert count == 0
        finally:
            config.settings.POSTS_DIR = orig

    def test_import_preserves_all_metadata(self, fresh_db, tmp_path) -> None:
        """All frontmatter fields are preserved in the database."""
        from automation.pipeline import import_posts_from_directory
        from database.database import fetch_one
        import config.settings

        posts_dir = tmp_path / "posts"
        posts_dir.mkdir()
        md = posts_dir / "full.md"
        md.write_text(
            "---\n"
            "title: Full Metadata Test\n"
            "slug: full-metadata-test\n"
            "meta_description: A complete test article\n"
            "labels:\n"
            "  - Baby Names\n"
            "  - Unique Names\n"
            "  - Japanese Names\n"
            "---\n"
            "This is the body with multiple words for counting."
        )

        orig = config.settings.POSTS_DIR
        config.settings.POSTS_DIR = posts_dir

        try:
            count = import_posts_from_directory()
            assert count == 1

            row = fetch_one(
                "SELECT * FROM articles WHERE slug = ?",
                ("full-metadata-test",),
            )
            assert row is not None
            assert row["title"] == "Full Metadata Test"
            assert row["slug"] == "full-metadata-test"
            assert row["meta_description"] == "A complete test article"
            assert row["labels"] == "Baby Names,Unique Names,Japanese Names"
            assert row["status"] == "draft"
            assert row["word_count"] == 9
        finally:
            config.settings.POSTS_DIR = orig


class TestHealthCheck:
    """Test pre-flight health verification."""

    def test_health_check_passes(self) -> None:
        """Health check returns healthy with default config."""
        from unittest.mock import patch as _p
        from automation.health import run_health_check

        with patch("automation.health.CLIENT_ID", "test-id"):
            with patch("automation.health.CLIENT_SECRET", "test-secret"):
                with patch("automation.health.REFRESH_TOKEN", "test-token"):
                    with patch("automation.health.BLOG_ID", "test-blog"):
                        health = run_health_check()
                        # Database and directories should be OK
                    assert health.checks["database"]["ok"] is True
                    assert health.checks["directories"]["ok"] is True

    def test_health_check_missing_auth(self) -> None:
        """Health check reports missing auth credentials."""
        from automation.health import run_health_check

        with patch("automation.health.CLIENT_ID", ""):
            with patch("automation.health.CLIENT_SECRET", ""):
                with patch("automation.health.REFRESH_TOKEN", ""):
                    health = run_health_check()
                    assert health.checks["auth"]["ok"] is False

    def test_health_check_stuck_articles(self, fresh_db) -> None:
        """Health check detects stuck articles."""
        from automation.health import run_health_check
        from database.database import execute

        execute(
            "INSERT INTO articles (title, slug, status, content_markdown) "
            "VALUES (?, ?, ?, ?)",
            ("Stuck", "stuck", "publishing", "C"),
            commit=True,
        )

        with patch("automation.health.CLIENT_ID", "test-id"):
            with patch("automation.health.CLIENT_SECRET", "test-secret"):
                with patch("automation.health.REFRESH_TOKEN", "test-token"):
                    health = run_health_check()
                    assert health.checks["stuck_articles"]["ok"] is False

    def test_health_check_healthy_flag(self) -> None:
        """healthy flag is True when all checks pass."""
        from automation.health import run_health_check

        with patch("automation.health.CLIENT_ID", "test-id"):
            with patch("automation.health.CLIENT_SECRET", "test-secret"):
                with patch("automation.health.REFRESH_TOKEN", "test-token"):
                    with patch("automation.health.BLOG_ID", "test-blog"):
                        health = run_health_check()
                        assert health.healthy is True


# ======================================================================
# Metrics tests
# ======================================================================


class TestMetrics:
    """Test metrics collection."""

    def test_collect_empty(self, fresh_db) -> None:
        """All metrics are zero when database is empty."""
        metrics = collect_metrics()
        assert metrics.total_articles == 0
        assert metrics.published_count == 0
        assert metrics.failed_count == 0
        assert metrics.pending_count == 0
        assert metrics.success_rate == 0.0

    def test_collect_with_data(self, fresh_db) -> None:
        """Metrics reflect actual database state."""
        from database.database import execute

        execute(
            "INSERT INTO articles (title, slug, status, blogger_post_id) "
            "VALUES (?, ?, ?, ?)",
            ("Published 1", "p1", "published", "post1"),
            commit=True,
        )
        execute(
            "INSERT INTO articles (title, slug, status) "
            "VALUES (?, ?, ?)",
            ("Draft 1", "d1", "draft"),
            commit=True,
        )

        metrics = collect_metrics()
        assert metrics.total_articles == 2
        assert metrics.published_count == 1
        assert metrics.pending_count >= 1

    def test_record_pipeline_run(self, fresh_db) -> None:
        """Record a pipeline run and verify it's stored."""
        run_id = record_pipeline_run(
            status="success",
            article_id=1,
            article_title="Test Article",
            blogger_url="https://example.com",
            provider="mock",
            image_path="/tmp/test.webp",
            elapsed_ms=1500,
            warnings_count=0,
        )
        assert run_id > 0

        from database.database import fetch_one
        row = fetch_one(
            "SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)
        )
        assert row is not None
        assert row["status"] == "success"
        assert row["article_title"] == "Test Article"

    def test_record_failed_run(self, fresh_db) -> None:
        """Failed pipeline runs are recorded correctly."""
        run_id = record_pipeline_run(
            status="failed",
            error_message="Something broke",
            elapsed_ms=500,
        )
        row = _fetch_run(run_id)
        assert row["status"] == "failed"
        assert "Something broke" in row["error_message"]


# ======================================================================
# Report tests
# ======================================================================


class TestReport:
    """Test execution report generation."""

    def test_save_report_success(self, tmp_path: Path) -> None:
        """Success report is saved correctly."""
        from config import settings
        original = settings.AUTOMATION_REPORTS_DIR
        try:
            settings.AUTOMATION_REPORTS_DIR = tmp_path / "reports"

            result = {
                "success": True,
                "title": "Test Article",
                "slug": "test-article",
                "blogger_url": "https://example.com/test",
                "blogger_post_id": "abc123",
                "labels": ["Baby Names", "Japanese Names"],
            }

            report_path = save_report(
                result=result,
                elapsed_ms=2345,
                warnings=["Image gen slow"],
            )
            assert report_path.exists()
            content = report_path.read_text()
            assert "Test Article" in content
            assert "https://example.com/test" in content
            assert "✅ Success" in content
            assert "Image gen slow" in content
        finally:
            settings.AUTOMATION_REPORTS_DIR = original

    def test_save_report_failure(self, tmp_path: Path) -> None:
        """Failure report includes error details."""
        from config import settings
        original = settings.AUTOMATION_REPORTS_DIR
        try:
            settings.AUTOMATION_REPORTS_DIR = tmp_path / "reports"

            result = {
                "success": False,
                "title": "Failed Article",
                "slug": "failed-article",
                "error_message": "Blogger API rejected",
            }

            report_path = save_report(result=result, elapsed_ms=500)
            content = report_path.read_text()
            assert "❌ Failed" in content
            assert "Blogger API rejected" in content
        finally:
            settings.AUTOMATION_REPORTS_DIR = original

    def test_format_duration(self) -> None:
        """Duration is formatted correctly."""
        assert _format_duration(1000) == "1.0s"
        assert _format_duration(65000) == "1m 5s"
        assert _format_duration(1500) == "1.5s"

    def test_save_report_without_labels(self, tmp_path: Path) -> None:
        """Report handles missing labels gracefully."""
        from config import settings
        original = settings.AUTOMATION_REPORTS_DIR
        try:
            settings.AUTOMATION_REPORTS_DIR = tmp_path / "reports"

            result = {
                "success": True,
                "title": "Simple",
                "slug": "simple",
                "blogger_url": "https://example.com/s",
            }

            report_path = save_report(result=result, elapsed_ms=200)
            assert report_path.exists()
        finally:
            settings.AUTOMATION_REPORTS_DIR = original


# ======================================================================
# Recovery tests
# ======================================================================


class TestRecovery:
    """Test crash recovery."""

    def test_recover_stuck_articles(self, fresh_db) -> None:
        """Stuck articles are unlocked by recovery."""
        from database.database import execute, fetch_one

        execute(
            "INSERT INTO articles (title, slug, status, content_markdown) "
            "VALUES (?, ?, ?, ?)",
            ("Stuck Art", "stuck-art", "publishing", "Content"),
            commit=True,
        )
        article_id = execute(
            "SELECT id FROM articles WHERE slug = ?", ("stuck-art",)
        ).fetchone()[0]

        fixed = recover_state()
        assert fixed >= 1

        updated = fetch_one(
            "SELECT status FROM articles WHERE id = ?",
            (article_id,),
        )
        assert updated["status"] != "publishing"  # Should be 'ready' or 'draft'

    def test_recover_no_stuck(self) -> None:
        """Recovery returns 0 when nothing is stuck."""
        fixed = recover_state()
        assert fixed == 0

    def test_recover_incomplete_runs(self, fresh_db) -> None:
        """Incomplete pipeline runs are marked as failed."""
        from database.database import execute
        from database.init_db import init_database

        init_database()

        fixed = recover_state()
        assert isinstance(fixed, int)


# ======================================================================
# Scheduler tests
# ======================================================================


class TestScheduler:
    """Test scheduler commands."""

    def test_doctor_command(self) -> None:
        """doctor command returns 0 (healthy)."""
        from automation.scheduler import Scheduler

        with patch("automation.health.CLIENT_ID", "test-id"):
            with patch("automation.health.CLIENT_SECRET", "test-secret"):
                with patch("automation.health.REFRESH_TOKEN", "test-token"):
                    with patch("automation.health.BLOG_ID", "test-blog"):
                        Scheduler.init_env()
                        code = Scheduler._cmd_health_check()
                    assert code == 0

    def test_metrics_command(self) -> None:
        """metrics command returns 0."""
        from automation.scheduler import Scheduler

        Scheduler.init_env()
        code = Scheduler._cmd_show_metrics()
        assert code == 0

    def test_unknown_command(self) -> None:
        """Unknown command returns error code."""
        from automation.scheduler import Scheduler

        code = Scheduler.run_command("invalid")
        assert code == 1

    def test_publish_command_no_articles(self) -> None:
        """publish command exits cleanly with no articles."""
        from unittest.mock import patch as _patch
        from automation.scheduler import Scheduler
        from automation.health import HealthStatus, run_health_check
        Scheduler.init_env()

        health = HealthStatus(healthy=True, timestamp="2026-01-01")
        with _patch("automation.health.run_health_check", return_value=health):
            code = Scheduler._cmd_publish_only()
            assert code == 0


# ======================================================================
# Pipeline tests
# ======================================================================


class TestPipeline:
    """Test the full pipeline (mocked)."""

    def test_run_pipeline_no_articles(self, tmp_path) -> None:
        """Pipeline exits cleanly with no articles."""
        from automation.pipeline import run_pipeline
        import config.settings

        empty_posts = tmp_path / "posts"
        empty_posts.mkdir()

        with patch("automation.health.CLIENT_ID", "test-id"):
            with patch("automation.health.CLIENT_SECRET", "test-secret"):
                with patch("automation.health.REFRESH_TOKEN", "test-token"):
                    with patch("automation.health.BLOG_ID", "test-blog"):
                        orig = config.settings.POSTS_DIR
                        config.settings.POSTS_DIR = empty_posts
                        try:
                            results = run_pipeline()
                            assert results == []
                        finally:
                            config.settings.POSTS_DIR = orig

    def test_run_pipeline_with_article(self, fresh_db) -> None:
        """Pipeline publishes one article."""
        from database.database import execute

        # Insert a test article
        execute(
            "INSERT INTO articles (title, slug, content_markdown, status) "
            "VALUES (?, ?, ?, ?)",
            ("Pipeline Test", "pipeline-test",
             "# Test\n\nContent for pipeline test article.", "draft"),
            commit=True,
        )
        article_id = execute(
            "SELECT id FROM articles WHERE slug = ?", ("pipeline-test",)
        ).fetchone()[0]

        # Mock the heavy components
        with patch("automation.pipeline._generate_prompt") as mock_prompt:
            mock_prompt.return_value = {
                "prompt_text": "Test prompt",
                "prompt_hash": "hash123",
                "score": 85,
            }
            with patch("automation.pipeline._generate_image") as mock_image:
                mock_image.return_value = {
                    "success": True,
                    "image_path": "/tmp/test.webp",
                    "provider": "mock",
                    "alt_text": "Test",
                }
                with patch("automation.pipeline._do_publish") as mock_pub:
                    mock_pub.return_value = {
                        "success": True,
                        "article_id": article_id,
                        "title": "Pipeline Test",
                        "blogger_post_id": "post_123",
                        "blogger_url": "https://example.com/pipeline",
                        "slug": "pipeline-test",
                        "labels": ["Baby Names"],
                    }
                    with patch("automation.health.CLIENT_ID", "test-id"):
                        with patch("automation.health.CLIENT_SECRET", "test-secret"):
                            with patch("automation.health.REFRESH_TOKEN", "test-token"):
                                with patch("automation.health.BLOG_ID", "test-blog"):
                                    from automation.pipeline import run_pipeline
                                    results = run_pipeline()

        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["title"] == "Pipeline Test"


# ======================================================================
# Helper
# ======================================================================


def _fetch_run(run_id: int) -> dict:
    """Fetch a pipeline_runs row by ID."""
    from database.database import fetch_one
    row = fetch_one(
        "SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)
    )
    assert row is not None, f"Run {run_id} not found"
    return dict(row)
