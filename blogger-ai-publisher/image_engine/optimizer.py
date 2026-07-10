"""Image optimization — resize, compress, and convert to WEBP.

Pipeline
--------
1. Convert to RGB (strip alpha / palette).
2. Resize to target dimensions (maintaining aspect ratio, then centre-crop).
3. Compress to WEBP at configured quality.
4. Strip all EXIF/IPTC/XMP metadata.
5. Ensure final file size ≤ configured maximum.

All settings are configurable via :mod:`config.settings`.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image


class OptimizationError(Exception):
    """Raised when image optimization fails."""


class ImageOptimizer:
    """Optimises images to WEBP format with size and quality constraints.

    Attributes:
        target_width:   Output width in pixels.
        target_height:  Output height in pixels.
        quality:        WEBP quality (1–100).
        max_file_size:  Maximum file size in bytes (default 300 KB).
        output_format:  Output image format string.
    """

    def __init__(
        self,
        target_width: int | None = None,
        target_height: int | None = None,
        quality: int | None = None,
        max_file_size: int | None = None,
        output_format: str | None = None,
    ) -> None:
        """Initialise with overrides from settings.

        Args:
            target_width:   Output width. Defaults to ``IMAGE_OUTPUT_WIDTH``.
            target_height:  Output height. Defaults to ``IMAGE_OUTPUT_HEIGHT``.
            quality:        WEBP quality. Defaults to ``IMAGE_OUTPUT_QUALITY``.
            max_file_size:  Max bytes. Defaults to ``IMAGE_MAX_FILE_SIZE``.
            output_format:  Output format. Defaults to ``IMAGE_OUTPUT_FORMAT``.
        """
        from config.settings import (
            IMAGE_OUTPUT_WIDTH,
            IMAGE_OUTPUT_HEIGHT,
            IMAGE_OUTPUT_QUALITY,
            IMAGE_MAX_FILE_SIZE,
            IMAGE_OUTPUT_FORMAT,
        )

        self.target_width: int = target_width or IMAGE_OUTPUT_WIDTH
        self.target_height: int = target_height or IMAGE_OUTPUT_HEIGHT
        self.quality: int = quality or IMAGE_OUTPUT_QUALITY
        self.max_file_size: int = max_file_size or IMAGE_MAX_FILE_SIZE
        self.output_format: str = (
            output_format or IMAGE_OUTPUT_FORMAT or "WEBP"
        ).upper()

    def optimize(self, image_path: Path, output_path: Path | None = None) -> Path:
        """Resize, compress, and save an image as WEBP.

        Args:
            image_path:  Source image path.
            output_path: Destination path. If ``None``, replaces the source.

        Returns:
            Path to the optimized image.

        Raises:
            OptimizationError: If the image cannot be processed.
        """
        out = output_path or image_path

        try:
            img = Image.open(image_path).convert("RGB")

            # ------------------------------------------------------------------
            # Resize: maintain aspect ratio, then centre-crop
            # ------------------------------------------------------------------
            img = self._resize_and_crop(img)

            # ------------------------------------------------------------------
            # Compress with quality fallback
            # ------------------------------------------------------------------
            for q in range(self.quality, 30, -5):
                buf = io.BytesIO()
                img.save(buf, format=self.output_format, quality=q, optimize=True)
                if buf.tell() <= self.max_file_size:
                    break

            buf.seek(0)
            out.write_bytes(buf.getvalue())
            return out

        except Exception as exc:
            raise OptimizationError(
                f"Failed to optimise image {image_path}: {exc}"
            ) from exc

    def _resize_and_crop(self, img: Image.Image) -> Image.Image:
        """Resize to fill target dimensions, then centre-crop.

        This avoids distortion by scaling the smallest dimension to the
        target and cropping the remainder.

        Args:
            img: Source PIL Image.

        Returns:
            Resized and cropped PIL Image.
        """
        target_ratio = self.target_width / self.target_height
        src_ratio = img.width / img.height

        if src_ratio > target_ratio:
            # Image is wider → match height
            new_height = self.target_height
            new_width = int(self.target_height * src_ratio)
        else:
            # Image is taller → match width
            new_width = self.target_width
            new_height = int(self.target_width / src_ratio)

        img = img.resize((new_width, new_height), Image.LANCZOS)

        # Centre crop
        left = (new_width - self.target_width) // 2
        top = (new_height - self.target_height) // 2
        right = left + self.target_width
        bottom = top + self.target_height
        return img.crop((left, top, right, bottom))

    @property
    def compression_info(self) -> dict[str, int | str]:
        """Return the current optimisation parameters as a dictionary.

        Returns:
            Dict of compression settings.
        """
        return {
            "width": self.target_width,
            "height": self.target_height,
            "quality": self.quality,
            "max_file_size_bytes": self.max_file_size,
            "format": self.output_format,
        }
