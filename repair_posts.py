#!/usr/bin/env python3
"""
Post Repair Script (Refactored)

Scans all markdown files in posts/ and ensures valid YAML frontmatter.
Legacy files with unquoted colons in values are repaired by regenerating
frontmatter via build_frontmatter().

IMPORTANT: This script NEVER exits with non-zero status. Invalid files
are logged as warnings and skipped — they do NOT block publish.py.
"""

import logging
import sys
from pathlib import Path

from utils.helpers import sanitize_labels, build_frontmatter
from utils.yaml_parser import parse_frontmatter, extract_date_from_filename

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

POSTS_DIR = Path(__file__).resolve().parent / "posts"


def repair_file(filepath: Path) -> bool:
    """Repair a single markdown file's frontmatter.

    Strategy for legacy files (unquoted colons, bad formatting):
    1. Try to parse frontmatter normally.
    2. If parsing fails, try to salvage title from H1 in body.
    3. If no H1 found, derive title from filename slug.
    4. Rebuild frontmatter cleanly via build_frontmatter().
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception as exc:
        log.warning("Cannot read %s: %s", filepath.name, exc)
        return False

    # --- Step 1: Extract body (everything after closing ---) ---
    body = text
    fm_text = ""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            body = parts[2]

    # --- Step 2: Try to parse existing frontmatter ---
    title = None
    labels = ["Baby Names"]
    try:
        import yaml

        if fm_text:
            old_fm = yaml.safe_load(fm_text)
            if isinstance(old_fm, dict):
                title = str(old_fm.get("title", ""))
                old_labels = old_fm.get("labels", [])
                if isinstance(old_labels, list) and len(old_labels) > 0:
                    labels = sanitize_labels(old_labels)
    except Exception:
        pass  # Legacy YAML — will rebuild from scratch

    # --- Step 3: Fallback — extract title from body H1 ---
    if not title or not title.strip():
        first_lines = body.strip().split("\n", 5)[:5]
        for line in first_lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                break

    # --- Step 4: Fallback — derive from filename ---
    if not title or not title.strip():
        stem = filepath.stem
        # Remove date prefix YYYY-MM-DD-
        import re

        title_slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)
        # Replace hyphens with spaces and capitalize
        title = title_slug.replace("-", " ").title()

    # --- Step 5: Get date from filename ---
    date_str = extract_date_from_filename(filepath.name)

    # --- Step 6: Rebuild clean frontmatter ---
    frontmatter = build_frontmatter(title, labels, date_str)
    # Strip any leading/trailing whitespace from body
    body = body.strip()
    new_content = f"{frontmatter}\n\n{body}\n"

    filepath.write_text(new_content, encoding="utf-8")
    log.info(
        "Repaired: %s | title=%r | date=%s",
        filepath.name,
        title,
        date_str,
    )
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
    skipped = 0

    for md_file in md_files:
        if repair_file(md_file):
            # Verify the repaired file actually parses now
            _, body = parse_frontmatter(md_file)
            if body:
                repaired += 1
            else:
                skipped += 1
                log.warning(
                    "Skipped (no body after repair): %s", md_file.name
                )
        else:
            skipped += 1
            log.warning("Skip (unreadable): %s", md_file.name)

    # Count files that were already valid (parse_frontmatter succeeds)
    already_valid = 0
    for md_file in md_files:
        fm, body = parse_frontmatter(md_file)
        if fm and body:
            already_valid += 1

    log.info(
        "Repair scan complete. Total: %d, Already Valid: %d, Repaired: %d, Skipped: %d",
        total,
        already_valid,
        repaired,
        skipped,
    )

    # NEVER exit with non-zero — always allow publish.py to proceed
    log.info("Repair complete. Proceeding with publish regardless of skipped files.")


if __name__ == "__main__":
    main()
