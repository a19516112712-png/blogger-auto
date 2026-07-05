#!/usr/bin/env python3
"""
Blogger Content Generator -- Generation-Only Pipeline

Decoupled architecture:
  generate_content.py  ->  [Keyword] -> [AI Generate] -> [Save Markdown to posts/]
  publish.py           ->  [Read posts/] -> [Publish to Blogger via API]

This script ONLY generates articles and saves clean markdown files.
It does NOT authenticate with Blogger or call any publishing API.

Features:
  - Keywords from env var BLOG_KEYWORDS (comma-separated) or hardcoded list
  - Generates 3000-5000 word SEO articles via Agnes AI
  - Saves markdown with frontmatter to posts/
  - Auto-labels via _generate_labels() with fallback buffer guaranteeing >=4 labels
  - Zero SQLite dependency
  - Zero Blogger publishing calls
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import markdown
import yaml
from openai import OpenAI

# --- Shared helpers -----------------------------------------------
from utils.helpers import (
    slugify, sanitize_labels, sanitize_title,
    build_frontmatter, strip_fences,
    count_words, generate_meta_description, enforce_title_rules,
    BANNED_PHRASES, MIN_LABELS, MAX_LABELS, FORBIDDEN_LABELS,
)

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
DEFAULT_MODEL = "agnes-2.0-flash"
MODEL = os.environ.get("AGNES_MODEL", DEFAULT_MODEL)
AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"

MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 30]

# Quality gates
MIN_WORD_COUNT = 3000

_quota_exhausted = False


# =========================================================================
# KEYWORD INPUT -- env var or hardcoded fallback
# =========================================================================

def get_keywords():
    """Load keywords from BLOG_KEYWORDS env var (comma-separated).

    Falls back to a curated list if env var is empty/unset.
    """
    raw = os.environ.get("BLOG_KEYWORDS", "").strip()
    if raw:
        keywords = [k.strip() for k in raw.split(",") if k.strip()]
        log.info("Loaded %d keywords from BLOG_KEYWORDS env var", len(keywords))
        return keywords

    # Hardcoded fallback -- production-ready topic list
    keywords = [
        "100 Irish Baby Names with Meanings",
        "100 Japanese Baby Names for Boys and Girls",
        "100 Unique Vintage Baby Names",
        "100 Biblical Girl Names and Meanings",
        "100 Nature Inspired Baby Names",
        "100 Celtic Baby Names for Boys",
        "100 Floral Baby Names for Girls",
        "100 Star and Celestial Baby Names",
        "100 Strong Baby Boy Names",
        "100 Elegant Baby Girl Names",
        "100 Nordic Baby Names with Meanings",
        "100 African Baby Names and Origins",
        "100 Fantasy Baby Names Inspired by Mythology",
        "100 Short One-Syllable Baby Names",
        "100 Modern Trending Baby Names 2026",
    ]
    log.info("Using %d hardcoded fallback keywords", len(keywords))
    return keywords


# =========================================================================
# AI ARTICLE GENERATION
# =========================================================================

def generate_article_with_retry(client, keyword):
    """Generate one article via Agnes AI with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            prompt = _build_prompt(keyword)
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=12000,
            )
            content = response.choices[0].message.content.strip()
            return _parse_article(content, keyword)

        except Exception as exc:
            log.error("Generation attempt %d failed: %s", attempt + 1, exc)
            if _is_quota_error(exc):
                global _quota_exhausted
                _quota_exhausted = True
                return None
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])

    log.error("All %d attempts failed for: %s", MAX_RETRIES, keyword)
    return None


def _is_quota_error(exc):
    """Detect rate-limit / quota exhaustion."""
    msg = str(exc).lower()
    return "429" in msg or "quota" in msg or "rate limit" in msg


