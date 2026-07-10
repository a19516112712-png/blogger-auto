"""SQL table definitions as dataclass-like models.

Actual table schemas live in :mod:`database.init_db`; these dataclasses
are used for type-safe construction and serialization of rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# Base mixin
# ---------------------------------------------------------------------------
@dataclass
class BaseModel:
    """Shared fields for all database models."""

    id: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary, dropping internal keys.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        return {
            k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in self.__dict__.items()
        }


# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------
@dataclass
class Article(BaseModel):
    """Represents a single blog article."""

    title: str = ""
    slug: str = ""
    meta_description: str = ""
    content_markdown: str = ""
    content_html: str = ""
    word_count: int = 0
    labels: str = ""  # Comma-separated label list
    status: str = "draft"  # draft | published | failed
    blogger_post_id: str = ""
    blogger_url: str = ""
    published_at: datetime | None = None
    is_improved: bool = False
    improvement_count: int = 0
    search_intent_type: str = ""
    publish_status: str = "pending"  # pending | success | failed
    publish_attempts: int = 0
    last_publish_error: str = ""


# ---------------------------------------------------------------------------
# Generated images
# ---------------------------------------------------------------------------
@dataclass
class GeneratedImage(BaseModel):
    """Metadata for an AI-generated image."""

    article_id: int = 0
    prompt_text: str = ""
    image_path: str = ""
    alt_text: str = ""
    width: int = 0
    height: int = 0
    file_size_bytes: int = 0
    mime_type: str = "image/webp"
    status: str = "generated"  # generated | uploaded | failed
    phash: str = ""  # Perceptual hash for deduplication
    provider: str = ""  # Provider that generated (huggingface, pollinations, mock)
    generation_seed: int = 0
    generation_time_ms: int = 0
    optimized: bool = False
    quality: int = 90


# ---------------------------------------------------------------------------
# Used prompts
# ---------------------------------------------------------------------------
@dataclass
class UsedPrompt(BaseModel):
    """Track every prompt sent to the AI to avoid repetition."""

    prompt_text: str = ""
    response_preview: str = ""
    model: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    duration_ms: int = 0
    prompt_type: str = ""  # article | image | improve
    target_slug: str = ""
    success: bool = True
    error_message: str = ""
    prompt_hash: str = ""


# ---------------------------------------------------------------------------
# Image engine result
# ---------------------------------------------------------------------------
@dataclass
class ImageResult:
    """Complete result from the Image Engine pipeline.

    Returned by :meth:`image_engine.manager.ImageManager.generate`.
    """

    image_path: Path = field(default_factory=lambda: Path(""))
    alt_text: str = ""
    caption: str = ""
    title: str = ""
    description: str = ""
    width: int = 0
    height: int = 0
    file_size_bytes: int = 0
    phash: str = ""
    provider: str = ""
    generation_seed: int = 0
    generation_time_ms: int = 0
    optimized: bool = False
    quality: int = 90
    seo_keywords: list[str] = field(default_factory=list)
    success: bool = True
    error_message: str = ""
