#!/usr/bin/env python3
"""
Autonomous Keyword Discovery Module
====================================
Discovers high-potential baby name keywords from multiple sources:
  - Internal topic gap analysis (what haven't we covered)
  - Semantic keyword expansion (related terms from seed topics)
  - Pre-computed CPC data for baby naming niches
  - Trending topic detection via available signals

Returns scored keywords ready for content generation.
"""

import json
import os
import random
from datetime import datetime
from pathlib import Path

# ── CPC data by baby name niche (USD, estimated) ─────────────────────────
NICHE_CPC_DATA = {
    # High revenue niches ($2.00+ CPC)
    "baby names that mean": 2.85,
    "baby girl names": 2.40,
    "baby boy names": 2.35,
    "unique baby names": 2.20,
    "gender neutral names": 2.10,
    "middle names": 1.95,
    "biblical names": 1.90,
    "japanese names": 1.85,
    "vintage names": 1.80,
    "rare names": 1.75,
    # Medium revenue niches ($1.00-$2.00 CPC)
    "irish names": 1.65,
    "nature names": 1.60,
    "strong names": 1.55,
    "modern names": 1.50,
    "twin names": 1.45,
    "greek names": 1.40,
    "french names": 1.35,
    "italian names": 1.30,
    "spanish names": 1.25,
    "german names": 1.20,
    "scandinavian names": 1.15,
    "celtic names": 1.10,
    "korean names": 1.05,
    "arabic names": 1.00,
    # Growing niches (rising CPC)
    "names by letter": 1.80,
    "short names": 1.70,
    "cute names": 1.90,
    "beautiful names": 1.85,
    "flower names": 1.60,
    "ocean names": 1.55,
    "star names": 1.50,
    "moon names": 1.45,
    "color names": 1.40,
    "animal names": 1.35,
    "tree names": 1.30,
    "gemstone names": 1.25,
    "seasonal names": 1.20,
    "mythology names": 1.15,
    "literary names": 1.10,
    "musical names": 1.05,
    "royal names": 1.00,
}

# ── Search intent strength by modifier ──────────────────────────────────
INTENT_SCORES = {
    "names that mean": 0.95,   # Very high intent
    "girl names": 0.90,
    "boy names": 0.90,
    "with meanings": 0.85,
    "unique": 0.80,
    "rare": 0.80,
    "beautiful": 0.75,
    "popular": 0.70,
    "modern": 0.65,
    "vintage": 0.65,
    "gender neutral": 0.60,
    "and meanings": 0.85,
}

# ── SEO difficulty estimates (lower = easier to rank) ──────────────────
SEO_DIFFICULTY = {
    "baby names": 75,         # Very competitive
    "baby girl names": 80,
    "baby boy names": 80,
    "unique baby names": 55,
    "rare baby names": 40,    # Lower competition
    "vintage baby names": 45,
    "gender neutral names": 50,
    "japanese baby names": 35,
    "irish baby names": 40,
    "biblical baby names": 50,
    "nature baby names": 45,
    "names that mean": 55,
    "middle names": 60,
    "korean baby names": 25,  # Very low competition
    "arabic baby names": 30,
    "celtic baby names": 30,
    "nordic baby names": 25,
    "flower baby names": 40,
    "ocean baby names": 35,
    "star baby names": 35,
    "season baby names": 30,
}

# ── Semantic topic clusters (pillar + supporting) ──────────────────────
TOPIC_CLUSTERS = {
    "names_by_meaning": {
        "pillar": "Baby Names That Mean — Complete Guide",
        "supporting": [
            "love", "hope", "light", "strength", "miracle", "peace",
            "wisdom", "joy", "brave", "warrior", "grace", "beauty",
            "blessing", "gift", "victory", "protector", "angel",
            "moon", "sun", "star", "fire", "water", "earth",
            "queen", "king", "lion", "eagle", "wolf", "rose",
        ]
    },
    "international_names": {
        "pillar": "International Baby Names From Around the World",
        "supporting": [
            "japanese", "irish", "korean", "french", "italian",
            "spanish", "german", "arabic", "greek", "scandinavian",
            "celtic", "nordic", "russian", "polish", "dutch",
            "hawaiian", "african", "indian", "persian", "chinese",
        ]
    },
    "style_collections": {
        "pillar": "Baby Names by Style — Complete Collections",
        "supporting": [
            "vintage", "modern", "unique", "rare", "cute", "short",
            "gender neutral", "strong", "beautiful", "royal",
            "bohemian", "literary", "musical", "mythology",
        ]
    },
    "nature_names": {
        "pillar": "Nature-Inspired Baby Names",
        "supporting": [
            "flower", "tree", "ocean", "mountain", "river", "star",
            "moon", "bird", "animal", "gemstone", "color", "season",
            "forest", "desert", "island", "garden", "meadow",
        ]
    },
    "letters": {
        "pillar": None,  # No pillar — letter pages are standalone
        "supporting": [chr(c) for c in range(ord('a'), ord('z')+1)]
    },
}

