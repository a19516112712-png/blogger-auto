"""Publisher — main orchestrator for the Blogger publishing pipeline.

Pipeline (idempotent, per article)
-----------------------------------
1. Load article from database
2. Load generated image from database
3. Build complete HTML (hero image + content)
4. Generate labels
5. Generate slug (if not already set)
6. Authenticate with Blogger API
7. Create or update Blogger post
8. Update database record (post ID, URL, status)
9. Mark article as published
10. Move markdown source to published/archive directory
"""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from blogger.auth import AuthError, get_credentials
from blogger.client import ClientError, create_post
from blogger.html_builder import build_article_html, HtmlBuildError
from blogger.image_uploader import ImageUploadError, build_image_tag
from blogger.labels import generate_labels
from blogger.slug import generate_slug
from config.logging import get_logger
from config.settings import (
    ARTICLES_DIR,
    BLOG_ID,
    PUBLISHED_DIR,
    PUBLISHER_IMAGE_MAX_RETRIES,
    PUBLISHER_MAX_RETRIES,
)
from database.database import execute, fetch_one, fetch_all, last_insert_rowid, get_connection

log = get_logger(__name__)


class PublishError(Exception):
    """Raised when article publishing fails."""


class Publisher:
    """Orchestrator for publishing articles to Blogger.

    Usage::

        publisher = Publisher()
        result = publisher.publish_article(article_id=42)
    """

    def __init__(self) -> None:
        """Initialise publisher state."""
        self.max_retries: int = PUBLISHER_MAX_RETRIES
        self.image_max_retries: int = PUBLISHER_IMAGE_MAX_RETRIES

        # Ensure directories exist
        PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
        ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Main public API
    # ------------------------------------------------------------------

    def publish_article(self, article_id: int) -> dict[str, Any]:
        """Publish a single article to Blogger.

        This method is **idempotent**: if the article has already been
        published (``blogger_post_id`` is set), it will update the
        existing post instead of creating a duplicate.

        Args:
            article_id: The database ``articles.id`` to publish.

        Returns:
            A result dict with keys:
            - ``success``: ``True`` if published successfully.
            - ``article_id``: The database article ID.
            - ``title``: Article title.
            - ``blogger_post_id``: Blogger post ID.
            - ``blogger_url``: Published URL on Blogger.
            - ``published_at``: ISO timestamp of publication.
            - ``slug``: URL slug used.
            - ``labels``: Labels applied.
            - ``error_message``: Error details if failed.
        """
        start_time = time.perf_counter()

        try:
            # 1. Load article from database
            article = self._load_article(article_id)
            if article is None:
                raise PublishError(f"Article not found: id={article_id}")

            title = article["title"]
            content_md = article["content_markdown"]
            meta_desc = article["meta_description"]
            slug = article["slug"] or generate_slug(title)
            existing_labels = self._parse_labels(article["labels"])
            existing_post_id = article["blogger_post_id"]

            log.info("Publishing article: id=%d, title=%s", article_id, title)

            # 2. Load generated image
            image_result = self._load_image(article_id)

            # 3. Build image tag
            image_tag_result: dict[str, Any] | None = None
            if image_result and image_result.get("image_path"):
                try:
                    image_tag_result = build_image_tag(
                        image_path=image_result["image_path"],
                        alt_text=image_result.get("alt_text", ""),
                        title=f"{title} — Baby Name Ideas",
                        caption=f"{title} — discover the perfect name",
                        width=image_result.get("width", 0),
                        height=image_result.get("height", 0),
                        lazy_load=True,
                    )
                except ImageUploadError as exc:
                    log.warning(
                        "Image build failed for article %d: %s — "
                        "proceeding without image",
                        article_id,
                        exc,
                    )

            # 4. Build article HTML
            hero_path = image_tag_result.get("data_uri", "") if image_tag_result else ""
            html = build_article_html(
                title=title,
                content_markdown=content_md,
                meta_description=meta_desc,
                hero_image_path=hero_path,
                hero_alt=image_result.get("alt_text", "") if image_result else "",
                hero_caption=f"{title} — Baby Name Ideas" if title else "",
                hero_width=image_result.get("width", 0) if image_result else 0,
                hero_height=image_result.get("height", 0) if image_result else 0,
                slug=slug,
                labels=existing_labels,
            )

            # 5. Generate labels
            labels = generate_labels(
                title=title,
                existing_labels=existing_labels,
                slug=slug,
            )

            # 6. Authenticate (validate credentials)
            get_credentials()

            # 7. Publish to Blogger
            is_update = bool(existing_post_id)
            if is_update:
                response = self._update_post(
                    post_id=existing_post_id,
                    title=title,
                    content=html,
                    labels=labels,
                )
                log.info("Updated existing post: id=%s", existing_post_id)
            else:
                response = self._create_new_post(
                    title=title,
                    content=html,
                    labels=labels,
                )
                log.info("Created new post: id=%s", response.get("id"))

            blogger_post_id = response.get("id", "")
            blogger_url = response.get("url", "")
            published_at = response.get("published", datetime.utcnow().isoformat())

            # 8. Update database
            self._update_article_record(
                article_id=article_id,
                blogger_post_id=blogger_post_id,
                blogger_url=blogger_url,
                published_at=published_at,
                status="success",
                slug=slug,
                labels=labels,
            )

            # 9. Update image record
            self._update_image_record(article_id, blogger_post_id)

            # 10. Archive article source
            self._archive_article(article_id, title, slug)

            elapsed = int((time.perf_counter() - start_time) * 1000)
            log.info(
                "Article published successfully: id=%d, title=%s, "
                "url=%s, elapsed=%dms",
                article_id,
                title,
                blogger_url,
                elapsed,
            )

            return {
                "success": True,
                "article_id": article_id,
                "title": title,
                "blogger_post_id": blogger_post_id,
                "blogger_url": blogger_url,
                "published_at": published_at,
                "slug": slug,
                "labels": labels,
                "error_message": "",
            }

        except (PublishError, AuthError, ClientError, HtmlBuildError) as exc:
            error_msg = str(exc)
            log.error("Publish failed for article %d: %s", article_id, error_msg)

            # Update database with failure
            self._record_publish_failure(
                article_id=article_id,
                error_message=error_msg,
            )

            return {
                "success": False,
                "article_id": article_id,
                "title": "",
                "blogger_post_id": "",
                "blogger_url": "",
                "published_at": "",
                "slug": "",
                "labels": [],
                "error_message": error_msg,
            }

    # ------------------------------------------------------------------
    # Internal loaders
    # ------------------------------------------------------------------

    @staticmethod
    def _load_article(article_id: int) -> dict[str, Any] | None:
        """Load an article from the database.

        Args:
            article_id: Database article ID.

        Returns:
            Article row as a dict, or ``None`` if not found.
        """
        row = fetch_one(
            "SELECT * FROM articles WHERE id = ?", (article_id,)
        )
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def _load_image(article_id: int) -> dict[str, Any] | None:
        """Load the generated image for an article from the database.

        Args:
            article_id: Database article ID.

        Returns:
            Image row as a dict, or ``None`` if not found.
        """
        row = fetch_one(
            "SELECT * FROM generated_images WHERE article_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (article_id,),
        )
        if row is None:
            return None
        result = dict(row)
        # Ensure image_path exists on disk
        img_path = result.get("image_path", "")
        if img_path and not Path(img_path).exists():
            log.warning(
                "Image file not found on disk for article %d: %s",
                article_id,
                img_path,
            )
        return result

    # ------------------------------------------------------------------
    # Blogger API interaction
    # ------------------------------------------------------------------

    @staticmethod
    def _create_new_post(
        title: str,
        content: str,
        labels: list[str],
    ) -> dict[str, Any]:
        """Create a new post on Blogger.

        Args:
            title:   Post title.
            content: Post HTML content.
            labels:  Post labels.

        Returns:
            Blogger API response dict.

        Raises:
            ClientError: If the API call fails.
        """
        return create_post(
            title=title,
            content=content,
            labels=labels,
            is_draft=False,
        )

    @staticmethod
    def _update_post(
        post_id: str,
        title: str,
        content: str,
        labels: list[str],
    ) -> dict[str, Any]:
        """Update an existing post on Blogger.

        Args:
            post_id: Blogger post ID.
            title:   Updated title.
            content: Updated HTML content.
            labels:  Updated labels.

        Returns:
            Blogger API response dict.
        """
        # Use the update_post from client module
        from blogger.client import update_post as _update
        return _update(
            post_id=post_id,
            title=title,
            content=content,
            labels=labels,
            is_draft=False,
        )

    # ------------------------------------------------------------------
    # Database updates
    # ------------------------------------------------------------------

    @staticmethod
    def _update_article_record(
        article_id: int,
        blogger_post_id: str,
        blogger_url: str,
        published_at: str,
        status: str,
        slug: str,
        labels: list[str],
    ) -> None:
        """Update the article record after successful publishing.

        Args:
            article_id:       Database article ID.
            blogger_post_id:  Blogger post ID.
            blogger_url:      Published URL.
            published_at:     ISO timestamp.
            status:           Publish status (``"success"`` or ``"failed"``).
            slug:             URL slug.
            labels:           Labels list.
        """
        now = datetime.utcnow().isoformat()
        execute(
            """UPDATE articles SET
                blogger_post_id = ?,
                blogger_url = ?,
                published_at = ?,
                status = ?,
                slug = ?,
                labels = ?,
                publish_status = ?,
                updated_at = ?
            WHERE id = ?""",
            (
                blogger_post_id,
                blogger_url,
                published_at,
                "published",
                slug,
                ",".join(labels),
                "success",
                now,
                article_id,
            ),
            commit=True,
        )
        log.info(
            "Database updated: article=%d, post_id=%s, url=%s",
            article_id,
            blogger_post_id,
            blogger_url,
        )

    @staticmethod
    def _update_image_record(article_id: int, blogger_post_id: str) -> None:
        """Update the image record status after publishing.

        Args:
            article_id:       Database article ID.
            blogger_post_id:  Blogger post ID.
        """
        execute(
            """UPDATE generated_images SET
                status = 'uploaded',
                updated_at = datetime('now')
            WHERE article_id = ? AND status = 'generated'""",
            (article_id,),
            commit=True,
        )

    @staticmethod
    def _record_publish_failure(
        article_id: int,
        error_message: str,
    ) -> None:
        """Record a publish failure in the database.

        Args:
            article_id:    Database article ID.
            error_message: Error description.
        """
        now = datetime.utcnow().isoformat()
        execute(
            """UPDATE articles SET
                publish_status = 'failed',
                publish_attempts = publish_attempts + 1,
                last_publish_error = ?,
                updated_at = ?
            WHERE id = ?""",
            (error_message, now, article_id),
            commit=True,
        )

    # ------------------------------------------------------------------
    # Archival
    # ------------------------------------------------------------------

    @staticmethod
    def _archive_article(
        article_id: int,
        title: str,
        slug: str,
    ) -> None:
        """Move the article source file to the published/archive directory.

        Args:
            article_id: Database article ID.
            title:      Article title (used for filename).
            slug:       URL slug (used for filename).
        """
        # Look for markdown files matching this article
        slug_part = slug or f"article-{article_id}"
        source_files = list(ARTICLES_DIR.glob(f"*{slug_part}*.md"))
        source_files.extend(ARTICLES_DIR.glob(f"*{article_id}*.md"))

        if not source_files:
            # Fallback: try to find any md file with matching title fragment
            title_part = title.lower().replace(" ", "-")[:30]
            source_files = list(ARTICLES_DIR.glob(f"*{title_part}*.md"))

        if source_files:
            source = source_files[0]
            archive_name = f"{datetime.utcnow().strftime('%Y%m%d')}-{slug_part}.md"
            dest = PUBLISHED_DIR / archive_name
            try:
                shutil.copy2(str(source), str(dest))
                source.unlink()
                log.info(
                    "Article archived: %s → %s",
                    source.name,
                    dest.name,
                )
            except OSError as exc:
                log.warning(
                    "Failed to archive article %d: %s",
                    article_id,
                    exc,
                )
        else:
            log.debug("No source file found to archive for article %d", article_id)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_labels(labels_str: str) -> list[str]:
        """Parse a comma-separated label string into a list.

        Args:
            labels_str: Comma-separated labels (e.g. ``"Baby Names,Irish Names"``).

        Returns:
            List of label strings.
        """
        if not labels_str or not labels_str.strip():
            return []
        return [
            label.strip()
            for label in labels_str.split(",")
            if label.strip()
        ]

    # ------------------------------------------------------------------
    # Batch publishing
    # ------------------------------------------------------------------

    def publish_pending_articles(
        self,
        max_articles: int = 10,
        status_filter: str = "draft",
    ) -> list[dict[str, Any]]:
        """Publish all pending (unpublished) articles.

        Args:
            max_articles:  Maximum number of articles to publish in one batch.
            status_filter: Article status to filter by (default ``"draft"``).

        Returns:
            A list of result dicts from each publish attempt.
        """
        rows = fetch_all(
            "SELECT id, title FROM articles "
            "WHERE status = ? AND blogger_post_id = '' "
            "ORDER BY created_at ASC LIMIT ?",
            (status_filter, max_articles),
        )

        results: list[dict[str, Any]] = []
        for row in rows:
            result = self.publish_article(article_id=row["id"])
            results.append(result)

        log.info(
            "Batch publish complete: %d/%d articles processed",
            len(results),
            len(rows),
        )
        return results

    def republish_failed_articles(
        self,
        max_articles: int = 10,
    ) -> list[dict[str, Any]]:
        """Retry publishing articles that previously failed.

        Args:
            max_articles: Maximum number of failed articles to retry.

        Returns:
            A list of result dicts.
        """
        rows = fetch_all(
            "SELECT id, title FROM articles "
            "WHERE publish_status = 'failed' "
            "AND publish_attempts < ? "
            "ORDER BY publish_attempts ASC, updated_at DESC "
            "LIMIT ?",
            (PUBLISHER_MAX_RETRIES, max_articles),
        )

        results: list[dict[str, Any]] = []
        for row in rows:
            result = self.publish_article(article_id=row["id"])
            results.append(result)

        log.info(
            "Republish batch complete: %d/%d failed articles retried",
            len(results),
            len(rows),
        )
        return results
