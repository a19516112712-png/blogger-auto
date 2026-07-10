"""Image generation provider implementations.

Available providers (imported lazily by :class:`ImageManager`):

- :class:`MockProvider` — in-memory test image (no network).
- :class:`PollinationsProvider` — free public API.
- :class:`HuggingFaceProvider` — HF Inference API (FLUX.1-schnell).
"""

from __future__ import annotations

from image_engine.providers.mock import MockProvider
from image_engine.providers.pollinations import PollinationsProvider

__all__ = [
    "HuggingFaceProvider",
    "MockProvider",
    "PollinationsProvider",
]
