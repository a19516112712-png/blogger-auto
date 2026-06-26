#!/usr/bin/env python3
"""
SEO Graph & Topic Cluster System
==================================
Builds semantic topic clusters, detects content gaps, suggests internal
links, and prevents content cannibalization.

Features:
  - Pillar + supporting page architecture
  - Content gap detection
  - Internal link graph generation
  - Duplicate/similar topic avoidance
  - Cluster completeness scoring
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from typing import Optional

# ── Topic cluster definitions ───────────────────────────────────────────
CLUSTERS = {
    "names_by_meaning": {
        "pillar": {
            "topic": "Baby Names That Mean — The Ultimate Guide to Meaningful Names",
            "slug": "baby-names-that-mean-ultimate-guide",
            "priority": 10,  # Publish when cluster is >50% complete
        },
        "supporting_keywords": [
            {"kw": "love", "template": "100 Baby Names That Mean Love — Beautiful Loving Names"},
            {"kw": "hope", "template": "100 Baby Names That Mean Hope — Hopeful Names for Bright Futures"},
            {"kw": "light", "template": "100 Baby Names That Mean Light — Bright & Radiant Names"},
            {"kw": "strength", "template": "100 Baby Names That Mean Strength — Strong Powerful Names"},
            {"kw": "miracle", "template": "100 Baby Names That Mean Miracle — Blessed Names from Above"},
            {"kw": "peace", "template": "100 Baby Names That Mean Peace — Calm & Peaceful Names"},
            {"kw": "wisdom", "template": "100 Baby Names That Mean Wisdom — Intelligent & Wise Names"},
            {"kw": "joy", "template": "100 Baby Names That Mean Joy — Happy & Joyful Names"},
            {"kw": "brave", "template": "100 Baby Names That Mean Brave — Courageous Hero Names"},
            {"kw": "warrior", "template": "100 Baby Names That Mean Warrior — Fierce Battle Names"},
            {"kw": "grace", "template": "100 Baby Names That Mean Grace — Elegant Names with Poise"},
            {"kw": "beauty", "template": "100 Baby Names That Mean Beauty — Gorgeous Names"},
            {"kw": "blessing", "template": "100 Baby Names That Mean Blessing — Thankful Names"},
            {"kw": "gift", "template": "100 Baby Names That Mean Gift — Precious Names from Above"},
            {"kw": "victory", "template": "100 Baby Names That Mean Victory — Winning Champion Names"},
        ]
    },
    "international_names": {
        "pillar": {
            "topic": "International Baby Names — Beautiful Names from Every Culture",
            "slug": "international-baby-names-world-cultures",
            "priority": 8,
        },
        "supporting_keywords": [
            {"kw": "japanese", "template": "100 Japanese Baby Names with Beautiful Meanings"},
            {"kw": "irish", "template": "100 Irish Baby Names — Celtic Names with Rich Heritage"},
            {"kw": "korean", "template": "100 Korean Baby Names — Beautiful Names from the Land of Morning Calm"},
            {"kw": "french", "template": "100 French Baby Names — Chic & Elegant Parisian Names"},
            {"kw": "italian", "template": "100 Italian Baby Names — Romantic Names from Bella Italia"},
            {"kw": "spanish", "template": "100 Spanish Baby Names — Vibrant Hispanic Names"},
            {"kw": "german", "template": "100 German Baby Names — Strong Traditional Names"},
            {"kw": "arabic", "template": "100 Arabic Baby Names — Beautiful Islamic Names"},
            {"kw": "greek", "template": "100 Greek Baby Names — Mythological & Ancient Names"},
            {"kw": "scandinavian", "template": "100 Scandinavian Baby Names — Modern Nordic Names"},
            {"kw": "celtic", "template": "100 Celtic Baby Names — Ancient Gaelic & Welsh Names"},
            {"kw": "nordic", "template": "100 Nordic Baby Names — Viking-Inspired Strong Names"},
            {"kw": "russian", "template": "100 Russian Baby Names — Beautiful Slavic Names"},
            {"kw": "indian", "template": "100 Indian Baby Names — Hindu & Sanskrit Names"},
            {"kw": "african", "template": "100 African Baby Names — Names from Across the Continent"},
        ]
    },
    "style_collections": {
        "pillar": {
            "topic": "Baby Names by Style — Find the Perfect Name Category",
            "slug": "baby-names-by-style-categories",
            "priority": 7,
        },
        "supporting_keywords": [
            {"kw": "vintage", "template": "100 Vintage Baby Names Making a Comeback"},
            {"kw": "modern", "template": "100 Modern Baby Names Trending Now"},
            {"kw": "unique", "template": "100 Unique Baby Names You Haven't Heard Before"},
            {"kw": "rare", "template": "100 Rare Baby Names — Hidden Gems Worth Discovering"},
            {"kw": "cute", "template": "100 Cute Baby Names — Adorable Names for Sweet Babies"},
            {"kw": "short", "template": "100 Short Baby Names — Sweet One-Syllable Names"},
            {"kw": "gender neutral", "template": "100 Gender Neutral Baby Names for Modern Families"},
            {"kw": "strong", "template": "100 Strong Baby Names — Powerful Names with Presence"},
            {"kw": "royal", "template": "100 Royal Baby Names — Regal & Aristocratic Names"},
            {"kw": "bohemian", "template": "100 Bohemian Baby Names — Free-Spirited Artistic Names"},
        ]
    },
    "nature_names": {
        "pillar": {
            "topic": "Nature-Inspired Baby Names — Beautiful Names from the Natural World",
            "slug": "nature-inspired-baby-names-guide",
            "priority": 6,
        },
        "supporting_keywords": [
            {"kw": "flower", "template": "100 Flower Baby Names — Beautiful Botanical Names"},
            {"kw": "tree", "template": "100 Tree Baby Names — Strong Forest-Inspired Names"},
            {"kw": "ocean", "template": "100 Ocean Baby Names — Sea & Water-Inspired Names"},
            {"kw": "mountain", "template": "100 Mountain Baby Names — Majestic Peak-Inspired Names"},
            {"kw": "star", "template": "100 Star Baby Names — Celestial & Constellation Names"},
            {"kw": "moon", "template": "100 Moon Baby Names — Lunar & Mystical Names"},
            {"kw": "bird", "template": "100 Bird Baby Names — Beautiful Feathered Friend Names"},
            {"kw": "gemstone", "template": "100 Gemstone Baby Names — Jewel & Precious Stone Names"},
            {"kw": "color", "template": "100 Color Baby Names — Vibrant Rainbow-Inspired Names"},
            {"kw": "season", "template": "100 Season Baby Names — Winter Spring Summer Autumn"},
        ]
    },
}

# ── Internal link graph ─────────────────────────────────────────────────
def build_link_graph(posts_dir: Path, history: set) -> dict:
    """Build an internal linking graph from existing posts.

    Returns a dict mapping topic slug → [related_slug, ...].
    """
    graph = defaultdict(list)
    post_files = list(posts_dir.glob("*.md"))

    for pf in post_files:
        slug = pf.stem.lower()
        text = pf.read_text(encoding="utf-8", errors="ignore")[:5000]
        # Find references to other slugs
        for other in post_files:
            other_slug = other.stem.lower()
            if other_slug != slug and other_slug in text.lower():
                graph[slug].append(other_slug)
    return dict(graph)


def suggest_internal_links(topic_kw: str, cluster_name: str, history: set) -> list:
    """Suggest internal link targets for a new article.

    Prioritizes:
      1. Same-cluster supporting pages (most relevant)
      2. Cluster pillar page (if exists)
      3. Cross-cluster related pages
    """
    suggestions = []

    # Same-cluster suggestions
    if cluster_name in CLUSTERS:
        cluster = CLUSTERS[cluster_name]
        for sk in cluster["supporting_keywords"]:
            s_slug = re.sub(r"[^a-z0-9]+", "-", sk["template"].lower())[:80].strip("-")
            if s_slug in history:
                suggestions.append({
                    "slug": s_slug,
                    "title": sk["template"],
                    "priority": "high",
                    "reason": f"Same cluster: {cluster_name}",
                })

        # Pillar suggestion
        p_slug = cluster["pillar"]["slug"]
        if p_slug in history:
            suggestions.append({
                "slug": p_slug,
                "title": cluster["pillar"]["topic"],
                "priority": "highest",
                "reason": "Cluster pillar page",
            })

    return suggestions[:5]


def detect_content_gaps(posts_dir: Path, history: set) -> list:
    """Find cluster keywords not yet covered. Returns priority-ordered gaps."""
    gaps = []
    for cluster_name, cluster in CLUSTERS.items():
        covered = 0
        total = len(cluster["supporting_keywords"])
        for sk in cluster["supporting_keywords"]:
            kw_slug = re.sub(r"[^a-z0-9]+", "-", sk["template"].lower())[:80].strip("-")
            if kw_slug in history or sk["kw"] in history:
                covered += 1
            else:
                gaps.append({
                    "cluster": cluster_name,
                    "keyword": sk["kw"],
                    "template": sk["template"],
                    "priority": cluster["pillar"]["priority"],
                    "completeness": round(covered / total * 100),
                })
    gaps.sort(key=lambda g: (g["priority"], g["completeness"]), reverse=True)
    return gaps[:20]


def cluster_status(posts_dir: Path, history: set) -> list:
    """Report completeness of each topic cluster."""
    status = []
    for cluster_name, cluster in CLUSTERS.items():
        covered = 0
        total = len(cluster["supporting_keywords"])
        for sk in cluster["supporting_keywords"]:
            kw_slug = re.sub(r"[^a-z0-9]+", "-", sk["template"].lower())[:80].strip("-")
            if kw_slug in history or sk["kw"] in history:
                covered += 1
        pct = round(covered / total * 100, 0) if total > 0 else 0
        status.append({
            "cluster": cluster_name,
            "pillar_topic": cluster["pillar"]["topic"],
            "covered": covered,
            "total": total,
            "completeness": int(pct),
            "ready_for_pillar": pct >= 50,  # Pillar ready when 50%+ supporting done
        })
    status.sort(key=lambda s: s["completeness"], reverse=True)
    return status


# ── Main ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    posts_dir = Path(__file__).resolve().parent / "posts"
    history_file = Path(__file__).resolve().parent / "generated_topics.json"
    history = set()
    if history_file.exists():
        data = json.loads(history_file.read_text())
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    history.add(item.get("slug", "").lower().strip())
        elif isinstance(data, dict):
            for k in ("blacklist_topics",):
                for item in data.get(k, []):
                    history.add(str(item).lower().strip())

    print("=" * 60)
    print("SEO GRAPH — Topic Cluster Status")
    print("=" * 60)
    for s in cluster_status(posts_dir, history):
        bar = "█" * (s["completeness"] // 10) + "░" * (10 - s["completeness"] // 10)
        ready = "🔴 READY FOR PILLAR" if s["ready_for_pillar"] else ""
        print(f"  {s['cluster']}: [{bar}] {s['completeness']}% ({s['covered']}/{s['total']}) {ready}")

    print(f"\nContent Gaps (top 10):")
    for i, g in enumerate(detect_content_gaps(posts_dir, history)[:10], 1):
        print(f"  {i}. [{g['cluster']}] {g['keyword']} (priority: {g['priority']})")
