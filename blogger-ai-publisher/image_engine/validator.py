"""Image validation — rejects corrupt, blank, single-colour, or undersized images.

Validation rules
----------------
1. File must be readable by Pillow.
2. Dimensions must be >= configured minimum (1600×900).
3. Image must not be blank (all black or all white).
4. Image must not be single-colour (standard deviation > threshold).
5. Format must be supported by Pillow.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError


class ValidationError(Exception):
    """Raised when an image fails validation."""


class ImageValidator:
    """Validates generated images against quality and dimension requirements.

    Attributes:
        min_width:  Minimum acceptable width in pixels.
        min_height: Minimum acceptable height in pixels.
    """

    def __init__(
        self,
        min_width: int | None = None,
        min_height: int | None = None,
    ) -> None:
        """Initialise with optional overrides from settings.

        Args:
            min_width:  Minimum width. Defaults to ``IMAGE_OUTPUT_WIDTH``.
            min_height: Minimum height. Defaults to ``IMAGE_OUTPUT_HEIGHT``.
        """
        from config.settings import IMAGE_OUTPUT_WIDTH, IMAGE_OUTPUT_HEIGHT

        self.min_width: int = min_width or IMAGE_OUTPUT_WIDTH
        self.min_height: int = min_height or IMAGE_OUTPUT_HEIGHT

    def validate(self, image_path: Path) -> Path:
        """Validate an image file.

        Args:
            image_path: Path to the image file to validate.

        Returns:
            The same ``image_path`` (for chaining).

        Raises:
            ValidationError: If any validation check fails.
        """
        self._check_file_exists(image_path)
        img = self._open_image(image_path)
        self._check_dimensions(img, image_path)
        self._check_not_blank(img, image_path)
        self._check_not_single_color(img, image_path)
        return image_path

    # ------------------------------------------------------------------
    # Internal checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_file_exists(image_path: Path) -> None:
        """Ensure the file exists and is non-empty."""
        if not image_path.exists():
            raise ValidationError(f"Image file does not exist: {image_path}")
        if image_path.stat().st_size == 0:
            raise ValidationError(f"Image file is empty: {image_path}")

    @staticmethod
    def _open_image(image_path: Path) -> Image.Image:
        """Open the image with Pillow."""
        try:
            return Image.open(image_path).convert("RGB")
        except UnidentifiedImageError as exc:
            raise ValidationError(
                f"Cannot identify image file: {image_path} — {exc}"
            ) from exc
        except Exception as exc:
            raise ValidationError(
                f"Failed to open image: {image_path} — {exc}"
            ) from exc

    def _check_dimensions(
        self,
        img: Image.Image,
        image_path: Path,
    ) -> None:
        """Reject images smaller than the configured minimum."""
        w, h = img.size
        if w < self.min_width or h < self.min_height:
            raise ValidationError(
                f"Image too small: {w}×{h} (min {self.min_width}×{self.min_height})"
                f" — {image_path}"
            )

    @staticmethod
    def _check_not_blank(img: Image.Image, image_path: Path) -> None:
        """Reject images that are all black or all white (blank)."""
        arr = np.array(img, dtype=np.uint8)
        mean = arr.mean()
        std = arr.std()

        # All-black → mean ≈ 0
        if mean < 1.0:
            raise ValidationError(
                f"Image is blank (all black, mean={mean:.1f}): {image_path}"
            )
        # All-white → mean ≈ 255
        if mean > 254.0:
            raise ValidationError(
                f"Image is blank (all white, mean={mean:.1f}): {image_path}"
            )

        # Very low variance → single colour or near-single-colour
        if std < 5.0:
            raise ValidationError(
                f"Image has very low variance (std={std:.1f}) — "
                f"likely single colour: {image_path}"
            )

    @staticmethod
    def _check_not_single_color(img: Image.Image, image_path: Path) -> None:
        """Reject images that are single colour.

        Checks the number of unique pixels (sampled).  If all sampled
        pixels are the same, the image is considered single-colour.
        """
        arr = np.array(img, dtype=np.uint8)
        # Sample ~1000 pixels in a grid pattern
        h, w = arr.shape[:2]
        step = max(1, (h * w // 1000) ** 0.5)
        step = max(1, int(step))
        sampled = arr[::step, ::step]

        if sampled.size == 0:
            raise ValidationError(
                f"Image has no valid pixels: {image_path}"
            )

        # Check if all sampled pixels are identical
        flat = sampled.reshape(-1, 3)
        unique = len(set(tuple(p) for p in flat[:1000]))  # limit checks
        if unique == 1:
            raise ValidationError(
                f"Image is single colour (all sampled pixels identical): {image_path}"
            )
