"""Complete publishing pipeline orchestration.

Runs one full cycle:

1. Health check
2. Crash recovery
3. Import unpublished posts from disk
4. Acquire next article from queue
5. Generate image (Prompt Engine → Image Engine)
6. Build HTML
7. Publish to Blogger
8. Update database
9. Archive article
10. Record metrics
11. Generate report

This module is designed to be called by the Scheduler (CLI) or by
GitHub Actions.
"""

from __future__ import annotations

import time
from typing import Any

from config.logging import get_logger
from config.settings import AUTOMATION_MAX_ARTICLES_PER_RUN
from database.database import execute, fetch_one

log = get_logger(__name__)




def import_posts_from_directory() -> int:
    """Scan the posts directory and import unpublished markdown files
    into the articles table.

    Reads YAML frontmatter from each markdown file, extracts
    ``title``, ``slug``, ``labels`` (list), ``meta_description``,
    and the body content.  Skips files whose ``slug`` already exists
    in the ``articles`` table.

    Returns:
        Number of new articles imported.
    """
    import yaml
    from pathlib import Path as _Path
    from config.settings import POSTS_DIR
    from database.database import execute, fetch_one

    if not POSTS_DIR.is_dir():
        log.warning("Posts directory does not exist: %s", POSTS_DIR)
        return 0

    md_files = sorted(POSTS_DIR.glob("*.md"))
    if not md_files:
        log.warning("No markdown files found in %s", POSTS_DIR)
        return 0

    imported = 0
    for md_file in md_files:
        raw = md_file.read_text(encoding="utf-8")

        # Parse YAML frontmatter (between --- delimiters)
        if not raw.startswith("---"):
            log.debug("Skipping %s — no frontmatter", md_file.name)
            continue

        parts = raw.split("---", 2)
        if len(parts) < 3:
            log.debug("Skipping %s — malformed frontmatter", md_file.name)
            continue

        try:
            meta = yaml.safe_load(parts[1])
        except Exception as exc:
            log.warning("Failed to parse YAML in %s: %s", md_file.name, exc)
            continue

        if not isinstance(meta, dict):
            continue

        title = (meta.get("title") or "").strip()
        slug = (meta.get("slug") or "").strip()
        labels_raw = meta.get("labels") or []
        meta_description = (meta.get("meta_description") or "").strip()
        body = parts[2].strip()

        if not title or not slug:
            log.debug("Skipping %s — missing title or slug", md_file.name)
            continue

        # Check for duplicate slug
        existing = fetch_one(
            "SELECT id FROM articles WHERE slug = ?", (slug,)
        )
        if existing is not None:
            log.debug("Skipping %s — slug already exists: %s", md_file.name, slug)
            continue

        # Normalise labels to comma-separated string
        if isinstance(labels_raw, list):
            labels_str = ",".join(
                str(lbl).strip() for lbl in labels_raw if lbl
            )
        elif isinstance(labels_raw, str):
            labels_str = labels_raw
        else:
            labels_str = ""

        word_count = len(body.split())

        execute(
            """INSERT INTO articles
               (title, slug, meta_description, content_markdown,
                labels, word_count, status, publish_status)
               VALUES (?, ?, ?, ?, ?, ?, 'draft', 'pending')""",
            (title, slug, meta_description, body, labels_str, word_count),
            commit=True,
        )
        imported += 1
        log.info(
            "Imported post: %s → slug=%s, labels=%s",
            md_file.name, slug, labels_str,
        )

    log.info("Imported %d new article(s) from posts directory", imported)
    return imported


class PipelineError(Exception):
    """Raised when the pipeline encounters a fatal error."""


