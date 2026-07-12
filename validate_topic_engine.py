#!/usr/bin/env python3
"""
Validation Script — Topic Generation Engine Metrics

Reports:
  - total_keyword_universe
  - total_topic_clusters
  - duplicate_probability
  - daily_diversity_score
  - maximum_unique_publishing_days_before_exhaustion

Run with:
    python validate_topic_engine.py
"""

import json
import math
import random
import re
import sqlite3
import sys
import yaml
from collections import Counter
from datetime import datetime
from pathlib import Path

# Add parent to path
sys_path = str(Path(__file__).resolve().parent)
sys.path.insert(0, sys_path)

from keyword_discovery import (
    TEMPLATES,
    TOP_LEVEL_CLUSTERS,
    _extract_top_level_cluster,
    _topic_similarity,
    _normalize,
    MEANINGS, ORIGINS, GENGENDERS, POPULARITY, RELIGIONS, NATURE,
    ANIMALS, FLOWERS, COLORS, SEASONS, LETTERS, ENDINGS, YEARS,
    MYTHOLOGIES, OCCUPATIONS, SPACE_SCIENCE, LITERATURE_FANTASY,
    HISTORY_ANCIENT, COUNTRIES_CITIES, PRONUNCIATION_SPELLING,
    FAMILY_RELATIONSHIPS, TRAITS_QUALITIES, CELEBRITY_TRENDS,
)
from database.topic_queue import TopicQueue
from database.schema import DB_PATH


def compute_keyword_universe():
    """Compute total keyword universe size via combinatorial explosion."""
    pools = {
        "MEANINGS": MEANINGS, "ORIGINS": ORIGINS, "GENGENDERS": GENGENDERS,
        "POPULARITY": POPULARITY, "RELIGIONS": RELIGIONS, "NATURE": NATURE,
        "ANIMALS": ANIMALS, "FLOWERS": FLOWERS, "COLORS": COLORS,
        "SEASONS": SEASONS, "LETTERS": LETTERS, "ENDINGS": ENDINGS,
        "YEARS": YEARS, "MYTHOLOGIES": MYTHOLOGIES, "OCCUPATIONS": OCCUPATIONS,
        "SPACE_SCIENCE": SPACE_SCIENCE, "LITERATURE_FANTASY": LITERATURE_FANTASY,
        "HISTORY_ANCIENT": HISTORY_ANCIENT, "COUNTRIES_CITIES": COUNTRIES_CITIES,
        "PRONUNCIATION_SPELLING": PRONUNCIATION_SPELLING,
        "FAMILY_RELATIONSHIPS": FAMILY_RELATIONSHIPS,
        "TRAITS_QUALITIES": TRAITS_QUALITIES,
        "CELEBRITY_TRENDS": CELEBRITY_TRENDS,
    }
    pool_sizes = {k: len(v) for k, v in pools.items()}
    avg_pool = sum(pool_sizes.values()) / max(len(pool_sizes), 1)

    single_ph = sum(1 for t in TEMPLATES if t.count("{") == 1)
    double_ph = sum(1 for t in TEMPLATES if t.count("{") == 2)
    triple_ph = sum(1 for t in TEMPLATES if t.count("{") >= 3)

    single_combos = single_ph * int(avg_pool ** 1)
    double_combos = double_ph * int(avg_pool ** 2)
    triple_combos = triple_ph * int(avg_pool ** 3)
    total = single_combos + double_combos + triple_combos

    return {
        "pool_count": len(pool_sizes),
        "total_items_in_pools": sum(pool_sizes.values()),
        "avg_pool_size": round(avg_pool, 1),
        "pool_sizes": dict(sorted(pool_sizes.items(), key=lambda x: -x[1])[:10]),
        "templates": len(TEMPLATES),
        "single_placeholder_templates": single_ph,
        "double_placeholder_templates": double_ph,
        "triple_placeholder_templates": triple_ph,
        "estimated_single_combos": single_combos,
        "estimated_double_combos": double_combos,
        "estimated_triple_combos": triple_combos,
        "total_estimated_combinations": total,
    }


def compute_topic_clusters():
    """Compute total topic clusters from TOP_LEVEL_CLUSTERS."""
    top_level_count = len(TOP_LEVEL_CLUSTERS)
    pillar_counts = {cat: len(pills) for cat, pills in TOP_LEVEL_CLUSTERS.items()}
    total_pillars = sum(pillar_counts.values())
    sub_dims_per_pillar = 8
    total_sub_clusters = total_pillars * sub_dims_per_pillar
    total_clusters = top_level_count + total_pillars + total_sub_clusters

    return {
        "top_level_categories": top_level_count,
        "category_names": list(TOP_LEVEL_CLUSTERS.keys()),
        "total_pillars": total_pillars,
        "pillars_per_category": pillar_counts,
        "sub_dimensions_per_pillar": sub_dims_per_pillar,
        "total_sub_clusters": total_sub_clusters,
        "total_hierarchical_clusters": total_clusters,
    }


