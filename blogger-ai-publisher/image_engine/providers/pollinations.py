"""Pollinations AI image provider — free, open image generation API.

Uses the public Pollinations API endpoint:

    https://image.pollinations.ai/prompt/{prompt}

No API key is required.  The endpoint returns raw image bytes.

Configuration
-------------
- Timeout: 20 seconds (configurable via ``IMAGE_PROVIDER_TIMEOUT``).
- Retries: 3 attempts per image (manager handles provider fallback).
- Output: WEBP, 1600×900, quality=90, RGB, max 300 KB.
- Seed: one random seed per image (logged).
"""

from __future__ import annotations

import logging
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from image_engine.base import (
    BaseProvider,
    GeneratedImage,
    GenerationError,
)

log = logging.getLogger(__name__)


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
        from config.settings import POLLINATIONS_BASE_URL, IMAGE_PROVIDER_TIMEOUT

        self._base_url: str = base_url or POLLINATIONS_BASE_URL
        self._timeout: int = IMAGE_PROVIDER_TIMEOUT
        super().__init__()

    def _validate_config(self) -> None:
        """Pollinations requires no API keys — always valid."""

    def generate(self, prompt: str, seed: int | None = None) -> GeneratedImage:
        """Generate an image via the Pollinations API.

        Args:
            prompt: Text prompt describing the desired image.
            seed:   Optional seed for reproducibility.  If ``None``,
                    a random seed is generated.

        Returns:
            A :class:`GeneratedImage` with the downloaded file.

        Raises:
            GenerationError: If the API request fails or returns no data.
        """
        from config.settings import IMAGE_OUTPUT_WIDTH, IMAGE_OUTPUT_HEIGHT

        start = time.perf_counter()
        rng_seed = seed if seed is not None else random.randint(0, 2**32 - 1)
        retry_count = 0

        for attempt in range(1, 4):  # up to 3 attempts
            try:
                encoded = urllib.parse.quote(prompt)
                url = (
                    f"{self._base_url}/{encoded}"
                    f"?width={IMAGE_OUTPUT_WIDTH}"
                    f"&height={IMAGE_OUTPUT_HEIGHT}"
                    f"&seed={rng_seed}"
                    f"&format=webp"
                    f"&quality=90"
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

                with urllib.request.urlopen(req, timeout=self._timeout) as response:
                    image_data = response.read()

                if not image_data:
                    raise GenerationError("Pollinations returned empty response")

                file_size_kb = len(image_data) / 1024
                elapsed = int((time.perf_counter() - start) * 1000)

                temp_dir = Path("/tmp") / "pollinations_images"
                temp_dir.mkdir(parents=True, exist_ok=True)
                out_path = temp_dir / f"pollinations_{rng_seed}.webp"
                out_path.write_bytes(image_data)

                log.info(
                    "Pollinations: provider=%s seed=%d elapsed=%dms "
                    "retries=%d size=%.1fKB path=%s",
                    self.name,
                    rng_seed,
                    elapsed,
                    retry_count,
                    file_size_kb,
                    out_path.name,
                )

                return GeneratedImage(
                    image_path=out_path,
                    provider=self.name,
                    generation_seed=rng_seed,
                    generation_time_ms=elapsed,
                )

            except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
                retry_count += 1
                if attempt < 3:
                    delay = attempt * 2  # linear backoff: 2s, 4s
                    log.warning(
                        "Pollinations attempt %d/3 failed (seed=%d): %s "
                        "— retrying in %ds",
                        attempt,
                        rng_seed,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    elapsed = int((time.perf_counter() - start) * 1000)
                    log.error(
                        "Pollinations exhausted after 3 attempts "
                        "(seed=%d, elapsed=%dms): %s",
                        rng_seed,
                        elapsed,
                        exc,
                    )
                    raise GenerationError(
                        f"Pollinations failed after 3 retries: {exc}"
                    ) from exc

            except Exception as exc:
                elapsed = int((time.perf_counter() - start) * 1000)
                log.error(
                    "Pollinations unexpected error (seed=%d, elapsed=%dms): %s",
                    rng_seed,
                    elapsed,
                    exc,
                )
                raise GenerationError(
                    f"Pollinations unexpected error: {exc}"
                ) from exc

        # Should not reach here
        raise GenerationError("Pollinations exhausted all retries")
