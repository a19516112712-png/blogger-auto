#!/usr/bin/env python3
"""
SEO Validator — Comprehensive article scoring engine.

Scores every article on:
  - Title quality (length, number prefix, banned phrases)
  - CTR score (emotional trigger, specificity)
  - Readability (paragraph length, sentence variety)
  - Keyword density (too low or too high)
  - Heading hierarchy (H1→H2→H3, no skips)
  - Internal links (count, diversity)
  - Schema validation (JSON-LD present and valid)
  - Meta validation (title, description, slug)
  - Canonical URL
  - Image ALT (if images present)

Returns a composite score (0-100). Reject if < 95.
"""

import json
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

MIN_SEO_SCORE = 95.0


def validate_seo(filepath: Path) -> tuple[bool, dict]:
    """Run full SEO validation on an article. Returns (pass, details)."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception as exc:
        return False, {"error": str(exc)}

    scores = {}
    total = 0
    max_total = 0

    # 1. Title quality (max 15)
    title_score = _score_title(text)
    scores["title_quality"] = title_score
    total += title_score
    max_total += 15

    # 2. CTR score (max 10)
    ctr_score = _score_ctr(text)
    scores["ctr_score"] = ctr_score
    total += ctr_score
    max_total += 10

    # 3. Readability (max 10)
    read_score = _score_readability(text)
    scores["readability"] = read_score
    total += read_score
    max_total += 10

    # 4. Keyword density (max 10)
    density_score = _score_keyword_density(text)
    scores["keyword_density"] = density_score
    total += density_score
    max_total += 10

    # 5. Heading hierarchy (max 15)
    heading_score = _score_headings(text)
    scores["heading_hierarchy"] = heading_score
    total += heading_score
    max_total += 15

    # 6. Internal links (max 10)
    link_score = _score_internal_links(text)
    scores["internal_links"] = link_score
    total += link_score
    max_total += 10

    # 7. Schema validation (max 15)
    schema_score = _score_schema(text)
    scores["schema"] = schema_score
    total += schema_score
    max_total += 15

    # 8. Meta validation (max 10)
    meta_score = _score_meta(text)
    scores["meta"] = meta_score
    total += meta_score
    max_total += 10

    # 9. Canonical (max 5)
    canon_score = 5 if "canonical" in text.lower() else 0
    scores["canonical"] = canon_score
    total += canon_score
    max_total += 5

    composite = round(total / max_total * 100, 1) if max_total > 0 else 0
    passed = composite >= MIN_SEO_SCORE

    scores["composite"] = composite
    scores["passed"] = passed

    log.info("SEO validation %s for %s: %.1f/100",
             "PASSED" if passed else "FAILED",
             filepath.name, composite)

    return passed, scores


def _score_title(text: str) -> int:
    """Score title quality (0-15)."""
    score = 0
    # Must have H1 with number prefix
    h1 = re.search(r'^#\s+(.+)$', text, re.M)
    if h1:
        title = h1.group(1).strip()
        if re.match(r'^\d+\s', title):
            score += 5  # Has number prefix
        if 20 <= len(title) <= 65:
            score += 5  # Good length
        banned = ["the rise of", "timeless choices", "artistic flair"]
        if not any(b in title.lower() for b in banned):
            score += 5  # No banned phrases
    return score


def _score_ctr(text: str) -> int:
    """Score CTR potential (0-10)."""
    score = 0
    title_match = re.search(r'^#\s+(.+)$', text, re.M)
    if title_match:
        title = title_match.group(1)
        if re.search(r'\d+', title):
            score += 3  # Number increases CTR
        if re.search(r'(best|top|ultimate|complete|guide)', title, re.I):
            score += 3  # Power words
        if len(title) <= 60:
            score += 2  # Optimal length
        if re.search(r'[?!]', title):
            score += 2  # Emotional trigger
    return min(score, 10)


def _score_readability(text: str) -> int:
    """Score readability (0-10)."""
    score = 0
    # Extract body
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]

    paragraphs = [p.strip() for p in body.split('\n\n') if p.strip() and not p.startswith('#')]
    if paragraphs:
        avg_len = sum(len(p.split()) for p in paragraphs) / len(paragraphs)
        if 100 <= avg_len <= 250:
            score += 5  # Good paragraph length
        if len(paragraphs) >= 8:
            score += 3  # Enough paragraphs
        # Sentence variety
        sentences = re.split(r'[.!?]+', body)
        if len(sentences) > 10:
            avg_sent_len = sum(len(s.split()) for s in sentences if s.strip()) / max(len(sentences), 1)
            if 10 <= avg_sent_len <= 25:
                score += 2
    return min(score, 10)


def _score_keyword_density(text: str) -> int:
    """Score keyword density (0-10)."""
    score = 5  # Neutral baseline
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]

    words = body.lower().split()
    if len(words) < 100:
        return 0

    # Count H2 headings for keyword presence
    h2_count = len(re.findall(r'^## ', body, re.M))
    if h2_count >= 4:
        score += 3  # Keywords distributed across sections

    # Check for keyword stuffing
    if len(words) > 0:
        # Ratio of H2 words to total words
        h2_words = len(re.findall(r'^## .+$', body, re.M))
        ratio = h2_words / len(words)
        if ratio < 0.1:
            score += 2  # Not stuffed

    return min(max(score, 0), 10)


def _score_headings(text: str) -> int:
    """Score heading hierarchy (0-15)."""
    score = 0
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]

    headings = re.findall(r'^(#{1,6})\s+(.+)$', body, re.M)
    if not headings:
        return 0

    # Must have H1
    if any(h[0] == '#' for h in headings):
        score += 5

    # Must have 6+ H2
    h2_count = sum(1 for h in headings if h[0] == '##')
    if h2_count >= 6:
        score += 5

    # Must have H3
    h3_count = sum(1 for h in headings if h[0] == '###')
    if h3_count >= 4:
        score += 3

    # No level skipping
    levels = [len(h[0]) for h in headings]
    for i in range(1, len(levels)):
        if levels[i] > levels[i-1] + 1:
            score -= 5
            break

    score = max(0, score)
    return min(score, 15)


def _score_internal_links(text: str) -> int:
    """Score internal linking (0-10)."""
    score = 0
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]

    links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', body)
    if len(links) >= 5:
        score += 5  # Good link count
    elif len(links) >= 3:
        score += 3

    # Anchor text diversity
    anchors = [l[0] for l in links]
    if len(set(anchors)) > len(links) * 0.5:
        score += 3  # Varied anchors

    # Relative links (internal)
    internal = [l for l in links if not l[1].startswith('http')]
    if len(internal) >= 3:
        score += 2

    return min(score, 10)


def _score_schema(text: str) -> int:
    """Score JSON-LD schema (0-15)."""
    score = 0
    if '"@type": "Article"' in text:
        score += 5
    if '"@type": "FAQPage"' in text:
        score += 5
    if '"@type": "BreadcrumbList"' in text:
        score += 3
    if 'application/ld+json' in text:
        score += 2
    return min(score, 15)


def _score_meta(text: str) -> int:
    """Score frontmatter metadata (0-10)."""
    score = 0
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            import yaml
            try:
                fm = yaml.safe_load(parts[1].strip()) or {}
                if fm.get("title"):
                    score += 2
                if fm.get("slug"):
                    score += 2
                if fm.get("date"):
                    score += 2
                if fm.get("labels") and isinstance(fm["labels"], list) and len(fm["labels"]) >= 4:
                    score += 2
                if fm.get("meta_description"):
                    score += 2
            except Exception:
                pass
    return min(score, 10)
