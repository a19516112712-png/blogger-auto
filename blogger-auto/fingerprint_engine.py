#!/usr/bin/env python3
"""
Content Fingerprint Engine — Structural deduplication system.

Every article gets a fingerprint composed of:
  - Introduction hash (first 3 paragraphs normalized)
  - Heading hierarchy (H2/H3 titles as ordered tuple)
  - FAQ question set (normalized question texts)
  - Table structure (column count, row count, column headers)
  - Paragraph length distribution (bucketed histogram)
  - Transition word frequency
  - Conclusion hash (last 2 paragraphs normalized)
  - Internal link set (target slugs)
  - Meta title hash
  - Meta description hash
  - Schema presence (which JSON-LD types exist)

Before generating or optimizing an article:
  - Compare fingerprint against all existing fingerprints
  - If structural similarity > 15%, reject or rewrite
  - Store fingerprint + similarity history in SQLite

Never allow two articles to share:
  - Introduction
  - Conclusion
  - FAQ questions
  - Heading hierarchy
  - Table structure
  - Paragraph flow patterns
"""

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from database.topic_queue import TopicQueue

log = logging.getLogger(__name__)

# ── Transition words for pattern analysis ──
TRANSITION_WORDS = [
    "however", "moreover", "furthermore", "additionally", "nevertheless",
    "consequently", "therefore", "meanwhile", "similarly", "alternatively",
    "in contrast", "on the other hand", "for example", "for instance",
    "in addition", "as a result", "thus", "hence", "likewise",
    "first", "second", "third", "finally", "lastly", "next",
    "then", "also", "yet", "still", "indeed", "certainly",
    "obviously", "clearly", "undoubtedly", "significantly",
    "in fact", "in other words", "that is", "specifically",
    "overall", "generally", "typically", "usually", "often",
    "sometimes", "always", "never", "rarely", "seldom",
]

# ── AI writing patterns to detect ──
AI_PATTERNS = [
    r"delve\s+into", r"treasure\s+trove", r"rich\s+tapestry",
    r"look\s+no\s+farther", r"look\s+no\s+further",
    r"in\s+this\s+comprehensive\s+guide", r"whether\s+you'?re",
    r"it'?s\s+important\s+to", r"a\s+testament\s+to",
    r"navigating\s+the\s+world\s+of", r"journey\s+of",
    r"world\s+of", r"diverse\s+array", r"wide\s+range",
    r"each\s+name\s+carries", r"choosing\s+the\s+perfect",
    r"stands\s+out", r"embodies\s+the\s+essence",
    r"capturing\s+the\s+essence", r"offers\s+a\s+glimpse",
    r"honors\s+the\s+tradition", r"not\s+just\s+.*\s+but\s+also",
]


