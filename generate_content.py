#!/usr/bin/env python3
"""
Blogger Content Generator — Production Grade (Refactored)

Uses Agnes AI (OpenAI-compatible) to generate SEO-optimized
baby-name articles. Articles are saved as markdown into posts/.

Changes from v1:
  - REMOVED hardcoded TOPICS array — topics come from SQLite
  - TOPIC_QUEUE: SQLite-backed topic lifecycle (pending→generating→generated→published)
  - JSON-LD structured data (Article, FAQ, Breadcrumb schemas) auto-injected
  - Dual dedup: SQLite + file-scan + content hash
  - Imports shared helpers from utils/ (no duplicate functions)
  - Keyword discovery fallback when built-in pool is exhausted
"""

import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from openai import OpenAI

# ── Shared helpers (no duplicates) ──────────────────────────────────────
from utils.helpers import (
    slugify, sanitize_labels, sanitize_title, extract_title_from_text,
    build_frontmatter, strip_existing_frontmatter, strip_fences,
    count_words, generate_meta_description, enforce_title_rules,
    BANNED_PHRASES, MIN_TITLE_LENGTH, MIN_BODY_WORDS,
    MIN_LABELS, MAX_LABELS, FORBIDDEN_LABELS, compute_content_hash,
)
from utils.yaml_parser import parse_frontmatter, extract_date_from_filename, has_valid_frontmatter

# ── Database ────────────────────────────────────────────────────────────
from database.topic_queue import TopicQueue
from database.schema import DB_PATH

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
FALLBACK_MODEL = "agnes-1.5-flash"
MODEL = os.environ.get("AGNES_MODEL", DEFAULT_MODEL)
DEFAULT_ARTICLES_PER_RUN = 5
ARTICLES_PER_RUN = int(os.environ.get("ARTICLES_PER_RUN", DEFAULT_ARTICLES_PER_RUN))
AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"

MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 30]
RETRYABLE_CODES = (429, 500, 503)

_quota_exhausted = False


# ---------------------------------------------------------------------------
# JSON-LD Structured Data Generator
# ---------------------------------------------------------------------------

