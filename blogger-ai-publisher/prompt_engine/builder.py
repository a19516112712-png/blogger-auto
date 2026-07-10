"""Prompt builder — constructs unique image prompts from YAML component libraries.

Randomly selects component fragments from each YAML category and combines
them into a rich prompt string.  Each invocation produces a different prompt
thanks to :py:mod:`random` shuffling with a fresh seed.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import yaml

from prompt_engine.models import PromptComponents

# ---------------------------------------------------------------------------
# YAML library loader
# ---------------------------------------------------------------------------
_LIBRARY_DIR = Path(__file__).resolve().parent.parent / "prompt_library"

# Cache for loaded YAML libraries (loaded once at import time).
_LIBRARY_CACHE: dict[str, dict[str, list[str]]] = {}


def _load_library(name: str) -> dict[str, list[str]]:
    """Load a YAML library file, caching the result.

    Args:
        name: YAML filename without extension (e.g. ``"subject"``).

    Returns:
        Dictionary mapping subcategory → list of prompt fragments.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
    """
    if name not in _LIBRARY_CACHE:
        path = _LIBRARY_DIR / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Prompt library not found: {path}")
        with path.open(encoding="utf-8") as fh:
            _LIBRARY_CACHE[name] = yaml.safe_load(fh)
    return _LIBRARY_CACHE[name]


# ---------------------------------------------------------------------------
# Component selection
# ---------------------------------------------------------------------------
def _pick_fragments(
    library_name: str,
    category: str = "",
    count: int = 1,
) -> list[str]:
    """Pick random fragment(s) from a named YAML library.

    Args:
        library_name: Name of the YAML file (e.g. ``"subject"``).
        category:     Optional subcategory within the library.  If empty,
                      picks from *all* categories in that library.
        count:        Number of fragments to pick (default 1).

    Returns:
        A list of chosen prompt fragment strings.
    """
    data = _load_library(library_name)

    if category:
        pool: list[str] = data.get(category, [])
    else:
        pool = [
            fragment
            for sublist in data.values()
            for fragment in (sublist if isinstance(sublist, list) else [sublist])
        ]

    if not pool:
        return []

    return random.sample(pool, min(count, len(pool)))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def build_components(analysis_category: str = "") -> PromptComponents:
    """Build a :class:`~prompt_engine.models.PromptComponents` from the YAML
    library, selecting random fragments for each category.

    Args:
        analysis_category: The category returned by ``analyzer.analyze_title``.
                           Used to bias the *subject* selection.

    Returns:
        A populated :class:`~prompt_engine.models.PromptComponents` with at
        least one fragment per component category.
    """
    # Use the analysis category to select subject, fall back to random.
    subject_category: str = analysis_category if analysis_category in (
        "girl_names", "boy_names", "gender_neutral", "nature_names",
        "mythology_names", "vintage_names", "international_names",
    ) else ""

    # If the category is not a subject category, map it.
    _CATEGORY_FALLBACK: dict[str, str] = {
        "biblical_names": "mythology_names",
        "unique_names": "gender_neutral",
        "names_by_meaning": "mythology_names",
    }
    if not subject_category:
        subject_category = _CATEGORY_FALLBACK.get(analysis_category, "gender_neutral")

    components = PromptComponents(
        subject=_pick_fragments("subject", subject_category, count=1),
        camera=_pick_fragments("camera", "angles", count=1)
               + _pick_fragments("camera", "lenses", count=1)
               + _pick_fragments("camera", "focus", count=1),
        lighting=_pick_fragments("lighting", count=2),
        composition=_pick_fragments("composition", count=2),
        background=_pick_fragments("background", count=1),
        style=_pick_fragments("style", count=2),
        color=_pick_fragments("color", count=1),
        mood=_pick_fragments("mood", count=1),
        negative=_pick_fragments("negative", count=3),
    )
    return components


def components_to_prompt(components: PromptComponents) -> str:
    """Convert a :class:`~prompt_engine.models.PromptComponents` into a single
    comma-separated positive prompt string (negative excluded).

    Args:
        components: The component set produced by :func:`build_components`.

    Returns:
        A comma-separated prompt string.
    """
    parts: list[str] = []
    for lst in (components.subject, components.camera, components.lighting,
                components.composition, components.background,
                components.style, components.color, components.mood):
        parts.extend(fragment for fragment in lst if fragment)
    return ", ".join(parts)


def components_to_negative_prompt(components: PromptComponents) -> str:
    """Extract the negative prompt string from components.

    Args:
        components: The component set.

    Returns:
        A comma-separated negative prompt string.
    """
    return ", ".join(f for f in components.negative if f)
