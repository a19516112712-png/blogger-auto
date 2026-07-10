"""Crash and error recovery for the automation engine.

Handles:
1. Articles stuck in ``'publishing'`` state after an unexpected crash.
2. Incomplete pipeline runs from the previous execution.
3. Validation and repair of the article queue.

Designed to be called at the start of every pipeline execution so that
the system is **self-healing**.
"""

from __future__ import annotations

from config.logging import get_logger
from database.database import execute, fetch_all, fetch_one, get_connection

log = get_logger(__name__)


class RecoveryError(Exception):
    """Raised when recovery fails."""


def recover_state() -> int:
    """Run all recovery procedures and return the number of articles fixed.

    Steps:
    1. Unlock any articles stuck in ``'publishing'`` state.
    2. Detect incomplete pipeline runs and mark them as failed.
    3. Validate database integrity.

    Returns:
        Number of articles or runs that were recovered.

    Raises:
        RecoveryError: If a critical recovery step fails.
    """
    fixed = 0
    fixed += _recover_stuck_articles()
    fixed += _recover_incomplete_runs()
    _validate_integrity()

    if fixed > 0:
        log.info("Recovery complete: %d items fixed", fixed)
    else:
        log.info("Recovery complete: nothing to fix")
    return fixed


# ------------------------------------------------------------------
# Recovery steps
# ------------------------------------------------------------------


def _recover_stuck_articles() -> int:
    """Find articles stuck in ``'publishing'`` state and unlock them.

    Returns:
        Number of articles unlocked.
    """
    stuck = fetch_all(
        "SELECT id, title, updated_at FROM articles WHERE status = 'publishing'"
    )
    for article in stuck:
        article_id = article["id"]
        # Increment attempt count and set back to ready/draft
        now_sql = "datetime('now')"
        execute(
            f"""UPDATE articles SET
                status = CASE
                    WHEN publish_attempts >= 10 THEN 'failed'
                    ELSE 'ready'
                END,
                publish_attempts = publish_attempts + 1,
                last_publish_error = 'Recovered from crash (stuck in publishing)',
                updated_at = {now_sql}
                WHERE id = ?
                AND status = 'publishing'""",
            (article_id,),
            commit=True,
        )
        log.warning(
            "Unlocked stuck article %d: %s",
            article_id,
            article["title"],
        )

    count = len(stuck)
    if count:
        log.info("Recovered %d stuck article(s)", count)
    return count


def _recover_incomplete_runs() -> int:
    """Mark any pipeline runs stuck in ``'running'`` state as failed.

    Returns:
        Number of runs recovered.
    """
    now_sql = "datetime('now')"
    execute(
        f"""UPDATE pipeline_runs SET
            status = 'failed',
            finished_at = {now_sql},
            error_message = 'Recovered from crash (incomplete run)'
            WHERE status = 'running'""",
        commit=True,
    )
    affected = execute(
        "SELECT changes() AS cnt"
    ).fetchone()
    count = affected["cnt"] if affected else 0
    if count:
        log.info("Recovered %d incomplete pipeline run(s)", count)
    return count


def _validate_integrity() -> None:
    """Run a quick integrity check on the database.

    Raises:
        RecoveryError: If integrity check fails.
    """
    try:
        conn = get_connection()
        row = conn.execute("PRAGMA integrity_check").fetchone()
        result = row[0] if row else "unknown"
        if result != "ok":
            raise RecoveryError(f"Database integrity check failed: {result}")
        log.debug("Database integrity check passed")
    except RecoveryError:
        raise
    except Exception as exc:
        raise RecoveryError(f"Integrity check error: {exc}") from exc
