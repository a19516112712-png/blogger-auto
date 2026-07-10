"""Abstract base class for image generation providers.

All providers (real and mock) inherit from :class:`BaseProvider` and
implement :meth:`~BaseProvider.generate`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import NamedTuple


class GeneratedImage(NamedTuple):
    """Raw output from a provider before validation/optimization.

    Attributes:
        image_path:    Temporary path to the downloaded/generated image.
        provider:      Provider name (e.g. ``"huggingface"``).
        generation_seed: Seed used for reproducibility (0 if not supported).
        generation_time_ms: Wall-clock time spent generating, in milliseconds.
    """

    image_path: Path
    provider: str
    generation_seed: int = 0
    generation_time_ms: int = 0


class BaseProvider(ABC):
    """Abstract interface for image generation providers.

    Subclasses must:

    - Set :attr:`name` to a unique provider identifier.
    - Implement :meth:`generate` which returns a :class:`GeneratedImage`.
    """

    name: str = "base"

    def __init__(self) -> None:
        """Validate provider configuration on instantiation."""
        self._validate_config()

    @abstractmethod
    def _validate_config(self) -> None:
        """Raise :class:`ConfigurationError` if required settings are missing.

        Called automatically during ``__init__``.
        """

    @abstractmethod
    def generate(self, prompt: str, seed: int | None = None) -> GeneratedImage:
        """Generate an image from the given text prompt.

        Args:
            prompt: Text description to generate from.
            seed:   Optional seed for reproducible generation.

        Returns:
            A :class:`GeneratedImage` named tuple.

        Raises:
            GenerationError: If the provider fails to produce an image.
        """


class ConfigurationError(Exception):
    """Raised when a provider's configuration is incomplete or invalid."""


class GenerationError(Exception):
    """Raised when image generation fails at the provider level."""
