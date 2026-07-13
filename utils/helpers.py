#!/usr/bin/env python3
"""
Shared helpers — single source of truth for all utility functions.

Extracted from:
  generate_content.py  (slugify, sanitize_title, build_frontmatter, etc.)
  publish.py           (slugify, sanitize_labels, sanitize_title)
  repair_posts.py      (sanitize_labels, build_frontmatter, extract_title)

All modules import from here instead of duplicating.
"""

import hashlib
import re
from datetime import datetime

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FORBIDDEN_LABELS = {"seo", "blog", "article", "content", "post", "seo optimized", "adsense"}
BANNED_PHRASES = [
    "the rise of", "timeless choices", "artistic flair", "perfect balance",
    "modern parents", "creative naming ideas", "for your little one",
    "beautiful choices", "inspired living", "elegant selections",
    "meaningful journey", "hidden gems", "naming inspiration",
    "magical names", "dreamy names", "enchanting names", "whimsical names",
    "naming ideas",
]
MIN_TITLE_LENGTH = 10
MIN_BODY_WORDS = 1500
MIN_LABELS = 4
MAX_LABELS = 6

# ---------------------------------------------------------------------------
# Slug
# ---------------------------------------------------------------------------

def slugify(title: str) -> str:
    """Convert a title to a safe filename slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:80]


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

def sanitize_labels(labels) -> list:
    """Strip forbidden labels and deduplicate. Always includes 'Baby Names' first."""
    if isinstance(labels, str):
        labels = [lbl.strip() for lbl in labels.split(",") if lbl.strip()]
    if not isinstance(labels, list):
        return ["Baby Names"]
    cleaned = []
    seen = {"baby names"}
    for lbl in labels:
        lbl_str = str(lbl).strip()
        if not lbl_str:
            continue
        if lbl_str.lower() in FORBIDDEN_LABELS:
            continue
        if lbl_str.lower() not in seen:
            cleaned.append(lbl_str)
            seen.add(lbl_str.lower())
    if not cleaned or "Baby Names" not in cleaned:
        return ["Baby Names"] + cleaned
    return cleaned


# ---------------------------------------------------------------------------
# Title extraction
# ---------------------------------------------------------------------------

def sanitize_title(raw_title: str | None, filename: str = "") -> str | None:
    """Clean and validate a title from frontmatter. Strips YAML key prefixes."""
    if not raw_title:
        return None
    title = raw_title.strip()
    YAML_KEY_PREFIXES = ("title:", "date:", "labels:", "meta_description:", "---", "# ")
    for prefix in YAML_KEY_PREFIXES:
        if title.lower().startswith(prefix):
            if ":" in prefix:
                title = title.split(":", 1)[1].strip()
            else:
                title = title[len(prefix):].strip()
            break
    return title if title.strip() else None


def extract_title_from_text(text: str, fallback: str = "") -> str:
    """Extract title from first H1 heading or first non-empty line."""
    match = re.search(r"^#\s+(.+?)$", text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("---") and not stripped.startswith("```"):
            return stripped[:150]
    return fallback


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

def build_frontmatter(title: str, labels: list[str], today: str,
                      topic: str = "", meta_desc: str | None = None) -> str:
    """Construct valid YAML frontmatter block."""
    seo_title = title[:65] if len(title) <= 65 else title[:62] + "..."
    if meta_desc is None:
        meta_desc = generate_meta_description(title, topic)
    data = {
        "title": title,
        "labels": labels,
        "date": today,
        "slug": slugify(title),
        "meta_description": meta_desc,
        "seo_title": seo_title,
        "og_title": title,
        "og_description": meta_desc,
    }
    yaml_body = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return "---\n" + yaml_body + "---"


def strip_existing_frontmatter(text: str) -> str:
    """Remove YAML frontmatter block if present."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text.strip()


def strip_fences(text: str) -> str:
    """Remove outermost ```markdown ... ``` fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rsplit("\n", 1)[0]
    return text.strip()


# ---------------------------------------------------------------------------
# Title Normalization
# ---------------------------------------------------------------------------

def normalize_title_for_dedup(title: str) -> str:
    """Normalize a title for duplicate detection.
    
    Strips trailing numeric suffixes so "Foo 1" and "Foo" are treated as duplicates.
    """
    t = title.strip().lower()
    # Remove trailing numbered suffixes: ' 1', ' 2', '-1', '(1)', etc.
    t = re.sub(r'\s+[0-9]+\s*$', '', t)
    t = re.sub(r'\s*-[0-9]+\s*$', '', t)
    t = re.sub(r'\s*\([0-9]+\)\s*$', '', t)
    return t.strip()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def count_words(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def enforce_title_rules(title: str) -> str | None:
    """Post-process title to ensure SEO rules. Returns None if invalid.
    
    Strips trailing numeric suffixes (e.g., ' 1', '-1', '(1)') to prevent
    duplicate articles that differ only by a number.
    """
    title = title.strip()
    original = title
    if title.startswith("# "):
        title = title[2:].strip()

    # Strip trailing numbered suffixes first
    title = re.sub(r'\s+[0-9]+\s*$', '', title)
    title = re.sub(r'\s*-[0-9]+\s*$', '', title)
    title = re.sub(r'\s*\([0-9]+\)\s*$', '', title)

    title_lower = title.lower()
    for phrase in BANNED_PHRASES:
        if phrase in title_lower:
            return None

    if len(title) > 65:
        trimmed = title[:65].rsplit(" ", 1)[0]
        if len(trimmed) < 10:
            return None
        title = trimmed

    if not re.match(r"^\d+\s", title):
        return None

    if title != original:
        pass  # silent adjustment
    return title


def generate_meta_description(title: str, topic: str = "") -> str:
    """Generate SEO meta description."""
    desc_title = re.sub(r"^\d+\s+", "", title)
    return (
        f"Discover {title.lower()}, including meanings, origins, "
        f"pronunciation guides, and naming ideas. Find the perfect "
        f"{desc_title.lower()} for your baby."
    )[:160]


def compute_content_hash(text: str) -> str:
    """Compute SHA-256 hash of content for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# ---------------------------------------------------------------------------
# AI Client Factory
# ---------------------------------------------------------------------------

def get_client(base_url: str = "https://apihub.agnes-ai.com/v1", model: str = "agnes-2.0-flash"):
    """Create an OpenAI-compatible client for Agnes AI."""
    from openai import OpenAI
    import os
    api_key = os.environ.get("AGNES_API_KEY")
    if not api_key:
        raise EnvironmentError("AGNES_API_KEY not set")
    return OpenAI(api_key=api_key, base_url=base_url)

# ---------------------------------------------------------------------------
# Internal Link Graph Builder
# ---------------------------------------------------------------------------

def build_link_graph(posts_dir):
    """Build internal link graph from all articles.
    
    Returns dict mapping slug -> list of target slugs found in that article.
    """
    import re
    posts_dir = Path(posts_dir)
    graph = {}
    
    for md_file in posts_dir.glob("*.md"):
        content = md_file.read_text()
        source_slug = slugify(md_file.stem)
        
        links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', content)
        targets = []
        for anchor, url in links:
            if "/p/" in url:
                match = re.search(r'/p/\d+_([^/]+)\.html', url)
                if match:
                    targets.append(match.group(1))
        
        graph[source_slug] = targets
    
    return graph

