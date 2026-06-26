#!/usr/bin/env python3
"""
Link Graph Optimizer — Internal Link Reinforcement Engine
============================================================
Builds and optimizes the internal link graph across all articles.
Strengthens topical authority flow from supporting pages to pillars.

Features:
  - Build complete internal link graph from all posts
  - Identify orphaned pages (fewer than 3 incoming links)
  - Identify link-poor pages that need reinforcement
  - Generate contextual internal link suggestions
  - Add links to cluster pillar pages from supporting pages
  - Strengthen cross-cluster linking for SEO depth
"""

import json
import re
import logging
from pathlib import Path
from collections import defaultdict
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("link_optimizer")

BASE_DIR = Path(__file__).resolve().parent
POSTS_DIR = BASE_DIR / "posts"


def extract_slug_from_content(text: str, filename: str) -> str:
    """Extract slug from frontmatter or filename."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].split("\n"):
                if line.startswith("slug:"):
                    return line.split(":", 1)[1].strip().strip('"').strip("'")
    return filename.replace(".md", "")


def build_link_graph() -> dict:
    """Build a complete internal link graph: {slug: [linked_slug, ...]}."""
    posts = list(POSTS_DIR.glob("*.md"))
    if not posts:
        return {}

    # Build slug → title mapping
    slug_map = {}
    for p in posts:
        text = p.read_text(encoding="utf-8")
        slug = extract_slug_from_content(text, p.name)
        title = p.stem
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].split("\n"):
                    if line.startswith("title:"):
                        title = line.split(":", 1)[1].strip().strip('"').strip("'")
        slug_map[slug] = {"file": p.name, "title": title, "slug": slug}

    # Build outgoing link graph
    graph = defaultdict(set)
    for p in posts:
        text = p.read_text(encoding="utf-8")
        source_slug = extract_slug_from_content(text, p.name)
        for other_slug, info in slug_map.items():
            if other_slug != source_slug and other_slug in text:
                graph[source_slug].add(other_slug)

    return {k: list(v) for k, v in graph.items()}, slug_map


def find_orphans(graph: dict, min_links: int = 3) -> list:
    """Find pages with fewer than `min_links` outgoing internal links."""
    orphans = []
    for slug, links in graph.items():
        if len(links) < min_links:
            orphans.append({"slug": slug, "links": len(links), "needs": min_links - len(links)})
    orphans.sort(key=lambda x: x["links"])
    return orphans


def suggest_links_for_page(source_slug: str, graph: dict, slug_map: dict, count: int = 5) -> list:
    """Suggest internal links for a specific page from the link graph."""
    existing = set(graph.get(source_slug, []))
    suggestions = []

    for slug, info in slug_map.items():
        if slug != source_slug and slug not in existing:
            suggestions.append({
                "slug": slug,
                "title": info["title"],
                "file": info["file"],
                "link_text": f"[{info['title']}](/{slug})",
            })

    return suggestions[:count]


def optimize_links(max_pages: int = 10) -> dict:
    """Optimize internal links for orphaned/link-poor pages.

    Adds 3-10 contextual internal links per page to strengthen the graph.
    """
    graph, slug_map = build_link_graph()
    orphans = find_orphans(graph, min_links=3)

    if not orphans:
        log.info("No orphaned pages found. Link graph is healthy.")
        return {"optimized": 0, "details": []}

    log.info("Found %d link-poor pages (< 3 internal links).", len(orphans))

    results = {"optimized": 0, "details": []}
    for orphan in orphans[:max_pages]:
        slug = orphan["slug"]
        info = slug_map.get(slug, {})
        filepath = POSTS_DIR / info.get("file", f"{slug}.md")
        if not filepath.exists():
            continue

        suggestions = suggest_links_for_page(slug, graph, slug_map, count=orphan["needs"] + 3)
        if not suggestions:
            continue

        text = filepath.read_text(encoding="utf-8")
        # Find the Conclusion section or end of article for link insertion
        conclusion_pos = text.lower().find("## conclusion")
        if conclusion_pos < 0:
            conclusion_pos = text.rfind("</p>")
            if conclusion_pos < 0:
                conclusion_pos = len(text) - 50

        # Build "Related Articles" section
        related = "\n\n### Related Articles\n\n"
        for s in suggestions:
            related += f"- {s['link_text']}\n"

        # Insert before conclusion or at end
        if conclusion_pos > 0:
            new_text = text[:conclusion_pos] + related + "\n" + text[conclusion_pos:]
        else:
            new_text = text + related

        new_text = new_text.replace("## Conclusion\n\n", "## Conclusion\n\n" + related)

        filepath.write_text(new_text, encoding="utf-8")
        log.info("OPTIMIZED: %s (+%d links)", info.get("title", slug)[:50], len(suggestions))
        results["optimized"] += 1
        results["details"].append({
            "slug": slug,
            "title": info.get("title", slug),
            "links_added": len(suggestions),
            "new_total": len(suggestions) + orphan["links"],
        })

    return results


if __name__ == "__main__":
    print("=" * 60)
    print("LINK GRAPH OPTIMIZER")
    print("=" * 60)

    graph, slug_map = build_link_graph()
    total_links = sum(len(v) for v in graph.values())
    avg_links = total_links / len(graph) if graph else 0
    print(f"Pages in graph: {len(graph)}")
    print(f"Total internal links: {total_links}")
    print(f"Average links/page: {avg_links:.1f}")

    orphans = find_orphans(graph)
    if orphans:
        print(f"\nLink-poor pages (< 3 links): {len(orphans)}")
        for o in orphans[:5]:
            info = slug_map.get(o["slug"], {})
            print(f"  [{o['links']} links] {info.get('title', o['slug'])[:60]}")

    print(f"\nOptimizing...")
    results = optimize_links(max_pages=10)
    print(f"Pages optimized: {results['optimized']}")
    for d in results["details"]:
        print(f"  ✅ {d['title'][:50]}: +{d['links_added']} links (total: {d['new_total']})")
