"""Prompt validator — checks generated prompts against quality, safety, and
formatting rules before they are saved or used.

Rules:

    1. **Minimum length**: positive prompt >= 50 characters.
    2. **Required keywords**: prompt must contain at least one keyword from
       a required set (e.g. ``"baby"``, ``"newborn"``, ``"infant"``).
    3. **Negative prompt exists**: the negative prompt must not be empty.
    4. **16:9 hero image**: the prompt should reference landscape framing or
       wide composition keywords for hero images.
    5. **No forbidden words**: prompt must not contain any banned terms.
"""

from __future__ import annotations

import re
from typing import Any

from prompt_engine.models import GeneratedPrompt, PromptComponents, PromptScore

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# These can be overridden via keyword arguments to ``validate()``.

MIN_POSITIVE_LENGTH: int = 50
MAX_POSITIVE_LENGTH: int = 2000
MIN_NEGATIVE_LENGTH: int = 10

REQUIRED_KEYWORDS: list[str] = [
    "baby", "newborn", "infant", "child",
]

FORBIDDEN_WORDS: list[str] = [
    "naked", "nudity", "violence", "weapon", "blood",
    "gore", "horror", "scary", "death",
]

HERO_KEYWORDS: list[str] = [
    "landscape", "wide", "16:9", "horizontal", "panoramic",
    "letterbox", "wide shot", "wide frame",
]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate(
    prompt_text: str,
    negative_prompt_text: str = "",
    *,
    min_positive_length: int = MIN_POSITIVE_LENGTH,
    max_positive_length: int = MAX_POSITIVE_LENGTH,
    min_negative_length: int = MIN_NEGATIVE_LENGTH,
    required_keywords: list[str] | None = None,
    forbidden_words: list[str] | None = None,
    require_hero: bool = False,
) -> tuple[bool, list[str]]:
    """Validate a prompt against quality and safety rules.

    Args:
        prompt_text:         The positive prompt string.
        negative_prompt_text: The negative prompt string.
        min_positive_length: Minimum character length for the positive prompt.
        max_positive_length: Maximum character length for the positive prompt.
        min_negative_length: Minimum character length for the negative prompt.
        required_keywords:   Keywords that must be present in the positive prompt.
        forbidden_words:     Words that must NOT appear in either prompt.
        require_hero:        If ``True``, check for 16:9 / wide framing keywords.

    Returns:
        A ``(is_valid, reasons)`` tuple where ``reasons`` contains human-readable
        failure messages.  When ``is_valid`` is ``True``, ``reasons`` is empty.
    """
    reasons: list[str] = []

    # 1. Minimum length
    prompt_clean = prompt_text.strip()
    if len(prompt_clean) < min_positive_length:
        reasons.append(
            f"Positive prompt too short: {len(prompt_clean)} chars "
            f"(min {min_positive_length})"
        )
    if len(prompt_clean) > max_positive_length:
        reasons.append(
            f"Positive prompt too long: {len(prompt_clean)} chars "
            f"(max {max_positive_length})"
        )

    # 2. Required keywords
    req_kw = required_keywords or REQUIRED_KEYWORDS
    prompt_lower = prompt_clean.lower()
    found_kw = [kw for kw in req_kw if kw in prompt_lower]
    if not found_kw:
        reasons.append(
            f"No required keywords found: {req_kw}"
        )

    # 3. Negative prompt exists
    neg_clean = negative_prompt_text.strip()
    if len(neg_clean) < min_negative_length:
        reasons.append(
            f"Negative prompt too short: {len(neg_clean)} chars "
            f"(min {min_negative_length})"
        )

    # 4. Hero image check
    if require_hero:
        hero_found = [kw for kw in HERO_KEYWORDS if kw in prompt_lower]
        if not hero_found:
            reasons.append(
                "Hero image (16:9) keywords not found. "
                "Add landscape/wide framing to the prompt."
            )

    # 5. Forbidden words
    forbid = forbidden_words or FORBIDDEN_WORDS
    bad_words = [bw for bw in forbid if bw in prompt_lower]
    if bad_words:
        reasons.append(
            f"Forbidden words detected: {bad_words}"
        )

    return (len(reasons) == 0, reasons)
