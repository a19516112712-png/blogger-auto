#!/usr/bin/env python3
"""
Content Gap Detector — SERP-Competitive Gap Analysis
======================================================
Compares our content against what top-ranking SERP results contain,
identifying exactly what's missing to match/beat competitors.

For each post:
  1. Detect search intent type
  2. Check required elements against intent benchmarks
  3. Generate specific improvement actions to fill gaps
  4. Prioritize by search volume × completeness gap

Output: prioritized improvement actions for real traffic growth.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("content_gaps")

BASE_DIR = Path(__file__).resolve().parent
POSTS_DIR = BASE_DIR / "posts"


def run_full_gap_analysis() -> dict:
    """Run complete content gap analysis. Returns prioritized actions."""
    from serp_intent_analyzer import scan_all_intents, get_intent_gaps, INTENT_MAP

    # 1. Intent analysis of all posts
    post_analyses = scan_all_intents()

    # 2. Intent coverage gaps
    intent_gaps = get_intent_gaps()

    # 3. Generate improvement actions for each post
    actions = []
    for pa in post_analyses:
        if pa.get("completeness", 100) >= 80:
            continue  # Already well-optimized

        # Priority = volume weight × (100 - completeness) / 100
        volume_weight = {"high": 1.0, "medium": 0.6, "low": 0.3}.get(
            pa.get("volume_tier", "medium"), 0.5
        )
        priority = volume_weight * (100 - pa["completeness"]) / 100

        actions.append({
            "title": pa["title"],
            "file": pa["file"],
            "intent_type": pa["intent_type"],
            "completeness": pa["completeness"],
            "word_count_gap": pa["word_count_gap"],
            "gaps": pa["gaps"],
            "priority": round(priority, 2),
            "action_type": "IMPROVE" if pa["word_count_gap"] < 500 else "EXPAND",
        })

    # 4. Generate NEW content actions for uncovered high-volume queries
    new_content_actions = []
    for g in intent_gaps.get("high_volume_query_gaps", [])[:10]:
        intent = INTENT_MAP.get(
            {
                "List Intent": "LIST_INTENT",
                "Origin Intent": "ORIGIN_INTENT",
                "Trend Intent": "TREND_INTENT",
                "Style Intent": "STYLE_INTENT",
                "FAQ Intent": "FAQ_INTENT",
            }.get(g["intent_type"], "LIST_INTENT")
        )
        if intent:
            new_content_actions.append({
                "query": g["query"],
                "intent_type": g["intent_type"],
                "volume": g["volume"],
                "ctr_potential": g["ctr_potential"],
                "target_word_count": intent.avg_word_count,
                "priority": g["ctr_potential"],
                "action_type": "CREATE",
            })

    # 5. Sort by priority
    actions.sort(key=lambda a: a["priority"], reverse=True)
    new_content_actions.sort(key=lambda a: a["priority"], reverse=True)

    return {
        "improve_existing": actions[:10],
        "create_new": new_content_actions[:10],
        "total_posts_analyzed": len(post_analyses),
        "posts_needing_improvement": len(actions),
        "uncovered_high_volume_queries": len(
            intent_gaps.get("high_volume_query_gaps", [])
        ),
    }


def generate_improvement_plan(analysis: dict) -> list:
    """Generate a concrete improvement plan with specific actions."""
    plan = []

    # Improve existing content
    for item in analysis.get("improve_existing", []):
        plan.append({
            "action": item["action_type"],
            "target": item["title"],
            "intent": item["intent_type"],
            "priority": item["priority"],
            "gaps_to_fill": item["gaps"][:3],
            "add_words": item["word_count_gap"],
        })

    # Create new content for uncovered queries
    for item in analysis.get("create_new", []):
        plan.append({
            "action": "CREATE",
            "target": item["query"],
            "intent": item["intent_type"],
            "priority": round(item["priority"], 2),
            "target_words": item["target_word_count"],
            "gaps_to_fill": ["full SERP-matched article"],
        })

    plan.sort(key=lambda p: p["priority"], reverse=True)
    return plan


if __name__ == "__main__":
    print("=" * 60)
    print("CONTENT GAP DETECTOR")
    print("=" * 60)

    analysis = run_full_gap_analysis()

    print(f"\nPosts analyzed: {analysis['total_posts_analyzed']}")
    print(f"Posts needing improvement: {analysis['posts_needing_improvement']}")
    print(f"Uncovered high-volume queries: {analysis['uncovered_high_volume_queries']}")

    print("\n─── IMPROVE EXISTING (top 5) ───")
    for i, item in enumerate(analysis["improve_existing"][:5], 1):
        print(f"  {i}. [{item['priority']:.2f}] {item['title'][:60]}")
        print(f"     Intent: {item['intent_type']} | Gap: {item['word_count_gap']}w | + {len(item['gaps'])} elements missing")

    print("\n─── CREATE NEW (top 5) ───")
    for i, item in enumerate(analysis["create_new"][:5], 1):
        print(f"  {i}. [{item['priority']:.2f}] NEW: \"{item['query']}\"")
        print(f"     Intent: {item['intent_type']} | Target: {item['target_word_count']}w")

    # Generate plan
    plan = generate_improvement_plan(analysis)
    print(f"\n─── TOTAL ACTIONS: {len(plan)} ───")
    for i, p in enumerate(plan[:10], 1):
        print(f"  {i}. [{p['action']}] {p['target'][:55]} ({p['intent']}, priority={p['priority']})")