def generate_json_ld(title: str, slug: str, body: str, topic: str,
                     labels: list[str]) -> str:
    """Generate JSON-LD structured data blocks for an article.

    Produces Article, FAQPage, and BreadcrumbList schemas.
    """
    base_url = "https://babynameideas2026.blogspot.com"
    url = f"{base_url}/p/{slug}.html"
    today = datetime.now().strftime("%Y-%m-%d")
    breadcrumb_items = [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": base_url},
        {"@type": "ListItem", "position": 2, "name": "Baby Names", "item": f"{base_url}/search/label/Baby%20Names"},
        {"@type": "ListItem", "position": 3, "name": title, "item": url},
    ]

    # Extract FAQ from body if present
    faq_items = []
    faq_pattern = r"###\s+Q:\s*(.+?)\n(.*?)(?=###\s+Q:|$)"
    for match in re.finditer(faq_pattern, body, re.DOTALL):
        question = match.group(1).strip()
        answer = re.sub(r"\n+", " ", match.group(2).strip())
        if len(question) > 5 and len(answer) > 20:
            faq_items.append({"@type": "Question", "name": question,
                              "acceptedAnswer": {"@type": "Answer", "text": answer}})

    # Limit to 10 FAQs for schema validity
    faq_items = faq_items[:10]

    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "@id": url + "#article",
                "headline": title,
                "name": title,
                "description": generate_meta_description(title, topic),
                "image": "",
                "datePublished": today,
                "dateModified": today,
                "author": {"@type": "Organization", "name": "Baby Name Ideas"},
                "publisher": {
                    "@type": "Organization",
                    "name": "Baby Name Ideas",
                    "logo": {"@type": "ImageObject", "url": f"{base_url}/images/logo.png"},
                },
                "mainEntityOfPage": {"@type": "WebPage", "@id": url},
                "keyword": topic,
                "articleSection": labels[0] if labels else "Baby Names",
                "wordCount": count_words(body),
                "thumbnailUrl": "",
            },
            {
                "@type": "BreadcrumbList",
                "@id": url + "#breadcrumb",
                "itemListElement": breadcrumb_items,
            },
        ],
    }

    if faq_items:
        ld["@graph"].append({
            "@type": "FAQPage",
            "@id": url + "#faq",
            "mainEntity": faq_items,
        })

    return json.dumps(ld, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Topic Queue Integration
# ---------------------------------------------------------------------------

def pick_topics_from_queue(queue: TopicQueue, num: int,
                           blacklist: dict) -> list[dict]:
    """Pick `num` pending topics from SQLite, filtered by blacklist.

    Uses ORDER BY RANDOM() via SQLite for true randomness.
    """
    db_topics = queue.get_pending_topics(limit=num * 3)
    
    available = []
    skipped = []
    for t in db_topics:
        kw_lower = t["keyword"].strip().lower()
        if kw_lower in blacklist["topics"]:
            skipped.append(t["keyword"])
            continue
        if kw_lower in blacklist["slugs"]:
            skipped.append(t["keyword"])
            continue
        available.append(t)

    # Shuffle and sample
    random.shuffle(available)
    chosen = available[:num] if len(available) >= num else available

    for dup in skipped:
        log.info("Duplicate detected: Skipping topic '%s' (already in blacklist).", dup)

    log.info("picked %d fresh topics from %d pending (blacklisted: %d)",
             len(chosen), len(available) + len(skipped), len(skipped))
    return chosen


def discover_and_insert_new_keywords(queue: TopicQueue, count: int,
                                     blacklist: dict) -> list[int]:
    """Fallback: discover new keywords via combinatorial engine.

    Returns list of keyword IDs inserted into the database.
    """
    try:
        from keyword_discovery import discover_keywords
    except ImportError:
        log.error("keyword_discovery.py not found.")
        return []

    history = set()
    for t in blacklist.get("topics", set()):
        history.add(t.lower().strip())

    keywords = discover_keywords(queue, count=count * 3, history_blacklist=history)
    inserted_ids = []
    for kw_tuple in keywords:
        keyword = kw_tuple[0]
        kw_lower = keyword.lower().strip()
        if kw_lower in history:
            continue
        row_id = queue.conn.execute(
            "SELECT id FROM keywords WHERE keyword = ?", (kw_lower,)
        ).fetchone()
        if row_id:
            inserted_ids.append(row_id[0])
        else:
            # Will be inserted via bulk_insert
            pass

    if inserted_ids:
        log.info("Found %d existing keywords in DB.", len(inserted_ids))
        return inserted_ids

    # Bulk insert new keywords
    inserted = queue.bulk_insert_keywords(keywords)
    log.info("Inserted %d new keywords via combinatorial discovery.", inserted)
    return queue.get_pending_topics(limit=inserted)


# ---------------------------------------------------------------------------
# Article generation with retry & quota protection
# ---------------------------------------------------------------------------

def is_quota_exhausted() -> bool:
    return _quota_exhausted


def set_quota_exhausted():
    global _quota_exhausted
    _quota_exhausted = True


def generate_article_with_retry(client: OpenAI, topic: dict) -> str | None:
    """Generate an article with retry logic for transient failures."""
    global _quota_exhausted
    keyword = topic["keyword"]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            active_model = MODEL
            try:
                response = client.chat.completions.create(
                    model=active_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Write an SEO-optimized blog article about: {keyword}"},
                    ],
                    temperature=0.9,
                    top_p=0.95,
                    max_tokens=8192,
                )
            except Exception as model_exc:
                exc_str = str(model_exc).lower()
                if "model_not_found" in exc_str and active_model != FALLBACK_MODEL:
                    log.warning("Model '%s' not found, falling back to '%s'.", active_model, FALLBACK_MODEL)
                    active_model = FALLBACK_MODEL
                    response = client.chat.completions.create(
                        model=active_model,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": f"Write an SEO-optimized blog article about: {keyword}"},
                        ],
                        temperature=0.9,
                        top_p=0.95,
                        max_tokens=8192,
                    )
                else:
                    raise

            if response.choices and response.choices[0].message.content:
                return response.choices[0].message.content
            log.warning("Attempt %d: empty response for '%s'.", attempt, keyword)
        except Exception as exc:
            exc_str = str(exc).lower()
            status_code = getattr(exc, "status_code", None)

            if status_code == 429 or "429" in exc_str or "rate_limit" in exc_str or "resource_exhausted" in exc_str:
                log.warning("[WARNING] Agnes AI rate limit exceeded (429).")
                if not _quota_exhausted:
                    set_quota_exhausted()
                return None

            if status_code in RETRYABLE_CODES or any(str(c) in exc_str for c in RETRYABLE_CODES) or "timeout" in exc_str:
                if attempt < MAX_RETRIES:
                    delay = RETRY_DELAYS[attempt - 1]
                    log.warning("Attempt %d/%d failed (%s). Retrying in %ds…", attempt, MAX_RETRIES, type(exc).__name__, delay)
                    time.sleep(delay)
                    continue
            log.error("Agnes AI API error for '%s' (attempt %d): %s", keyword, attempt, exc)
            return None

    log.error("All %d retries exhausted for topic '%s'.", MAX_RETRIES, keyword)
    return None


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a professional Programmatic SEO content writer specializing in baby names.

