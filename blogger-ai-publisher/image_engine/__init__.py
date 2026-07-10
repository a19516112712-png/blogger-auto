"""AI Image Engine v1.0 — production-ready image generation pipeline.

The Image Engine generates a **unique hero image** for each article by:

1. Receiving a prompt (typically from the Prompt Engine).
2. Trying configured providers in order (with automatic fallback).
3. Validating the result (dimensions, corruption, blank/empty).
4. Optimising output (WEBP, 1600×900, RGB, quality 90, ≤300 KB).
5. Computing a perceptual hash for deduplication.
6. Persisting metadata in the SQLite ``generated_images`` table.
7. Returning an :class:`~database.models.ImageResult`.

Architecture
------------
::

    Prompt
      │
      ▼
    ImageManager.generate()
      │
      ├─► Provider.generate(prompt)
      │     ├─► huggingface (FLUX.1-schnell via Inference API)
      │     ├─► pollinations (Pollinations AI free API)
      │     └─► mock (testing only)
      │
      ├─► Validator.validate(image)         reject if corrupt/too-small
      ├─► Optimizer.optimize(image)         resize → WEBP → compress
      ├─► Deduplicator.is_duplicate(phash)  reject if Hamming ≤ threshold
      └─► store metadata → database
"""

from __future__ import annotations

from image_engine.manager import ImageManager

__all__ = ["ImageManager"]
