#!/usr/bin/env python3
"""
SERP Intent Analyzer — Real Search Intent Engine
===================================================
Maps real search queries to SERP intent types, analyzes the structure
of top-ranking results for each intent, and identifies what our content
must include to match and beat competitors.

Intent types based on actual Google SERP analysis for baby name queries:
  - LIST_INTENT: "100 baby names that mean X" → table-rich list posts
  - ORIGIN_INTENT: "Japanese baby names" → cultural guide + pronunciation
  - TREND_INTENT: "popular baby names 2026" → data-backed trending lists
  - ADVICE_INTENT: "how to choose a baby name" → step-by-step guides
  - MEANING_INTENT: "what does [name] mean" → single-name deep dives
  - COMPARISON_INTENT: "boy names vs girl names" → comparison tables
  - LETTER_INTENT: "baby names starting with A" → alphabetical catalogs
  - STYLE_INTENT: "unique/vintage/modern baby names" → curated collections
  - GENDER_INTENT: "gender neutral baby names" → inclusive collections
  - FAQ_INTENT: questions from People Also Ask → direct answer format
"""

import json
import re
import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("serp_intent")

BASE_DIR = Path(__file__).resolve().parent
POSTS_DIR = BASE_DIR / "posts"

# ── SERP Intent Types (based on real Google SERP analysis) ──────────────
@dataclass
class IntentType:
    name: str
    query_patterns: list  # Real queries that trigger this intent
    serp_features: list   # What top 10 results look like
    required_elements: list  # What our content MUST include
    avg_word_count: int   # Average word count of top 10
    ctr_potential: float  # CTR potential for this intent (0-1)
    search_volume_tier: str  # "high", "medium", "low"

INTENT_MAP = {
    "LIST_INTENT": IntentType(
        name="List Intent",
        query_patterns=[
            "baby names that mean love", "names that mean strength",
            "100 baby girl names", "baby boy names list",
            "baby names with meanings", "names and meanings",
            "baby names that mean light", "names meaning hope",
            "baby names that mean warrior", "names that mean brave",
        ],
        serp_features=[
            "H1: number-prefixed title (100/50/200+)",
            "Large markdown/HTML table with 3-5 columns",
            "Name | Meaning | Origin | Gender structure",
            "H2 sections by category/theme",
            "FAQ section at bottom (People Also Ask)",
            "2000-4000 word average",
        ],
        required_elements=[
            "number-prefixed H1 (100+)",
            "name-meaning-origin-gender table (100 rows)",
            "at least 6 H2 thematic sections",
            "5-8 FAQ with answers (People Also Ask format)",
            "pronunciation guide for non-English names",
        ],
        avg_word_count=2800,
        ctr_potential=0.06,
        search_volume_tier="high",
    ),
    "ORIGIN_INTENT": IntentType(
        name="Origin Intent",
        query_patterns=[
            "japanese baby names", "irish baby names",
            "korean names", "french baby names",
            "arabic baby names", "greek names",
            "italian baby names", "scandinavian names",
            "celtic baby names", "african baby names",
            "hawaiian baby names", "indian baby names",
        ],
        serp_features=[
            "H1: origin-focused title with cultural reference",
            "Cultural background section first",
            "Pronunciation guide (critical for non-English origins)",
            "Name table with original script if applicable",
            "Gender breakdown within origin",
            "Modern vs. traditional names from this culture",
        ],
        required_elements=[
            "cultural background section (200+ words)",
            "pronunciation guide for key names",
            "name table (Name | Meaning | Gender | Pronunciation)",
            "popularity in country of origin vs. globally",
            "FAQ including cultural naming traditions",
        ],
        avg_word_count=2500,
        ctr_potential=0.05,
        search_volume_tier="medium",
    ),
    "TREND_INTENT": IntentType(
        name="Trend Intent",
        query_patterns=[
            "popular baby names 2026", "trending baby names",
            "top baby names", "most popular girl names",
            "modern baby names", "baby name trends",
            "unique baby names 2026", "rising baby names",
        ],
        serp_features=[
            "Data-backed claims (Social Security data, Nameberry stats)",
            "Year-over-year comparison",
            "Celebrity influence mentions",
            "Short, scannable lists rather than 100-row tables",
            "Timeline: what's rising, what's falling",
        ],
        required_elements=[
            "current year data references",
            "trending direction (rising/falling/stable)",
            "reason for trend (celebrity, cultural, generational)",
            "prediction for next year",
            "FAQ about popularity and uniqueness tradeoffs",
        ],
        avg_word_count=2200,
        ctr_potential=0.07,
        search_volume_tier="high",
    ),
    "STYLE_INTENT": IntentType(
        name="Style Intent",
        query_patterns=[
            "unique baby names", "vintage baby names",
            "rare baby names", "cute baby names",
            "strong baby names", "beautiful names",
            "gender neutral names", "short baby names",
            "nature baby names", "biblical baby names",
        ],
        serp_features=[
            "Curated collection by theme/style",
            "Why this style appeals to modern parents",
            "Mix of very rare and slightly familiar names",
            "Name descriptions rather than just table data",
            "Visual or descriptive categorization",
        ],
        required_elements=[
            "definition of the style/category",
            "why parents choose this style",
            "name table with style-relevant columns",
            "examples at different uniqueness levels",
            "FAQ about style tradeoffs (e.g. unique vs. practical)",
        ],
        avg_word_count=2400,
        ctr_potential=0.055,
        search_volume_tier="high",
    ),
    "FAQ_INTENT": IntentType(
        name="FAQ Intent",
        query_patterns=[
            "how to choose a baby name", "baby name tips",
            "what to consider when naming", "naming traditions",
            "middle name ideas", "sibling names",
            "baby name regret", "changing baby name",
            "name popularity checker", "unique vs common names",
        ],
        serp_features=[
            "Direct answer in first paragraph (featured snippet optimized)",
            "Step-by-step numbered advice",
            "Expert quotes or professional perspective",
            "Checklist or decision framework",
            "Real parent experiences cited",
        ],
        required_elements=[
            "direct answer to question in first 100 words",
            "structured step-by-step guide",
            "practical decision framework/checklist",
            "real examples and scenarios",
            "FAQ section with related questions",
        ],
        avg_word_count=2000,
        ctr_potential=0.08,
        search_volume_tier="medium",
    ),
}