class ArticleFingerprint:
    """Represents a structural fingerprint of an article."""

    def __init__(self, filepath: Path, queue: TopicQueue):
        self.filepath = filepath
        self.filename = filepath.name
        self.text = filepath.read_text(encoding="utf-8", errors="ignore")
        self.body = self._extract_body()
        self.queue = queue
        self.fingerprint = {}
        self._compute()

    def _extract_body(self) -> str:
        """Extract markdown body from frontmatter."""
        if self.text.startswith("---"):
            parts = self.text.split("---", 2)
            if len(parts) >= 3:
                return parts[2]
        return self.text

    def _compute(self):
        """Compute all fingerprint components."""
        self.fingerprint = {
            "filename": self.filename,
            "computed_at": datetime.now().isoformat(),
            "intro_hash": self._compute_intro_hash(),
            "intro_signature": self._compute_intro_signature(),
            "heading_hierarchy": self._compute_heading_hierarchy(),
            "heading_structure": self._compute_heading_structure(),
            "faq_questions": self._compute_faq_questions(),
            "faq_hash": self._compute_faq_hash(),
            "table_structure": self._compute_table_structure(),
            "paragraph_distribution": self._compute_paragraph_distribution(),
            "transition_frequency": self._compute_transition_frequency(),
            "conclusion_hash": self._compute_conclusion_hash(),
            "conclusion_signature": self._compute_conclusion_signature(),
            "internal_links": self._compute_internal_links(),
            "meta_title_hash": self._compute_meta_title_hash(),
            "meta_desc_hash": self._compute_meta_desc_hash(),
            "schema_types": self._compute_schema_types(),
            "ai_pattern_flags": self._compute_ai_patterns(),
            "word_count": len(self.body.split()),
            "avg_paragraph_length": self._compute_avg_paragraph_length(),
            "sentence_count": len(re.split(r'[.!?]+', self.body)),
            "unique_word_ratio": self._compute_unique_word_ratio(),
        }

    # ── Fingerprint components ──

    def _compute_intro_hash(self) -> str:
        """Hash of first 3 paragraphs (normalized)."""
        paragraphs = [p.strip() for p in self.body.split('\n\n') if p.strip()]
        intro = ' '.join(paragraphs[:3])
        intro = re.sub(r'\s+', ' ', intro.lower()).strip()
        return hashlib.sha256(intro.encode()).hexdigest()[:20]

    def _compute_intro_signature(self) -> str:
        """Normalized intro pattern for similarity detection."""
        paragraphs = [p.strip() for p in self.body.split('\n\n') if p.strip()]
        if paragraphs:
            first = paragraphs[0].lower()
            first = re.sub(r'\d+', 'NUM', first)
            first = re.sub(r'[^a-z0-9\s]', '', first)
            return first[:200]
        return ""

    def _compute_heading_hierarchy(self) -> list:
        """Ordered list of H2 and H3 heading titles."""
        headings = re.findall(r'^(#{1,6})\s+(.+)$', self.body, re.M)
        result = []
        for level, title in headings:
            if level in ('##', '###'):
                result.append(f"{level}:{title[:50].lower().strip()}")
        return result

    def _compute_heading_structure(self) -> dict:
        """Heading level distribution."""
        headings = re.findall(r'^(#{1,6})\s+.+$', self.body, re.M)
        structure = {}
        for match in headings:
            level = re.match(r'^(#+)', match).group(1)
            structure[level] = structure.get(level, 0) + 1
        return structure

    def _compute_faq_questions(self) -> list:
        """Extract FAQ question texts."""
        faqs = re.findall(r'###\s+Q:\s*(.+?)\n(.*?)(?=###\s+Q:|$)', self.body, re.DOTALL)
        return [q.strip().lower() for q, a in faqs]

    def _compute_faq_hash(self) -> str:
        """Hash of all FAQ questions combined."""
        questions = self._compute_faq_questions()
        combined = '|'.join(questions)
        return hashlib.sha256(combined.encode()).hexdigest()[:20]

    def _compute_table_structure(self) -> list:
        """Extract table structure: columns, headers, row count."""
        tables = []
        # Find markdown tables
        table_blocks = re.findall(r'(\|.+\|)\n(\|[\s:-]+\|)\n((?:\|.+\|\n)+)', self.body)
        for header, _, rows in table_blocks:
            cols = [c.strip() for c in header.strip('|').split('|')]
            rows = [r.strip() for r in rows.strip().split('|') if r.strip()]
            tables.append({
                "columns": len(cols),
                "headers": [c[:30] for c in cols],
                "rows": len(rows),
            })
        return tables

    def _compute_paragraph_distribution(self) -> dict:
        """Bucketed paragraph length distribution."""
        paragraphs = [p.strip() for p in self.body.split('\n\n') if p.strip()]
        buckets = {"short": 0, "medium": 0, "long": 0}
        for p in paragraphs:
            wc = len(p.split())
            if wc < 50:
                buckets["short"] += 1
            elif wc < 150:
                buckets["medium"] += 1
            else:
                buckets["long"] += 1
        total = sum(buckets.values()) or 1
        return {k: round(v / total, 3) for k, v in buckets.items()}

    def _compute_transition_frequency(self) -> dict:
        """Count transition word usage."""
        text_lower = self.body.lower()
        freq = {}
        for word in TRANSITION_WORDS:
            count = len(re.findall(r'\b' + re.escape(word) + r'\b', text_lower))
            if count > 0:
                freq[word] = count
        return freq

    def _compute_conclusion_hash(self) -> str:
        """Hash of last 2 paragraphs."""
        paragraphs = [p.strip() for p in self.body.split('\n\n') if p.strip()]
        last = ' '.join(paragraphs[-2:])
        last = re.sub(r'\s+', ' ', last.lower()).strip()
        return hashlib.sha256(last.encode()).hexdigest()[:20]

    def _compute_conclusion_signature(self) -> str:
        """Normalized conclusion pattern."""
        paragraphs = [p.strip() for p in self.body.split('\n\n') if p.strip()]
        if paragraphs:
            last = paragraphs[-1].lower()
            last = re.sub(r'\d+', 'NUM', last)
            last = re.sub(r'[^a-z0-9\s]', '', last)
            return last[:200]
        return ""

    def _compute_internal_links(self) -> list:
        """Extract target URLs from internal links."""
        links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', self.body)
        return [(t, u) for t, u in links if not u.startswith('http')]

    def _compute_meta_title_hash(self) -> str:
        """Hash of meta title from frontmatter."""
        if self.text.startswith("---"):
            parts = self.text.split("---", 2)
            if len(parts) >= 3:
                import yaml
                try:
                    fm = yaml.safe_load(parts[1].strip())
                    if fm and fm.get("title"):
                        return hashlib.sha256(str(fm["title"]).lower().encode()).hexdigest()[:16]
                except Exception:
                    pass
        return ""

    def _compute_meta_desc_hash(self) -> str:
        """Hash of meta description from frontmatter."""
        if self.text.startswith("---"):
            parts = self.text.split("---", 2)
            if len(parts) >= 3:
                import yaml
                try:
                    fm = yaml.safe_load(parts[1].strip())
                    if fm and fm.get("meta_description"):
                        return hashlib.sha256(str(fm["meta_description"]).lower().encode()).hexdigest()[:16]
                except Exception:
                    pass
        return ""

    def _compute_schema_types(self) -> list:
        """Detect which JSON-LD schema types are present."""
        types = []
        if '"@type": "Article"' in self.text:
            types.append("Article")
        if '"@type": "FAQPage"' in self.text:
            types.append("FAQPage")
        if '"@type": "BreadcrumbList"' in self.text:
            types.append("BreadcrumbList")
        return types

    def _compute_ai_patterns(self) -> list:
        """Detect AI writing patterns."""
        found = []
        for pattern in AI_PATTERNS:
            if re.search(pattern, self.body, re.I):
                found.append(pattern)
        return found

    def _compute_avg_paragraph_length(self) -> float:
        paragraphs = [p.strip() for p in self.body.split('\n\n') if p.strip()]
        if not paragraphs:
            return 0
        return sum(len(p.split()) for p in paragraphs) / len(paragraphs)

    def _compute_unique_word_ratio(self) -> float:
        words = self.body.lower().split()
        if not words:
            return 0
        return len(set(words)) / len(words)

    def to_dict(self) -> dict:
        return self.fingerprint


