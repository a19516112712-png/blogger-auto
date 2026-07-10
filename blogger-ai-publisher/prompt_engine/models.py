"""Dataclass models for the AI Prompt Engine.

All models use :py:func:`dataclasses.dataclass` with full type annotations.
They serve as the shared contract between *analyzer*, *builder*, *validator*,
*scorer*, and *generator*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# PromptAnalysis – output of the analyzer module
# ---------------------------------------------------------------------------
@dataclass
class PromptAnalysis:
    """Structured analysis of an article title for image prompt generation.

    Every field is derived from the article title via keyword matching and
    semantic heuristics.
    """

    topic: str = ""
    category: str = ""          # girl_names, boy_names, gender_neutral, etc.
    country: str = ""           # us, uk, japan, ireland, etc.
    audience: str = ""          # parents, expectant_parents, gift_givers, etc.
    language: str = "en"        # ISO 639-1 code
    content_type: str = ""      # list, guide, meaning, trend, origin
    seo_intent: str = ""        # informational, commercial, navigational, transactional

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary.

        Returns:
            A dictionary representation suitable for JSON serialization.
        """
        return self.__dict__.copy()


# ---------------------------------------------------------------------------
# PromptComponents – building blocks selected from YAML library
# ---------------------------------------------------------------------------
@dataclass
class PromptComponents:
    """Component fragments selected from the YAML prompt library.

    Each field is a *list* of random fragments from the corresponding
    YAML category so that the builder can concatenate them.
    """

    subject: list[str] = field(default_factory=list)
    camera: list[str] = field(default_factory=list)
    lighting: list[str] = field(default_factory=list)
    composition: list[str] = field(default_factory=list)
    background: list[str] = field(default_factory=list)
    style: list[str] = field(default_factory=list)
    color: list[str] = field(default_factory=list)
    mood: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)

    @property
    def positive_count(self) -> int:
        """Number of non-negative component categories that have entries."""
        return sum(1 for lst in (
            self.subject, self.camera, self.lighting, self.composition,
            self.background, self.style, self.color, self.mood,
        ) if lst)


# ---------------------------------------------------------------------------
# PromptScore – output of the scorer module
# ---------------------------------------------------------------------------
@dataclass
class PromptScore:
    """Quality score for a generated prompt.

    Every dimension is an integer between 0 and 100.  The overall score is
    a configurable weighted average.
    """

    clarity: int = 0
    uniqueness: int = 0
    photography_quality: int = 0
    seo_relevance: int = 0
    composition_quality: int = 0
    overall: int = 0

    def __post_init__(self) -> None:
        """Clamp all scores to the 0–100 range."""
        for name in ("clarity", "uniqueness", "photography_quality",
                     "seo_relevance", "composition_quality", "overall"):
            val: int = getattr(self, name)
            setattr(self, name, max(0, min(100, val)))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary.

        Returns:
            A dictionary of all score fields.
        """
        return {
            "clarity": self.clarity,
            "uniqueness": self.uniqueness,
            "photography_quality": self.photography_quality,
            "seo_relevance": self.seo_relevance,
            "composition_quality": self.composition_quality,
            "overall": self.overall,
        }


# ---------------------------------------------------------------------------
# GeneratedPrompt – output of the generator module
# ---------------------------------------------------------------------------
@dataclass
class GeneratedPrompt:
    """A complete, validated, scored, and de-duplicated prompt ready for use."""

    prompt_text: str = ""
    negative_prompt: str = ""
    components: PromptComponents = field(default_factory=PromptComponents)
    analysis: PromptAnalysis = field(default_factory=PromptAnalysis)
    score: PromptScore = field(default_factory=PromptScore)
    prompt_hash: str = ""
    is_valid: bool = False
    created_at: str = ""

    def __post_init__(self) -> None:
        """Set the creation timestamp if not already set."""
        if not self.created_at:
            self.created_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full prompt to a nested dictionary.

        Returns:
            A complete dictionary representation.
        """
        return {
            "prompt_text": self.prompt_text,
            "negative_prompt": self.negative_prompt,
            "components": {
                "subject": self.components.subject,
                "camera": self.components.camera,
                "lighting": self.components.lighting,
                "composition": self.components.composition,
                "background": self.components.background,
                "style": self.components.style,
                "color": self.components.color,
                "mood": self.components.mood,
                "negative": self.components.negative,
            },
            "analysis": self.analysis.to_dict(),
            "score": self.score.to_dict(),
            "prompt_hash": self.prompt_hash,
            "is_valid": self.is_valid,
            "created_at": self.created_at,
        }
