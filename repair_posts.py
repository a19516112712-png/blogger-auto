#!/usr/bin/env python3
"""
Post Repair Script (Refactored)

Scans all markdown files in posts/ and ensures valid YAML frontmatter.
Uses shared helpers from utils/ — no duplicate functions.
"""

import logging
import sys
from pathlib import Path

from utils.helpers import sanitize_labels, build_frontmatter, FORBIDDEN_LABELS
from utils.yaml_parser import parse_frontmatter, extract_date_from_filename, has_valid_frontmatter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

POSTS_DIR = Path(__file__).resolve().parent / "posts"
REQUIRED_FRONTMATTER_FIELDS = {"title", "date", "labels"}
DEFAULT_LABELS = ["Baby Names"]


def repair_file(filepath: Path) -> bool:
    """Repair a single markdown file's frontmatter."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception as exc:
        log.error("Cannot read %s: %s", filepath.name, exc)
        return False

    # Extract title from H1
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]

    title = body.split('\n')[0].strip()
    if title.startswith('# '):
        title = title[2:].strip()

    date_str = extract_date_from_filename(filepath.name)

    # Salvage existing labels
    labels = list(DEFAULT_LABELS)
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            import yaml
            try:
                old_fm = yaml.safe_load(parts[1].strip())
                if isinstance(old_fm, dict) and "labels" in old_fm:
                    labels = sanitize_labels(old_fm["labels"])
            except Exception:
                pass

    frontmatter = build_frontmatter(title, labels, date_str)
    new_content = f"{frontmatter}\n\n{body}\n"

    if not has_valid_frontmatter_path(new_content):
        log.error("Repair FAILED for %s", filepath.name)
        return False

    filepath.write_text(new_content, encoding="utf-8")
    log.info("Repaired: %s | title=%r | date=%s", filepath.name, title, date_str)
    return True


def has_valid_frontmatter_path(content: str) -> bool:
    """Validate frontmatter from string content."""
    if not content.startswith("---"):
        return False
    parts = content.split("---", 2)
    if len(parts) < 3:
        return False
    import yaml
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


def main():
    log.info("Starting post repair scan…")

    md_files = sorted(POSTS_DIR.glob("*.md"))
    if not md_files:
        log.info("No markdown files found in %s.", POSTS_DIR)
        return

    total = len(md_files)
    already_valid = 0
    repaired = 0
    failed = 0

    for md_file in md_files:
        if has_valid_frontmatter(md_file):
            already_valid += 1
        else:
            if repair_file(md_file):
                repaired += 1
            else:
                failed += 1

    log.info("Repair scan complete. Total: %d, Valid: %d, Repaired: %d, Failed: %d",
             total, already_valid, repaired, failed)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
