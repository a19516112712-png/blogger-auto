"""Application configuration loaded from environment variables.

All settings use sensible defaults and can be overridden via `.env` file
or environment variables.  Uses ``pathlib`` for all filesystem paths.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final


# ---------------------------------------------------------------------------
# Project root & sub-directories
# ---------------------------------------------------------------------------
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

ARTICLES_DIR: Final[Path] = PROJECT_ROOT / "articles"
PUBLISHED_DIR: Final[Path] = PROJECT_ROOT / "published"
IMAGES_DIR: Final[Path] = PROJECT_ROOT / "images"
PROMPTS_DIR: Final[Path] = PROJECT_ROOT / "prompts"
TEMPLATES_DIR: Final[Path] = PROJECT_ROOT / "templates"
LOGS_DIR: Final[Path] = PROJECT_ROOT / "logs"
DATABASE_DIR: Final[Path] = PROJECT_ROOT / "database"
POSTS_DIR: Final[Path] = PROJECT_ROOT.parent / "posts"

# Ensure directories exist at import time (idempotent)
for _dir in (ARTICLES_DIR, PUBLISHED_DIR, IMAGES_DIR, PROMPTS_DIR,
             TEMPLATES_DIR, LOGS_DIR, DATABASE_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL: Final[str] = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{DATABASE_DIR / 'blogger_ai_publisher.db'}",
)
DATABASE_PATH: Final[Path] = Path(
    DATABASE_URL.replace("sqlite:///", "")
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: Final[str] = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR: Final[Path] = LOGS_DIR  # alias
LOG_FILE: Final[Path] = LOGS_DIR / "app.log"
_ENV_FORMAT = os.getenv("LOG_FORMAT")
_LOG_FORMAT_DEFAULT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_FORMAT: Final[str] = (
    _ENV_FORMAT
    if _ENV_FORMAT and all(f"({s})" in _ENV_FORMAT for s in ("asctime", "levelname", "name", "message"))
    else _LOG_FORMAT_DEFAULT
)
LOG_DATE_FORMAT: Final[str] = os.getenv(
    "LOG_DATE_FORMAT",
    "%Y-%m-%d %H:%M:%S",
)

# ---------------------------------------------------------------------------
# Blogger API
# ---------------------------------------------------------------------------
BLOG_ID: Final[str] = os.getenv("BLOG_ID", "")
CLIENT_ID: Final[str] = os.getenv("CLIENT_ID", "")
CLIENT_SECRET: Final[str] = os.getenv("CLIENT_SECRET", "")
REFRESH_TOKEN: Final[str] = os.getenv("REFRESH_TOKEN", "")
BLOG_URL: Final[str] = os.getenv("BLOG_URL", "https://babynameideas2026.blogspot.com")

# ---------------------------------------------------------------------------
# AI Generation
# ---------------------------------------------------------------------------
AGNES_API_KEY: Final[str] = os.getenv("AGNES_API_KEY", "")
AGNES_MODEL: Final[str] = os.getenv("AGNES_MODEL", "agnes-2.0-flash")
AGNES_BASE_URL: Final[str] = os.getenv(
    "AGNES_BASE_URL",
    "https://apihub.agnes-ai.com/v1",
)

# ---------------------------------------------------------------------------
# Image Engine
# ---------------------------------------------------------------------------
# Output image specifications
IMAGE_OUTPUT_WIDTH: Final[int] = int(os.getenv("IMAGE_OUTPUT_WIDTH", "1600"))
IMAGE_OUTPUT_HEIGHT: Final[int] = int(os.getenv("IMAGE_OUTPUT_HEIGHT", "900"))
IMAGE_OUTPUT_FORMAT: Final[str] = os.getenv("IMAGE_OUTPUT_FORMAT", "WEBP")
IMAGE_OUTPUT_QUALITY: Final[int] = int(os.getenv("IMAGE_OUTPUT_QUALITY", "90"))
IMAGE_MAX_FILE_SIZE: Final[int] = int(os.getenv(
    "IMAGE_MAX_FILE_SIZE", str(300 * 1024)  # 300 KB
))

# Provider configuration (comma-separated ordered list; first available wins)
IMAGE_PROVIDERS: Final[list[str]] = os.getenv(
    "IMAGE_PROVIDERS",
    "pollinations,huggingface",
).split(",")

# Max retries across all providers
IMAGE_MAX_RETRIES: Final[int] = int(os.getenv("IMAGE_MAX_RETRIES", "3"))

# Per-provider settings
IMAGE_PROVIDER_TIMEOUT: Final[int] = int(
    os.getenv("IMAGE_PROVIDER_TIMEOUT", "20")
)

HUGGINGFACE_API_TOKEN: Final[str] = os.getenv("HUGGINGFACE_API_TOKEN", "")
HUGGINGFACE_MODEL: Final[str] = os.getenv(
    "HUGGINGFACE_MODEL",
    "black-forest-labs/FLUX.1-schnell",
)
POLLINATIONS_BASE_URL: Final[str] = os.getenv(
    "POLLINATIONS_BASE_URL",
    "https://image.pollinations.ai/prompt",
)

# Image deduplication: Hamming distance threshold (0 = exact, ≤ 5 = near-duplicate)
IMAGE_PHASH_THRESHOLD: Final[int] = int(os.getenv("IMAGE_PHASH_THRESHOLD", "5"))

# ---------------------------------------------------------------------------
# Publisher Engine
# ---------------------------------------------------------------------------
# Retry settings
PUBLISHER_MAX_RETRIES: Final[int] = int(os.getenv("PUBLISHER_MAX_RETRIES", "3"))
PUBLISHER_RETRY_DELAY_SECONDS: Final[int] = int(
    os.getenv("PUBLISHER_RETRY_DELAY_SECONDS", "5")
)
PUBLISHER_MAX_BACKOFF_SECONDS: Final[int] = int(
    os.getenv("PUBLISHER_MAX_BACKOFF_SECONDS", "60")
)

# Image upload
PUBLISHER_IMAGE_MAX_RETRIES: Final[int] = int(
    os.getenv("PUBLISHER_IMAGE_MAX_RETRIES", "3")
)

# Slug
PUBLISHER_SLUG_MAX_LENGTH: Final[int] = int(
    os.getenv("PUBLISHER_SLUG_MAX_LENGTH", "75")
)

# Default labels (fallback if article has none)
PUBLISHER_DEFAULT_LABELS: Final[list[str]] = os.getenv(
    "PUBLISHER_DEFAULT_LABELS",
    "Baby Names",
).split(",")

# Blogger API scope
BLOGGER_SCOPE: Final[str] = "https://www.googleapis.com/auth/blogger"
BLOGGER_TOKEN_URI: Final[str] = "https://oauth2.googleapis.com/token"

# ---------------------------------------------------------------------------
# Automation Engine
# ---------------------------------------------------------------------------
AUTOMATION_MAX_ARTICLES_PER_RUN: Final[int] = int(
    os.getenv("AUTOMATION_MAX_ARTICLES_PER_RUN", "1")
)
AUTOMATION_RETRY_FAILED: Final[bool] = os.getenv(
    "AUTOMATION_RETRY_FAILED", "true"
).lower() in ("1", "true", "yes")
AUTOMATION_HEALTH_CHECK_ENABLED: Final[bool] = os.getenv(
    "AUTOMATION_HEALTH_CHECK_ENABLED", "true"
).lower() in ("1", "true", "yes")
AUTOMATION_REPORTS_DIR: Final[Path] = LOGS_DIR / "reports"
AUTOMATION_MIN_DISK_SPACE_MB: Final[int] = int(
    os.getenv("AUTOMATION_MIN_DISK_SPACE_MB", "500")
)

# ---------------------------------------------------------------------------
# Content defaults
# ---------------------------------------------------------------------------
DEFAULT_ARTICLES_PER_RUN: Final[int] = int(
    os.getenv("ARTICLES_PER_RUN", "10")
)
MIN_ARTICLE_WORDS: Final[int] = int(os.getenv("MIN_ARTICLE_WORDS", "1500"))
TARGET_ARTICLE_WORDS: Final[int] = int(os.getenv("TARGET_ARTICLE_WORDS", "2500"))


def validate() -> list[str]:
    """Check critical settings and return a list of missing values.

    Returns:
        A list of human-readable warnings.  Empty when all critical
        settings are present.
    """
    warnings: list[str] = []
    if not BLOG_ID:
        warnings.append("BLOG_ID is not set — publishing will be disabled.")
    if not CLIENT_ID:
        warnings.append("CLIENT_ID is not set — Blogger API auth unavailable.")
    if not AGNES_API_KEY:
        warnings.append("AGNES_API_KEY is not set — AI generation disabled.")
    return warnings