Your job is to write high-quality, SEO-optimized articles that rank on Google and provide real value to parents searching for baby names.

=== TITLE RULES ===
The first line of your response MUST be an H1 heading (# ) with the EXACT format:
# 100 {Topic Keyword Phrase}
- ALWAYS start with a number (100, 150, 200, 250)
- Maximum 65 characters total
- NEVER use banned phrases

=== ARTICLE STRUCTURE ===
1. # Title (H1 — number-prefixed, SEO-optimized)
2. Engaging introduction (2-3 paragraphs, naturally include the primary keyword)
3. ## Quick Answer (2-3 sentence summary)
4. ## Table of Contents (ordered list)
5. ## 100 {Topic} Names and Meanings — LARGE TABLE with: # | Name | Meaning | Origin | Pronunciation | Gender
6. ## Meaning and Origin — Cultural background section (200+ words)
7. ## Pronunciation Guide — Key names with phonetic spelling
8. ## Popularity and Trends — Current rankings and trend data
9. ## Variants and Nicknames — Alternative spellings and cute nicknames
10. ## Famous People and Characters — Named after celebrities, fictional characters
11. ## Name Combinations — Middle name pairings, sibling name sets, twin names
12. ## FAQ — 8-12 Q&A pairs (format: ### Q: Question? \\n Answer)
13. ## Conclusion
14. ## Related Articles — 5-10 internal links in markdown format

=== CONTENT RULES ===
- Total article length: 2500-4000 words minimum
- The name table is the core — at least 100 names with all 6 columns
- Every name needs: meaning, origin, pronunciation, gender
- Use real, verified name data — do not fabricate meanings
- Write unique, original content — no generic AI filler
- Include cultural context and naming traditions
- Bold key terms and baby names for emphasis
- Natural English only — no repetitive phrases like "delve into", "treasure trove", "rich tapestry"

=== INTERNAL LINKING ===
At the end, add "Related Articles" with 5-10 contextual internal links:
- [100 Irish Baby Names for Boys and Girls](/100-irish-baby-names)
Pick links thematically related to the current topic.

Return ONLY the article body in markdown. No YAML frontmatter, no code fences, no commentary."""


# ---------------------------------------------------------------------------
# Save pipeline with production validation + JSON-LD
# ---------------------------------------------------------------------------

def save_and_validate(article_text: str, topic: dict, blacklist: dict,
                      queue: TopicQueue) -> Path | None:
    """Clean, extract, validate, add JSON-LD, and save an article."""
    today = datetime.now().strftime("%Y-%m-%d")
    keyword = topic["keyword"]
    keyword_id = topic.get("id")

    # 1. Clean raw response
    cleaned = strip_fences(article_text)
    body = strip_existing_frontmatter(cleaned)

    # 2. Extract and enforce SEO title rules
    raw_title = extract_title_from_text(body, keyword)
    title = enforce_title_rules(raw_title)
    if title is None:
        log.error("[ERROR] Title failed SEO rules for '%s': %s", keyword, raw_title)
        if keyword_id:
            queue.mark_failed(keyword_id, title, None, "Title failed SEO rules")
        return None

    # 3. Dedup checks (SQLite + blacklist)
    title_lower = title.strip().lower()
    if title_lower in blacklist["titles"]:
        log.info("[INFO] Duplicate title: '%s'. Skipping.", title)
        return None
    slug = slugify(title)
    if slug.lower() in blacklist["slugs"]:
        log.info("[INFO] Duplicate slug: '%s'. Skipping.", slug)
        return None
    if queue.is_duplicate_slug(slug):
        log.info("[INFO] Duplicate slug in DB: '%s'. Skipping.", slug)
        return None
    if queue.is_duplicate_title(title):
        log.info("[INFO] Duplicate title in DB: '%s'. Skipping.", title)
        return None

    # 4. Generate labels
    labels = generate_labels_from_keyword(keyword)

    # 5. Build frontmatter
    frontmatter = build_frontmatter(title, labels, today, keyword)

    # 6. Word count check
    word_count = count_words(body)
    if word_count < MIN_BODY_WORDS:
        log.warning("[WARN] Low word count %d for '%s' (min %d).", word_count, keyword, MIN_BODY_WORDS)

    # 7. Compute content hash
    full_content = frontmatter + "\n\n" + body
    content_hash = compute_content_hash(full_content)

    # 8. Generate JSON-LD structured data
    json_ld = generate_json_ld(title, slug, body, keyword, labels)

    # 9. Assemble final document
    full_doc = f"{frontmatter}\n\n{body}\n\n<!-- JSON-LD Structured Data -->\n<script type=\"application/ld+json\">\n{json_ld}\n</script>\n"

    # 10. Save
    filename = f"{today}-{slug}.md"
    filepath = POSTS_DIR / filename
    counter = 1
    while filepath.exists():
        filename = f"{today}-{slug}-{counter}.md"
        filepath = POSTS_DIR / filename
        counter += 1
    filepath.write_text(full_doc, encoding="utf-8")

    # 11. Post-save validation
    if not has_valid_frontmatter(filepath):
        log.error("[ERROR] Post-save validation FAILED for '%s'. Deleting.", keyword)
        try:
            filepath.unlink()
        except Exception:
            pass
        if keyword_id:
            queue.mark_failed(keyword_id, title, slug, "Post-save validation failed")
        return None

    # 12. Update history in DB
    if keyword_id:
        queue.mark_generated(keyword_id, title, slug, word_count,
                            min(100, word_count / 40), str(filepath))

    # Update in-memory blacklist
    blacklist["titles"].add(title_lower)
    blacklist["slugs"].add(slug.lower())

    log.info("Generated unique article: %s | labels=%d | %d words | JSON-LD: ✓",
             filepath.name, len(labels), word_count)
    return filepath


def generate_labels_from_keyword(keyword: str) -> list[str]:
    """Derive topic-specific labels from keyword."""
    kw_lower = keyword.lower()
    seen = {"Baby Names"}
    labels = ["Baby Names"]

    # Origin labels
    origin_map = {
        "irish": "Irish Names", "japanese": "Japanese Names", "korean": "Korean Names",
        "french": "French Names", "italian": "Italian Names", "spanish": "Spanish Names",
        "german": "German Names", "arabic": "Arabic Names", "greek": "Greek Names",
        "norse": "Norse Names", "celtic": "Celtic Names", "nordic": "Nordic Names",
        "hebrew": "Hebrew Names", "scandinavian": "Scandinavian Names",
    }
    for term, lbl in origin_map.items():
        if term in kw_lower and lbl not in seen:
            labels.append(lbl)
            seen.add(lbl)
            if len(labels) >= MAX_LABELS:
                break

    # Style labels
    style_map = {
        "unique": "Unique Names", "rare": "Rare Names", "vintage": "Vintage Names",
        "modern": "Modern Names", "classic": "Classic Names", "popular": "Popular Names",
        "gender": "Gender Neutral Names", "unisex": "Unisex Names",
        "biblical": "Biblical Names", "mythology": "Mythology Names",
        "nature": "Nature Names", "flower": "Flower Names", "animal": "Animal Names",
        "meaning": "Names by Meaning", "twin": "Twin Names",
        "middle": "Middle Names", "sibling": "Sibling Names",
    }
    for term, lbl in style_map.items():
        if term in kw_lower and lbl not in seen:
            labels.append(lbl)
            seen.add(lbl)
            if len(labels) >= MAX_LABELS:
                break

    return labels[:MAX_LABELS]


# ---------------------------------------------------------------------------
# Blacklist from existing posts (file-scan)
# ---------------------------------------------------------------------------

def build_blacklist() -> dict:
    """Combine DB state + existing posts into a unified blacklist."""
    titles, slugs = set(), set()
    if POSTS_DIR.exists():
        for md_file in POSTS_DIR.glob("*.md"):
            name = md_file.stem
            slug_match = re.match(r"^\d{4}-\d{2}-\d{2}-(.+)", name)
            slugs.add((slug_match.group(1) if slug_match else name).lower())
            try:
                text = md_file.read_text(encoding="utf-8")
                if text.startswith("---"):
                    parts = text.split("---", 2)
                    if len(parts) >= 3:
                        fm = yaml.safe_load(parts[1].strip())
                        if isinstance(fm, dict) and fm.get("title"):
                            titles.add(str(fm["title"]).strip().lower())
            except Exception:
                pass
    log.info("Blacklist built: %d titles, %d slugs from files.", len(titles), len(slugs))
    return {"topics": set(), "titles": titles, "slugs": slugs}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info("=" * 50)
    log.info("Starting content generation (SQLite-backed)…")
    log.info("Requested articles: %d | Model: %s", ARTICLES_PER_RUN, MODEL)

    api_key = os.environ.get("AGNES_API_KEY")
    if not api_key:
        log.error("AGNES_API_KEY environment variable is not set.")
        sys.exit(1)

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    blacklist = build_blacklist()

    # Initialize database
    queue = TopicQueue()
    log.info("Database: %s", DB_PATH)

    # Get topics from SQLite queue
    topics = pick_topics_from_queue(queue, ARTICLES_PER_RUN, blacklist)

    if not topics:
        log.warning("No pending topics in database. Attempting keyword discovery…")
        topic_ids = discover_and_insert_new_keywords(queue, ARTICLES_PER_RUN, blacklist)
        if topic_ids:
            topics = [{"id": tid, "keyword": ""} for tid in topic_ids]
            # Reload keywords
            for t in topics:
                row = queue.conn.execute(
                    "SELECT keyword FROM keywords WHERE id = ?", (t["id"],)
                ).fetchone()
                if row:
                    t["keyword"] = row[0]

    if not topics:
        log.warning("No topics available. Exiting gracefully.")
        queue.close()
        sys.exit(0)

    log.info("Selected topics for today:")
    for i, t in enumerate(topics, 1):
        log.info("  %d. [%s] %s", i, t.get("cluster", "?"), t["keyword"])

    # Mark as generating
    topic_ids = [t["id"] for t in topics if t.get("id")]
    queue.mark_generating(topic_ids)

    # Generate articles
    client = OpenAI(api_key=api_key, base_url=AGNES_BASE_URL)
    generated = 0
    rejected = 0
    quota_failures = 0
    validation_failures = 0

    for topic in topics:
        if is_quota_exhausted():
            log.warning("[WARNING] Rate limit reached. Stopping.")
            break

        log.info("Generating article for: %s", topic["keyword"])
        article = generate_article_with_retry(client, topic)

        if article is None:
            if is_quota_exhausted():
                quota_failures += 1
                break
            rejected += 1
            if topic.get("id"):
                queue.mark_failed(topic["id"], None, None, "Generation failed")
            continue

        filepath = save_and_validate(article, topic, blacklist, queue)
        if filepath:
            generated += 1
        else:
            validation_failures += 1

    # Summary
    stats = queue.stats()
    log.info("=" * 50)
    log.info("GENERATION SUMMARY")
    log.info("==================")
    log.info("  Generated:           %d", generated)
    log.info("  Rejected:            %d", rejected)
    log.info("  Quota failures:      %d", quota_failures)
    log.info("  Validation failures: %d", validation_failures)
    log.info("  DB stats: %s", json.dumps(stats))
    log.info("==================")

    queue.close()

    if generated >= 1:
        sys.exit(0)
    if is_quota_exhausted():
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
