"""Article queue manager — locks articles during publishing, prevents
duplicate publication, and handles state transitions.

States
------
- ``draft``    — created but not yet queued for publishing
- ``ready``    — queued and waiting for the pipeline
- ``publishing`` — currently being published (locked)
- ``published``  — successfully published
- ``failed``     — publishing failed, eligible for retry
- ``retry``      — queued for retry after failure
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from config.logging import get_logger
from config.settings import AUTOMATION_RETRY_FAILED
from database.database import execute, fetch_all, fetch_one

log = get_logger(__name__)


class QueueError(Exception):
    """Raised when a queue operation fails."""


class ArticleQueue:
    """Manages the article publishing queue with locking.

    Usage::

        queue = ArticleQueue()
        article = queue.acquire_next()
        if article:
            try:
                # ... publish ...
                queue.mark_published(article["id"], post_id, url)
            except Exception:
                queue.mark_failed(article["id"], str(exc))
    """

    # ------------------------------------------------------------------
    # Acquire the next article (with lock)
    # ------------------------------------------------------------------

    def acquire_next(self) -> dict[str, Any] | None:
        """Acquire the next unpublished article for publishing.

        Locks the article by setting ``status`` to ``'publishing'``.
        Only returns articles in state ``draft``, ``ready``, or
        ``failed`` (with retry).

        Returns:
            Article row as a dict, or ``None`` if nothing to publish.

        Raises:
            QueueError: If the lock fails.
        """
        now = datetime.utcnow().isoformat()

        # Prioritise: failed → ready → draft (oldest first)
        article = fetch_one(
            """SELECT * FROM articles
               WHERE status IN ('draft', 'ready', 'failed')
               AND (publish_status IS NULL
                    OR publish_status != 'success'
                    OR blogger_post_id = '')
               AND publish_attempts < 10
               ORDER BY
                 CASE status
                   WHEN 'failed' THEN 0
                   WHEN 'ready' THEN 1
                   WHEN 'draft' THEN 2
                 END,
                 created_at ASC
               LIMIT 1"""
        )

        if article is None:
            return None

        article_id = article["id"]

        # Lock the article
        updated = execute(
            """UPDATE articles SET
                status = 'publishing',
                updated_at = ?
               WHERE id = ?
               AND status IN ('draft', 'ready', 'failed')""",
            (now, article_id),
        )
        if updated.rowcount == 0:
            raise QueueError(
                f"Failed to lock article {article_id} — "
                "concurrent ownership conflict"
            )

        log.info("Acquired article %d: %s", article_id, article["title"])
        return dict(article)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    @staticmethod
    def mark_published(
        article_id: int,
        blogger_post_id: str,
        blogger_url: str,
    ) -> None:
        """Mark an article as successfully published.

        Args:
            article_id:      Database article ID.
            blogger_post_id: Blogger post ID.
            blogger_url:     Published URL.
        """
        now = datetime.utcnow().isoformat()
        execute(
            """UPDATE articles SET
                status = 'published',
                publish_status = 'success',
                blogger_post_id = ?,
                blogger_url = ?,
                published_at = ?,
                updated_at = ?
               WHERE id = ?""",
            (blogger_post_id, blogger_url, now, now, article_id),
            commit=True,
        )
        log.info("Article %d marked as published", article_id)

    @staticmethod
    def mark_failed(
        article_id: int,
        error_message: str,
        max_retries: int = 10,
    ) -> None:
        """Mark an article as failed.

        If the article has exceeded ``max_retries``, it stays on
        ``failed``.  Otherwise it goes back to ``ready`` for retry.

        Args:
            article_id:    Database article ID.
            error_message: Error description.
            max_retries:   Maximum publish attempts before giving up.
        """
        now = datetime.utcnow().isoformat()
        execute(
            """UPDATE articles SET
                status = CASE
                  WHEN publish_attempts >= ? THEN 'failed'
                  ELSE 'ready'
                END,
                publish_status = 'failed',
                publish_attempts = publish_attempts + 1,
                last_publish_error = ?,
                updated_at = ?
               WHERE id = ?""",
            (max_retries, error_message, now, article_id),
            commit=True,
        )
        log.warning(
            "Article %d marked as failed (will retry)", article_id)

    @staticmethod
    def unlock(article_id: int) -> None:
        """Unlock an article that was stuck in 'publishing' state.

        Used during recovery to release articles that were being
        published when a crash occurred.

        Args:
            article_id: Database article ID.
        """
        now = datetime.utcnow().isoformat()
        execute(
            """UPDATE articles SET
                status = CASE
                  WHEN publish_attempts > 0 THEN 'ready'
                  ELSE 'draft'
                END,
                updated_at = ?
               WHERE id = ? AND status = 'publishing'""",
            (now, article_id),
            commit=True,
        )
        log.info("Article %d unlocked for retry", article_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @staticmethod
    def count_pending() -> int:
        """Return the number of articles waiting to be published.

        Returns:
            Integer count.
        """
        row = fetch_one(
            """SELECT COUNT(*) AS cnt FROM articles
               WHERE status IN ('draft', 'ready', 'failed')
               AND (publish_status IS NULL OR publish_status != 'success')"""
        )
        return row["cnt"] if row else 0

    @staticmethod
    def count_stuck() -> int:
        """Return the number of articles stuck in 'publishing' state.

        Returns:
            Integer count.
        """
        row = fetch_one(
            "SELECT COUNT(*) AS cnt FROM articles WHERE status = 'publishing'"
        )
        return row["cnt"] if row else 0

    @staticmethod
    def list_recent(limit: int = 10) -> list[dict[str, Any]]:
        """Return the most recently published articles.

        Args:
            limit: Maximum number of articles.

        Returns:
            List of article dicts.
        """
        rows = fetch_all(
            """SELECT id, title, blogger_url, published_at, status
               FROM articles
               WHERE status = 'published'
               ORDER BY published_at DESC
               LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in rows]
