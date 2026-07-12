#!/usr/bin/env python3
"""
Topic Cluster Engine — Hierarchical cluster builder for all 19 top-level clusters.

Builds hierarchical topic clusters automatically:
  origin (top-level)
  ├─ origin_irish (pillar)
  │  ├─ origin_irish_boy_names
  │  ├─ origin_irish_girl_names
  │  └─ origin_irish_unisex_names
  ├─ origin_japanese
  └─ ...

Each cluster auto-links to its siblings and parent.

Covers all 19 top-level clusters:
  origin, meaning, nature, animals, flowers, mythology, style, religion,
  colors, seasons, occupations, celebrity_trends, space_science,
  literature_fantasy, history_ancient, countries_cities,
  pronunciation_spelling, family_relationships, traits_qualities
"""

import logging
from datetime import datetime

from database.topic_queue import TopicQueue
from keyword_discovery import TOP_LEVEL_CLUSTERS

log = logging.getLogger(__name__)

# Sub-dimensions applied to every pillar across all categories
SUB_DIMENSIONS = [
    "boy_names", "girl_names", "unisex_names",
    "middle_names", "twin_names", "nickname_ideas",
    "surname_ideas", "baby_names",
]


def build_clusters(queue: TopicQueue) -> dict:
    """Build all cluster hierarchies from TOP_LEVEL_CLUSTERS definitions.

    Returns stats dict.
    """
    stats = {"clusters_created": 0, "keywords_added": 0}

    # Create top-level category roots
    category_roots = {}
    for cat_name in TOP_LEVEL_CLUSTERS:
        root_id = queue.add_cluster(
            name=f"cluster_{cat_name}",
            parent=None,
            pillar_keyword=f"{cat_name} baby names",
            depth=0,
        )
        category_roots[cat_name] = root_id
        stats["clusters_created"] += 1
        log.info("Created top-level cluster: %s (id=%d)", cat_name, root_id)

    # Create pillar nodes under each category
    for cat_name, pillars in TOP_LEVEL_CLUSTERS.items():
        for pillar in pillars:
            pillar_name = f"{cat_name}_{pillar.lower()}"
            pillar_id = queue.add_cluster(
                name=pillar_name,
                parent=f"cluster_{cat_name}",
                pillar_keyword=f"{pillar} baby names",
                depth=1,
            )
            stats["clusters_created"] += 1

            # Create sub-clusters for each dimension
            for dim in SUB_DIMENSIONS:
                sub_name = f"{cat_name}_{pillar.lower()}_{dim}"
                sub_id = queue.add_cluster(
                    name=sub_name,
                    parent=pillar_name,
                    depth=2,
                )
                stats["clusters_created"] += 1

                # Generate keywords for this sub-cluster
                kws = _generate_cluster_keywords(pillar, dim, cat_name)
                stats["keywords_added"] += len(kws)

    log.info("Cluster build complete: %d clusters, ~%d keywords",
             stats["clusters_created"], stats["keywords_added"])
    return stats


def _generate_cluster_keywords(pillar: str, dimension: str,
                                category: str) -> list[str]:
    """Generate keywords for a specific cluster leaf."""
    keywords = []
    templates = [
        f"{pillar} {dimension.replace('_', ' ')} baby names",
        f"{dimension.replace('_', ' ')} {pillar} names",
        f"unique {pillar} {dimension.replace('_', ' ')} names",
        f"modern {pillar} {dimension.replace('_', ' ')} names",
    ]
    keywords.extend(templates)

    # Letter-specific templates
    if "starting" in dimension or "letter" in dimension:
        for letter in "abcdefghij":
            keywords.append(f"{pillar} {dimension.replace('_', ' ')} starting with {letter}")

    # Ending-specific templates
    if "ending" in dimension:
        endings = ["a", "ia", "ea", "o", "er", "ley", "ette"]
        for ending in endings:
            keywords.append(f"{pillar} names ending with {ending}")

    return keywords


def get_cluster_hierarchy(queue: TopicQueue) -> list[dict]:
    """Return the full cluster tree."""
    clusters = queue.get_all_clusters()
    tree = []
    for c in clusters:
        tree.append({
            "id": c["id"],
            "name": c["name"],
            "parent": c["parent"],
            "pillar": c["pillar"],
            "depth": c["depth"],
            "keyword_count": len(queue.get_cluster_keywords(c["name"])),
        })
    return tree
