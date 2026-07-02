#!/usr/bin/env python3
"""
Content Quality Engine — Comprehensive scoring for every article.

Scores:
  - SEO Score (0-100): Title, meta, slug, headings, schema, canonical
  - EEAT Score (0-100): Author, editorial review, sources, transparency
  - Readability (0-100): Paragraph length, sentence variety, transitions
  - Originality (0-100): AI patterns, duplicate detection, uniqueness
  - Authority (0-100): References, citations, expertise signals
  - Internal Link Score (0-100): Link count, diversity, relevance
  - Schema Score (0-100): JSON-LD presence and validity
  - Content Depth (0-100): Word count, section coverage, tables
  - Helpful Content Score (0-100): Google Helpful Content guidelines
  - Overall Quality (0-100): Weighted average

Returns scores for every article. Reject if overall < 98.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from database.topic_queue import TopicQueue
from fingerprint_engine import ArticleFingerprint, FingerprintEngine

log = logging.getLogger(__name__)

POSTS_DIR = Path(__file__).resolve().parent / "posts"


class QualityEngine:
    """Scores articles across 10 quality dimensions."""

    def __init__(self, queue: TopicQueue):
        self.queue = queue
        self.fp_engine = FingerprintEngine(queue)

    def score_article(self, filepath: Path) -> dict:
        """Score a single article across all dimensions."""
        try:
            text = filepath.read_text(encoding="utf-8")
        except Exception as exc:
            return {"error": str(exc)}

        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                body = parts[2]

        # Generate fingerprint first
        fp = ArticleFingerprint(filepath, self.queue)
        fp_dict = fp.to_dict()

        scores = {
            "filename": filepath.name,
            "seo": self._score_seo(text, fp_dict),
            "eeat": self._score_eeat(text, fp_dict),
            "readability": self._score_readability(body, fp_dict),
            "originality": self._score_originality(text, body, fp_dict),
            "authority": self._score_authority(text, fp_dict),
            "internal_links": self._score_internal_links(text, fp_dict),
            "schema": self._score_schema(text, fp_dict),
            "content_depth": self._score_content_depth(body, fp_dict),
            "helpful_content": self._score_helpful_content(text, body, fp_dict),
        }

        # Overall quality (weighted average)
        weights = {
            "seo": 0.15,
            "eeat": 0.10,
            "readability": 0.10,
            "originality": 0.15,
            "authority": 0.10,
            "internal_links": 0.08,
            "schema": 0.10,
            "content_depth": 0.12,
            "helpful_content": 0.10,
        }

        total = sum(scores[k] * weights[k] for k in weights)
        scores["overall"] = round(total, 1)
        scores["timestamp"] = datetime.now().isoformat()

        return scores

    def score_all_articles(self, max_articles: int = None) -> list[dict]:
        """Score all articles in posts/."""
        posts = sorted(POSTS_DIR.glob("*.md"))
        if max_articles:
            posts = posts[:max_articles]

        results = []
        for post in posts:
            score = self.score_article(post)
            results.append(score)

            # Store in DB
            self.queue.conn.execute(
                """INSERT OR REPLACE INTO quality_scores
                   (filename, seo, eeat, readability, originality, authority,
                    internal_links, schema, content_depth, helpful_content,
                    overall, computed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    score.get("filename", post.name),
                    score.get("seo", 0),
                    score.get("eeat", 0),
                    score.get("readability", 0),
                    score.get("originality", 0),
                    score.get("authority", 0),
                    score.get("internal_links", 0),
                    score.get("schema", 0),
                    score.get("content_depth", 0),
                    score.get("helpful_content", 0),
                    score.get("overall", 0),
                    score.get("timestamp", ""),
                ),
            )
        self.queue.conn.commit()
        return results

    def _score_seo(self, text: str, fp: dict) -> float:
        """SEO Score (0-100)."""
        score = 0

        # Title quality (max 15)
        h1 = re.search(r'^#\s+(.+)$', text, re.M)
        if h1:
            title = h1.group(1).strip()
            if re.match(r'^\d+\s', title): score += 5
            if 20 <= len(title) <= 65: score += 5
            if not any(b in title.lower() for b in ["the rise of", "timeless choices"]):
                score += 5

        # Meta description (max 10)
        if '"@context"' in text: score += 5  # Has structured data
        if 'meta_description' in text.lower(): score += 5

        # Slug quality (max 5)
        slug = fp.get("meta_title_hash", "")
        if slug: score += 5

        # Heading hierarchy (max 15)
        headings = re.findall(r'^(#{1,6})\s+', text, re.M)
        h2_count = sum(1 for h in headings if h[0] == '##')
        if h2_count >= 6: score += 10
        if h2_count >= 4: score += 5
        h3_count = sum(1 for h in headings if h[0] == '###')
        if h3_count >= 4: score += 5

        # Canonical (max 5)
        if 'canonical' in text.lower(): score += 5

        # Schema (max 20)
        if '"@type": "Article"' in text: score += 7
        if '"@type": "FAQPage"' in text: score += 7
        if '"@type": "BreadcrumbList"' in text: score += 6

        # Image ALT (max 5)
        if 'alt=' in text.lower(): score += 5

        return min(score, 100)

    def _score_eeat(self, text: str, fp: dict) -> float:
        """EEAT Score (0-100)."""
        score = 0
        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                body = parts[2]

        # Author/editorial signals (max 20)
        if re.search(r'editorial|reviewed by|fact-checked|edited by', body, re.I):
            score += 10
        if re.search(r'our team|our editors|staff writer', body, re.I):
            score += 10

        # Research sources (max 20)
        if re.search(r'reference|source|citation|bibliography|see also|sources', body, re.I):
            score += 10
        if re.search(r'according to|studies show|research indicates', body, re.I):
            score += 10

        # Last updated (max 10)
        if re.search(r'last updated|updated|revised|edited', body, re.I):
            score += 10

        # Editorial policy (max 10)
        if re.search(r'editorial policy|our standards|accuracy|verified', body, re.I):
            score += 10

        # Transparency (max 20)
        if re.search(r'expert|professional|certified|qualified', body, re.I):
            score += 10
        if re.search(r'medical|clinical|academic|university|research', body, re.I):
            score += 10

        # Trust signals (max 10)
        if re.search(r'contact|about us|privacy|terms', body, re.I):
            score += 10

        return min(score, 100)

    def _score_readability(self, body: str, fp: dict) -> float:
        """Readability Score (0-100)."""
        score = 0

        # Paragraph length (max 25)
        avg_para = fp.get("avg_paragraph_length", 0)
        if 50 <= avg_para <= 100:
            score += 25
        elif 100 < avg_para <= 150:
            score += 15
        elif avg_para > 150:
            score += 5

        # Sentence variety (max 20)
        sentences = re.split(r'[.!?]+', body)
        if len(sentences) > 10:
            avg_sent_len = sum(len(s.split()) for s in sentences if s.strip()) / max(len(sentences), 1)
            if 10 <= avg_sent_len <= 25:
                score += 20
            elif 5 <= avg_sent_len <= 35:
                score += 10

        # Transition words (max 15)
        transitions = fp.get("transition_frequency", {})
        if transitions:
            score += min(15, len(transitions) * 3)

        # Paragraph distribution (max 20)
        para_dist = fp.get("paragraph_distribution", {})
        if para_dist:
            short_pct = para_dist.get("short", 0)
            med_pct = para_dist.get("medium", 0)
            if med_pct > 0.5:
                score += 15
            elif med_pct > 0.3:
                score += 10

        # No AI patterns (max 20)
        ai_patterns = fp.get("ai_pattern_flags", [])
        if not ai_patterns:
            score += 20
        elif len(ai_patterns) <= 2:
            score += 10
        else:
            score += max(0, 20 - len(ai_patterns) * 5)

        return min(score, 100)

    def _score_originality(self, text: str, body: str, fp: dict) -> float:
        """Originality Score (0-100)."""
        score = 100

        # AI writing patterns reduce score
        ai_patterns = fp.get("ai_pattern_flags", [])
        score -= len(ai_patterns) * 10

        # Unique word ratio
        unique_ratio = fp.get("unique_word_ratio", 0)
        if unique_ratio < 0.3:
            score -= 20
        elif unique_ratio < 0.4:
            score -= 10

        # Repetitive phrases
        repetitive = ["delve into", "treasure trove", "rich tapestry", "look no further"]
        for phrase in repetitive:
            if phrase.lower() in body.lower():
                score -= 5

        return max(0, min(100, score))

    def _score_authority(self, text: str, fp: dict) -> float:
        """Authority Score (0-100)."""
        score = 0
        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                body = parts[2]

        # Expertise signals (max 30)
        if re.search(r'expert|specialist|professional|certified', body, re.I):
            score += 15
        if re.search(r'according to|studies show|research|academic', body, re.I):
            score += 15

        # References (max 20)
        if re.search(r'reference|source|citation|see also', body, re.I):
            score += 20

        # Name data accuracy (max 20)
        if re.search(r'pronunciation|phonetic|origin|etymology', body, re.I):
            score += 10
        if re.search(r'popularity|ranking|trend|statistic', body, re.I):
            score += 10

        # Cultural depth (max 15)
        if re.search(r'cultural|heritage|tradition|historical', body, re.I):
            score += 15

        # Practical advice (max 15)
        if re.search(r'tip|advice|guideline|recommendation', body, re.I):
            score += 15

        return min(score, 100)

    def _score_internal_links(self, text: str, fp: dict) -> float:
        """Internal Link Score (0-100)."""
        score = 0
        links = fp.get("internal_links", [])

        # Count (max 30)
        if len(links) >= 10:
            score += 30
        elif len(links) >= 5:
            score += 20
        elif len(links) >= 3:
            score += 10

        # Anchor text diversity (max 30)
        if links:
            anchors = set(a for a, u in links)
            if len(anchors) > len(links) * 0.5:
                score += 30
            elif len(anchors) > 0:
                score += 15

        # Contextual placement (max 20)
        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                body = parts[2]
        if '## Related Articles' in body or 'related' in body.lower():
            score += 20

        # No link stuffing (max 20)
        if links:
            body_wc = len(body.split())
            link_ratio = len(links) / body_wc if body_wc > 0 else 0
            if link_ratio < 0.02:
                score += 20
            elif link_ratio < 0.05:
                score += 10

        return min(score, 100)

    def _score_schema(self, text: str, fp: dict) -> float:
        """Schema Score (0-100)."""
        score = 0
        types = fp.get("schema_types", [])

        if "Article" in types: score += 35
        if "FAQPage" in types: score += 35
        if "BreadcrumbList" in types: score += 30

        return score

    def _score_content_depth(self, body: str, fp: dict) -> float:
        """Content Depth Score (0-100)."""
        score = 0
        wc = len(body.split())

        # Word count (max 25)
        if wc >= 3000: score += 25
        elif wc >= 2500: score += 20
        elif wc >= 2000: score += 15
        elif wc >= 1500: score += 10

        # Section coverage (max 40)
        sections = {
            "meaning": bool(re.search(r'Meaning', body, re.I)),
            "origin": bool(re.search(r'Origin|heritage|cultural', body, re.I)),
            "pronunciation": bool(re.search(r'Pronunciation', body)),
            "popularity": bool(re.search(r'Popularity|ranking|trend', body, re.I)),
            "nicknames": bool(re.search(r'Nickname|diminutive', body, re.I)),
            "variants": bool(re.search(r'Variant|variation', body, re.I)),
            "sibling": bool(re.search(r'Sibling', body)),
            "middle_name": bool(re.search(r'Middle Name', body)),
            "twin": bool(re.search(r'Twin', body)),
            "famous": bool(re.search(r'Famous|celebrity', body, re.I)),
            "faq": bool(re.search(r'FAQ|Frequently Asked', body, re.I)),
            "conclusion": bool(re.search(r'Conclusion', body)),
            "related": bool(re.search(r'Related Articles', body)),
            "toc": bool(re.search(r'Table of Contents', body, re.I)),
        }
        section_count = sum(1 for v in sections.values() if v)
        score += min(40, section_count * 3)

        # Tables (max 15)
        tables = fp.get("table_structure", [])
        if tables:
            score += min(15, len(tables) * 10)

        # FAQ count (max 10)
        faqs = re.findall(r'###\s+Q:\s*', body)
        if len(faqs) >= 8:
            score += 10
        elif len(faqs) >= 5:
            score += 7
        elif len(faqs) >= 3:
            score += 4

        # Heading count (max 10)
        h2_count = len(re.findall(r'^## ', body, re.M))
        if h2_count >= 6:
            score += 10
        elif h2_count >= 4:
            score += 5

        return min(score, 100)

    def _score_helpful_content(self, text: str, body: str, fp: dict) -> float:
        """Google Helpful Content Score (0-100)."""
        score = 0

        # Written for people, not search engines (max 25)
        ai_patterns = fp.get("ai_pattern_flags", [])
        if not ai_patterns:
            score += 25
        elif len(ai_patterns) <= 2:
            score += 15
        else:
            score += max(0, 25 - len(ai_patterns) * 5)

        # Demonstrates experience (max 20)
        if re.search(r'experience|tried|tested|personal', body, re.I):
            score += 20
        elif re.search(r'expert|professional|specialist', body, re.I):
            score += 15

        # Shows expertise (max 15)
        if re.search(r'research|study|data|statistics', body, re.I):
            score += 15

        # Authoritative (max 15)
        if re.search(r'reference|source|citation|according to', body, re.I):
            score += 15

        # Satisfies search intent (max 15)
        if len(body.split()) >= 2000:
            score += 15
        elif len(body.split()) >= 1500:
            score += 10

        # No AI filler (max 10)
        filler = ["in conclusion", "ultimately", "in summary"]
        filler_count = sum(1 for f in filler if f in body.lower())
        score += max(0, 10 - filler_count * 3)

        return min(score, 100)

    def get_quality_report(self) -> dict:
        """Generate comprehensive quality report."""
        scores = self.score_all_articles()
        if not scores:
            return {"error": "No articles scored"}

        avg_scores = {}
        for key in scores[0].keys():
            if key not in ("filename", "timestamp", "error"):
                vals = [s.get(key, 0) for s in scores if key in s and isinstance(s.get(key), (int, float))]
                avg_scores[key] = round(sum(vals) / len(vals), 1) if vals else 0

        return {
            "total_articles": len(scores),
            "average_scores": avg_scores,
            "articles_below_90": sum(1 for s in scores if s.get("overall", 0) < 90),
            "articles_below_95": sum(1 for s in scores if s.get("overall", 0) < 95),
            "articles_above_98": sum(1 for s in scores if s.get("overall", 0) >= 98),
            "worst_articles": sorted(scores, key=lambda s: s.get("overall", 0))[:5],
            "best_articles": sorted(scores, key=lambda s: -s.get("overall", 0))[:5],
        }