# ── CTR potential modifiers (based on SERP features) ──────────────────
def estimate_ctr_potential(topic: str) -> float:
    """Estimate CTR potential based on topic characteristics."""
    topic_lower = topic.lower()
    ctr = 0.03  # Base CTR

    # Modifiers that increase CTR
    if "meaning" in topic_lower: ctr += 0.015
    if "100" in topic_lower: ctr += 0.010   # List posts perform well
    if "girl" in topic_lower: ctr += 0.005
    if "boy" in topic_lower: ctr += 0.005
    if "unique" in topic_lower: ctr += 0.005
    if "rare" in topic_lower: ctr += 0.008

    return min(ctr, 0.08)


# ── Revenue scoring engine ────────────────────────────────────────────
def score_keyword(topic: str) -> dict:
    """Score a keyword for revenue potential. Returns a dict with scores."""
    topic_lower = topic.lower()

    # Find CPC
    cpc = 0.50  # Default low
    for niche, value in NICHE_CPC_DATA.items():
        if niche in topic_lower:
            cpc = max(cpc, value)

    # Find search intent
    intent = 0.50  # Default medium
    for modifier, score in INTENT_SCORES.items():
        if modifier in topic_lower:
            intent = max(intent, score)

    # Find SEO difficulty (invert: lower difficulty = higher score)
    difficulty = 75  # Default high
    for term, score in SEO_DIFFICULTY.items():
        if term in topic_lower:
            difficulty = min(difficulty, score)
    seo_score = 1.0 - (difficulty / 100.0)  # Invert

    # CTR potential
    ctr = estimate_ctr_potential(topic)

    # Monetization probability
    monetization = 0.70
    if "meaning" in topic_lower: monetization = 0.85
    if "girl" in topic_lower: monetization = max(monetization, 0.80)
    if "boy" in topic_lower: monetization = max(monetization, 0.80)
    if "unique" in topic_lower: monetization = 0.75
    if "rare" in topic_lower: monetization = 0.75

    # Composite revenue score (weighted)
    revenue_score = (
        cpc * 0.35 +
        intent * 100 * 0.25 +
        seo_score * 100 * 0.20 +
        ctr * 1000 * 0.10 +
        monetization * 100 * 0.10
    )

    return {
        "topic": topic,
        "cpc": round(cpc, 2),
        "search_intent": round(intent, 2),
        "seo_difficulty": difficulty,
        "seo_rankability": round(seo_score, 2),
        "ctr_potential": round(ctr, 3),
        "monetization_prob": round(monetization, 2),
        "revenue_score": round(revenue_score, 2),
    }


# ── Keyword discovery ─────────────────────────────────────────────────
def load_history() -> set:
    """Load previously generated topics/slugs/titles to avoid duplicates."""
    history_file = Path(__file__).resolve().parent / "generated_topics.json"
    if not history_file.exists():
        return set()
    try:
        data = json.loads(history_file.read_text())
        blacklist = set()
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    blacklist.add(item.get("topic", "").lower().strip())
                    blacklist.add(item.get("slug", "").lower().strip())
                    blacklist.add(item.get("title", "").lower().strip())
        elif isinstance(data, dict):
            for k in ("blacklist_topics", "blacklist_titles"):
                for item in data.get(k, []):
                    blacklist.add(str(item).lower().strip())
        return blacklist
    except Exception:
        return set()


