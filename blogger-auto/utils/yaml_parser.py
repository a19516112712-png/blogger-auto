#!/usr/bin/env python3
"""
YAML frontmatter parser — single source for all markdown parsing.

Replaces duplicate yaml.safe_load() calls across generate_content.py,
publish.py, and repair_posts.py.
"""

import re
import yaml
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


def parse_frontmatter(filepath: Path) -> tuple[dict | None, str]:
    """Parse a markdown file's frontmatter and body.

    Returns (frontmatter_dict, body_text).
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception as exc:
        log.error("Cannot read %s: %s", filepath.name, exc)
        return None, ""

    body = text
    frontmatter = None

    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1].strip())
                if isinstance(fm, dict):
                    frontmatter = fm
                body = parts[2]
            except yaml.YAMLError as exc:
                log.warning("YAML parse error in %s: %s", filepath.name, exc)
                body = text

    return frontmatter, body.strip()


def extract_date_from_filename(filename: str) -> str:
    """Extract date from filename like 2026-06-16-slug.md."""
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", filename)
    if match:
        return match.group(1)
    return datetime.now().strftime("%Y-%m-%d")


REQUIRED_FRONTMATTER_FIELDS = {"title", "date", "labels"}
DEFAULT_LABELS = ["Baby Names"]
FORBIDDEN_LABELS = {"seo", "blog", "article", "content", "post", "seo optimized", "adsense"}


def has_valid_frontmatter(filepath: Path) -> bool:
    """Check if a markdown file has valid YAML frontmatter with required fields."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return False

    if not text.startswith("---"):
        return False

    parts = text.split("---", 2)
    if len(parts) < 3:
        return False

    try:
        fm = yaml.safe_load(parts[1].strip())
    except yaml.YAMLError:
        return False

    if not isinstance(fm, dict):
        return False

    for field in REQUIRED_FRONTMATTER_FIELDS:
        if field not in fm or fm[field] is None:
            return False
        if field in ("title", "date") and not str(fm[field]).strip():
            return False
        if field == "labels":
            if not isinstance(fm[field], list) or len(fm[field]) == 0:
                return False

    return True