def _build_prompt(keyword):
    """Build the AI generation prompt for a keyword."""
    return f"""Generate a comprehensive, SEO-optimized baby names article.

TOPIC: {keyword}

ARTICLE REQUIREMENTS:
- Word count: 3000-5000 words minimum
- Start with a unique, compelling introduction (150-250 words)
- Include exactly 6-8 H2 sections, each with 2-4 H3 subsections
- Include a Quick Facts table early in the article
- Add a Meaning section with etymology
- Add an Origin section with cultural context
- Add Pronunciation guide
- Add Popularity trends
- Add Nickname Ideas section
- Add Middle Name Suggestions
- Add Sibling Name Suggestions
- Add Similar Names section
- Include 8-12 unique FAQs in ### Q: / A: format
- Add 5-10 contextual internal links using [Anchor](/p/SLUG.html) format
- Include a Related Articles section
- End with a unique conclusion (100-150 words)

STRUCTURE:
# [Article Title with Number]

## Quick Answer / Summary
[Markdown table with key facts]

## Introduction
[Unique, compelling intro]

## [H2 Section 1]
### [H3 Subsection]
Content...

## [H2 Section 2]
...

## Meaning & Etymology
...

## Origin & Cultural Context
...

## Pronunciation Guide
...

## Popularity Trends
...

## Nickname Ideas
...

## Middle Name Suggestions
...

## Sibling Name Ideas
...

## Similar Names to Consider
...

## FAQ
### Q: [Question]?
[A: Answer...]

...

## Conclusion
[Unique closing]

INTERNAL LINKS: Use [Anchor Text](/p/SLUG.html) format.

SCHEMA: Include JSON-LD Article, FAQPage, and BreadcrumbList schemas.

EEAT SIGNALS: Include editorial review note, research sources, last updated date.

RULES:
- NEVER use generic AI phrases like "In today's world"
- NEVER repeat paragraph structures
- ALWAYS use unique examples and anecdotes
- Write in natural, engaging English
- Include specific data, statistics, and references
"""


_SYSTEM_PROMPT = """You are an expert baby naming consultant and SEO content writer.
Write comprehensive, authoritative articles demonstrating deep expertise (EEAT).
Follow the exact structure specified. Never use clichés or generic AI patterns.
Include specific cultural references, historical context, and expert opinions."""


# =========================================================================
# PARSE AI RESPONSE
# =========================================================================

def _parse_article(content, keyword):
    """Parse the AI response into a structured article dict."""
    content = strip_fences(content)

    # Extract title from H1
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if not title_match:
        log.warning("No H1 title found in generated content")
        return None

    title = title_match.group(1).strip()
    clean_title = enforce_title_rules(title)
    if not clean_title:
        log.warning("Title failed validation: %s", title)
        return None

    # Extract body (everything after title H1)
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            body = parts[2].strip()
    else:
        body = re.sub(r'^#\s+.+$\n+', '', body, flags=re.MULTILINE).strip()

    word_count = count_words(body)
    if word_count < MIN_WORD_COUNT:
        log.warning("Too short: %d words (min %d). Rejecting.", word_count, MIN_WORD_COUNT)
        return None

    # Generate labels
    labels = _generate_labels(keyword, clean_title)
    meta_desc = generate_meta_description(clean_title, keyword)
    today = datetime.now().strftime("%Y-%m-%d")
    frontmatter = build_frontmatter(clean_title, labels, today, keyword, meta_desc)
    full_content = f"{frontmatter}\n\n{body}\n"

    slug = slugify(clean_title)
    url = f"https://babynameideas2026.blogspot.com/p/{slug}.html"

    return {
        "title": clean_title,
        "slug": slug,
        "url": url,
        "body": body,
        "full_content": full_content,
        "labels": labels,
        "word_count": word_count,
        "keyword": keyword,
    }


# =========================================================================
# LABELS -- auto-generate with fallback buffer
# =========================================================================

