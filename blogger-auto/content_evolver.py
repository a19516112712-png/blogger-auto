#!/usr/bin/env python3
"""
Content Evolution Engine — Automatic article improvement.

Every published article enters refresh_queue after configurable days.
When due, the engine:
  1. Expands article content
  2. Updates FAQ
  3. Updates statistics/years
  4. Improves title/CTR
  5. Improves schema
  6. Improves internal links
  7. Republishes update
  8. Maintains version history

Preserves original URL, slug, and publish date.
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from database.topic_queue import TopicQueue
from utils.helpers import compute_content_hash, get_client

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
POSTS_DIR = BASE_DIR / "posts"
VERSION_DIR = BASE_DIR / "versions"

AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
MODEL = os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
MAX_RETRIES = 2
RETRY_DELAYS = [5, 15]


# get_client is now in utils.helpers


def evolve_article(filepath: Path, actions: list[str], queue: TopicQueue,
                   published_id: int) -> bool:
    """Evolve a single article using Agnes AI.

    Preserves URL, slug, and publish date.
    Creates version backup.
    """
    try:
        original = filepath.read_text(encoding="utf-8")
    except Exception as exc:
        log.error("Cannot read %s: %s", filepath.name, exc)
        return False

    old_wc = len(original.split())
    old_hash = compute_content_hash(original)

    # Build evolution prompt
    action_desc = "\n".join(f"- {a}" for a in actions)
    new_year = datetime.now().strftime("%Y")

    prompt = f"""You are an expert SEO content improver. Evolve this baby name article.

EVOLUTION ACTIONS:
{action_desc}

CRITICAL RULES:
1. KEEP the exact same title, slug, and frontmatter structure.
2. KEEP the publish date unchanged.
3. KEEP all existing content — only ADD and EXPAND, never remove.
4. Update any year references to {new_year}.
5. Expand word count by 30-50% (target: {int(old_wc * 1.4)}+ words).
6. Add/update FAQ section with 8-12 Q&A pairs.
7. Add JSON-LD FAQ schema if missing.
8. Add 5-10 contextual internal links to related articles.
9. Improve title CTR if needed (keep number prefix).
10. Return the COMPLETE updated article including frontmatter.

ORIGINAL ARTICLE:
{original[:12000]}

Return the COMPLETE improved article."""

    client = get_client()
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert SEO content evolution specialist. Expand articles while preserving original structure, URLs, and metadata."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,
                max_tokens=8192,
            )
            improved = resp.choices[0].message.content.strip()
            new_wc = len(improved.split())

            if new_wc > old_wc * 1.2:  # At least 20% growth
                # Create version backup
                VERSION_DIR.mkdir(exist_ok=True)
                backup = VERSION_DIR / f"{filepath.stem}.v{datetime.now().strftime('%Y%m%d%H%M%S')}.md"
                backup.write_text(original, encoding="utf-8")

                # Write evolved content
                filepath.write_text(improved, encoding="utf-8")

                # Update DB
                queue.conn.execute(
                    """UPDATE refresh_queue SET status = 'done', actual_date = ?,
                       actions = ? WHERE id = ?""",
                    (datetime.now().isoformat(), ",".join(actions), published_id),
                )
                queue.conn.commit()

                log.info("EVOLVED: %s (%dw → %dw, +%dw) | backup: %s",
                         filepath.name, old_wc, new_wc, new_wc - old_wc, backup.name)
                return True
            else:
                log.warning("Evolve attempt %d: insufficient growth (%dw → %dw).",
                            attempt + 1, old_wc, new_wc)
        except Exception as exc:
            log.warning("Evolve attempt %d failed: %s", attempt + 1, exc)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])

    log.error("EVOLVE FAILED: %s", filepath.name)
    return False


def run_evolution_cycle(queue: TopicQueue, max_articles: int = 5) -> dict:
    """Run a full content evolution cycle.

    Returns stats dict.
    """
    due_articles = queue.get_refresh_due()
    if not due_articles:
        log.info("No articles due for evolution.")
        return {"due": 0, "evolved": 0, "failed": 0}

    log.info("Found %d articles due for evolution.", len(due_articles))

    results = {"due": len(due_articles), "evolved": 0, "failed": 0, "details": []}

    for article in due_articles[:max_articles]:
        slug = article["slug"]
        # Find the file
        filepath = None
        for f in sorted(POSTS_DIR.glob("*.md")):
            stem = f.stem
            slug_from_name = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)
            if slug_from_name == slug:
                filepath = f
                break

        if not filepath:
            log.warning("File not found for slug '%s'. Skipping.", slug)
            results["failed"] += 1
            continue

        actions = article.get("actions", ["expand_content", "update_faq", "improve_schema"])
        if evolve_article(filepath, actions, queue, article["id"]):
            results["evolved"] += 1
            results["details"].append({
                "title": article["title"],
                "slug": slug,
                "action": "evolved",
            })
        else:
            results["failed"] += 1
            results["details"].append({
                "title": article["title"],
                "slug": slug,
                "action": "failed",
            })

    return results