def compute_duplicate_probability():
    """Estimate duplicate probability after N generations."""
    queue = TopicQueue()
    db_topics = set()

    rows = queue.conn.execute("SELECT LOWER(keyword) FROM keywords").fetchall()
    db_topics |= {r[0] for r in rows}

    rows = queue.conn.execute("SELECT normalized_topic FROM topic_history").fetchall()
    db_topics |= {r[0] for r in rows}

    rows = queue.conn.execute("SELECT LOWER(title) FROM published").fetchall()
    db_topics |= {r[0] for r in rows}

    posts_dir = Path(sys_path) / "posts"
    if posts_dir.exists():
        for md in posts_dir.glob("*.md"):
            try:
                text = md.read_text(encoding="utf-8")
                if text.startswith("---"):
                    parts = text.split("---", 2)
                    if len(parts) >= 3:
                        fm = yaml.safe_load(parts[1].strip())
                        if isinstance(fm, dict) and fm.get("title"):
                            db_topics.add(str(fm["title"]).strip().lower())
            except Exception:
                pass

    total_known = len(db_topics)
    universe = get_total_theoretical_combinations()

    n = 1000
    prob = 1 - math.exp(-(n ** 2) / (2 * max(universe, 1)))

    sample_size = min(50, total_known)
    similarities = []
    if sample_size > 1:
        topics_list = list(db_topics)[:sample_size]
        for i in range(len(topics_list)):
            for j in range(i + 1, min(i + 10, len(topics_list))):
                sim = _topic_similarity(topics_list[i], topics_list[j])
                similarities.append(sim)

    avg_sim = sum(similarities) / len(similarities) if similarities else 0

    return {
        "total_known_unique_topics": total_known,
        "theoretical_universe": universe,
        "duplicate_probability_after_1000_generations": round(prob * 100, 4),
        "average_existing_similarity": round(avg_sim, 4),
        "similarity_threshold": 0.15,
        "topics_above_threshold": sum(1 for s in similarities if s > 0.15),
    }


def compute_daily_diversity_score():
    """Compute expected daily diversity score."""
    queue = TopicQueue()
    rows = queue.conn.execute(
        "SELECT keyword FROM keywords WHERE status = 'pending' ORDER BY RANDOM() LIMIT 50"
    ).fetchall()

    if not rows:
        return {"score": 0, "reason": "no_pending_topics"}

    keywords = [r[0] for r in rows]
    clusters = [_extract_top_level_cluster(kw) for kw in keywords]
    cluster_counts = Counter(clusters)
    unique_clusters = len(cluster_counts)

    base_score = (unique_clusters / len(keywords)) * 100
    category_bonus = min(5.0, unique_clusters * 0.5)
    diversity_score = min(100.0, round(base_score + category_bonus, 1))

    return {
        "score": diversity_score,
        "unique_clusters": unique_clusters,
        "total_topics_sampled": len(keywords),
        "cluster_distribution": dict(cluster_counts.most_common(10)),
        "passes_threshold": diversity_score >= 95,
    }


def compute_max_publishing_days():
    """Estimate maximum unique publishing days before exhaustion."""
    queue = TopicQueue()
    pending = queue.conn.execute(
        "SELECT COUNT(*) FROM keywords WHERE status = 'pending'"
    ).fetchone()[0]
    articles_per_day = 5
    days_from_pending = pending // articles_per_day if articles_per_day > 0 else 0
    universe = get_total_theoretical_combinations()
    days_from_theory = universe // articles_per_day

    return {
        "pending_topics": pending,
        "articles_per_day": articles_per_day,
        "days_until_pending_exhausted": days_from_pending,
        "theoretical_universe": universe,
        "max_days_with_auto_discovery": days_from_theory,
        "recommendation": f"Need to run keyword discovery to replenish. Currently have {days_from_pending} days of content.",
    }


def get_total_theoretical_combinations() -> int:
    """Calculate approximate total unique combinations across all dimensions."""
    pools = {
        "MEANINGS": MEANINGS, "ORIGINS": ORIGINS, "GENGENDERS": GENGENDERS,
        "POPULARITY": POPULARITY, "RELIGIONS": RELIGIONS, "NATURE": NATURE,
        "ANIMALS": ANIMALS, "FLOWERS": FLOWERS, "COLORS": COLORS,
        "SEASONS": SEASONS, "LETTERS": LETTERS, "ENDINGS": ENDINGS,
        "YEARS": YEARS, "MYTHOLOGIES": MYTHOLOGIES, "OCCUPATIONS": OCCUPATIONS,
        "SPACE_SCIENCE": SPACE_SCIENCE, "LITERATURE_FANTASY": LITERATURE_FANTASY,
        "HISTORY_ANCIENT": HISTORY_ANCIENT, "COUNTRIES_CITIES": COUNTRIES_CITIES,
        "PRONUNCIATION_SPELLING": PRONUNCIATION_SPELLING,
        "FAMILY_RELATIONSHIPS": FAMILY_RELATIONSHIPS,
        "TRAITS_QUALITIES": TRAITS_QUALITIES,
        "CELEBRITY_TRENDS": CELEBRITY_TRENDS,
    }
    sizes = {k: len(v) for k, v in pools.items()}
    avg_size = sum(sizes.values()) / max(len(sizes), 1)
    return int(avg_size ** 2 * len(TEMPLATES))


