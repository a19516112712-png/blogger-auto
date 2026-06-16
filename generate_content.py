#!/usr/bin/env python3
"""
Blogger Content Generator

Uses the Gemini API (gemini-2.5-flash) to generate 5 SEO-optimized
baby-name articles per day. Articles are written as markdown files
into the posts/ directory, ready for automatic publishing.

Frontmatter is constructed programmatically — never trusted from the LLM.
A history database (generated_topics.json) prevents duplicate generation.
"""

import json
import logging
import os
import random
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml
from google import genai

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
HISTORY_FILE = Path(__file__).resolve().parent / "generated_topics.json"
MODEL = "gemini-2.5-flash"
ARTICLES_PER_RUN = 5

# Diverse baby-name topics to rotate through each day.
TOPICS = [
    "Vintage baby names making a comeback",
    "Nature-inspired baby names for modern parents",
    "Gender-neutral baby names on the rise",
    "Baby names inspired by mythology",
    "Short and sweet one-syllable baby names",
    "Royal and aristocratic baby names",
    "Bohemian baby names with artistic flair",
    "Strong baby boy names with deep meanings",
    "Beautiful baby girl names from around the world",
    "Celestial and space-inspired baby names",
    "Literary baby names from classic novels",
    "Trending baby names for the current year",
    "Biblical baby names with timeless appeal",
    "Ocean and water-inspired baby names",
    "Names with powerful meanings: courage, love, wisdom",
    "Unique baby names parents haven't overused yet",
    "Musical baby names for creative families",
    "Earthy and botanical baby names for girls and boys",
    "Baby names inspired by famous scientists and inventors",
    "International baby names that work in any language",
]

# Map topic keywords → additional labels for each article.
TOPIC_LABEL_MAP = {
    "vintage":       "Vintage Names",
    "nature":        "Nature Names",
    "gender-neutral": "Gender Neutral",
    "mythology":     "Mythology Names",
    "royal":         "Royal Names",
    "bohemian":      "Bohemian Names",
    "celestial":     "Celestial Names",
    "literary":      "Literary Names",
    "biblical":      "Biblical Names",
    "ocean":         "Ocean Names",
    "water":         "Nature Names",
    "musical":       "Musical Names",
    "earthy":        "Nature Names",
    "botanical":     "Nature Names",
    "scientists":    "STEM Names",
    "inventors":     "STEM Names",
    "international": "International Names",
    "powerful":      "Meaningful Names",
    "unique":        "Unique Names",
}


# ---------------------------------------------------------------------------
# Prompt template — NO frontmatter; we build that ourselves.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a professional SEO content writer specializing in baby names.
You write engaging, well-researched, and informative blog articles for expectant parents.

Return ONLY the article body in markdown. Do NOT include YAML frontmatter or fenced code blocks.

