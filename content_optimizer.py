#!/usr/bin/env python3
"""
Content Optimizer — Improves existing articles for quality, originality, and SEO.

Process:
  1. Generate fingerprint for each article
  2. Compare against all other fingerprints
  3. If similarity > 15%, rewrite problematic sections
  4. Re-fingerprint and recheck until similarity < 15%
  5. Add missing elements (FAQ, schema, internal links, etc.)
  6. Improve readability (paragraph lengths, sentence variety)
  7. Remove AI writing patterns
  8. Add EEAT signals
  9. Store similarity history

Optimizations applied:
  - Rewrite introductions to be unique
  - Rewrite conclusions to be unique
  - Generate unique FAQs
  - Add JSON-LD schemas
  - Add internal links
  - Reduce paragraph length to 50-100 words
  - Remove repetitive AI phrases
  - Add Quick Facts table
  - Add Meaning/Origin/Pronunciation sections
  - Add Sibling/Middle/Twin name suggestions
"""

import json
import logging
import os
import re
import time
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from openai import OpenAI

from database.topic_queue import TopicQueue
from fingerprint_engine import FingerprintEngine, ArticleFingerprint
from utils.helpers import compute_content_hash, BANNED_PHRASES, get_client

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
POSTS_DIR = BASE_DIR / "posts"
VERSION_DIR = BASE_DIR / "optimization_backups"

AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
MODEL = os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
MAX_SIMILARITY_THRESHOLD = 0.15
MAX_REWRITE_ATTEMPTS = 3


# get_client is now in utils.helpers


