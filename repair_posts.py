#!/usr/bin/env python3
"""
Post Repair Script

Scans all markdown files in posts/ and ensures every file has valid
YAML frontmatter. If frontmatter is missing or malformed, it is
rebuilt automatically by extracting the title from the first H1 heading.

Run this before publish.py to guarantee zero skipped posts due to
frontmatter issues.
"""

import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
POSTS_DIR = Path(__file__).resolve().parent / "posts"

REQUIRED_FRONTMATTER_FIELDS = {"title", "date", "labels"}

DEFAULT_LABELS = ["Baby Names"]
# Excludes "SEO" — labels describe content theme, not publishing strategy


# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------
def has_valid_frontmatter(filepath: Path) -> bool:
    """Check whether a file starts with `---` and contains parseable YAML
    with all required fields.

    Args:
        filepath: Path to the markdown file.

    Returns:
        True if the frontmatter is valid.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception as exc:
        log.warning("Cannot read %s: %s", filepath.name, exc)
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

    # Check all required fields present and non-empty
    for field in REQUIRED_FRONTMATTER_FIELDS:
        if field not in fm:
            return False
        if fm[field] is None:
            return False
        # title and date must be non-empty strings
        if field in ("title", "date") and not str(fm[field]).strip():
            return False
        # labels must be a non-empty list
        if field == "labels":
            if not isinstance(fm[field], list) or len(fm[field]) == 0:
                return False

    return True


def extract_title_from_body(body: str, fallback: str) -> str:
    """Extract the title from the first H1 heading in the body.

    Args:
        body: Markdown body text (after any frontmatter).
        fallback: Fallback title if no H1 is found.

    Returns:
        Extracted or fallback title.
    """
    match = re.search(r"^#\s+(.+?)$", body, re.MULTILINE)
    if match:
        title = match.group(1).strip()
        # Sanitize: strip any YAML key prefixes that leaked into the title
        for prefix in ("title:", "date:", "labels:", "meta_description:", "---"):
            if title.lower().startswith(prefix):
                if prefix in ("date:", "labels:", "meta_description:", "---"):
                    log.warning("Title begins with '%s' in %s — skipping H1 extraction.", prefix.rstrip(":"), filepath.name if 'filepath' in dir() else 'unknown')
                    break
                title = title.split(":", 1)[1].strip()
                log.info("Stripped '%s' prefix from extracted title.", prefix.rstrip(":"))
                break
        return title
    # Try first non-empty, non-delimiter line
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("---") and not stripped.startswith("```"):
            return stripped[:150]
    return fallback


def extract_date_from_filename(filename: str) -> str:
    """Try to extract a date from a filename like 2026-06-16-slug.md.

    Falls back to today's date if no date prefix is found.
    """
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", filename)
    if match:
        return match.group(1)
    return datetime.now().strftime("%Y-%m-%d")


def build_frontmatter(title: str, labels: list[str], date_str: str) -> str:
    """Build a valid YAML frontmatter block using yaml.dump."""
    data = {
        "title": title,
        "labels": labels,
        "date": date_str,
    }
    yaml_body = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return "---\n" + yaml_body + "---"


def repair_file(filepath: Path) -> bool:
    """Repair a single markdown file's frontmatter.

    Args:
        filepath: Path to the .md file.

    Returns:
        True if the file was repaired, False if it needed no repair or
        could not be repaired.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception as exc:
        log.error("Cannot read %s: %s", filepath.name, exc)
        return False

    # Separate existing frontmatter from body
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2].strip()
        else:
            body = text
    else:
        body = text

    # Extract metadata
    title = extract_title_from_body(body, filepath.stem)
    date_str = extract_date_from_filename(filepath.name)
    labels = DEFAULT_LABELS

    # Build fresh frontmatter
    frontmatter = build_frontmatter(title, labels, date_str)
    new_content = f"{frontmatter}\n\n{body}\n"

    # Validate the new content
    if not has_valid_frontmatter_path(new_content):
        log.error("Repair FAILED for %s: rebuilt frontmatter still invalid.", filepath.name)
        return False

    filepath.write_text(new_content, encoding="utf-8")
    log.info("Repaired: %s | title=%r | date=%s", filepath.name, title, date_str)
    return True


def has_valid_frontmatter_path(content: str) -> bool:
    """Like has_valid_frontmatter but operates on a string."""
    if not content.startswith("---"):
        return False
    parts = content.split("---", 2)
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
        if field == "labels" and (not isinstance(fm[field], list) or len(fm[field]) == 0):
            return False
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
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
            log.info("OK: %s", md_file.name)
            already_valid += 1
        else:
            log.warning("BROKEN frontmatter: %s — attempting repair…", md_file.name)
            if repair_file(md_file):
                repaired += 1
            else:
                failed += 1

    log.info("Repair scan complete.")
    log.info("  Total files:     %d", total)
    log.info("  Already valid:   %d", already_valid)
    log.info("  Repaired:        %d", repaired)
    log.info("  Failed:          %d", failed)

    if failed > 0:
        log.error("%d file(s) could not be repaired.", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
