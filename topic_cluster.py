#!/usr/bin/env python3
"""
Topic Cluster Engine — Automated cluster builder and maintainer.

Builds hierarchical topic clusters automatically:
  Irish Baby Names (pillar)
  ├─ Irish Boy Names
  ├─ Irish Girl Names
  ├─ Irish Middle Names
  ├─ Irish Twin Names
  ├─ Irish Names Starting With A
  └─ Irish Names Ending With N

Each cluster auto-links to its siblings and parent.
"""

import logging
from datetime import datetime

from database.topic_queue import TopicQueue

log = logging.getLogger(__name__)

# Cluster definitions — pillar + sub-dimensions
CLUSTER_DEFINITIONS = {
    "origin": {
        "pillars": [
            "Irish", "Japanese", "Korean", "French", "Italian", "Spanish",
            "German", "Arabic", "Greek", "Scandinavian", "Celtic", "Nordic",
            "Russian", "Polish", "Dutch", "Hawaiian", "African", "Indian",
            "Persian", "Chinese", "Hebrew", "Latin", "Slavic", "Portuguese",
            "Turkish", "Egyptian", "Welsh", "Scottish", "English", "Finnish",
        ],
        "dimensions": [
            "Boy", "Girl", "Unisex", "Middle Names", "Twin Names",
            "Starting With", "Ending With", "Last Names", "Dog Names",
            "Nicknames", "Baby Names",
        ],
    },
    "meaning": {
        "pillars": [
            "Love", "Hope", "Light", "Peace", "Joy", "Strength", "Grace",
            "Wisdom", "Miracle", "Blessing", "Dream", "Star", "Brave",
            "Courage", "Faith", "Truth", "Honor", "Victory", "Freedom",
            "Beauty", "Power", "Kindness", "Noble", "Pure", "Bright",
        ],
        "dimensions": [
            "Boy", "Girl", "Unisex", "Baby Names", "Middle Names",
        ],
    },
    "nature": {
        "pillars": [
            "Flower", "Tree", "Ocean", "Mountain", "River", "Lake",
            "Forest", "Garden", "Meadow", "Beach", "Star", "Moon",
            "Sun", "Sky", "Earth", "Fire", "Water", "Wind",
            "Bird", "Animal", "Dragon", "Phoenix", "Diamond", "Pearl",
        ],
        "dimensions": [
            "Boy", "Girl", "Baby Names", "Middle Names",
        ],
    },
    "mythology": {
        "pillars": [
            "Greek", "Roman", "Norse", "Egyptian", "Celtic", "Hindu",
            "Japanese", "Aztec", "Mayan", "Mesopotamian", "Persian",
        ],
        "dimensions": [
            "Boy", "Girl", "God", "Goddess", "Warrior", "Baby Names",
        ],
    },
    "style": {
        "pillars": [
            "Vintage", "Modern", "Unique", "Rare", "Classic", "Trending",
            "Popular", "Contemporary", "Traditional", "Bohemian",
        ],
        "dimensions": [
            "Boy", "Girl", "Baby Names", "Middle Names", "Twin Names",
        ],
    },
}


def build_clusters(queue: TopicQueue) -> dict:
    """Build all cluster hierarchies from definitions.

    Returns stats dict.
    """
    stats = {"clusters_created": 0, "keywords_added": 0}

    for category, config in CLUSTER_DEFINITIONS.items():
        for pillar in config["pillars"]:
            pillar_name = f"{category}_{pillar.lower()}"
            pillar_id = queue.add_cluster(
                name=pillar_name,
                parent=f"cluster_{category}",
                pillar_keyword=f"{pillar} baby names",
                depth=1,
            )
            stats["clusters_created"] += 1

            for dim in config["dimensions"]:
                sub_name = f"{category}_{pillar.lower()}_{dim.lower()}"
                sub_id = queue.add_cluster(
                    name=sub_name,
                    parent=pillar_name,
                    depth=2,
                )
                stats["clusters_created"] += 1

                # Generate keywords for this sub-cluster
                kws = _generate_cluster_keywords(pillar, dim, category)
                stats["keywords_added"] += len(kws)

    log.info("Cluster build complete: %d clusters, %d keywords",
             stats["clusters_created"], stats["keywords_added"])
    return stats


def _generate_cluster_keywords(pillar: str, dimension: str,
                                category: str) -> list[str]:
    """Generate keywords for a specific cluster leaf."""
    keywords = []
    templates = [
        f"{pillar} {dimension} baby names",
        f"{dimension} {pillar} names",
        f"unique {pillar} {dimension.lower()} names",
        f"modern {pillar} {dimension.lower()} names",
    ]
    if "starting" in dimension.lower():
        for letter in "abcdefghij":
            keywords.append(f"{pillar} {dimension.lower()} {letter}")
    if "ending" in dimension.lower():
        endings = ["a", "ia", "ea", "o", "er", "ley", "ette"]
        for ending in endings:
            keywords.append(f"{pillar} names ending with {ending}")
    else:
        keywords.extend(templates)

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
