"""SEO-friendly URL slug generation for Blogger articles.

Rules
-----
1. Lowercase.
2. Hyphen-separated (not underscores).
3. ASCII only (non-ASCII characters are transliterated or removed).
4. Maximum 75 characters (configurable).
5. Remove leading/trailing hyphens.
6. Remove consecutive hyphens.
7. Strip common filler words (a, an, the, and, for, etc.).
"""

from __future__ import annotations

import re
import unicodedata

from config.logging import get_logger
from config.settings import PUBLISHER_SLUG_MAX_LENGTH

log = get_logger(__name__)

# Words to remove from slugs (they add length without SEO value)
_STOP_WORDS: set[str] = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "is", "it", "as", "be", "are",
}

# Characters to replace with hyphens
_REPLACE_PATTERN: re.Pattern = re.compile(r"[^a-z0-9-]")


def generate_slug(title: str, max_length: int | None = None) -> str:
    """Generate an SEO-friendly URL slug from a title.

    Args:
        title:      Article title (e.g. ``"100 Japanese Baby Names"``).
        max_length: Maximum slug length. Defaults to
                    ``PUBLISHER_SLUG_MAX_LENGTH`` from settings.

    Returns:
        A clean, lowercase, hyphen-separated slug string.

    Examples:
        >>> generate_slug("100 Japanese Baby Names")
        '100-japanese-baby-names'

        >>> generate_slug("What's Your Baby's Name?")
        'whats-your-babys-name'

        >>> generate_slug("  Spaces   Everywhere!!!  ")
        'spaces-everywhere'
    """
    if not title or not title.strip():
        log.warning("Empty title provided for slug generation")
        return "untitled"

    limit = max_length or PUBLISHER_SLUG_MAX_LENGTH

    # Normalize unicode characters
    text = unicodedata.normalize("NFKD", title)
    text = text.encode("ascii", "ignore").decode("ascii")

    # Lowercase
    text = text.lower()

    # Remove stop words (but keep the number prefix if present)
    words = text.split()
    filtered: list[str] = []
    for word in words:
        # Always keep numbers and number-prefixed words
        if word.isdigit() or re.match(r"^\d", word):
            filtered.append(word)
        elif word not in _STOP_WORDS:
            filtered.append(word)

    text = " ".join(filtered)

    # Replace non-alphanumeric characters with hyphens
    text = text.replace("'", "")  # Remove apostrophes first
    text = text.replace("&", "and")
    text = _REPLACE_PATTERN.sub("-", text)

    # Clean up hyphens
    text = re.sub(r"-+", "-", text)  # No consecutive hyphens
    text = text.strip("-")  # No leading/trailing hyphens

    # Truncate
    if len(text) > limit:
        text = text[:limit].rstrip("-")

    if not text:
        return "untitled"

    log.debug("Generated slug: %s (from title: %s)", text, title)
    return text
