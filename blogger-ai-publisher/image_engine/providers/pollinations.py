"""Pollinations AI image provider — free, open image generation API.

Uses the public Pollinations API endpoint:

    https://image.pollinations.ai/prompt/{prompt}

No API key is required.  The endpoint returns raw image bytes.
"""

from __future__ import annotations

import random
import time
import urllib.request
import urllib.error
from pathlib import Path

from image_engine.base import (
    BaseProvider,
    ConfigurationError,
    GeneratedImage,
    GenerationError,
)


class PollinationsProvider(BaseProvider):
    """Provider that generates images via the free Pollinations AI API.

    Requires no authentication.  The prompt is URL-encoded and sent as a
    GET request to ``https://image.pollinations.ai/prompt/...``.

    Attributes:
        name: Provider identifier (``"pollinations"``).
    """

    name: str = "pollinations"

    def __init__(self, base_url: str | None = None) -> None:
        """Initialise with an optional custom base URL.

        Args:
            base_url: Override the default Pollinations endpoint.
        """
        self._base_url: str = base_url or "https://image.pollinations.ai/prompt"
        super().__init__()

    def _validate_config(self) -> None:
        """Pollinations requires no API keys — always valid."""

    def generate(self, prompt: str, seed: int | None = None) -> GeneratedImage:
        """Generate an image via the Pollinations API.

        Args:
            prompt: Text prompt describing the desired image.
            seed:   Optional seed for reproducibility.

        Returns:
            A :class:`GeneratedImage` with the downloaded file.

        Raises:
            GenerationError: If the API request fails or returns no data.
        """
        from config.settings import IMAGE_OUTPUT_WIDTH, IMAGE_OUTPUT_HEIGHT

        start = time.perf_counter()
        rng_seed = seed if seed is not None else random.randint(0, 2**32 - 1)

        try:
            import urllib.parse

            encoded = urllib.parse.quote(prompt)
            url = (
                f"{self._base_url}/{encoded}"
                f"?width={IMAGE_OUTPUT_WIDTH}"
                f"&height={IMAGE_OUTPUT_HEIGHT}"
                f"&seed={rng_seed}"
                f"&format=webp"
            )

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "BloggerAIPublisher/1.0 "
                        "(image-generation-engine)"
                    ),
                },
            )

            with urllib.request.urlopen(req, timeout=60) as response:
                image_data = response.read()

            if not image_data:
                raise GenerationError("Pollinations returned empty response")

            temp_dir = Path("/tmp") / "pollinations_images"
            temp_dir.mkdir(parents=True, exist_ok=True)
            out_path = temp_dir / f"pollinations_{rng_seed}.webp"
            out_path.write_bytes(image_data)

            elapsed = int((time.perf_counter() - start) * 1000)

            return GeneratedImage(
                image_path=out_path,
                provider=self.name,
                generation_seed=rng_seed,
                generation_time_ms=elapsed,
            )

        except urllib.error.URLError as exc:
            raise GenerationError(
                f"Pollinations API request failed: {exc}"
            ) from exc
        except OSError as exc:
            raise GenerationError(
                f"Pollinations file write failed: {exc}"
            ) from exc
