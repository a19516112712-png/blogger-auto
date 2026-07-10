"""Article title analysis engine.

Parses a baby name article title and returns a structured
:class:`~prompt_engine.models.PromptAnalysis` containing the topic,
category, country, audience, language, content type, and SEO intent.
"""

from __future__ import annotations

import re
from typing import Any

from prompt_engine.models import PromptAnalysis

# ---------------------------------------------------------------------------
# Keyword → category mapping
# ---------------------------------------------------------------------------
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "girl_names": [
        "girl", "girls", "feminine", "female", "daughter",
        "princess", "queen", "goddess", "lady", "maiden",
    ],
    "boy_names": [
        "boy", "boys", "masculine", "male", "son",
        "king", "prince", "lord", "warrior", "knight",
    ],
    "gender_neutral": [
        "gender neutral", "unisex", "androgynous", "nonbinary",
        "non-binary", "gender-fluid", "neutral",
    ],
    "nature_names": [
        "nature", "flower", "tree", "ocean", "mountain", "river",
        "forest", "garden", "bird", "animal", "gemstone", "season",
        "earth", "sky", "moon", "sun", "star", "botanical",
    ],
    "mythology_names": [
        "mythology", "mythological", "greek", "roman", "norse",
        "celtic", "goddess", "god", "legend", "mythical",
        "fantasy", "magical", "dragon", "phoenix",
    ],
    "vintage_names": [
        "vintage", "classic", "retro", "old-fashioned", "antique",
        "traditional", "timeless", "heritage", "nostalgia",
    ],
    "international_names": [
        "japanese", "irish", "korean", "french", "italian",
        "spanish", "german", "arabic", "greek", "russian",
        "scandinavian", "celtic", "nordic", "african", "indian",
        "hawaiian", "international", "world", "global",
    ],
    "biblical_names": [
        "biblical", "bible", "christian", "hebrew", "religious",
        "faith", "spiritual", "saint", "angel", "testament",
    ],
    "unique_names": [
        "unique", "rare", "uncommon", "distinctive", "unusual",
        "different", "one-of-a-kind", "standout",
    ],
}

_COUNTRY_KEYWORDS: dict[str, list[str]] = {
    "us": ["american", "united states", "us"],
    "uk": ["british", "english", "uk", "united kingdom"],
    "japan": ["japanese"],
    "ireland": ["irish"],
    "france": ["french"],
    "korea": ["korean"],
    "italy": ["italian"],
    "spain": ["spanish"],
    "germany": ["german"],
    "arabic": ["arabic", "middle eastern"],
    "india": ["indian", "hindu", "sanskrit"],
    "africa": ["african"],
    "scandinavia": ["scandinavian", "nordic", "swedish", "norwegian"],
}

_SEO_INTENT_KEYWORDS: dict[str, list[str]] = {
    "informational": [
        "meaning", "mean", "what does", "origin", "significance",
        "names that", "guide", "ideas",
    ],
    "commercial": [
        "popular", "trending", "best", "top", "2026",
        "modern", "current", "beautiful", "cute",
    ],
    "navigational": [
        "list", "collection", "catalog", "catalogue", "directory",
    ],
    "transactional": [
        "find", "choose", "pick", "select", "name generator",
    ],
}

_CONTENT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "list": ["100", "50",  "200", "top", "list", "collection"],
    "guide": ["guide", "how to", "tips", "advice", "complete"],
    "meaning": ["meaning", "mean", "significance", "origin"],
    "trend": ["trending", "popular", "modern", "2026", "current"],
    "origin": _COUNTRY_KEYWORDS["japan"]
              + _COUNTRY_KEYWORDS["ireland"]
              + _COUNTRY_KEYWORDS["france"]
              + ["origin", "international", "from"],
}

# The special category "names_by_meaning" acts as a catch-all for
# "names that mean X" patterns.
_MEANING_PATTERN = re.compile(r"names that mean\s+(.+)", re.IGNORECASE)


def _match_keywords(text: str, mapping: dict[str, list[str]]) -> str:
    """Find the first mapping key whose keywords match the text.

    Args:
        text:    Lowercased input text.
        mapping: Dictionary mapping value → list of keyword strings.

    Returns:
        The first matching value, or ``""`` if nothing matched.
    """
    text_lower = text.lower()
    for key, keywords in mapping.items():
        for kw in keywords:
            if kw in text_lower:
                return key
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def analyze_title(title: str) -> PromptAnalysis:
    """Analyze a baby name article title and return a structured analysis.

    Args:
        title: The article title to analyze (e.g. "100 Japanese Baby Names").

    Returns:
        A :class:`~prompt_engine.models.PromptAnalysis` instance.
    """
    # Detect meaning-based names
    meaning_match = _MEANING_PATTERN.search(title)
    meaning_topic = meaning_match.group(1).strip() if meaning_match else ""

    topic = meaning_topic or title.strip()
    category: str = _match_keywords(title, _CATEGORY_KEYWORDS)
    if not category and _MEANING_PATTERN.search(title):
        category = "names_by_meaning"

    country: str = _match_keywords(title, _COUNTRY_KEYWORDS)

    # Audience
    if any(w in title.lower() for w in ("girl", "daughter", "princess")):
        audience = "parents_of_girls"
    elif any(w in title.lower() for w in ("boy", "son", "prince", "warrior")):
        audience = "parents_of_boys"
    elif any(w in title.lower() for w in ("gender neutral", "unisex")):
        audience = "parents_seeking_neutral"
    else:
        audience = "expectant_parents"

    seo_intent: str = _match_keywords(title, _SEO_INTENT_KEYWORDS)
    if not seo_intent:
        seo_intent = "informational"

    content_type: str = _match_keywords(title, _CONTENT_TYPE_KEYWORDS)
    if not content_type:
        content_type = "list"

    return PromptAnalysis(
        topic=topic,
        category=category,
        country=country,
        audience=audience,
        language="en",
        content_type=content_type,
        seo_intent=seo_intent,
    )
