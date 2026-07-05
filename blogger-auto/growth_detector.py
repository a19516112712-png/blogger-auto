#!/usr/bin/env python3
"""
Growth Detector — Self-Improving SEO Analysis Engine
=====================================================
Scans all published content and identifies improvement opportunities.

Detection signals:
  1. Word count < 1500 → HIGH PRIORITY (below quality threshold)
  2. Word count 1500-2000 → MEDIUM PRIORITY (expansion candidates)
  3. No FAQ section → missing long-tail SEO coverage
  4. No markdown tables → missing structured data UX
  5. Fewer than 4 H2 sections → weak heading hierarchy
  6. Missing internal links → orphaned content
  7. Old publish date → content freshness candidate

Also accepts Google Search Console CSV data (impressions, CTR, position)
when available, and merges with internal heuristics.
"""

import json
import re
import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from utils.helpers import count_words
from dataclasses import dataclass, field


@dataclass
class ImprovementCandidate:
    """A page identified for improvement with priority and recommended actions."""
    filename: str
    title: str
    slug: str
    word_count: int
    has_faq: bool
    has_table: bool
    h2_count: int
    internal_links: int
    date: str

    # Growth signals (0-100, higher = more urgent)
    urgency_score: int = 0

    # Recommended actions
    actions: list = field(default_factory=list)

    # Optional Search Console data
    impressions: int = 0
    ctr: float = 0.0
    position: float = 99.0
    has_search_data: bool = False