def _generate_labels(keyword, title):
    """Auto-generate labels from keyword/title."""
    labels = ["Baby Names"]
    seen = {"baby names"}
    kw_lower = keyword.lower()
    title_lower = title.lower()

    origin_map = {
        "irish": "Irish Names", "japanese": "Japanese Names", "korean": "Korean Names",
        "french": "French Names", "italian": "Italian Names", "spanish": "Spanish Names",
        "german": "German Names", "arabic": "Arabic Names", "greek": "Greek Names",
        "celtic": "Celtic Names", "nordic": "Nordic Names", "russian": "Russian Names",
        "hebrew": "Hebrew Names", "latin": "Latin Names", "scandinavian": "Scandinavian Names",
        "african": "African Names", "indian": "Indian Names", "persian": "Persian Names",
        "chinese": "Chinese Names", "egyptian": "Egyptian Names", "mayan": "Mayan Names",
        "norse": "Norse Names", "hindu": "Hindu Names", "buddhist": "Buddhist Names",
        "sanskrit": "Sanskrit Names", "welsh": "Welsh Names", "scottish": "Scottish Names",
    }
    for term, lbl in origin_map.items():
        if term in kw_lower and lbl not in seen:
            labels.append(lbl)
            seen.add(lbl)
            if len(labels) >= MAX_LABELS:
                break

    style_map = {
        "mythology": "Mythology Names", "nature": "Nature Names", "flower": "Flower Names",
        "animal": "Animal Names", "meaning": "Names by Meaning", "twin": "Twin Names",
        "middle": "Middle Names", "sibling": "Sibling Names", "vintage": "Vintage Names",
        "modern": "Modern Names", "classic": "Classic Names", "rare": "Rare Names",
        "unique": "Unique Names", "biblical": "Biblical Names", "celestial": "Celestial Names",
        "zodiac": "Zodiac Names",
    }
    for term, lbl in style_map.items():
        if term in kw_lower and lbl not in seen:
            labels.append(lbl)
            seen.add(lbl)
            if len(labels) >= MAX_LABELS:
                break

    # -- Fallback buffer: guarantee >=4 unique labels --
    if len(labels) < 4:
        fallback = [
            "Naming Trends 2026",
            "Name Meanings",
            "Naming Tips",
        ]
        for fb in fallback:
            if fb.lower() not in seen:
                labels.append(fb)
                seen.add(fb.lower())
            if len(labels) >= 4:
                break

    return labels[:MAX_LABELS]


# =========================================================================
# MAIN -- generation-only pipeline
# =========================================================================

def main():
    log.info("=" * 60)
    log.info("CONTENT GENERATOR -- Generation Only (No Publishing)")
    log.info("=" * 60)
    log.info("Keywords from: %s", "BLOG_KEYWORDS env var" if os.environ.get("BLOG_KEYWORDS") else "hardcoded fallback")
    log.info("Model: %s", MODEL)

    api_key = os.environ.get("AGNES_API_KEY")
    if not api_key:
        log.error("AGNES_API_KEY not set.")
        sys.exit(1)

    POSTS_DIR.mkdir(parents=True, exist_ok=True)

    # -- Step 1: Load keywords --
    keywords = get_keywords()
    if not keywords:
        log.error("No keywords available. Exiting.")
        sys.exit(1)

    # -- Step 2: Generate articles --
    client = OpenAI(api_key=api_key, base_url=AGNES_BASE_URL)
    generated = 0
    failed = 0
    quota_stopped = False

    for keyword in keywords:
        if _quota_exhausted:
            log.warning("Quota exhausted. Stopping.")
            quota_stopped = True
            break

        log.info("[%d/%d] Generating for: %s", keywords.index(keyword) + 1, len(keywords), keyword)

        # Generate article
        article = generate_article_with_retry(client, keyword)
        if article is None:
            if _quota_exhausted:
                quota_stopped = True
                break
            failed += 1
            continue

        title = article["title"]
        slug = article["slug"]

        # Save markdown to disk
        date_prefix = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date_prefix}-{slug}.md"
        filepath = POSTS_DIR / filename
        counter = 1
        while filepath.exists():
            filename = f"{date_prefix}-{slug}-{counter}.md"
            filepath = POSTS_DIR / filename
            counter += 1
            if counter > 10:
                log.error("Filename collision for '%s'", slug)
                failed += 1
                continue

        filepath.write_text(article["full_content"], encoding="utf-8")
        log.info("Generated: %s (%d words, %d labels)", filename, article["word_count"], len(article["labels"]))
        generated += 1

    # -- Summary --
    log.info("=" * 60)
    log.info("GENERATION SUMMARY")
    log.info("==================")
    log.info("  Keywords processed:    %d", len(keywords))
    log.info("  Generated (saved):     %d", generated)
    log.info("  Failed:                %d", failed)
    log.info("==================")

    if generated >= 1:
        sys.exit(0)
    if quota_stopped:
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
