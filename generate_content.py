#!/usr/bin/env python3
"""
Blogger Content Generator

Uses the Gemini API (gemini-2.5-flash) to generate 5 SEO-optimized
baby-name articles per day. Articles are written as markdown files
into the posts/ directory, ready for automatic publishing.

Frontmatter is constructed programmatically — never trusted from the LLM.
"""

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
# Frontmatter construction (programmatic — never trusts LLM output)
# ---------------------------------------------------------------------------
def extract_title(body: str, topic: str) -> str:
    """Extract the article title from the first H1 heading in the body.

    Falls back to the topic string if no H1 is found.
    """
    match = re.search(r"^#\s+(.+?)$", body, re.MULTILINE)
    if match:
        return match.group(1).strip()
    # Last resort: use first substantive line
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
    """Construct a valid YAML frontmatter block using yaml.dump for safe serialization.

    Handles titles with colons, apostrophes, ampersands, and other YAML
    special characters that would break simple f-string formatting.
    """
    data = {
        "title": title,
        "labels": labels,
        "date": today,
    }
    yaml_body = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return "---\n" + yaml_body + "---"


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def pick_topics(num: int) -> list[str]:
    """Pick `num` topics, avoiding repetition where possible."""
    available = list(TOPICS)
    random.shuffle(available)
    chosen = available[:num]
    while len(chosen) < num:
        chosen.append(random.choice(TOPICS))
    return chosen


def generate_article(client: genai.Client, topic: str) -> str | None:
    """Generate a single SEO baby-name article for the given topic.

    Args:
        client: Initialized Gemini API client.
        topic: The baby-name topic to write about.

    Returns:
        Raw markdown string on success, or None on failure.
    """
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




def validate_saved_file(filepath: Path) -> bool:
    """Validate that a saved markdown file has correct frontmatter and body.

    Checks:
        - File starts with ---
        - YAML is parseable
        - title, date, labels all present and non-empty
        - Body exists after frontmatter
    """
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
def save_and_validate(article_text: str, topic: str) -> Path | None:
    """Clean, extract metadata, build frontmatter, validate, and save.

    Frontmatter is always built programmatically — never trusted from Gemini.
    Validation checks: title exists, body non-empty, YAML is valid.

    Returns:
        Path to the saved file, or None if validation fails.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # --- Step 1: clean the raw response ---
    cleaned = strip_fences(article_text)
    body = strip_existing_frontmatter(cleaned)

    # --- Step 2: extract title from H1 heading ---
    title = extract_title(body, topic)

    # --- Step 3: generate labels from topic ---
    labels = generate_labels(topic)

    # --- Step 4: build frontmatter programmatically ---
    frontmatter = build_frontmatter(title, labels, today)

    # --- Step 5: validate ---
    if not body.strip():
        log.error("Validation FAILED for topic '%s': empty body.", topic)
        return None

    if title == topic:
        log.warning("Could not extract H1 title from response for '%s'; using topic as fallback.", topic)

    # Verify frontmatter is parseable YAML with required fields
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

    # --- Step 6: assemble and save ---
    full_doc = f"{frontmatter}\n\n{body}\n"

    slug = slugify(title)
    date_prefix = today
    filename = f"{date_prefix}-{slug}.md"
    filepath = POSTS_DIR / filename

    # Avoid overwriting existing files
    counter = 1
    while filepath.exists():
        filename = f"{date_prefix}-{slug}-{counter}.md"
        filepath = POSTS_DIR / filename
        counter += 1

    filepath.write_text(full_doc, encoding="utf-8")

    # --- Post-save validation: read back and verify ---
    if not validate_saved_file(filepath):
        log.error("Post-save validation FAILED for '%s'. Deleting corrupt file.", topic)
        try:
            filepath.unlink()
        except Exception:
            pass
        return None

    log.info("Saved + validated: %s | title=%r | labels=%s | %d chars",
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

    client = genai.Client(api_key=api_key)
    topics = pick_topics(ARTICLES_PER_RUN)

    log.info("Selected topics for today:")
    for i, t in enumerate(topics, 1):
        log.info("  %d. %s", i, t)

    generated = 0
    for topic in topics:
        log.info("Generating article for: %s", topic)
        article = generate_article(client, topic)

        if article is None:
            log.warning("Skipping topic '%s' due to generation failure.", topic)
            continue

        filepath = save_and_validate(article, topic)
        if filepath:
            generated += 1
        else:
            log.error("Validation failed for topic '%s'; article discarded.", topic)

    log.info("Content generation complete. Generated %d/%d articles.",
             generated, ARTICLES_PER_RUN)

    if generated == 0:
        log.error("No articles were generated. Exiting with failure.")
        sys.exit(1)


if __name__ == "__main__":
    main()
