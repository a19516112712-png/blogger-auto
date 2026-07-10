"""Image deduplication — perceptual hash comparison against database history.

Uses :mod:`imagehash` to compute a 64-bit perceptual hash (pHash).
Images are compared with a configurable Hamming distance threshold.

If the minimum Hamming distance to any previously stored hash is
≤ ``IMAGE_PHASH_THRESHOLD`` (default 5), the image is considered
a duplicate and must be regenerated.
"""

from __future__ import annotations

from pathlib import Path

import imagehash
from PIL import Image


class DeduplicationError(Exception):
    """Raised when deduplication processing fails."""


class ImageDeduplicator:
    """Detects duplicate images by perceptual hash comparison.

    Attributes:
        threshold: Maximum Hamming distance for a duplicate match.
    """

    def __init__(self, threshold: int | None = None) -> None:
        """Initialise with optional threshold override.

        Args:
            threshold: Hamming distance threshold. Defaults to
                ``IMAGE_PHASH_THRESHOLD`` from settings.
        """
        from config.settings import IMAGE_PHASH_THRESHOLD

        self.threshold: int = threshold if threshold is not None else IMAGE_PHASH_THRESHOLD

    def compute_phash(self, image_path: Path) -> str:
        """Compute the perceptual hash of an image.

        Args:
            image_path: Path to the image file.

        Returns:
            Hexadecimal string representation of the 64-bit pHash.

        Raises:
            DeduplicationError: If the hash cannot be computed.
        """
        try:
            img = Image.open(image_path)
            phash = imagehash.phash(img)
            return str(phash)
        except Exception as exc:
            raise DeduplicationError(
                f"Failed to compute pHash for {image_path}: {exc}"
            ) from exc

    def is_duplicate(
        self,
        phash: str,
        existing_hashes: list[str],
    ) -> bool:
        """Check whether a pHash is a duplicate of any existing hash.

        Args:
            phash:           Hex pHash string to check.
            existing_hashes: List of hex pHash strings from the database.

        Returns:
            ``True`` if the minimum Hamming distance to any existing hash
            is ≤ ``threshold``.
        """
        if not existing_hashes:
            return False

        try:
            target_hash = imagehash.hex_to_hash(phash)
        except Exception as exc:
            raise DeduplicationError(
                f"Failed to parse target hash '{phash}': {exc}"
            ) from exc

        for existing in existing_hashes:
            try:
                existing_hash = imagehash.hex_to_hash(existing)
                distance = target_hash - existing_hash
                if distance <= self.threshold:
                    return True
            except Exception:
                # Skip invalid hashes in the database
                continue

        return False

    def load_existing_hashes(self) -> list[str]:
        """Load all existing pHash values from the database.

        Returns:
            List of hex pHash strings.  Empty if the database is empty
            or the table has no ``phash`` column yet.
        """
        from database.database import fetch_all

        try:
            rows = fetch_all(
                "SELECT phash FROM generated_images WHERE phash != ''"
            )
            return [row["phash"] for row in rows]
        except Exception:
            return []