Structure:
- *First line* must be an H1 heading (# Title) — this becomes the post title
- Engaging introduction (2-3 paragraphs)
- Use H2 (##) for major sections and H3 (###) for subsections
- Include 4-5 H2 sections with substantive content
- At least one H2 section should be a list or comparison format
- End with an H2 FAQ section containing 4-5 questions with detailed answers
- Total length: 800-1200 words
- Use bullet points and numbered lists where appropriate
- Bold key terms and baby names for emphasis
- Write in a warm, helpful tone suitable for parents"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def slugify(title: str) -> str:
    """Convert a title to a safe filename slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:80]


def strip_fences(text: str) -> str:
    """Remove outermost ```markdown ... ``` fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rsplit("\n", 1)[0]
    return text.strip()


# ---------------------------------------------------------------------------
# History database — prevents duplicate generation
# ---------------------------------------------------------------------------
def load_history() -> list[dict]:
    """Load the generation history from generated_topics.json.

    Returns:
        List of dicts with keys: topic, title, slug, date.
        Returns empty list if the file does not exist or is corrupt.
    """
    if not HISTORY_FILE.exists():
        log.info("No history file found. Starting fresh.")
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            log.info("Loaded history: %d previous generation(s).", len(data))
            return data
        log.warning("History file is not a list; ignoring.")
        return []
    except (json.JSONDecodeError, Exception) as exc:
        log.warning("Could not parse history file: %s. Starting fresh.", exc)
        return []


def save_history_entry(topic: str, title: str, slug: str):
    """Append a new entry to generated_topics.json."""
    history = load_history()
    today = datetime.now().strftime("%Y-%m-%d")
    entry = {
        "topic": topic,
        "title": title,
        "slug": slug,
        "date": today,
    }
    history.append(entry)
    HISTORY_FILE.write_text(
        json.dumps(history, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    log.info("History updated: added '%s' → %d total entries.", topic, len(history))


def scan_existing_posts() -> dict:
    """Scan all markdown files in posts/ and extract titles, slugs, and topics.

    Reads the YAML frontmatter of every .md file.  Slugs are derived from
    filenames (stripping date prefix and .md extension).

    Returns:
        dict with keys 'titles', 'slugs' — each a set of lowercased strings.
    """
    titles = set()
    slugs = set()

    if not POSTS_DIR.exists():
        return {"titles": titles, "slugs": slugs}

    for md_file in POSTS_DIR.glob("*.md"):
        # Extract slug from filename: strip date prefix and .md
        name = md_file.stem
        # Remove date prefix like "2026-06-16-"
        slug_match = re.match(r"^\d{4}-\d{2}-\d{2}-(.+)", name)
        if slug_match:
            slugs.add(slug_match.group(1).lower())
        else:
            slugs.add(name.lower())

        # Extract title from frontmatter
        try:
            text = md_file.read_text(encoding="utf-8")
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    fm = yaml.safe_load(parts[1].strip())
                    if isinstance(fm, dict) and fm.get("title"):
                        titles.add(str(fm["title"]).strip().lower())
        except Exception:
            pass  # Corrupt file — skip

    log.info("Scanned existing posts: %d title(s), %d slug(s) found.",
             len(titles), len(slugs))
    return {"titles": titles, "slugs": slugs}


def build_blacklist() -> dict:
    """Combine history file + existing posts into a unified blacklist.

    Returns:
        dict with keys 'topics', 'titles', 'slugs' — each a set of lowercased strings.
    """
    history = load_history()
    existing = scan_existing_posts()

    blacklist_topics = set()
    blacklist_titles = set()
    blacklist_slugs = set()

    for entry in history:
        if entry.get("topic"):
            blacklist_topics.add(entry["topic"].strip().lower())
        if entry.get("title"):
            blacklist_titles.add(entry["title"].strip().lower())
        if entry.get("slug"):
            blacklist_slugs.add(entry["slug"].strip().lower())

    blacklist_titles |= existing["titles"]
    blacklist_slugs |= existing["slugs"]

    log.info("Blacklist built: %d topic(s), %d title(s), %d slug(s).",
             len(blacklist_topics), len(blacklist_titles), len(blacklist_slugs))
    return {
        "topics": blacklist_topics,
        "titles": blacklist_titles,
        "slugs": blacklist_slugs,
    }


# ---------------------------------------------------------------------------
# Frontmatter construction (programmatic — never trusts LLM output)
# ---------------------------------------------------------------------------
def extract_title(body: str, topic: str) -> str:
    """Extract the article title from the first H1 heading in the body."""
    match = re.search(r"^#\s+(.+?)$", body, re.MULTILINE)
    if match:
        return match.group(1).strip()
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("---") and not stripped.startswith("```"):
            return stripped[:150]
    return topic


def strip_existing_frontmatter(text: str) -> str:
    """Remove any YAML frontmatter block Gemini may have generated."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text


def generate_labels(topic: str) -> list[str]:
    """Derive topic-specific labels from the topic string."""
    labels = ["Baby Names", "SEO"]
    topic_lower = topic.lower()
    for keyword, label in TOPIC_LABEL_MAP.items():
        if keyword in topic_lower and label not in labels:
            labels.append(label)
    return labels


def build_frontmatter(title: str, labels: list[str], today: str) -> str:
    """Construct a valid YAML frontmatter block using yaml.dump for safe serialization."""
    data = {
        "title": title,
        "labels": labels,
        "date": today,
    }
    yaml_body = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return "---\n" + yaml_body + "---"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_saved_file(filepath: Path) -> bool:
    """Validate that a saved markdown file has correct frontmatter and body."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception as exc:
        log.error("Cannot read saved file %s: %s", filepath.name, exc)
        return False

    if not text.startswith("---"):
        log.error("Post-save validation FAILED: %s does not start with ---", filepath.name)
        return False

    parts = text.split("---", 2)
    if len(parts) < 3:
        log.error("Post-save validation FAILED: %s has malformed frontmatter delimiters", filepath.name)
        return False

    try:
        fm = yaml.safe_load(parts[1].strip())
    except yaml.YAMLError as exc:
        log.error("Post-save validation FAILED: %s YAML error — %s", filepath.name, exc)
        return False

    if not isinstance(fm, dict):
        log.error("Post-save validation FAILED: %s frontmatter is not a dict", filepath.name)
        return False

    for field in ("title", "date", "labels"):
        if field not in fm:
            log.error("Post-save validation FAILED: %s missing '%s' field", filepath.name, field)
            return False
        if fm[field] is None:
            log.error("Post-save validation FAILED: %s '%s' field is None", filepath.name, field)
            return False

    if not str(fm["title"]).strip():
        log.error("Post-save validation FAILED: %s has empty title", filepath.name)
        return False

    if not isinstance(fm["labels"], list) or len(fm["labels"]) == 0:
        log.error("Post-save validation FAILED: %s has empty/missing labels", filepath.name)
        return False

    body_text = parts[2].strip()
    if not body_text:
        log.error("Post-save validation FAILED: %s has empty body", filepath.name)
        return False

    return True


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def pick_topics(num: int, blacklist: dict) -> list[str]:
    """Pick `num` unique topics, skipping any that appear in the blacklist.

    Args:
        num: Number of topics to pick.
        blacklist: Dict with 'topics', 'titles', 'slugs' sets (from build_blacklist).

    Returns:
        List of topic strings.  May be shorter than `num` if not enough
        fresh topics remain.
    """
    available = []
    skipped = []

    for topic in TOPICS:
        if topic.strip().lower() in blacklist["topics"]:
            skipped.append(topic)
            continue
        available.append(topic)

    for dup in skipped:
        log.info("Duplicate detected: Skipping topic '%s' (already in history).", dup)

    random.shuffle(available)
    chosen = available[:num]

    if len(chosen) < num:
        log.warning(
            "Only %d fresh topic(s) available (wanted %d). %d of %d topics already used.",
            len(chosen), num, len(skipped), len(TOPICS),
        )

    return chosen


def generate_article(client: genai.Client, topic: str) -> str | None:
    """Generate a single SEO baby-name article for the given topic."""
    user_prompt = f"Write an SEO-optimized blog article about: {topic}"

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=user_prompt,
            config={
                "system_instruction": SYSTEM_PROMPT,
                "temperature": 0.9,
                "top_p": 0.95,
                "max_output_tokens": 4096,
            },
        )
    except Exception as exc:
        log.error("Gemini API error for topic '%s': %s", topic, exc)
        return None

    if not response.candidates or not response.text:
        log.error("Empty response from Gemini for topic '%s'", topic)
        return None

    return response.text


def save_and_validate(article_text: str, topic: str, blacklist: dict) -> Path | None:
    """Clean, extract metadata, build frontmatter, dedup-check, validate, and save.

    Adds an extra dedup check against the blacklist's titles and slugs
    before saving.  On success, appends to generated_topics.json.

    Returns:
        Path to the saved file, or None if validation or dedup fails.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # --- Step 1: clean the raw response ---
    cleaned = strip_fences(article_text)
    body = strip_existing_frontmatter(cleaned)

    # --- Step 2: extract title from H1 heading ---
    title = extract_title(body, topic)

    # --- Step 3: dedup check against history ---
    title_lower = title.strip().lower()
    if title_lower in blacklist["titles"]:
        log.info("Duplicate detected: Skipping topic '%s' (title '%s' already exists).", topic, title)
        return None

    slug = slugify(title)
    if slug.lower() in blacklist["slugs"]:
        log.info("Duplicate detected: Skipping topic '%s' (slug '%s' already exists).", topic, slug)
        return None

    # --- Step 4: generate labels from topic ---
    labels = generate_labels(topic)

    # --- Step 5: build frontmatter programmatically ---
    frontmatter = build_frontmatter(title, labels, today)

    # --- Step 6: validate ---
    if not body.strip():
        log.error("Validation FAILED for topic '%s': empty body.", topic)
        return None

    if title == topic:
        log.warning("Could not extract H1 title from response for '%s'; using topic as fallback.", topic)

    try:
        parsed = yaml.safe_load(frontmatter.split("---")[1].strip())
    except yaml.YAMLError as exc:
        log.error("Validation FAILED for topic '%s': frontmatter YAML error — %s", topic, exc)
        return None

    if not isinstance(parsed, dict) or "title" not in parsed:
        log.error("Validation FAILED for topic '%s': frontmatter missing 'title'.", topic)
        return None

    if not parsed["title"]:
        log.error("Validation FAILED for topic '%s': title is empty.", topic)
        return None

    # --- Step 7: assemble and save ---
    full_doc = f"{frontmatter}\n\n{body}\n"

    date_prefix = today
    filename = f"{date_prefix}-{slug}.md"
    filepath = POSTS_DIR / filename

    counter = 1
    while filepath.exists():
        filename = f"{date_prefix}-{slug}-{counter}.md"
        filepath = POSTS_DIR / filename
        counter += 1

    filepath.write_text(full_doc, encoding="utf-8")

    # --- Step 8: post-save validation ---
    if not validate_saved_file(filepath):
        log.error("Post-save validation FAILED for '%s'. Deleting corrupt file.", topic)
        try:
            filepath.unlink()
        except Exception:
            pass
        return None

    # --- Step 9: update history ---
    save_history_entry(topic, title, slug)

    log.info("Generated unique article: %s | title=%r | labels=%s | %d chars",
             filepath.name, title, labels, len(full_doc))
    return filepath


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    log.info("Starting content generation for Baby Names niche…")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY environment variable is not set.")
        sys.exit(1)

    POSTS_DIR.mkdir(parents=True, exist_ok=True)

    # Build the dedup blacklist from history + existing posts
    blacklist = build_blacklist()

    client = genai.Client(api_key=api_key)
    topics = pick_topics(ARTICLES_PER_RUN, blacklist)

    if not topics:
        log.error("No fresh topics available. All %d topics have been used.", len(TOPICS))
        sys.exit(0)

    log.info("Selected topics for today (post-dedup):")
    for i, t in enumerate(topics, 1):
        log.info("  %d. %s", i, t)

    generated = 0
    for topic in topics:
        log.info("Generating article for: %s", topic)
        article = generate_article(client, topic)

        if article is None:
            log.warning("Skipping topic '%s' due to generation failure.", topic)
            continue

        filepath = save_and_validate(article, topic, blacklist)
        if filepath:
            generated += 1
            # Update runtime blacklist so same-run duplicates are caught
            blacklist["titles"].add(filepath.stem.lower())
            blacklist["slugs"].add(
                re.sub(r"^\d{4}-\d{2}-\d{2}-", "", filepath.stem).lower()
            )
        else:
            log.error("Validation failed for topic '%s'; article discarded.", topic)

    log.info("Content generation complete. Generated %d/%d articles.",
             generated, len(topics))

    if generated == 0:
        log.error("No articles were generated. Exiting with failure.")
        sys.exit(1)


if __name__ == "__main__":
    main()
