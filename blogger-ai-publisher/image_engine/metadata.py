"""SEO metadata generation for images.

Automatically generates rich SEO metadata by analyzing the article title
through the Prompt Engine's ``analyze_title`` function, extracting
country, culture, gender, and audience to produce context-aware
descriptions.

Generated fields:
- ``filename`` (slug-based)
- ``alt`` text
- ``title`` attribute
- ``caption``
- ``description``
- SEO keywords
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImageMetadata:
    """SEO metadata for a generated image.

    Attributes:
        filename:      Filesystem filename (e.g. ``"100-japanese-baby-names.webp"``).
        alt_text:      Alt attribute for ``<img>`` tags (concise description).
        title:         Title attribute for the image.
        caption:       Caption displayed below the image.
        description:   Longer description (meta tag / schema).
        seo_keywords:  List of relevant keywords.
    """

    filename: str = ""
    alt_text: str = ""
    title: str = ""
    caption: str = ""
    description: str = ""
    seo_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, str | list[str]]:
        """Return metadata as a plain dictionary."""
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

    Uses the Prompt Engine's ``analyze_title`` to extract country,
    culture, gender, and audience context, then crafts metadata
    strings that reflect those attributes.

    Usage::

        gen = MetadataGenerator()
        meta = gen.generate("100 Japanese Baby Names", "japanese-baby-names")
    """

    _COUNTRY_LABEL: dict[str, str] = {
        "japan": "Japanese",
        "ireland": "Irish",
        "france": "French",
        "korea": "Korean",
        "italy": "Italian",
        "spain": "Spanish",
        "germany": "German",
        "india": "Indian",
        "arabic": "Arabic",
        "scandinavia": "Scandinavian",
        "africa": "African",
    }

    _GENDER_LABEL: dict[str, str] = {
        "girl_names": "girl",
        "boy_names": "boy",
        "gender_neutral": "gender-neutral",
    }

    def generate(
        self,
        title: str,
        slug: str,
        prompt_text: str = "",
    ) -> ImageMetadata:
        """Generate metadata from the article title and slug.

        Analyzes the title to extract country, gender, and cultural
        context, then tailors alt text, caption, and description
        accordingly.

        Args:
            title:       Article H1 title.
            slug:        URL slug for the article.
            prompt_text: Original generation prompt (optional).

        Returns:
            A :class:`ImageMetadata` dataclass.
        """
        filename = f"{slug}.webp"

        # Analyze the title for context-aware metadata
        try:
            from prompt_engine.analyzer import analyze_title
            analysis = analyze_title(title)
            country_label = self._COUNTRY_LABEL.get(analysis.country, "")
            gender_label = self._GENDER_LABEL.get(analysis.category, "")
        except Exception:
            country_label = ""
            gender_label = ""

        # Build a context prefix for richer descriptions
        context_parts = [p for p in [country_label, gender_label] if p]
        context_prefix = f"{' '.join(context_parts)} " if context_parts else ""

        # Alt text: concise, SEO-friendly
        alt_text = (
            f"{title} — {context_prefix}beautiful baby name ideas "
            f"with meanings, origins, and pronunciation guide"
        )

        # Title attribute
        title_attr = f"{title} — Baby Name Ideas"

        # Caption
        caption = (
            f"Inspiring {title.lower()}. "
            f"Discover {context_prefix}perfect {context_prefix}baby name "
            f"for your little one."
        )

        # Description (SEO meta)
        description = (
            f"Explore our curated collection of {title.lower()}. "
            f"{context_prefix.capitalize()}Each name includes its "
            f"meaning, origin, pronunciation, and cultural background."
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

        slug_parts = slug.replace("-", " ").replace("_", " ").split()
        keywords.extend(part.title() for part in slug_parts if len(part) > 2)

        for word in title.split():
            clean = word.strip(" ,.!?;:'\"").lower()
            if len(clean) > 2 and clean not in ("the", "and", "for", "with", "that"):
                keywords.append(word.strip(" ,.!?;:'\""))

        seen: set[str] = set()
        deduped: list[str] = []
        for kw in keywords:
            lower = kw.lower()
            if lower not in seen:
                seen.add(lower)
                deduped.append(kw)

        return deduped[:10]