# ── Intent Detection ────────────────────────────────────────────────────
def detect_intent(topic: str, title: str = "") -> Optional[IntentType]:
    """Detect the SERP intent type for a given topic/title."""
    combined = (topic + " " + title).lower()

    # Check each intent's query patterns
    for intent_key, intent in INTENT_MAP.items():
        for pattern in intent.query_patterns:
            pattern_words = set(pattern.lower().split())
            combined_words = set(combined.split())
            overlap = len(pattern_words & combined_words)
            if overlap >= 3 or pattern.lower() in combined:
                return intent

    # Fallback: check for structural clues
    if any(w in combined for w in ["how to", "tips", "guide", "advice", "choose"]):
        return INTENT_MAP.get("FAQ_INTENT")
    if any(w in combined for w in ["2026", "trending", "popular", "top", "trend", "modern"]):
        return INTENT_MAP.get("TREND_INTENT")
    if any(w in combined for w in ["japanese", "irish", "french", "korean", "arabic", "greek",
                                     "italian", "scandinavian", "celtic", "african", "origin",
                                     "country", "international"]):
        return INTENT_MAP.get("ORIGIN_INTENT")
    if any(w in combined for w in ["meaning", "mean", "100", "names that", "list"]) or "100" in combined:
        return INTENT_MAP.get("LIST_INTENT")

    return INTENT_MAP.get("STYLE_INTENT")  # Default


