"""Prompt scorer — evaluates a generated prompt against configurable
weighted criteria and returns a :class:`~prompt_engine.models.PromptScore`.

Scoring dimensions (each 0–100):

    * **clarity** — how readable and well-structured the prompt is.
    * **uniqueness** — how varied and creative the prompt feels.
    * **photography quality** — whether it references pro photography terms.
    * **SEO relevance** — whether it matches the article's topic/category.
    * **composition quality** — richness of composition descriptors.

The overall score is a weighted average of all dimensions.
"""

from __future__ import annotations

import re
from typing import Any

from prompt_engine.models import PromptComponents, PromptScore

# ---------------------------------------------------------------------------
# Default weights (configurable via keyword argument)
# ---------------------------------------------------------------------------
DEFAULT_WEIGHTS: dict[str, float] = {
    "clarity": 0.20,
    "uniqueness": 0.15,
    "photography_quality": 0.25,
    "seo_relevance": 0.20,
    "composition_quality": 0.20,
}

# Photography quality indicators — terms that suggest pro-level output.
_PHOTOGRAPHY_TERMS: list[str] = [
    "aperture", "f/", "mm lens", "bokeh", "softbox", "Rembrandt",
    "high-key", "low-key", "rim light", "catchlight", "depth of field",
    "flat lay", "cinematic", "editorial", "fine art",
    "golden hour", "overcast", "window light",
]

_COMPOSITION_TERMS: list[str] = [
    "centered", "symmetrical", "rule of thirds", "off-center",
    "framed by", "circular composition", "diagonal",
    "negative space", "layered", "foreground", "background",
    "sharp focus", "creamy bokeh", "selective focus",
]

_LENS_TERMS: list[str] = [
    "85mm", "50mm", "35mm", "105mm", "70-200mm", "telephoto",
    "prime lens", "macro lens", "wide lens",
]


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------
def _score_clarity(prompt_text: str, components: PromptComponents) -> int:
    """Score clarity based on prompt length and component count."""
    wc = len(prompt_text.split())
    if wc < 10:
        return 30
    if wc < 20:
        return 60
    if wc < 40:
        return 80
    return 95 if components.positive_count >= 6 else 85


def _score_uniqueness(prompt_text: str) -> int:
    """Score uniqueness based on uncommon word usage."""
    unique_ratio = len(set(prompt_text.lower().split())) / max(
        len(prompt_text.split()), 1
    )
    if unique_ratio > 0.70:
        return 90
    if unique_ratio > 0.55:
        return 70
    if unique_ratio > 0.40:
        return 50
    return 30


def _score_photography_quality(prompt_text: str) -> int:
    """Score photography quality by counting pro-photography terms."""
    text_lower = prompt_text.lower()
    count = sum(1 for term in _PHOTOGRAPHY_TERMS if term in text_lower)
    if count >= 5:
        return 95
    if count >= 3:
        return 75
    if count >= 1:
        return 50
    return 20


def _score_seo_relevance(
    prompt_text: str,
    article_title: str = "",
) -> int:
    """Score SEO relevance — prompt should reference the article topic."""
    if not article_title:
        return 70  # Neutral when no article title is provided.
    article_words = set(article_title.lower().split())
    prompt_words = set(prompt_text.lower().split())
    overlap = len(article_words & prompt_words) / max(len(article_words), 1)
    if overlap > 0.15:
        return 90
    if overlap > 0.08:
        return 70
    return 40


def _score_composition_quality(prompt_text: str) -> int:
    """Score composition quality based on composition + lens terms."""
    text_lower = prompt_text.lower()
    comp_count = sum(1 for term in _COMPOSITION_TERMS if term in text_lower)
    lens_count = sum(1 for term in _LENS_TERMS if term in text_lower)
    total = comp_count + lens_count
    if total >= 6:
        return 95
    if total >= 4:
        return 75
    if total >= 2:
        return 55
    return 30


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def score(
    prompt_text: str,
    components: PromptComponents,
    article_title: str = "",
    weights: dict[str, float] | None = None,
) -> PromptScore:
    """Score a generated prompt across all five quality dimensions.

    Args:
        prompt_text:   The positive prompt string.
        components:    The component set used to build the prompt.
        article_title: Optional article title for SEO relevance scoring.
        weights:       Optional custom weight dictionary.  Falls back to
                       ``DEFAULT_WEIGHTS`` when omitted.

    Returns:
        A :class:`~prompt_engine.models.PromptScore` instance.
    """
    w = weights or DEFAULT_WEIGHTS

    clarity_val = _score_clarity(prompt_text, components)
    uniqueness_val = _score_uniqueness(prompt_text)
    photography_val = _score_photography_quality(prompt_text)
    seo_val = _score_seo_relevance(prompt_text, article_title)
    composition_val = _score_composition_quality(prompt_text)

    overall_val = int(
        clarity_val * w.get("clarity", 0.20)
        + uniqueness_val * w.get("uniqueness", 0.15)
        + photography_val * w.get("photography_quality", 0.25)
        + seo_val * w.get("seo_relevance", 0.20)
        + composition_val * w.get("composition_quality", 0.20)
    )

    return PromptScore(
        clarity=clarity_val,
        uniqueness=uniqueness_val,
        photography_quality=photography_val,
        seo_relevance=seo_val,
        composition_quality=composition_val,
        overall=overall_val,
    )