def discover_keywords(count: int = 15, history_blacklist: set = None) -> list:
    """Discover top `count` keywords for content generation.

    Strategy:
      1. Semantic expansion from high-CPC seed topics
      2. Topic cluster gap analysis
      3. Shuffle for diversity, score, and return top N.
    """
    if history_blacklist is None:
        history_blacklist = load_history()

    candidates = []

    # Strategy 1: Expand from high-CPC seed topics
    # Separated modifier pools for semantic correctness
    MEANING_MODIFIERS = [
        "love", "hope", "light", "strength", "miracle", "peace",
        "wisdom", "joy", "brave", "warrior", "grace", "beauty",
        "blessing", "gift", "victory", "protector", "angel",
        "fire", "water", "earth", "wind", "moon", "sun", "star",
        "queen", "king", "lion", "eagle", "wolf", "rose",
        "royal", "garden", "island", "desert", "meadow",
        "forest", "ocean", "mountain", "river", "lake",
        "flower", "tree", "bird", "butterfly", "gem", "pearl",
        "gold", "silver", "rainbow", "storm", "snow",
    ]
    ORIGIN_MODIFIERS = [
        "japanese", "irish", "korean", "french", "italian",
        "spanish", "german", "arabic", "greek", "scandinavian",
        "celtic", "nordic", "russian", "polish", "dutch",
        "hawaiian", "african", "indian", "persian", "chinese",
        "hebrew", "latin", "slavic",
    ]
    STYLE_MODIFIERS = [
        "vintage", "modern", "unique", "rare", "cute", "short",
        "gender neutral", "strong", "beautiful", "royal",
        "bohemian", "literary", "musical", "mythology",
        "biblical",
    ]

    seeds = [
        ("100 baby names that mean {modifier} — beautiful names with meanings", MEANING_MODIFIERS),
        ("100 {origin} baby names and meanings", ORIGIN_MODIFIERS),
        ("100 {style} baby names with meanings", STYLE_MODIFIERS),
        ("100 gender neutral {style} names", [
            "nature", "vintage", "modern", "unique", "celtic",
            "literary", "musical", "mythology",
        ]),
        ("100 baby girl names inspired by {modifier}", [
            "flowers", "nature", "colors", "gems", "butterflies", "stars",
            "oceans", "gardens", "birds", "seasons",
        ]),
        ("100 baby boy names that mean {modifier}", [
            "strong", "warrior", "leader", "brave", "protector",
            "king", "lion", "eagle", "wolf", "bear",
        ]),
        ("baby names starting with {letter} — complete guide", [
            "a", "b", "c", "d", "e", "m", "n", "r", "s", "z",
        ]),
    ]

    for template, modifiers in seeds:
        random.shuffle(modifiers)
        for mod in modifiers[:5]:  # Take top 5 shuffled per seed
            topic = template.format(
                origin=mod, modifier=mod, style=mod,
                theme=mod, letter=mod.upper(),
            )
            if topic.lower().strip() not in history_blacklist:
                candidates.append(topic)

    # Strategy 2: Topic cluster gap check — find uncovered clusters
    all_supporting = set()
    for cluster in TOPIC_CLUSTERS.values():
        all_supporting.update(cluster["supporting"])
    covered = set()
    for t in candidates:
        for s in all_supporting:
            if s in t.lower():
                covered.add(s)
    # Push uncovered supports as candidates
    uncovered = all_supporting - covered
    for u in list(uncovered)[:10]:
        topic = f"100 baby names that mean {u} — beautiful names with meanings"
        if topic.lower().strip() not in history_blacklist:
            candidates.append(topic)

    # Score and rank
    scored = [score_keyword(c) for c in candidates]
    scored.sort(key=lambda x: x["revenue_score"], reverse=True)

    return scored[:count]


# ── Main (for testing) ─────────────────────────────────────────────────
if __name__ == "__main__":
    print("Autonomous Keyword Discovery Engine")
    print("=" * 60)
    history = load_history()
    print(f"History size: {len(history)} entries\n")
    keywords = discover_keywords(count=15)
    print(f"{'#':<3} {'Revenue':<8} {'CPC':<6} {'Intent':<7} {'SEO Diff':<9} {'Topic'}")
    print("-" * 90)
    for i, kw in enumerate(keywords, 1):
        print(f"{i:<3} {kw['revenue_score']:<8.1f} ${kw['cpc']:<5.2f} {kw['search_intent']:<7.2f} {kw['seo_difficulty']:<9} {kw['topic'][:55]}")
    print("-" * 90)
    print(f"\nDiscovered {len(keywords)} high-revenue keywords")
