"""Metrics collector for the automation engine.

Tracks:
- Articles published
- Average publish time
- Average image generation time
- Average retries before success
- Provider usage statistics
- Publish failures
- Success rate
- Disk usage

All metrics are stored in the database (``pipeline_runs`` table) and
computed on-demand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from config.logging import get_logger
from database.database import fetch_one, fetch_all, execute

log = get_logger(__name__)

REQUIRED_TABLES: set[str] = {"articles", "generated_images", "pipeline_runs"}


@dataclass
class SystemMetrics:
    """Complete system metrics snapshot.

    Attributes:
        timestamp:           ISO timestamp.
        total_articles:      Total articles in the database.
        published_count:     Successfully published articles.
        failed_count:        Failed publish attempts.
        pending_count:       Articles waiting to be published.
        success_rate:        Publish success rate (0.0 to 1.0).
        avg_publish_time_ms: Average publish time in milliseconds.
        avg_image_time_ms:   Average image generation time in ms.
        avg_retries:         Average retries before success.
        provider_usage:      Dict of provider name → usage count.
        disk_usage_mb:       Project disk usage in MB.
        recent_articles:     Latest published article titles and URLs.
    """
    timestamp: str = ""
    total_articles: int = 0
    published_count: int = 0
    failed_count: int = 0
    pending_count: int = 0
    success_rate: float = 0.0
    avg_publish_time_ms: float = 0.0
    avg_image_time_ms: float = 0.0
    avg_retries: float = 0.0
    provider_usage: dict[str, int] = field(default_factory=dict)
    disk_usage_mb: float = 0.0
    recent_articles: list[dict[str, Any]] = field(default_factory=list)


def collect_metrics() -> SystemMetrics:
    """Collect and return a snapshot of system metrics.

    Returns:
        A :class:`SystemMetrics` dataclass.
    """
    metrics = SystemMetrics(
        timestamp=datetime.utcnow().isoformat(),
    )

    # Total and published articles
    metrics.total_articles = _scalar(
        "SELECT COUNT(*) FROM articles"
    )
    metrics.published_count = _scalar(
        "SELECT COUNT(*) FROM articles WHERE status = 'published'"
    )
    metrics.failed_count = _scalar(
        "SELECT COUNT(*) FROM articles WHERE publish_status = 'failed'"
    )
    metrics.pending_count = _scalar(
        """SELECT COUNT(*) FROM articles
           WHERE status IN ('draft', 'ready')"""
    )

    # Success rate
    total_published = metrics.published_count + metrics.failed_count
    if total_published > 0:
        metrics.success_rate = round(
            metrics.published_count / total_published, 4
        )

    # Average publish time from pipeline_runs
    row = fetch_one(
        "SELECT AVG(elapsed_ms) AS avg_t FROM pipeline_runs "
        "WHERE status = 'success' AND elapsed_ms > 0"
    )
    if row and row["avg_t"]:
        metrics.avg_publish_time_ms = round(row["avg_t"], 1)

    # Average image generation time
    row = fetch_one(
        "SELECT AVG(generation_time_ms) AS avg_t FROM generated_images "
        "WHERE generation_time_ms > 0"
    )
    if row and row["avg_t"]:
        metrics.avg_image_time_ms = round(row["avg_t"], 1)

    # Average retries
    row = fetch_one(
        "SELECT AVG(publish_attempts) AS avg_r FROM articles "
        "WHERE publish_attempts > 0 AND status = 'published'"
    )
    if row and row["avg_r"]:
        metrics.avg_retries = round(row["avg_r"], 1)

    # Provider usage
    provider_rows = fetch_all(
        "SELECT provider, COUNT(*) AS cnt FROM generated_images "
        "WHERE provider != '' GROUP BY provider ORDER BY cnt DESC"
    )
    for r in provider_rows:
        metrics.provider_usage[r["provider"]] = r["cnt"]

    # Recent articles
    recent = fetch_all(
        "SELECT title, blogger_url, published_at FROM articles "
        "WHERE status = 'published' AND blogger_url != '' "
        "ORDER BY published_at DESC LIMIT 5"
    )
    metrics.recent_articles = [dict(r) for r in recent]

    # Disk usage (approximate)
    try:
        total = sum(
            f.stat().st_size
            for f in Path(".").rglob("*")
            if f.is_file() and ".git" not in f.parts
        )
        metrics.disk_usage_mb = round(total / (1024 * 1024), 2)
    except OSError:
        metrics.disk_usage_mb = 0.0

    log.info(
        "Metrics collected: %d published, %d failed, "
        "%.1f%% success rate",
        metrics.published_count,
        metrics.failed_count,
        metrics.success_rate * 100,
    )
    return metrics


def _scalar(sql: str) -> int:
    """Execute a scalar COUNT(*) query and return the result.

    Args:
        sql: SQL query.

    Returns:
        Integer result.
    """
    row = fetch_one(sql)
    if row:
        values = list(row)
        return values[0] if values else 0
    return 0


def record_pipeline_run(
    status: str,
    article_id: int | None = None,
    article_title: str = "",
    blogger_url: str = "",
    provider: str = "",
    image_path: str = "",
    elapsed_ms: int = 0,
    error_message: str = "",
    warnings_count: int = 0,
) -> int:
    """Record a pipeline execution in the database.

    Args:
        status:         ``"success"`` or ``"failed"``.
        article_id:     Database article ID.
        article_title:  Article title.
        blogger_url:    Published URL.
        provider:       Image provider name.
        image_path:     Path to generated image.
        elapsed_ms:     Total execution time in milliseconds.
        error_message:  Error message if failed.
        warnings_count: Number of warnings.

    Returns:
        The ID of the inserted pipeline_runs record.
    """
    from database.database import last_insert_rowid

    now = datetime.utcnow().isoformat()
    execute(
        """INSERT INTO pipeline_runs
           (started_at, finished_at, status, article_id, article_title,
            blogger_url, provider, image_path, elapsed_ms,
            error_message, warnings_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            now, now, status, article_id, article_title,
            blogger_url, provider, image_path, elapsed_ms,
            error_message, warnings_count,
        ),
        commit=True,
    )
    rid = last_insert_rowid()
    log.info("Pipeline run %d recorded: status=%s, elapsed=%dms", rid, status, elapsed_ms)
    return rid