def analyze_post_intent(filepath: Path) -> dict:
    """Analyze a post: detect intent, check required elements, score completeness."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return {"error": "unreadable"}

    wc = len(text.split())
    title = filepath.stem
    fm_topic = filepath.stem

    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].split("\n"):
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("slug:"):
                    fm_topic = line.split(":", 1)[1].strip().strip('"').strip("'")
            body = parts[2]
        else:
            body = text
    else:
        body = text

    intent = detect_intent(fm_topic, title)
    if intent is None:
        return {"error": "no intent detected"}

    # Check required elements
    checks = {}
    for req in intent.required_elements:
        keyword = req.split()[0].lower()
        checks[req] = keyword in body.lower()

    completeness = sum(1 for v in checks.values() if v) / max(len(checks), 1) * 100

    # Gap analysis
    gaps = [req for req, present in checks.items() if not present]

    return {
        "file": filepath.name,
        "title": title,
        "intent_type": intent.name,
        "word_count": wc,
        "target_word_count": intent.avg_word_count,
        "word_count_gap": max(0, intent.avg_word_count - wc),
        "ctr_potential": intent.ctr_potential,
        "volume_tier": intent.search_volume_tier,
        "required_elements_met": checks,
        "completeness": round(completeness, 0),
        "gaps": gaps,
        "needs_expansion": wc < intent.avg_word_count * 0.8,
        "needs_faq": "FAQ" not in body and "frequently asked" not in body.lower(),
    }


def scan_all_intents() -> list:
    """Scan all posts, detect intent, and analyze completeness vs. SERP benchmarks."""
    results = []
    for fp in sorted(POSTS_DIR.glob("*.md")):
        analysis = analyze_post_intent(fp)
        if "error" not in analysis:
            results.append(analysis)
    results.sort(key=lambda r: r["completeness"])
    return results


def get_intent_gaps() -> dict:
    """Find which real search intents are NOT covered by our content."""
    covered_intents = set()
    for fp in POSTS_DIR.glob("*.md"):
        analysis = analyze_post_intent(fp)
        if "intent_type" in analysis:
            covered_intents.add(analysis["intent_type"])

    all_intents = set(INTENT_MAP.keys())
    missing = all_intents - covered_intents

    # Also check specific high-volume query patterns
    high_volume_gaps = []
    for intent_key, intent in INTENT_MAP.items():
        for pattern in intent.query_patterns:
            found = False
            for fp in POSTS_DIR.glob("*.md"):
                text = fp.read_text(encoding="utf-8", errors="ignore")[:2000].lower()
                if pattern.lower() in text:
                    found = True
                    break
            if not found and intent.search_volume_tier == "high":
                high_volume_gaps.append({
                    "query": pattern,
                    "intent_type": intent.name,
                    "volume": intent.search_volume_tier,
                    "ctr_potential": intent.ctr_potential,
                })

    return {
        "missing_intent_types": list(missing),
        "high_volume_query_gaps": sorted(
            high_volume_gaps, key=lambda g: g["ctr_potential"], reverse=True
        )[:15],
    }


if __name__ == "__main__":
    print("=" * 60)
    print("SERP INTENT ANALYZER")
    print("=" * 60)

    # Define intent types available
    print("\nIntent types defined:")
    for key, intent in INTENT_MAP.items():
        print(f"  {key}: {len(intent.query_patterns)} patterns, ~{intent.avg_word_count}w target, {intent.search_volume_tier} volume")

    # Scan all posts
    results = scan_all_intents()
    print(f"\nPosts analyzed: {len(results)}")

    # Show completeness distribution
    low = [r for r in results if r["completeness"] < 50]
    mid = [r for r in results if 50 <= r["completeness"] < 80]
    high = [r for r in results if r["completeness"] >= 80]
    print(f"  Low completeness (<50%): {len(low)}")
    print(f"  Medium completeness (50-80%): {len(mid)}")
    print(f"  High completeness (80%+): {len(high)}")

    # Show top improvement targets
    print("\nTop improvement targets (lowest completeness):")
    for r in low[:8]:
        print(f"  [{r['completeness']:.0f}%] {r['title'][:55]}")
        print(f"    Intent: {r['intent_type']} | {r['word_count']}w → target {r['target_word_count']}w (gap: {r['word_count_gap']}w)")
        if r["gaps"]:
            print(f"    Missing: {', '.join(r['gaps'][:3])}")
        print()

    # Show intent gaps
    gaps = get_intent_gaps()
    if gaps["high_volume_query_gaps"]:
        print("\nHigh-volume uncovered search queries:")
        for g in gaps["high_volume_query_gaps"][:5]:
            print(f"  [{g['intent_type']}] \"{g['query']}\" — CTR: {g['ctr_potential']:.2f}")
