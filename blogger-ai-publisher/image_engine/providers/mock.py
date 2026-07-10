"""Mock image provider — generates in-memory test images.

Used for testing and CI environments where network access is unavailable.
Generates a solid-colour image with a simple text overlay.
"""

from __future__ import annotations

import io
import random
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from image_engine.base import (
    BaseProvider,
    ConfigurationError,
    GeneratedImage,
    GenerationError,
)


class MockProvider(BaseProvider):
    """Provider that creates in-memory test images (no network required).

    The image is a gradient background with the prompt text rendered on it.
    Dimensions match the configured output size (default 1600×900).

    Attributes:
        name: Provider identifier (``"mock"``).
    """

    name: str = "mock"

    def _validate_config(self) -> None:
        """Mock provider has no required configuration."""

    def generate(self, prompt: str, seed: int | None = None) -> GeneratedImage:
        """Generate a test image locally using Pillow.

        Args:
            prompt: Text to render on the image.
            seed:   Random seed for reproducibility.

        Returns:
            A :class:`GeneratedImage` with a temporary file.

        Raises:
            GenerationError: If image creation fails.
        """
        start = time.perf_counter()
        rng_seed = seed if seed is not None else random.randint(0, 2**32 - 1)
        rng = random.Random(rng_seed)

        # Load actual settings — use imports here to avoid circular deps
        # at module level.
        from config.settings import IMAGE_OUTPUT_WIDTH, IMAGE_OUTPUT_HEIGHT

        try:
            width = IMAGE_OUTPUT_WIDTH
            height = IMAGE_OUTPUT_HEIGHT

            # Create a gradient background
            img = Image.new("RGB", (width, height), color=self._random_pastel(rng))
            draw = ImageDraw.Draw(img)

            # Draw a few decorative circles
            for _ in range(rng.randint(3, 8)):
                cx = rng.randint(0, width)
                cy = rng.randint(0, height)
                r = rng.randint(50, 300)
                color = self._random_pastel(rng, alpha=60)
                draw.ellipse(
                    [cx - r, cy - r, cx + r, cy + r],
                    fill=color,
                )

            # Draw prompt text (truncated to fit)
            text = prompt[:80]
            try:
                font = ImageFont.truetype(
                    "/System/Library/Fonts/Helvetica.ttc", 40
                )
            except (OSError, IOError):
                font = ImageFont.load_default()

            # Center text
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx = (width - tw) // 2
            ty = (height - th) // 2
            draw.text((tx, ty), text, fill="white", font=font)

            # Save to bytes first, then write to temp file
            buf = io.BytesIO()
            img.save(buf, format="WEBP", quality=90)
            buf.seek(0)

            temp_dir = Path("/tmp") / "mock_images"
            temp_dir.mkdir(parents=True, exist_ok=True)
            out_path = temp_dir / f"mock_{rng_seed}.webp"
            out_path.write_bytes(buf.getvalue())

            elapsed = int((time.perf_counter() - start) * 1000)

            return GeneratedImage(
                image_path=out_path,
                provider=self.name,
                generation_seed=rng_seed,
                generation_time_ms=elapsed,
            )

        except Exception as exc:
            raise GenerationError(
                f"Mock provider failed: {exc}"
            ) from exc

    @staticmethod
    def _random_pastel(rng: random.Random, alpha: int = 255) -> tuple[int, ...]:
        """Return a random pastel RGB(A) colour."""
        r = rng.randint(180, 255)
        g = rng.randint(180, 255)
        b = rng.randint(180, 255)
        if alpha < 255:
            return (r, g, b, alpha)
        return (r, g, b)
