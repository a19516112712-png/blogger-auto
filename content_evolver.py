#!/usr/bin/env python3
"""
Content Evolver — Automatic Article Improvement Engine
========================================================
Takes improvement candidates from growth_detector and expands them
using Agnes AI. Optimizes for:
  - Word count (target 2500+)
  - FAQ sections (5-8 questions with schema)
  - Markdown tables (name-meaning-origin columns)
  - Heading hierarchy (6+ H2, 4+ H3)
  - Internal links (3-10 related articles)
  - Content freshness (update timestamps)
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from openai import OpenAI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("content_evolver")

BASE_DIR = Path(__file__).resolve().parent
POSTS_DIR = BASE_DIR / "posts"
HISTORY_FILE = BASE_DIR / "generated_topics.json"
IMPROVEMENT_LOG = BASE_DIR / "improvement_log.json"

AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
MODEL = os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
MAX_RETRIES = 2
RETRY_DELAYS = [5, 15]


def get_client():
    api_key = os.environ.get("AGNES_API_KEY")
    if not api_key:
        raise EnvironmentError("AGNES_API_KEY not set")
    return OpenAI(api_key=api_key, base_url=AGNES_BASE_URL)


def load_improvement_log() -> set:
    """Load previously improved slugs to avoid re-improving."""
    if not IMPROVEMENT_LOG.exists():
        return set()
    try:
        data = json.loads(IMPROVEMENT_LOG.read_text())
        return {item.get("slug", "") for item in data.get("improved", [])}
    except Exception:
        return set()


def save_improvement(slug: str, old_wc: int, new_wc: int, actions: list):
    """Record an improvement in the log."""
    log_data = {"improved": []}
    if IMPROVEMENT_LOG.exists():
        try:
            log_data = json.loads(IMPROVEMENT_LOG.read_text())
        except Exception:
            pass
    log_data.setdefault("improved", []).append({
        "slug": slug,
        "old_word_count": old_wc,
        "new_word_count": new_wc,
        "actions": actions,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    IMPROVEMENT_LOG.write_text(json.dumps(log_data, indent=2))


def expand_article(filepath: Path, actions: list) -> Optional[str]:
    """Expand an article using Agnes AI. Returns the new content or None."""
    original = filepath.read_text(encoding="utf-8")
    old_wc = len(original.split())

    # Build improvement prompt based on detected actions
    action_descriptions = []
    for a in actions:
        action_descriptions.append(f"- {a['action']}: {a['target']} (priority: {a['priority']})")

    prompt = f"""
You are an expert SEO content improver. Improve the following baby name article.

IMPROVEMENT ACTIONS NEEDED:
{chr(10).join(action_descriptions)}

RULES:
1. Keep the original title, slug, and frontmatter structure.
2. Keep ALL existing content — only ADD new sections, never remove.
3. Expand word count to 2500+ words.
4. Add a Frequently Asked Questions section with 5-8 Q&A pairs if missing.
5. Add a markdown table (Name | Meaning | Origin | Gender) if missing.
6. Ensure at least 6 H2 sections and 4 H3 sub-sections.
7. Add 3-10 internal links to related baby name articles on the site.
8. Update the date in frontmatter to today: {datetime.now().strftime('%Y-%m-%d')}
9. Keep labels unchanged from original.
10. Return the COMPLETE updated article including frontmatter.

ORIGINAL ARTICLE:
{original[:8000]}

Return the COMPLETE improved article (frontmatter + all content).
"""
    client = get_client()
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert SEO content improver. You expand articles while preserving original content. Return complete markdown."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,
                max_tokens=8000,
            )
            improved = resp.choices[0].message.content.strip()
            # Validate the improved content
            new_wc = len(improved.split())
            if new_wc > old_wc + 200:
                # Backup original
                backup_path = filepath.with_suffix(".md.bak")
                filepath.rename(backup_path)
                # Write improved
                filepath.write_text(improved, encoding="utf-8")
                save_improvement(filepath.stem, old_wc, new_wc, actions)
                log.info(
                    "EVOLVED: %s (%dw → %dw +%dw)",
                    filepath.name, old_wc, new_wc, new_wc - old_wc,
                )
                return improved
            else:
                log.warning(
                    "Evolve attempt %d: insufficient growth (%dw → %dw). Retrying...",
                    attempt + 1, old_wc, new_wc,
                )
        except Exception as exc:
            log.warning("Evolve attempt %d failed: %s", attempt + 1, exc)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])

    log.error("EVOLVE FAILED: %s (could not expand from %dw)", filepath.name, old_wc)
    return None


def evolve_candidates(candidates: list, max_improvements: int = 5) -> dict:
    """Evolve up to `max_improvements` candidates. Skips already improved."""
    already_improved = load_improvement_log()
    results = {"improved": 0, "skipped": 0, "failed": 0, "details": []}

    for c in candidates[:max_improvements]:
        if c.slug in already_improved:
            log.info("SKIP (already improved): %s", c.title[:50])
            results["skipped"] += 1
            continue

        filepath = POSTS_DIR / c.filename
        if not filepath.exists():
            log.warning("SKIP (file not found): %s", c.filename)
            results["skipped"] += 1
            continue

        log.info("EVOLVING: %s (score=%d, %dw)", c.title[:50], c.urgency_score, c.word_count)
        new_content = expand_article(filepath, c.actions)
        if new_content:
            results["improved"] += 1
            results["details"].append({
                "title": c.title,
                "slug": c.slug,
                "old_wc": c.word_count,
                "new_wc": len(new_content.split()),
            })
        else:
            results["failed"] += 1

    return results


if __name__ == "__main__":
    from growth_detector import scan_all_posts, classify_candidates

    print("=" * 60)
    print("CONTENT EVOLVER — Autonomous Article Improvement")
    print("=" * 60)

    candidates = scan_all_posts(POSTS_DIR)
    buckets = classify_candidates(candidates)

    high_growth = buckets["high_growth"][:5]
    print(f"\nTop {len(high_growth)} improvement targets:")
    for i, c in enumerate(high_growth, 1):
        print(f"  {i}. [{c.urgency_score}] {c.title[:55]} ({c.word_count}w)")

    print(f"\nRunning evolution on top candidates...\n")
    results = evolve_candidates(high_growth, max_improvements=3)

    print(f"\nRESULTS: improved={results['improved']} skipped={results['skipped']} failed={results['failed']}")
    for d in results["details"]:
        print(f"  ✅ {d['title'][:50]}: {d['old_wc']}w → {d['new_wc']}w (+{d['new_wc']-d['old_wc']}w)")
