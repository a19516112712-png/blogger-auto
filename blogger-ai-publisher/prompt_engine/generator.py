"""Prompt generator — the full pipeline entry point.

Combines *analyzer → builder → validator → scorer* into a single call,
enforces prompt hash deduplication against the SQLite database, and returns
a :class:`~prompt_engine.models.GeneratedPrompt`.

    >>> from prompt_engine.generator import generate_prompt
    >>> p = generate_prompt("100 Japanese Baby Names with Meanings")
    >>> p.is_valid
    True
    >>> p.score.overall
    75  # varies
    >>> p.prompt_hash
    'abc123...'
"""

import hashlib
import hashlib
import logging
import random
import time
from typing import Any

from database.database import execute, fetch_one
from prompt_engine.analyzer import analyze_title
from prompt_engine.builder import build_components, components_to_prompt, components_to_negative_prompt
from prompt_engine.models import GeneratedPrompt, PromptAnalysis, PromptComponents, PromptScore
from prompt_engine.scorer import score
from prompt_engine.validator import validate

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_ATTEMPTS: int = 50  # Max attempts to generate a unique, valid prompt.
VALIDATION_TIMEOUT: float = 2.0  # Seconds between retries.
MIN_SCORE_THRESHOLD: int = 50  # Prompts below this are discarded.


def _compute_hash(prompt_text: str, negative_prompt: str) -> str:
    """Compute SHA-256 hash of the combined prompt strings.

    Args:
        prompt_text:       Positive prompt.
        negative_prompt:   Negative prompt.

    Returns:
        A hex digest string.
    """
    return hashlib.sha256(
        f"{prompt_text}||{negative_prompt}".encode("utf-8")
    ).hexdigest()


def _prompt_hash_exists(hash_value: str) -> bool:
    """Check whether a prompt hash already exists in the database.

    Args:
        hash_value: SHA-256 hex digest.

    Returns:
        ``True`` if the hash is already in the ``used_prompts`` table.
    """
    row = fetch_one(
        "SELECT id FROM used_prompts WHERE prompt_hash = ? LIMIT 1",
        (hash_value,),
    )
    return row is not None


def _save_prompt_hash(hash_value: str, prompt_type: str, target_slug: str) -> None:
    """Record a new prompt hash so it won't be reused.

    Args:
        hash_value:  SHA-256 hex digest.
        prompt_type: Type identifier (e.g. ``"image"``).
        target_slug: The article slug this prompt was generated for.
    """
    execute(
        "INSERT INTO used_prompts "
        "(prompt_hash, prompt_type, target_slug, prompt_text, response_preview, model) "
        "VALUES (?, ?, ?, '', '', '')",
        (hash_value, prompt_type, target_slug),
        commit=True,
    )


# ---------------------------------------------------------------------------
# Main generation pipeline
# ---------------------------------------------------------------------------
def generate_prompt(
    article_title: str,
    *,
    article_slug: str = "",
    prompt_type: str = "image",
    require_hero: bool = False,
    min_score: int = MIN_SCORE_THRESHOLD,
    max_attempts: int = MAX_ATTEMPTS,
    seed: int | None = None,
) -> GeneratedPrompt:
    """Generate a unique, valid, scored prompt for an article.

    The pipeline ensures:

    1. The prompt passes all validation rules.
    2. The prompt's hash does not exist in the database.
    3. The prompt's overall score meets the minimum threshold.

    Args:
        article_title: The article title to generate a prompt for.
        article_slug:  The article slug (used for DB tracking).
        prompt_type:   Prompt type stored in ``used_prompts``.
        require_hero:  If ``True``, enforce 16:9 hero-image keywords.
        min_score:     Minimum acceptable overall score (0–100).
        max_attempts:  Maximum retries before giving up.
        seed:          Random seed for reproducibility (optional).

    Returns:
        A :class:`~prompt_engine.models.GeneratedPrompt` instance.  The
        ``is_valid`` field is ``True`` only when all checks passed.

    Note:
        Even when ``is_valid`` is ``False``, the returned object still
        contains the prompt text and score so callers can inspect failures.
    """
    if seed is not None:
        random.seed(seed)

    for attempt in range(1, max_attempts + 1):
        # 1. Analyze the article title
        analysis = analyze_title(article_title)

        # 2. Build prompt components biased by the analysis category
        components = build_components(analysis_category=analysis.category)

        # 3. Construct the prompt strings
        prompt_text = components_to_prompt(components)
        negative_text = components_to_negative_prompt(components)

        # 4. Compute the hash *before* scoring (cheap check)
        prompt_hash = _compute_hash(prompt_text, negative_text)

        # 5. Dedup check
        if _prompt_hash_exists(prompt_hash):
            log.debug(
                "Attempt %d/%d: hash collision — regenerating.",
                attempt, max_attempts,
            )
            continue

        # 6. Validate
        is_valid, reasons = validate(
            prompt_text,
            negative_prompt_text=negative_text,
            require_hero=require_hero,
        )

        if not is_valid:
            log.debug(
                "Attempt %d/%d: validation failed — %s",
                attempt, max_attempts, "; ".join(reasons),
            )
            # Store the failed prompt for tracking
            result = GeneratedPrompt(
                prompt_text=prompt_text,
                negative_prompt=negative_text,
                components=components,
                analysis=analysis,
                score=PromptScore(),  # No score when invalid
                prompt_hash=prompt_hash,
                is_valid=False,
            )
            return result

        # 7. Score
        prompt_score = score(
            prompt_text,
            components=components,
            article_title=article_title,
        )

        if prompt_score.overall < min_score:
            log.debug(
                "Attempt %d/%d: score %d below threshold %d — regenerating.",
                attempt, max_attempts, prompt_score.overall, min_score,
            )
            continue

        # 8. Persist the hash so it's never reused
        _save_prompt_hash(prompt_hash, prompt_type, article_slug)

        # 9. Build and return the final GeneratedPrompt
        result = GeneratedPrompt(
            prompt_text=prompt_text,
            negative_prompt=negative_text,
            components=components,
            analysis=analysis,
            score=prompt_score,
            prompt_hash=prompt_hash,
            is_valid=True,
        )
        log.info(
            "Prompt generated: hash=%s score=%d topic=%s",
            prompt_hash[:8], prompt_score.overall, article_title[:50],
        )
        return result

    # Exhausted attempts — return last state
    log.warning(
        "Failed to generate a valid prompt for '%s' after %d attempts.",
        article_title, max_attempts,
    )
    return GeneratedPrompt(
        prompt_text="",
        negative_prompt="",
        is_valid=False,
    )