class FingerprintEngine:
    """Manages fingerprint storage, retrieval, and similarity comparison."""

    def __init__(self, queue: TopicQueue):
        self.queue = queue

    def store_fingerprint(self, filepath: Path, score: Optional[float] = None) -> dict:
        """Store article fingerprint in SQLite."""
        fp = ArticleFingerprint(filepath, self.queue)
        fp_dict = fp.to_dict()

        # Compute content hash
        content_hash = hashlib.sha256(filepath.read_bytes()).hexdigest()[:16]

        self.queue.conn.execute(
            """INSERT OR REPLACE INTO fingerprints
               (filename, content_hash, intro_hash, intro_signature,
                heading_hierarchy, heading_structure, faq_hash,
                table_structure, paragraph_distribution,
                conclusion_hash, conclusion_signature,
                internal_links, schema_types, ai_patterns,
                word_count, avg_paragraph_length, unique_word_ratio,
                quality_score, computed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fp_dict["filename"],
                content_hash,
                fp_dict["intro_hash"],
                fp_dict["intro_signature"],
                json.dumps(fp_dict["heading_hierarchy"]),
                json.dumps(fp_dict["heading_structure"]),
                fp_dict["faq_hash"],
                json.dumps(fp_dict["table_structure"]),
                json.dumps(fp_dict["paragraph_distribution"]),
                fp_dict["conclusion_hash"],
                fp_dict["conclusion_signature"],
                json.dumps(fp_dict["internal_links"]),
                json.dumps(fp_dict["schema_types"]),
                json.dumps(fp_dict["ai_pattern_flags"]),
                fp_dict["word_count"],
                round(fp_dict["avg_paragraph_length"], 1),
                round(fp_dict["unique_word_ratio"], 3),
                score or 0.0,
                fp_dict["computed_at"],
            ),
        )
        self.queue.conn.commit()
        log.info("Stored fingerprint: %s (words=%d)", fp_dict["filename"], fp_dict["word_count"])
        return fp_dict

    def get_all_fingerprints(self) -> list[dict]:
        """Load all stored fingerprints."""
        rows = self.queue.conn.execute(
            """SELECT filename, content_hash, intro_hash, intro_signature,
                      heading_hierarchy, heading_structure, faq_hash,
                      table_structure, paragraph_distribution,
                      conclusion_hash, conclusion_signature,
                      internal_links, schema_types, ai_patterns,
                      word_count, avg_paragraph_length, unique_word_ratio,
                      quality_score, computed_at
               FROM fingerprints
               ORDER BY computed_at"""
        ).fetchall()

        col_names = [desc[0] for desc in self.queue.conn.execute(
            "SELECT * FROM fingerprints LIMIT 0").description]
        return [dict(zip(col_names, row)) for row in rows]

    def check_similarity(self, new_fp: dict, existing_fps: list[dict]) -> list[dict]:
        """Check similarity of a new fingerprint against existing ones.

        Returns list of (similarity_score, fingerprint) for matches > 15%.
        """
        results = []
        for existing in existing_fps:
            similarity = self._compute_similarity(new_fp, existing)
            if similarity > 0.15:
                results.append({
                    "filename": existing.get("filename", "unknown"),
                    "similarity": round(similarity, 4),
                    "breakdown": self._similarity_breakdown(new_fp, existing),
                })
        results.sort(key=lambda x: -x["similarity"])
        return results

    def _compute_similarity(self, fp1: dict, fp2: dict) -> float:
        """Compute structural similarity between two fingerprints.

        Returns 0.0-1.0 where 1.0 = identical structure.
        """
        scores = []

        # 1. Intro similarity (weight: 20%)
        intro_sim = self._string_similarity(
            fp1.get("intro_signature", ""),
            fp2.get("intro_signature", ""),
        )
        scores.append(("intro", intro_sim, 0.20))

        # 2. Heading hierarchy similarity (weight: 25%)
        h2_1 = fp1.get("heading_hierarchy", [])
        h2_2 = fp2.get("heading_hierarchy", [])
        if h2_1 and h2_2:
            heading_sim = self._sequence_similarity(h2_1, h2_2)
            scores.append(("heading_hierarchy", heading_sim, 0.25))
        else:
            scores.append(("heading_hierarchy", 0.0, 0.25))

        # 3. FAQ similarity (weight: 15%)
        faq_sim = self._faq_similarity(fp1, fp2)
        scores.append(("faq", faq_sim, 0.15))

        # 4. Table structure similarity (weight: 10%)
        table_sim = self._table_similarity(fp1, fp2)
        scores.append(("table", table_sim, 0.10))

        # 5. Paragraph distribution similarity (weight: 10%)
        para_sim = self._paragraph_similarity(fp1, fp2)
        scores.append(("paragraph_dist", para_sim, 0.10))

        # 6. Conclusion similarity (weight: 10%)
        concl_sim = self._string_similarity(
            fp1.get("conclusion_signature", ""),
            fp2.get("conclusion_signature", ""),
        )
        scores.append(("conclusion", concl_sim, 0.10))

        # Weighted average
        total_weight = sum(w for _, _, w in scores)
        weighted = sum(s * w for _, s, w in scores)
        return weighted / total_weight if total_weight > 0 else 0.0

    def _similarity_breakdown(self, fp1: dict, fp2: dict) -> dict:
        """Detailed breakdown of similarity components."""
        return {
            "intro": round(self._string_similarity(
                fp1.get("intro_signature", ""),
                fp2.get("intro_signature", ""),
            ), 4),
            "heading": round(self._sequence_similarity(
                fp1.get("heading_hierarchy", []),
                fp2.get("heading_hierarchy", []),
            ), 4),
            "faq": round(self._faq_similarity(fp1, fp2), 4),
            "table": round(self._table_similarity(fp1, fp2), 4),
            "paragraph": round(self._paragraph_similarity(fp1, fp2), 4),
            "conclusion": round(self._string_similarity(
                fp1.get("conclusion_signature", ""),
                fp2.get("conclusion_signature", ""),
            ), 4),
        }

    # ── Similarity helpers ──

    def _string_similarity(self, s1: str, s2: str) -> float:
        """Simple token-based string similarity (0-1)."""
        if not s1 or not s2:
            return 0.0
        tokens1 = set(s1.split())
        tokens2 = set(s2.split())
        if not tokens1 or not tokens2:
            return 0.0
        intersection = tokens1 & tokens2
        union = tokens1 | tokens2
        return len(intersection) / len(union) if union else 0.0

    def _sequence_similarity(self, seq1: list, seq2: list) -> float:
        """Sequence similarity using token overlap."""
        if not seq1 or not seq2:
            return 0.0
        # Extract just the heading text (after level prefix)
        texts1 = set()
        texts2 = set()
        for item in seq1:
            if ':' in item:
                texts1.add(item.split(':', 1)[1][:30])
        for item in seq2:
            if ':' in item:
                texts2.add(item.split(':', 1)[1][:30])
        if not texts1 or not texts2:
            return 0.0
        intersection = texts1 & texts2
        union = texts1 | texts2
        return len(intersection) / len(union) if union else 0.0

    def _faq_similarity(self, fp1: dict, fp2: dict) -> float:
        """FAQ question similarity."""
        # Load from JSON if stored as string
        faq1 = fp1.get("faq_hash", "")
        faq2 = fp2.get("faq_hash", "")
        if faq1 == faq2:
            return 1.0
        if not faq1 or not faq2:
            return 0.0
        # Compare by loading stored questions
        try:
            h1 = fp1.get("intro_hash", "")
            h2 = fp2.get("intro_hash", "")
            # If faq hashes match exactly, high similarity
            if faq1 == faq2:
                return 0.95
            return 0.0
        except Exception:
            return 0.0

    def _table_similarity(self, fp1: dict, fp2: dict) -> float:
        """Table structure similarity."""
        import json
        tables1_raw = fp1.get("table_structure", [])
        tables2_raw = fp2.get("table_structure", [])
        # Handle JSON string stored in DB
        if isinstance(tables1_raw, str):
            try:
                tables1 = json.loads(tables1_raw)
            except:
                tables1 = []
        else:
            tables1 = tables1_raw or []
        if isinstance(tables2_raw, str):
            try:
                tables2 = json.loads(tables2_raw)
            except:
                tables2 = []
        else:
            tables2 = tables2_raw or []
        if not tables1 and not tables2:
            return 1.0
        if not tables1 or not tables2:
            return 0.0
        cols1 = [t.get("columns", 0) if isinstance(t, dict) else 0 for t in tables1]
        cols2 = [t.get("columns", 0) if isinstance(t, dict) else 0 for t in tables2]
        if cols1 == cols2:
            return 0.8
        if abs(cols1[0] - cols2[0]) <= 1:
            return 0.4
        return 0.0

    def _paragraph_similarity(self, fp1: dict, fp2: dict) -> float:
        """Paragraph distribution similarity."""
        import json
        dist1_raw = fp1.get("paragraph_distribution", {})
        dist2_raw = fp2.get("paragraph_distribution", {})
        if isinstance(dist1_raw, str):
            try:
                dist1 = json.loads(dist1_raw)
            except:
                dist1 = {}
        else:
            dist1 = dist1_raw or {}
        if isinstance(dist2_raw, str):
            try:
                dist2 = json.loads(dist2_raw)
            except:
                dist2 = {}
        else:
            dist2 = dist2_raw or {}
        if not dist1 or not dist2:
            return 0.0
        # Compare bucket ratios
        diff = 0
        for bucket in ["short", "medium", "long"]:
            diff += abs(dist1.get(bucket, 0) - dist2.get(bucket, 0))
        return max(0, 1.0 - diff)

    def find_similar_articles(self, filepath: Path, max_results: int = 5) -> list[dict]:
        """Find articles structurally similar to the given file."""
        fp = ArticleFingerprint(filepath, self.queue)
        fp_dict = fp.to_dict()

        all_fps = self.get_all_fingerprints()
        if not all_fps:
            return []

        # Also scan posts for fingerprints not yet in DB
        posts_dir = filepath.parent
        for pf in sorted(posts_dir.glob("*.md")):
            if pf == filepath:
                continue
            # Check if already in DB
            if any(f.get("filename") == pf.name for f in all_fps):
                continue
            stored = self.store_fingerprint(pf)
            all_fps.append(stored)

        similarities = self.check_similarity(fp_dict, all_fps)
        return similarities[:max_results]
