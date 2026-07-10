"""SEO metadata generation for images.

Automatically generates:

- ``alt`` text
- ``title`` attribute
- ``caption``
- ``description``
- SEO keywords

All metadata is derived from the article slug and prompt text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImageMetadata:
    """SEO metadata for a generated image.

    Attributes:
        filename:    Filesystem filename (e.g. ``"100-japanese-baby-names.webp"``).
        alt_text:    Alt attribute for ``<img>`` tags (concise description).
        title:       Title attribute for the image.
        caption:     Caption displayed below the image.
        description: Longer description (meta tag / schema).
        seo_keywords: List of relevant keywords.
    """

    filename: str = ""
    alt_text: str = ""
    title: str = ""
    caption: str = ""
    description: str = ""
    seo_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, str | list[str]]:
        """Return metadata as a plain dictionary.

        Returns:
            Dictionary with all metadata fields.
        """
        return {
            "filename": self.filename,
            "alt_text": self.alt_text,
            "title": self.title,
            "caption": self.caption,
            "description": self.description,
            "seo_keywords": self.seo_keywords,
        }


class MetadataGenerator:
    """Generates SEO-friendly metadata for article hero images.

    Usage::

        gen = MetadataGenerator()
        meta = gen.generate("100 Japanese Baby Names", "japanese-baby-names")
    """

    def generate(
        self,
        title: str,
        slug: str,
        prompt_text: str = "",
    ) -> ImageMetadata:
        """Generate metadata from the article title and slug.

        Args:
            title:       Article H1 title.
            slug:        URL slug for the article.
            prompt_text: Original generation prompt (optional, used to
                         enrich descriptions).

        Returns:
            A :class:`ImageMetadata` dataclass.
        """
        filename = f"{slug}.webp"

        # Alt text: concise description
        alt_text = (
            f"{title} — Beautiful baby name ideas and meaningful name origins"
        )

        # Title attribute
        title_attr = f"{title} — Baby Name Ideas"

        # Caption
        caption = (
            f"Inspiring {title.lower()} — discover the perfect name for your baby"
        )

        # Description (SEO meta)
        description = (
            f"Explore our collection of {title.lower()}. "
            "Each name includes its meaning, origin, pronunciation, "
            "and cultural background."
        )

        # Keywords extracted from title
        keywords = self._extract_keywords(title, slug)

        return ImageMetadata(
            filename=filename,
            alt_text=alt_text[:200],
            title=title_attr[:200],
            caption=caption[:300],
            description=description[:350],
            seo_keywords=keywords,
        )

    @staticmethod
    def _extract_keywords(title: str, slug: str) -> list[str]:
        """Extract SEO keywords from the article title.

        Args:
            title: Article title.
            slug:  Article slug.

        Returns:
            A deduplicated list of keyword strings.
        """
        keywords: list[str] = []

        # Add slug-based keywords
        slug_parts = slug.replace("-", " ").replace("_", " ").split()
        keywords.extend(part.title() for part in slug_parts if len(part) > 2)

        # Add title-based keywords
        for word in title.split():
            clean = word.strip(" ,.!?;:'\"").lower()
            if len(clean) > 2 and clean not in ("the", "and", "for", "with", "that"):
                keywords.append(word.strip(" ,.!?;:'\""))

        # Remove duplicates while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for kw in keywords:
            lower = kw.lower()
            if lower not in seen:
                seen.add(lower)
                deduped.append(kw)

        return deduped[:10]  # Max 10 keywords