def main():
    print("=" * 70)
    print("TOPIC GENERATION ENGINE VALIDATION REPORT")
    print("Generated:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 70)

    # 1. Keyword Universe
    print("\n### 1. KEYWORD UNIVERSE")
    print("-" * 40)
    universe = compute_keyword_universe()
    print(f"  Dimension pools:           {universe['pool_count']}")
    print(f"  Total items in pools:      {universe['total_items_in_pools']}")
    print(f"  Average pool size:         {universe['avg_pool_size']}")
    print(f"  Templates:                 {universe['templates']}")
    print(f"  Estimated combos (single): {universe['estimated_single_combos']:,.0f}")
    print(f"  Estimated combos (double): {universe['estimated_double_combos']:,.0f}")
    print(f"  Estimated combos (triple): {universe['estimated_triple_combos']:,.0f}")
    print(f"  TOTAL ESTIMATED COMBOS:    {universe['total_estimated_combinations']:,.0f}")
    print(f"  Top 10 pools by size:")
    for name, size in universe['pool_sizes'].items():
        print(f"    {name:30s}: {size:4d}")

    # 2. Topic Clusters
    print("\n### 2. TOPIC CLUSTERS")
    print("-" * 40)
    clusters = compute_topic_clusters()
    print(f"  Top-level categories:      {clusters['top_level_categories']}")
    print(f"  Category names:            {', '.join(clusters['category_names'])}")
    print(f"  Total pillars:             {clusters['total_pillars']}")
    print(f"  Sub-dimensions/pillar:     {clusters['sub_dimensions_per_pillar']}")
    print(f"  Total sub-clusters:        {clusters['total_sub_clusters']}")
    print(f"  TOTAL HIERARCHICAL CLUSTERS: {clusters['total_hierarchical_clusters']}")
    print(f"  Pillars per category:")
    for cat, count in sorted(clusters['pillars_per_category'].items(), key=lambda x: -x[1]):
        print(f"    {cat:30s}: {count:3d} pillars")

    # 3. Duplicate Probability
    print("\n### 3. DUPLICATE PROBABILITY")
    print("-" * 40)
    dup_prob = compute_duplicate_probability()
    print(f"  Total known unique topics: {dup_prob['total_known_unique_topics']:,}")
    print(f"  Theoretical universe:      {dup_prob['theoretical_universe']:,.0f}")
    print(f"  Dup. prob. after 1000 gens:{dup_prob['duplicate_probability_after_1000_generations']:.4f}%")
    print(f"  Avg. existing similarity:  {dup_prob['average_existing_similarity']:.4f}")
    print(f"  Similarity threshold:      {dup_prob['similarity_threshold']}")
    print(f"  Topics above threshold:    {dup_prob['topics_above_threshold']}")

    # 4. Daily Diversity Score
    print("\n### 4. DAILY DIVERSITY SCORE")
    print("-" * 40)
    diversity = compute_daily_diversity_score()
    print(f"  Diversity score:           {diversity['score']}/100")
    print(f"  Unique clusters in sample: {diversity['unique_clusters']}")
    print(f"  Topics sampled:            {diversity['total_topics_sampled']}")
    print(f"  Passes >95 threshold:      {'YES' if diversity['passes_threshold'] else 'NO'}")
    if diversity['score'] < 95:
        print(f"  Cluster distribution:")
        for cluster, count in diversity['cluster_distribution'].items():
            print(f"    {cluster:30s}: {count:3d}")

    # 5. Max Publishing Days
    print("\n### 5. MAXIMUM UNIQUE PUBLISHING DAYS")
    print("-" * 40)
    max_days = compute_max_publishing_days()
    print(f"  Pending topics:            {max_days['pending_topics']}")
    print(f"  Articles per day:          {max_days['articles_per_day']}")
    print(f"  Days until pending empty:  {max_days['days_until_pending_exhausted']}")
    print(f"  Theoretical universe:      {max_days['theoretical_universe']:,.0f}")
    print(f"  Max days (with auto-fill): {max_days['max_days_with_auto_discovery']:,.0f}")
    print(f"  Recommendation:            {max_days['recommendation']}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total keyword universe:      {universe['total_estimated_combinations']:,.0f}")
    print(f"  Total topic clusters:        {clusters['total_hierarchical_clusters']}")
    print(f"  Duplicate probability:       {dup_prob['duplicate_probability_after_1000_generations']:.4f}%")
    print(f"  Daily diversity score:       {diversity['score']}/100")
    print(f"  Max unique publishing days:  {max_days['days_until_pending_exhausted']} (pending)")
    print(f"                             ~{max_days['max_days_with_auto_discovery']:,} (theoretical)")
    print("=" * 70)


if __name__ == "__main__":
    main()