# ── Analysis Engine ──────────────────────────────────────────────────────
def analyze_post(filepath: Path) -> Optional[ImprovementCandidate]:
    """Analyze a single markdown post for improvement opportunities."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return None

    wc = len(text.split())

    # Extract frontmatter
    title = filepath.stem
    slug = filepath.stem
    date = "unknown"
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body = parts[2]
            for line in fm_text.split("\n"):
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("slug:"):
                    slug = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("date:"):
                    date = line.split(":", 1)[1].strip().strip('"').strip("'")
        else:
            body = text
    else:
        body = text

    has_faq = bool(re.search(r'## Frequently Asked|## FAQ', body, re.IGNORECASE))
    has_table = "|---" in body
    h2_count = len(re.findall(r'^## ', body, re.MULTILINE))

    # Count rough internal links (relative URLs or slugs)
    internal_links = len(re.findall(
        r'\[([^\]]+)\]\(([^)]*)\)', body
    ))

    # Calculate urgency score
    score = 0
    actions = []

    # Word count signals
    if wc < 1500:
        score += 40
        actions.append({"action": "expand_content", "target": "2500+ words", "priority": "high"})
    elif wc < 2000:
        score += 20
        actions.append({"action": "expand_content", "target": "2500+ words", "priority": "medium"})

    # Structural signals
    if not has_faq:
        score += 15
        actions.append({"action": "add_faq", "target": "5-8 FAQs with schema", "priority": "high"})
    if not has_table:
        score += 10
        actions.append({"action": "add_table", "target": "Name-meaning-origin table", "priority": "medium"})
    if h2_count < 4:
        score += 8
        actions.append({"action": "improve_structure", "target": "6+ H2 sections", "priority": "low"})

    # Link signals
    if internal_links < 3:
        score += 7
        actions.append({"action": "add_internal_links", "target": "3-10 related links", "priority": "medium"})

    # Freshness signals
    try:
        post_date = datetime.strptime(date[:10], "%Y-%m-%d")
        days_old = (datetime.now() - post_date).days
        if days_old > 30:
            score += 5
            actions.append({"action": "refresh_content", "target": f"Updated for {datetime.now().strftime('%Y')}", "priority": "low"})
    except Exception:
        pass

    return ImprovementCandidate(
        filename=filepath.name,
        title=title,
        slug=slug,
        word_count=wc,
        has_faq=has_faq,
        has_table=has_table,
        h2_count=h2_count,
        internal_links=internal_links,
        date=date,
        urgency_score=min(score, 100),
        actions=actions,
    )


def scan_all_posts(posts_dir: Path) -> list[ImprovementCandidate]:
    """Scan all posts and return improvement candidates ranked by urgency."""
    candidates = []
    for fp in sorted(posts_dir.glob("*.md")):
        c = analyze_post(fp)
        if c is not None:
            candidates.append(c)
    candidates.sort(key=lambda c: c.urgency_score, reverse=True)
    return candidates


def merge_search_console_data(
    candidates: list[ImprovementCandidate],
    csv_path: Optional[Path] = None,
) -> list[ImprovementCandidate]:
    """Merge Google Search Console CSV export data with candidates."""
    if not csv_path or not csv_path.exists():
        return candidates

    sc_data = {}
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row.get("URL", row.get("Top pages", ""))
                if url:
                    slug = url.rstrip("/").split("/")[-1].replace(".html", "")
                    sc_data[slug] = {
                        "impressions": int(float(row.get("Impressions", 0))),
                        "ctr": float(row.get("CTR", 0)) * 100,
                        "position": float(row.get("Position", 99)),
                    }
    except Exception:
        pass

    for c in candidates:
        if c.slug in sc_data:
            d = sc_data[c.slug]
            c.impressions = d["impressions"]
            c.ctr = d["ctr"]
            c.position = d["position"]
            c.has_search_data = True

            # Boost score for pages ranking 4-40 with rising impressions
            if 4 <= d["position"] <= 40 and d["impressions"] > 0:
                position_bonus = int((40 - d["position"]) / 4)  # 0-9 bonus
                c.urgency_score = min(c.urgency_score + position_bonus, 100)
                if d["ctr"] < 3.0:
                    c.actions.append({
                        "action": "optimize_title_ctr",
                        "target": "Improve CTR from {:.1f}%".format(d["ctr"]),
                        "priority": "high",
                    })

    candidates.sort(key=lambda c: c.urgency_score, reverse=True)
    return candidates


def classify_candidates(candidates: list[ImprovementCandidate]) -> dict:
    """Classify into HIGH GROWTH and POTENTIAL GROWTH buckets."""
    high_growth = []
    potential_growth = []

    for c in candidates:
        if c.has_search_data and c.position <= 15:
            high_growth.append(c)
        elif c.urgency_score >= 30:
            high_growth.append(c)
        else:
            potential_growth.append(c)

    return {
        "high_growth": high_growth,
        "potential_growth": potential_growth,
        "total": len(candidates),
    }


# ── Main ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    posts_dir = Path(__file__).resolve().parent / "posts"
    candidates = scan_all_posts(posts_dir)

    buckets = classify_candidates(candidates)

    print("=" * 60)
    print("GROWTH DETECTOR — Content Improvement Analysis")
    print("=" * 60)
    print(f"Total posts analyzed: {buckets['total']}")
    print(f"High Growth candidates: {len(buckets['high_growth'])}")
    print(f"Potential Growth candidates: {len(buckets['potential_growth'])}")
    print()

    if buckets["high_growth"]:
        print("─── HIGH GROWTH (improve now) ───")
        for i, c in enumerate(buckets["high_growth"][:5], 1):
            print(f"  {i}. [{c.urgency_score}] {c.title[:55]}")
            print(f"     Words: {c.word_count} | FAQ: {c.has_faq} | Table: {c.has_table} | H2s: {c.h2_count} | Links: {c.internal_links}")
            for a in c.actions[:3]:
                print(f"     → {a['action']}: {a['target']} [{a['priority']}]")
            print()

    if buckets["potential_growth"]:
        print(f"─── POTENTIAL GROWTH ({len(buckets['potential_growth'])} pages) ───")
        for i, c in enumerate(buckets["potential_growth"][:5], 1):
            print(f"  {i}. [{c.urgency_score}] {c.title[:55]} ({c.word_count}w)")

    print(f"\nActions by type:")
    all_actions = {}
    for c in candidates:
        for a in c.actions:
            all_actions[a["action"]] = all_actions.get(a["action"], 0) + 1
    for action, count in sorted(all_actions.items(), key=lambda x: x[1], reverse=True):
        print(f"  {action}: {count} pages")
