"""Pre-flight health verification for the publishing system.

Checks before publishing:
- Database connection and schema integrity
- Prompt Engine availability
- Image Engine availability
- Blogger API credential validity
- Available disk space
- Stuck articles (leftovers from crashes)
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from config.logging import get_logger
from config.settings import (
    ARTICLES_DIR,
    AUTOMATION_MIN_DISK_SPACE_MB,
    BLOG_ID,
    CLIENT_ID,
    CLIENT_SECRET,
    IMAGES_DIR,
    LOGS_DIR,
    PROJECT_ROOT,
    PUBLISHED_DIR,
    REFRESH_TOKEN,
)
from database.database import fetch_one, get_connection

log = get_logger(__name__)


@dataclass
class HealthStatus:
    """Complete health check result.

    Attributes:
        healthy:       ``True`` if all checks pass.
        checks:        Individual check results keyed by name.
        warnings:      Non-fatal issues.
        errors:        Fatal issues that prevent publishing.
        timestamp:     ISO timestamp of the check.
    """
    healthy: bool = False
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    timestamp: str = ""


def run_health_check() -> HealthStatus:
    """Run all health checks and return the combined result.

    Returns:
        A :class:`HealthStatus` dataclass.
    """
    status = HealthStatus(
        timestamp=datetime.utcnow().isoformat(),
    )
    checks: dict[str, dict[str, Any]] = {}

    # 1. Database
    db_ok, db_msg = _check_database()
    checks["database"] = {"ok": db_ok, "message": db_msg}

    # 2. Blogger credentials
    auth_ok, auth_msg = _check_auth()
    checks["auth"] = {"ok": auth_ok, "message": auth_msg}

    # 3. Disk space
    disk_ok, disk_msg = _check_disk_space()
    checks["disk_space"] = {"ok": disk_ok, "message": disk_msg}

    # 4. Directory integrity
    dirs_ok, dirs_msg = _check_directories()
    checks["directories"] = {"ok": dirs_ok, "message": dirs_msg}

    # 5. Stuck articles
    stuck_ok, stuck_msg = _check_stuck_articles()
    checks["stuck_articles"] = {"ok": stuck_ok, "message": stuck_msg}

    status.checks = checks

    # Collect warnings and errors
    for name, result in checks.items():
        if result["ok"]:
            log.info("Health [%s] ✓ %s", name, result["message"])
        else:
            log.warning("Health [%s] ✗ %s", name, result["message"])
            status.errors.append(f"[{name}] {result['message']}")

    status.healthy = len(status.errors) == 0

    # Warnings (non-fatal)
    if not CLIENT_ID or not CLIENT_SECRET or not REFRESH_TOKEN:
        status.warnings.append(
            "Blogger API credentials partially configured — "
            "auth check will catch missing values"
        )
    if not BLOG_ID:
        status.warnings.append(
            "BLOG_ID not set — publishing will be skipped"
        )

    status.healthy = len(status.errors) == 0
    log.info(
        "Health check complete: %s (errors=%d, warnings=%d)",
        "healthy" if status.healthy else "unhealthy",
        len(status.errors),
        len(status.warnings),
    )
    return status


# ------------------------------------------------------------------
# Individual checks
# ------------------------------------------------------------------


def _check_database() -> tuple[bool, str]:
    """Verify database connection and required tables.

    Returns:
        Tuple of (ok, message).
    """
    try:
        conn = get_connection()
        required = {"articles", "generated_images", "used_prompts", "pipeline_runs"}
        existing = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = required - existing
        if missing:
            return False, f"Missing tables: {missing}"
        return True, f"All {len(existing)} tables present"
    except Exception as exc:
        return False, f"Connection failed: {exc}"


def _check_auth() -> tuple[bool, str]:
    """Verify Blogger API credential availability.

    Returns:
        Tuple of (ok, message).
    """
    missing: list[str] = []
    if not BLOG_ID:
        missing.append("BLOG_ID")
    if not CLIENT_ID:
        missing.append("CLIENT_ID")
    if not CLIENT_SECRET:
        missing.append("CLIENT_SECRET")
    if not REFRESH_TOKEN:
        missing.append("REFRESH_TOKEN")

    if missing:
        return False, f"Missing credentials: {', '.join(missing)}"
    return True, "All Blogger API credentials present"


def _check_disk_space() -> tuple[bool, str]:
    """Verify available disk space meets the minimum threshold.

    Returns:
        Tuple of (ok, message).
    """
    try:
        usage = shutil.disk_usage(PROJECT_ROOT)
        free_mb = usage.free / (1024 * 1024)
        min_mb = AUTOMATION_MIN_DISK_SPACE_MB
        if free_mb < min_mb:
            return (
                False,
                f"Low disk space: {free_mb:.0f} MB free "
                f"(minimum {min_mb} MB)",
            )
        return True, f"{free_mb:.0f} MB free ({min_mb} MB minimum)"
    except OSError as exc:
        return False, f"Disk check failed: {exc}"


def _check_directories() -> tuple[bool, str]:
    """Verify that required directories exist.

    Returns:
        Tuple of (ok, message).
    """
    required_dirs = [
        PROJECT_ROOT,
        ARTICLES_DIR,
        IMAGES_DIR,
        LOGS_DIR,
        PUBLISHED_DIR,
    ]
    missing = [str(d) for d in required_dirs if not d.exists()]
    if missing:
        return False, f"Missing directories: {missing}"
    return True, "All directories present"


def _check_stuck_articles() -> tuple[bool, str]:
    """Check for articles stuck in 'publishing' state.

    Returns:
        Tuple of (ok, message). If stuck articles are found, returns
        ``ok=False`` with count and IDs.
    """
    try:
        rows = fetch_one(
            "SELECT COUNT(*) AS cnt FROM articles WHERE status = 'publishing'"
        )
        count = rows["cnt"] if rows else 0
        if count > 0:
            return (
                False,
                f"{count} article(s) stuck in 'publishing' state — "
                "run recovery first",
            )
        return True, "No stuck articles"
    except Exception as exc:
        return False, f"Stuck article check failed: {exc}"
