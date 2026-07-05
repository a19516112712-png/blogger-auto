"""Shared utility functions extracted from duplicate modules."""
from .helpers import (
    slugify,
    sanitize_labels,
    sanitize_title,
    extract_title_from_text,
    build_frontmatter,
    strip_existing_frontmatter,
    strip_fences,
    count_words,
    generate_meta_description,
    enforce_title_rules,
    BANNED_PHRASES,
    MIN_TITLE_LENGTH,
    MIN_BODY_WORDS,
    MIN_LABELS,
    MAX_LABELS,
    FORBIDDEN_LABELS,
)
from .yaml_parser import parse_frontmatter, extract_date_from_filename

__all__ = [
    "slugify", "sanitize_labels", "sanitize_title",
    "extract_title_from_text", "build_frontmatter",
    "strip_existing_frontmatter", "strip_fences", "count_words",
    "generate_meta_description", "enforce_title_rules",
    "BANNED_PHRASES", "MIN_TITLE_LENGTH", "MIN_BODY_WORDS",
    "MIN_LABELS", "MAX_LABELS", "FORBIDDEN_LABELS",
    "parse_frontmatter", "extract_date_from_filename",
]