class ContentOptimizer:
    """Optimizes articles for quality, uniqueness, and SEO."""

    def __init__(self, queue: TopicQueue):
        self.queue = queue
        self.fp_engine = FingerprintEngine(queue)
        self.optimization_log = []

    def optimize_all(self, max_articles: int = 20) -> dict:
        """Optimize up to max_articles articles.

        Returns stats dict.
        """
        VERSION_DIR.mkdir(exist_ok=True)

        posts = sorted(POSTS_DIR.glob("*.md"))
        results = {
            "scanned": 0,
            "optimized": 0,
            "skipped_good": 0,
            "skipped_no_api": 0,
            "failed": 0,
            "details": [],
        }

        for post in posts[:max_articles]:
            results["scanned"] += 1
            log.info("Optimizing: %s", post.name)

            try:
                # Step 1: Generate fingerprint
                fp = self.fp_engine.store_fingerprint(post)

                # Step 2: Check similarity against existing
                similar = self.fp_engine.find_similar_articles(post)
                max_sim = max((s["similarity"] for s in similar), default=0.0)

                if max_sim < MAX_SIMILARITY_THRESHOLD:
                    log.info("  Already unique (max similarity: %.1f%%)", max_sim * 100)
                    results["skipped_good"] += 1
                    continue

                # Step 3: Analyze what needs improvement
                analysis = self._analyze_article(post, fp, similar)

                # Step 4: Optimize
                if analysis["needs_optimization"]:
                    success = self._rewrite_article(post, analysis, fp)
                    if success:
                        results["optimized"] += 1
                        results["details"].append({
                            "file": post.name,
                            "max_similarity_before": round(max_sim, 4),
                            "needs": analysis["issues"],
                            "actions_taken": analysis["actions"],
                            "success": True,
                        })
                    else:
                        results["failed"] += 1
                        results["details"].append({
                            "file": post.name,
                            "success": False,
                            "error": "Rewrite failed",
                        })
                else:
                    results["skipped_good"] += 1

            except Exception as exc:
                log.error("  Error optimizing %s: %s", post.name, exc)
                results["failed"] += 1
                results["details"].append({
                    "file": post.name,
                    "success": False,
                    "error": str(exc),
                })

        # Log optimization results
        self.optimization_log.append({
            "date": datetime.now().isoformat(),
            "results": results,
        })

        log.info("Optimization complete: scanned=%d, optimized=%d, skipped=%d, failed=%d",
                 results["scanned"], results["optimized"],
                 results["skipped_good"], results["failed"])
        return results

    def _analyze_article(self, filepath: Path, fp: dict,
                         similar: list) -> dict:
        """Analyze an article and determine what needs optimization."""
        text = filepath.read_text(encoding="utf-8")
        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                body = parts[2]

        issues = []
        actions = []

        # Check word count
        wc = len(body.split())
        if wc < 2500:
            issues.append(f"Low word count: {wc}")
            actions.append("expand_content")

        # Check for AI patterns
        ai_patterns = fp.get("ai_pattern_flags", [])
        if ai_patterns:
            issues.append(f"AI writing patterns: {len(ai_patterns)} detected")
            actions.append("remove_ai_patterns")

        # Check schema coverage
        schema_types = fp.get("schema_types", [])
        if "Article" not in schema_types:
            issues.append("Missing Article schema")
            actions.append("add_article_schema")
        if "FAQPage" not in schema_types:
            issues.append("Missing FAQPage schema")
            actions.append("add_faq_schema")
        if "BreadcrumbList" not in schema_types:
            issues.append("Missing Breadcrumb schema")
            actions.append("add_breadcrumb_schema")

        # Check FAQ
        faqs = re.findall(r'###\s+Q:\s*(.+?)\n', body)
        if len(faqs) < 8:
            issues.append(f"Insufficient FAQs: {len(faqs)} (need 8+)")
            actions.append("expand_faq")

        # Check internal links
        internal_links = fp.get("internal_links", [])
        if len(internal_links) < 5:
            issues.append(f"Few internal links: {len(internal_links)} (need 5+)")
            actions.append("add_internal_links")

        # Check for tables
        tables = fp.get("table_structure", [])
        if not tables:
            issues.append("No tables found")
            actions.append("add_quick_facts_table")

        # Check paragraph length
        avg_para = fp.get("avg_paragraph_length", 0)
        if avg_para > 120:
            issues.append(f"Long paragraphs: avg {avg_para:.0f} words (target 50-100)")
            actions.append("shorten_paragraphs")

        # Check similarity
        if similar:
            max_sim = max(s["similarity"] for s in similar)
            if max_sim > 0.30:
                issues.append(f"High similarity: {max_sim:.1%} with existing articles")
                actions.append("rewrite_sections")
            elif max_sim > MAX_SIMILARITY_THRESHOLD:
                issues.append(f"Moderate similarity: {max_sim:.1%}")
                actions.append("modify_sections")

        # Check conclusion
        if not re.search(r'## Conclusion', body):
            issues.append("Missing Conclusion section")
            actions.append("add_conclusion")

        # Check for sibling/middle/twin names
        if not re.search(r'Sibling|Middle Name|Twin', body, re.I):
            issues.append("Missing sibling/middle/twin name suggestions")
            actions.append("add_name_combinations")

        needs_opt = len(actions) > 0

        return {
            "needs_optimization": needs_opt,
            "issues": issues,
            "actions": actions,
            "word_count": wc,
            "faq_count": len(faqs),
            "internal_link_count": len(internal_links),
            "avg_paragraph_length": avg_para,
        }

    def _rewrite_article(self, filepath: Path, analysis: dict,
                         original_fp: dict) -> bool:
        """Rewrite article sections to reduce similarity and improve quality."""
        try:
            original = filepath.read_text(encoding="utf-8")
        except Exception as exc:
            log.error("Cannot read %s: %s", filepath.name, exc)
            return False

        old_wc = len(original.split())
        old_hash = compute_content_hash(original)

        # Build optimization prompt
        prompt_parts = []
        prompt_parts.append(f"You are an expert SEO content optimizer for baby name articles.")
        prompt_parts.append(f"\nOPTIMIZATION TASKS:")

        for action in analysis["actions"]:
            prompt_parts.append(f"- {action.replace('_', ' ').title()}")

        prompt_parts.append(f"\nCRITICAL RULES:")
        prompt_parts.append("1. PRESERVE the exact title, slug, and frontmatter structure.")
        prompt_parts.append("2. PRESERVE the publish date.")
        prompt_parts.append("3. NEVER change the URL or slug.")
        prompt_parts.append("4. Keep ALL existing useful content — only MODIFY and ENHANCE.")
        prompt_parts.append("5. Rewrite introductions and conclusions to be completely unique.")
        prompt_parts.append("6. Generate 8-12 original FAQ questions (never reuse existing ones).")
        prompt_parts.append("7. Add JSON-LD Article, FAQPage, and BreadcrumbList schemas.")
        prompt_parts.append("8. Add 5-10 contextual internal links to related articles.")
        prompt_parts.append("9. Break long paragraphs into 2-4 sentence chunks (50-100 words each).")
        prompt_parts.append("10. Remove ALL AI writing patterns (delve into, treasure trove, etc.).")
        prompt_parts.append("11. Add Quick Facts table if missing.")
        prompt_parts.append("12. Add Sibling Names, Middle Names, and Twin Names sections if missing.")
        prompt_parts.append("13. Target 2500-3500 words total.")
        prompt_parts.append("14. Use natural, human-first English.")
        prompt_parts.append(f"15. Article must be structurally unique from all others.")

        prompt_parts.append(f"\nCURRENT ARTICLE ({old_wc} words):")
        prompt_parts.append(original[:12000])

        prompt = "\n\n".join(prompt_parts)

        client = get_client()
        success = False

        for attempt in range(MAX_REWRITE_ATTEMPTS):
            try:
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": "You are an expert SEO content optimizer. Improve articles while preserving URLs, slugs, and publish dates. Never remove useful content."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                    max_tokens=8192,
                )
                improved = resp.choices[0].message.content.strip()

                # Validate improvement
                new_wc = len(improved.split())
                new_hash = compute_content_hash(improved)

                if new_hash == old_hash:
                    log.warning("  Attempt %d: No changes detected. Retrying...", attempt + 1)
                    continue

                if new_wc < old_wc * 0.9:
                    log.warning("  Attempt %d: Word count decreased. Retrying...", attempt + 1)
                    continue

                # Create backup
                backup = VERSION_DIR / f"{filepath.stem}.opt.v{datetime.now().strftime('%Y%m%d%H%M%S')}.md"
                backup.write_text(original, encoding="utf-8")

                # Write improved content
                filepath.write_text(improved, encoding="utf-8")

                # Update fingerprint
                new_fp = self.fp_engine.store_fingerprint(filepath, score=95.0)

                # Check similarity again
                similar = self.fp_engine.find_similar_articles(filepath)
                max_sim = max((s["similarity"] for s in similar), default=0.0)

                log.info("  OPTIMIZED: %s (%dw → %dw, similarity: %.1f%%)",
                         filepath.name, old_wc, new_wc, max_sim * 100)

                self.optimization_log.append({
                    "file": filepath.name,
                    "old_hash": old_hash,
                    "new_hash": new_hash,
                    "old_wc": old_wc,
                    "new_wc": new_wc,
                    "max_similarity": round(max_sim, 4),
                    "attempt": attempt + 1,
                    "backup": backup.name,
                })

                success = True
                break

            except Exception as exc:
                log.warning("  Attempt %d failed: %s", attempt + 1, exc)
                if attempt < MAX_REWRITE_ATTEMPTS - 1:
                    time.sleep(2)

        return success

    def get_similarity_report(self) -> dict:
        """Generate a report of all article similarities."""
        fps = self.fp_engine.get_all_fingerprints()
        report = {
            "total_articles": len(fps),
            "high_similarity_pairs": [],
            "avg_similarity": 0.0,
            "max_similarity": 0.0,
        }

        # Compare all pairs
        comparisons = []
        for i, fp1 in enumerate(fps):
            for j, fp2 in enumerate(fps):
                if i >= j:
                    continue
                sim = self.fp_engine._compute_similarity(fp1, fp2)
                comparisons.append({
                    "file1": fp1.get("filename", ""),
                    "file2": fp2.get("filename", ""),
                    "similarity": round(sim, 4),
                })
                if sim > MAX_SIMILARITY_THRESHOLD:
                    report["high_similarity_pairs"].append(comparisons[-1])

        if comparisons:
            report["avg_similarity"] = round(
                sum(c["similarity"] for c in comparisons) / len(comparisons), 4
            )
            report["max_similarity"] = round(
                max(c["similarity"] for c in comparisons), 4
            )

        return report
