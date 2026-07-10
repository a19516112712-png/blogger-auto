"""Automatic label generation for Blogger articles.

Generates relevant labels from an article's title, category, and content.

Rules
-----
1. Use article's existing labels if provided.
2. Extract relevant category labels from title heuristics.
3. Always include "Baby Names" as a base label.
4. Remove duplicates and empty strings.
5. Limit to 5 labels maximum (Blogger best practice).
"""

from __future__ import annotations

import re

from config.logging import get_logger
from config.settings import PUBLISHER_DEFAULT_LABELS

log = get_logger(__name__)

# Label mapping: keyword → label
# These are used when the article doesn't provide its own labels.
KEYWORD_TO_LABEL: dict[str, str] = {
    "girl": "Baby Girl Names",
    "boy": "Baby Boy Names",
    "gender neutral": "Gender Neutral Names",
    "unisex": "Gender Neutral Names",
    "japanese": "Japanese Names",
    "irish": "Irish Names",
    "biblical": "Biblical Names",
    "nature": "Nature Names",
    "unique": "Unique Names",
    "rare": "Rare Names",
    "vintage": "Vintage Names",
    "modern": "Modern Names",
    "strong": "Strong Names",
    "cute": "Cute Names",
    "meaning": "Names By Meaning",
    "love": "Names By Meaning",
    "light": "Names By Meaning",
    "hope": "Names By Meaning",
    "strength": "Names By Meaning",
    "miracle": "Names By Meaning",
    "warrior": "Names By Meaning",
    "beauty": "Names By Meaning",
    "blessing": "Names By Meaning",
    "wisdom": "Names By Meaning",
    "peace": "Names By Meaning",
    "french": "French Names",
    "spanish": "Spanish Names",
    "italian": "Italian Names",
    "german": "German Names",
    "greek": "Greek Names",
    "hebrew": "Hebrew Names",
    "arabic": "Arabic Names",
    "celtic": "Celtic Names",
    "nordic": "Nordic Names",
    "scandinavian": "Scandinavian Names",
    "royal": "Royal Names",
    "flower": "Nature Names",
    "tree": "Nature Names",
    "animal": "Nature Names",
    "ocean": "Nature Names",
    "moon": "Names By Meaning",
    "star": "Names By Meaning",
    "angel": "Names By Meaning",
}

# Core labels always included
BASE_LABELS: set[str] = {"Baby Names"}

MAX_LABELS: int = 5


def generate_labels(
    title: str = "",
    existing_labels: list[str] | None = None,
    slug: str = "",
) -> list[str]:
    """Generate a deduplicated list of labels for a Blogger post.

    Args:
        title:           Article title (used for keyword detection).
        existing_labels: Labels already assigned to the article.
        slug:            Article URL slug (used as secondary signal).

    Returns:
        A list of up to 5 unique, non-empty labels.
    """
    labels: set[str] = set()

    # 1. Add base labels
    labels.update(BASE_LABELS)

    # 2. Add existing article labels
    if existing_labels:
        labels.update(
            label.strip() for label in existing_labels if label.strip()
        )

    # 3. Extract labels from title keywords
    if title:
        title_lower = title.lower()
        for keyword, label in KEYWORD_TO_LABEL.items():
            if keyword in title_lower:
                labels.add(label)

    # 4. Extract labels from slug
    if slug:
        slug_lower = slug.lower().replace("-", " ").replace("_", " ")
        for keyword, label in KEYWORD_TO_LABEL.items():
            if keyword in slug_lower:
                labels.add(label)

    # 5. Fallback: if no labels at all, use default
    if not labels:
        labels.update(
            label.strip()
            for label in PUBLISHER_DEFAULT_LABELS
            if label.strip()
        )

    # 6. Sort and limit
    sorted_labels = sorted(labels, key=_label_sort_key)
    return sorted_labels[:MAX_LABELS]


def _label_sort_key(label: str) -> tuple:
    """Sort labels so that 'Baby Names' comes first, then alphabetical.

    Args:
        label: A label string.

    Returns:
        A sort key tuple.
    """
    if label == "Baby Names":
        return (0, label)
    return (1, label)
