"""ImageManager — orchestrator for the full image generation pipeline.

Pipeline
--------
::

    1. Receive (title, slug, prompt)
    2. Iterate through configured providers in order
    3. For each provider:
       a. Call provider.generate(prompt)
       b. Validator.validate(image)
       c. Optimizer.optimize(image) → final WEBP
       d. Deduplicator.compute_phash → compare against DB
       e. If duplicate → retry with next seed (up to max_retries)
       f. If success → store metadata → return ImageResult
    4. If all providers fail → return error ImageResult

All configurable from :mod:`config.settings`.
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Any

from config.logging import get_logger
from config.settings import (
    IMAGES_DIR,
    IMAGE_MAX_RETRIES,
    IMAGE_PROVIDERS,
    IMAGE_OUTPUT_WIDTH,
    IMAGE_OUTPUT_HEIGHT,
    IMAGE_OUTPUT_QUALITY,
)
from database.database import execute, fetch_one, last_insert_rowid
from image_engine.base import ConfigurationError, GenerationError, GeneratedImage
from image_engine.deduplicator import ImageDeduplicator
from image_engine.metadata import MetadataGenerator
from image_engine.optimizer import ImageOptimizer, OptimizationError
from image_engine.validator import ImageValidator, ValidationError

log = get_logger(__name__)


class ImageManager:
    """Orchestrator for the full image generation pipeline.

    Usage::

        mgr = ImageManager()
        result = mgr.generate(
            title="100 Japanese Baby Names",
            slug="japanese-baby-names",
            prompt="A beautiful illustration...",
        )
    """

    def __init__(self) -> None:
        """Initialise all sub-components from settings."""
        self.validator = ImageValidator()
        self.optimizer = ImageOptimizer()
        self.deduplicator = ImageDeduplicator()
        self.metadata_generator = MetadataGenerator()
        self.max_retries: int = IMAGE_MAX_RETRIES

        # Ensure the output directory exists
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        title: str,
        slug: str,
        prompt: str,
        article_id: int = 0,
    ) -> dict[str, Any]:
        """Run the full image generation pipeline.

        Args:
            title:      Article H1 title (used for metadata generation).
            slug:       URL slug (used for filename and dedup).
            prompt:     Text prompt for image generation.
            article_id: Optional database article ID to link the image.

        Returns:
            A dictionary with keys matching :class:`ImageResult` fields.
            ``success`` indicates whether generation succeeded.
        """
        # Generate SEO metadata first (filename, alt text, etc.)
        meta = self.metadata_generator.generate(
            title=title, slug=slug, prompt_text=prompt
        )

        # Augment prompt with photography style for unique hero images
        # Every article gets a combination driven by its title analysis
        prompt = self._build_production_prompt(title, prompt)

        # Try each provider in order, up to per-provider retries
        provider_retries = 3
        providers = self._get_provider_list()

        for provider_name in providers:
            for attempt in range(1, provider_retries + 1):
                seed = random.randint(0, 2**32 - 1)

                try:
                    raw: GeneratedImage = self._run_provider(
                        provider_name, prompt, seed
                    )

                    # Validate
                    self.validator.validate(raw.image_path)

                    # Optimize to final path
                    final_path = IMAGES_DIR / meta.filename
                    self.optimizer.optimize(raw.image_path, output_path=final_path)

                    # Deduplication check
                    phash = self.deduplicator.compute_phash(final_path)
                    existing = self.deduplicator.load_existing_hashes()
                    if self.deduplicator.is_duplicate(phash, existing):
                        log.warning(
                            "Duplicate image detected (phash=%s, provider=%s, "
                            "seed=%d, attempt=%d/%d) — regenerating...",
                            phash,
                            provider_name,
                            seed,
                            attempt,
                            provider_retries,
                        )
                        final_path.unlink(missing_ok=True)
                        continue

                    # Persist to database
                    self._store_image_record(
                        article_id=article_id,
                        prompt_text=prompt,
                        image_path=str(final_path),
                        alt_text=meta.alt_text,
                        width=IMAGE_OUTPUT_WIDTH,
                        height=IMAGE_OUTPUT_HEIGHT,
                        file_size_bytes=final_path.stat().st_size,
                        phash=phash,
                        provider=raw.provider,
                        generation_seed=raw.generation_seed,
                        generation_time_ms=raw.generation_time_ms,
                        quality=IMAGE_OUTPUT_QUALITY,
                    )

                    log.info(
                        "Image generated successfully: provider=%s seed=%d "
                        "phash=%s size=%dKB path=%s elapsed=%dms",
                        raw.provider,
                        raw.generation_seed,
                        phash,
                        final_path.stat().st_size / 1024,
                        final_path.name,
                        raw.generation_time_ms,
                    )

                    return {
                        "success": True,
                        "image_path": str(final_path),
                        "alt_text": meta.alt_text,
                        "caption": meta.caption,
                        "title": meta.title,
                        "description": meta.description,
                        "width": IMAGE_OUTPUT_WIDTH,
                        "height": IMAGE_OUTPUT_HEIGHT,
                        "file_size_bytes": final_path.stat().st_size,
                        "phash": phash,
                        "provider": raw.provider,
                        "generation_seed": raw.generation_seed,
                        "generation_time_ms": raw.generation_time_ms,
                        "optimized": True,
                        "quality": IMAGE_OUTPUT_QUALITY,
                        "seo_keywords": meta.seo_keywords,
                        "error_message": "",
                    }

                except (ValidationError, OptimizationError, GenerationError, ConfigurationError) as exc:
                    log.warning(
                        "Provider %s failed (provider_attempt=%d/%d, "
                        "seed=%d): %s",
                        provider_name,
                        attempt,
                        provider_retries,
                        seed,
                        exc,
                    )
                    continue

        # All providers exhausted
        error_msg = (
            f"All providers exhausted "
            f"(providers={providers}, retries={provider_retries} each)"
        )
        log.error(error_msg)
        return {
            "success": False,
            "image_path": "",
            "alt_text": meta.alt_text,
            "caption": meta.caption,
            "title": meta.title,
            "description": meta.description,
            "width": 0,
            "height": 0,
            "file_size_bytes": 0,
            "phash": "",
            "provider": "",
            "generation_seed": 0,
            "generation_time_ms": 0,
            "optimized": False,
            "quality": 0,
            "seo_keywords": meta.seo_keywords,
            "error_message": error_msg,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_production_prompt(title: str, existing_prompt: str) -> str:
        """Build a unique production-quality photography prompt.

        Analyzes the article title for country, culture, and gender
        context, then embeds the existing prompt into a high-end
        editorial photography scene.

        Args:
            title:           Article title (for analysis).
            existing_prompt: The base prompt from the Prompt Engine.

        Returns:
            A fully composed prompt string for ultra-realistic
            photography.
        """
        # Analyze title for context
        try:
            from prompt_engine.analyzer import analyze_title
            analysis = analyze_title(title)
            country = analysis.country
            category = analysis.category
        except Exception:
            country = ""
            category = ""

        # Build context-aware scene prefix
        if country:
            scene_prefix = (
                f"Professional editorial newborn photography set in "
                f"a {country.replace('_', ' ').title()} cultural "
                f"environment, "
            )
        elif category == "girl_names":
            scene_prefix = (
                f"Professional editorial portrait of a baby girl, "
            )
        elif category == "boy_names":
            scene_prefix = (
                f"Professional editorial portrait of a baby boy, "
            )
        elif category == "nature_names":
            scene_prefix = (
                f"Professional editorial nature photography with baby, "
            )
        else:
            scene_prefix = (
                f"Professional editorial newborn photography, "
            )

        # Core photography style that every image must have
        style_core = (
            f"ultra realistic photography, natural window lighting, "
            f"shot on 85mm f/1.4 lens, soft creamy bokeh, "
            f"high dynamic range, premium editorial quality, "
            f"authentic genuine beauty, no text, no watermark"
        )

        # Combine: scene context + existing prompt + style core
        # Use the existing prompt as the "subject" description
        # Assemble and clean: strip trailing/leading commas and whitespace
        parts = [scene_prefix, existing_prompt, style_core]
        cleaned = [p.strip().rstrip(",").lstrip(",").strip() for p in parts if p]
        return ", ".join(p for p in cleaned if p)

    @staticmethod
    def _get_provider_list() -> list[str]:
        """Return the ordered list of image providers.

        Reads from ``config.settings`` at call time so that tests
        can override ``IMAGE_PROVIDERS`` dynamically.

        Returns:
            List of provider name strings.  Empty if none configured.
        """
        from config.settings import IMAGE_PROVIDERS as _providers
        return [p.strip() for p in _providers if p.strip()]

    @staticmethod
    def _resolve_provider(name: str) -> Any:
        """Import and instantiate a provider class by name.

        Args:
            name: Provider name (``"mock"``, ``"pollinations"``,
                  ``"huggingface"``).

        Returns:
            An instance of the provider.

        Raises:
            ConfigurationError: If the provider name is unknown or its
                configuration is invalid.
        """
        name_lower = name.lower().strip()

        if name_lower == "mock":
            from image_engine.providers.mock import MockProvider
            return MockProvider()
        elif name_lower == "pollinations":
            from image_engine.providers.pollinations import PollinationsProvider
            return PollinationsProvider()
        elif name_lower == "huggingface":
            from image_engine.providers.huggingface import HuggingFaceProvider
            return HuggingFaceProvider()
        else:
            raise ConfigurationError(f"Unknown provider: {name}")

    def _run_provider(
        self,
        provider_name: str,
        prompt: str,
        seed: int,
    ) -> GeneratedImage:
        """Run a single provider and return the raw generated image.

        Args:
            provider_name: Provider identifier.
            prompt:        Text prompt.
            seed:          Generation seed.

        Returns:
            A :class:`GeneratedImage` named tuple.

        Raises:
            GenerationError: If the provider fails to generate.
            ConfigurationError: If the provider is unknown.
        """
        provider = self._resolve_provider(provider_name)
        log.info(
            "Generating image with provider=%s, seed=%d",
            provider_name,
            seed,
        )
        return provider.generate(prompt, seed=seed)

    @staticmethod
    def _store_image_record(
        article_id: int,
        prompt_text: str,
        image_path: str,
        alt_text: str,
        width: int,
        height: int,
        file_size_bytes: int,
        phash: str,
        provider: str,
        generation_seed: int,
        generation_time_ms: int,
        quality: int,
    ) -> int:
        """Insert a record into the ``generated_images`` table.

        Args:
            All fields matching the database schema.

        Returns:
            The row ID of the inserted record.
        """
        execute(
            """
            INSERT INTO generated_images (
                article_id, prompt_text, image_path, alt_text,
                width, height, file_size_bytes, mime_type, status,
                phash, provider, generation_seed, generation_time_ms,
                optimized, quality
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article_id if article_id else None,
                prompt_text,
                image_path,
                alt_text,
                width,
                height,
                file_size_bytes,
                "image/webp",
                "generated",
                phash,
                provider,
                generation_seed,
                generation_time_ms,
                1,  # optimized = True
                quality,
            ),
            commit=True,
        )
        return last_insert_rowid()
