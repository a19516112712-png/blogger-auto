#!/usr/bin/env python3
"""
Blogger Content Generator

Uses the Gemini API (gemini-2.5-flash) to generate 5 SEO-optimized
baby-name articles per day. Articles are written as markdown files
into the posts/ directory, ready for automatic publishing.
"""

import logging
import os
import random
import re
import sys
from datetime import datetime
from pathlib import Path

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


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a professional SEO content writer specializing in baby names.
You write engaging, well-researched, and informative blog articles for expectant parents.

Return ONLY valid markdown with YAML frontmatter. No extra commentary.

Frontmatter must include:
- title: An engaging, SEO-friendly headline (50-65 chars)
- labels: comma-separated labels (always include "Baby Names,SEO" plus topic-specific labels)
- meta_description: Compelling meta description (140-155 chars) with primary keyword

Article structure:
- Start with an engaging introduction (2-3 paragraphs)
- Use H2 (##) for major sections and H3 (###) for subsections
- Include 4-5 H2 sections with substantive content
- At least one H2 section should be a list or comparison format
- End with an H2 FAQ section containing 4-5 questions with detailed answers
- Total article length: 800-1200 words
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
        # Remove opening fence line
        text = text.split("\n", 1)[1] if "\n" in text else text
        # Remove closing fence
        if text.rstrip().endswith("```"):
            text = text.rsplit("\n", 1)[0]
    return text.strip()


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def pick_topics(num: int) -> list[str]:
    """Pick `num` topics, avoiding repetition where possible."""
    available = list(TOPICS)
    random.shuffle(available)
    chosen = available[:num]
    # If fewer topics than requested (shouldn't happen), repeat some
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


def save_and_validate(article_text: str, topic: str) -> Path | None:
    """Clean, validate, and save a generated article to posts/.

    Args:
        article_text: Raw article markdown from Gemini.
        topic: The topic string (used if title extraction fails).

    Returns:
        Path to the saved file, or None on failure.
    """
    cleaned = strip_fences(article_text)

    # Extract title for slug
    title_match = re.search(r"^title:\s*(.+?)$", cleaned, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip().strip('"').strip("'")
    else:
        title = topic

    slug = slugify(title)
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_prefix}-{slug}.md"
    filepath = POSTS_DIR / filename

    # Avoid overwriting an existing file with the same name
    counter = 1
    while filepath.exists():
        filename = f"{date_prefix}-{slug}-{counter}.md"
        filepath = POSTS_DIR / filename
        counter += 1

    filepath.write_text(cleaned + "\n", encoding="utf-8")
    log.info("Saved: %s (%d chars)", filepath.name, len(cleaned))
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

    log.info("Content generation complete. Generated %d/%d articles.",
             generated, ARTICLES_PER_RUN)

    if generated == 0:
        log.error("No articles were generated. Exiting with failure.")
        sys.exit(1)


if __name__ == "__main__":
    main()
