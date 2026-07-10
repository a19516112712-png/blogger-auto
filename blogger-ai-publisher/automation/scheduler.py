"""CLI scheduler — provides commands for the automation engine.

Commands
--------
- ``run``      — execute one full pipeline cycle
- ``publish``  — publish one pending article (no image gen)
- ``doctor``   — run health check only
- ``metrics``  — show system metrics
- ``retry``    — retry failed articles only
"""

from __future__ import annotations

import sys
import time
from typing import NoReturn

from config.logging import get_logger, setup_logging
from config.settings import validate as validate_settings
from database.database import close_connection
from database.init_db import init_database

log = get_logger(__name__)


class Scheduler:
    """CLI command scheduler for the automation engine.

    Usage::

        scheduler = Scheduler()
        scheduler.run_command("run")
    """

    @staticmethod
    def init_env() -> None:
        """Initialise the environment (DB, config check)."""
        setup_logging()
        warnings = validate_settings()
        for w in warnings:
            log.warning("Config: %s", w)
        init_database()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @staticmethod
    def run_command(command: str = "run") -> int:
        """Execute a scheduler command.

        Args:
            command: One of ``"run"``, ``"publish"``, ``"doctor"``,
                     ``"metrics"``, ``"retry"``.

        Returns:
            Exit code (0 = success, 1 = failure).
        """
        Scheduler.init_env()

        command_map = {
            "run": Scheduler._cmd_run_pipeline,
            "publish": Scheduler._cmd_publish_only,
            "doctor": Scheduler._cmd_health_check,
            "metrics": Scheduler._cmd_show_metrics,
            "retry": Scheduler._cmd_retry_failed,
        }

        func = command_map.get(command)
        if func is None:
            log.error("Unknown command: %s", command)
            print(f"Usage: python scripts/main.py [command]")
            print(f"Commands: run, publish, doctor, metrics, retry")
            return 1

        return func()

    # ------------------------------------------------------------------
    # Command implementations
    # ------------------------------------------------------------------

    @staticmethod
    def _cmd_run_pipeline() -> int:
        """Execute one full pipeline cycle.

        Returns:
            Exit code.
        """
        log.info("=" * 60)
        log.info("COMMAND: run — Full Pipeline")
        log.info("=" * 60)

        start_time = time.perf_counter()

        try:
            from automation.pipeline import run_pipeline

            results = run_pipeline()
            elapsed = int((time.perf_counter() - start_time) * 1000)

            published = [r for r in results if r.get("success")]
            failed = [r for r in results if not r.get("success")]

            log.info("-" * 60)
            log.info("PIPELINE SUMMARY")
            log.info("  Published:  %d", len(published))
            log.info("  Failed:     %d", len(failed))
            log.info("  Elapsed:    %d ms", elapsed)
            log.info("-" * 60)

            for r in published:
                log.info("  ✅ %s", r.get("title", ""))
                log.info("     %s", r.get("blogger_url", ""))

            for r in failed:
                log.warning(
                    "  ❌ %s — %s",
                    r.get("title", ""),
                    r.get("error_message", ""),
                )

            return 0 if not failed else 1

        except Exception as exc:
            elapsed = int((time.perf_counter() - start_time) * 1000)
            log.error("Pipeline failed after %d ms: %s", elapsed, exc)
            return 1

    @staticmethod
    def _cmd_publish_only() -> int:
        """Publish the next pending article without generating images.

        Returns:
            Exit code.
        """
        log.info("=" * 60)
        log.info("COMMAND: publish — Publish Pending Article")
        log.info("=" * 60)

        from automation.health import run_health_check
        from automation.queue import ArticleQueue

        health = run_health_check()
        if not health.healthy:
            log.error("Health check failed — aborting")
            return 1

        queue = ArticleQueue()
        article = queue.acquire_next()
        if article is None:
            log.info("No pending articles to publish")
            return 0

        from blogger.publisher import Publisher

        publisher = Publisher()
        result = publisher.publish_article(article_id=article["id"])

        if result.get("success"):
            log.info("✅ Published: %s", result.get("blogger_url"))
            return 0
        else:
            log.error("❌ Failed: %s", result.get("error_message"))
            return 1

    @staticmethod
    def _cmd_health_check() -> int:
        """Run health check only.

        Returns:
            Exit code (0 = healthy).
        """
        log.info("=" * 60)
        log.info("COMMAND: doctor — Health Check")
        log.info("=" * 60)

        from automation.health import run_health_check

        health = run_health_check()
        log.info("-" * 60)

        for name, check in health.checks.items():
            icon = "✓" if check["ok"] else "✗"
            log.info("  %s [%s] %s", icon, name, check["message"])

        log.info("-" * 60)

        if health.healthy:
            log.info("Result: HEALTHY (%d checks passed)", len(health.checks))
            return 0
        else:
            log.error("Result: UNHEALTHY (%d error(s))", len(health.errors))
            for err in health.errors:
                log.error("  ✗ %s", err)
            return 1

    @staticmethod
    def _cmd_show_metrics() -> int:
        """Display system metrics.

        Returns:
            Exit code (always 0).
        """
        log.info("=" * 60)
        log.info("COMMAND: metrics — System Metrics")
        log.info("=" * 60)

        from automation.metrics import collect_metrics

        metrics = collect_metrics()

        log.info("  Articles:           %d", metrics.total_articles)
        log.info("  Published:          %d", metrics.published_count)
        log.info("  Failed:             %d", metrics.failed_count)
        log.info("  Pending:            %d", metrics.pending_count)
        log.info("  Success rate:       %.1f%%", metrics.success_rate * 100)
        log.info("  Avg publish time:   %.0f ms", metrics.avg_publish_time_ms)
        log.info("  Avg image gen time: %.0f ms", metrics.avg_image_time_ms)
        log.info("  Avg retries:        %.1f", metrics.avg_retries)
        log.info("  Disk usage:         %.1f MB", metrics.disk_usage_mb)

        if metrics.provider_usage:
            log.info("  Providers:")
            for prov, cnt in metrics.provider_usage.items():
                log.info("    - %s: %d", prov, cnt)

        if metrics.recent_articles:
            log.info("  Recent publications:")
            for a in metrics.recent_articles:
                log.info("    - %s", a.get("title", ""))
                log.info("      %s", a.get("blogger_url", ""))

        log.info("-" * 60)
        return 0

    @staticmethod
    def _cmd_retry_failed() -> int:
        """Retry publishing failed articles.

        Returns:
            Exit code.
        """
        log.info("=" * 60)
        log.info("COMMAND: retry — Retry Failed Articles")
        log.info("=" * 60)

        from automation.queue import ArticleQueue
        from blogger.publisher import Publisher

        queue = ArticleQueue()
        pending = queue.count_pending()
        log.info("Pending articles: %d", pending)

        publisher = Publisher()
        results = publisher.republish_failed_articles(max_articles=10)

        published = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        log.info("Retried: %d", len(results))
        log.info("  Successful: %d", len(published))
        log.info("  Still failed: %d", len(failed))

        for r in published:
            log.info("  ✅ %s → %s", r.get("title"), r.get("blogger_url"))
        for r in failed:
            log.warning("  ❌ %s — %s", r.get("title"), r.get("error_message"))

        return 0 if not failed else 1