def run_pipeline() -> list[dict[str, Any]]:
    """Execute one complete publishing cycle.

    Returns:
        A list of result dicts (one per article published).

    Raises:
        PipelineError: If a pre-flight check fails.
    """
    from automation.health import run_health_check
    from automation.recovery import recover_state
    from automation.queue import ArticleQueue
    from automation.metrics import record_pipeline_run

    results: list[dict[str, Any]] = []
    max_articles = AUTOMATION_MAX_ARTICLES_PER_RUN

    # Step 1: Health check
    log.info("Pipeline — Step 1/8: Health check")
    health = run_health_check()
    if not health.healthy:
        for err in health.errors:
            log.error("Health check error: %s", err)
        raise PipelineError(
            f"Health check failed ({len(health.errors)} error(s)) — "
            "aborting pipeline"
        )

    # Step 2: Recovery
    log.info("Pipeline — Step 2/8: Crash recovery")
    recovered = recover_state()

    # Step 3: Auto-import unpublished posts
    log.info("Pipeline — Step 3/8: Import unpublished posts")
    imported = import_posts_from_directory()

    # Step 4: Article queue
    log.info("Pipeline — Step 4/8: Acquire article from queue")
    queue = ArticleQueue()
    pending = queue.count_pending()

    if pending == 0:
        log.info("No pending articles — pipeline complete")
        return []

    log.info("Pipeline — %d article(s) pending", pending)

    for cycle in range(max_articles):
        start_time = time.perf_counter()
        warnings: list[str] = []

        article = queue.acquire_next()
        if article is None:
            log.info("No more articles to publish (cycle %d)", cycle + 1)
            break

        article_id = article["id"]
        title = article["title"]
        slug = article["slug"]
        content_md = article["content_markdown"]

        if not content_md or not content_md.strip():
            warnings.append("Article has no content — skipping")
            queue.mark_failed(article_id, "Empty content", max_retries=1)
            continue

        # Step 5: Generate prompt
        log.info("Pipeline — Step 5/9: Generate prompt (article %d: %s)", article_id, title)
        prompt_result = _generate_prompt(title)

        # Step 6: Generate image
        log.info("Pipeline — Step 6/9: Generate image (article %d)", article_id)
        image_result = _generate_image(title, slug, prompt_result, article_id)
        provider = image_result.get("provider", "")
        image_path = image_result.get("image_path", "")

        if not image_result.get("success"):
            warnings.append(
                f"Image generation failed: {image_result.get('error_message', '')}"
            )

        # Step 7: Publish
        log.info("Pipeline — Step 7/9: Publish to Blogger (article %d)", article_id)
        publish_result = _do_publish(article_id, article, image_result)

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        # Step 8: Record run
        log.info("Pipeline — Step 8/9: Record metrics")
        record_pipeline_run(
            status="success" if publish_result.get("success") else "failed",
            article_id=article_id,
            article_title=title,
            blogger_url=publish_result.get("blogger_url", ""),
            provider=provider,
            image_path=image_path,
            elapsed_ms=elapsed_ms,
            error_message=publish_result.get("error_message", ""),
            warnings_count=len(warnings),
        )

        # Step 9: Generate report
        log.info("Pipeline — Step 9/9: Generate report")
        _generate_report(publish_result, elapsed_ms, warnings)

        results.append(publish_result)

        if publish_result.get("success"):
            log.info("✅ Published: %s → %s", title, publish_result.get("blogger_url"))
        else:
            log.warning("❌ Failed: %s — %s", title, publish_result.get("error_message"))

    return results


# ------------------------------------------------------------------
# Pipeline sub-steps
# ------------------------------------------------------------------


def _generate_prompt(title: str) -> dict[str, Any]:
    """Generate a prompt for the image engine from the article title.

    Args:
        title: Article title.

    Returns:
        Dict with ``prompt_text`` key.
    """
    try:
        from prompt_engine.generator import PromptGenerator
        from prompt_engine.models import GeneratedPrompt

        generator = PromptGenerator()
        result: GeneratedPrompt = generator.generate(title=title, hero_image=True)

        return {
            "prompt_text": result.prompt_text,
            "prompt_hash": result.prompt_hash,
            "score": result.score.overall if result.score else 0,
        }
    except Exception as exc:
        log.warning("Prompt generation failed, using fallback: %s", exc)
        return {
            "prompt_text": (
                f"Baby name article illustration for '{title}'. "
                "Soft pastel colors, gentle lighting, family-friendly."
            ),
            "prompt_hash": "",
            "score": 0,
        }


def _generate_image(
    title: str,
    slug: str,
    prompt_result: dict[str, Any],
    article_id: int,
) -> dict[str, Any]:
    """Generate an image using the Image Engine.

    Args:
        title:          Article title.
        slug:           Article slug.
        prompt_result:  Result from ``_generate_prompt()``.
        article_id:     Database article ID.

    Returns:
        Image generation result dict.
    """
    prompt_text = prompt_result.get(
        "prompt_text",
        f"Baby names illustration for {title}",
    )

    try:
        from image_engine.manager import ImageManager

        mgr = ImageManager()
        image_result = mgr.generate(
            title=title,
            slug=slug,
            prompt=prompt_text,
            article_id=article_id,
        )
        return image_result
    except Exception as exc:
        log.error("Image generation failed: %s", exc)
        return {
            "success": False,
            "image_path": "",
            "provider": "",
            "error_message": str(exc),
        }


def _do_publish(
    article_id: int,
    article: dict[str, Any],
    image_result: dict[str, Any],
) -> dict[str, Any]:
    """Publish the article to Blogger.

    Args:
        article_id:   Database article ID.
        article:      Article data dict.
        image_result: Image generation result.

    Returns:
        Publish result dict.
    """
    try:
        from blogger.publisher import Publisher

        publisher = Publisher()
        result = publisher.publish_article(article_id=article_id)
        return result
    except Exception as exc:
        log.error("Publishing failed for article %d: %s", article_id, exc)
        return {
            "success": False,
            "article_id": article_id,
            "title": article.get("title", ""),
            "error_message": str(exc),
        }


def _generate_report(
    result: dict[str, Any],
    elapsed_ms: int,
    warnings: list[str],
) -> None:
    """Save an execution report.

    Args:
        result:     Publish result dict.
        elapsed_ms: Execution time in milliseconds.
        warnings:   Warning messages.
    """
    try:
        from automation.notifier import save_report
        save_report(result=result, elapsed_ms=elapsed_ms, warnings=warnings)
    except Exception as exc:
        log.warning("Failed to save report: %s", exc)
