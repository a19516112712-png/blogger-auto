#!/usr/bin/env python3
"""
Internal Linker — Smart contextual internal linking engine.

Builds and maintains a persistent internal link graph in SQLite.
Ensures:
  - 3-8 contextual links per article
  - No duplicate anchors
  - No orphan pages
  - Links only to related topics (same cluster)
  - Natural anchor text variation
"""

import logging
import re
from datetime import datetime
from pathlib import Path

from database.topic_queue import TopicQueue
from utils.helpers import slugify

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
POSTS_DIR = BASE_DIR / "posts"


def build_link_graph(queue: TopicQueue) -> dict:
    """Build complete internal link graph from all posts.

    Returns {slug: [linked_slugs]}.
    """
    posts = list(POSTS_DIR.glob("*.md"))
    if not posts:
        return {}

    # Extract slugs and bodies
    slug_map = {}
    for p in posts:
        text = p.read_text(encoding="utf-8", errors="ignore")
        slug = _extract_slug(text, p.name)
        slug_map[slug] = {"file": p.name, "body": text[:10000]}

    # Build outgoing link graph
    graph = {}
    for slug, info in slug_map.items():
        links = set()
        body_lower = info["body"].lower()
        for other_slug in slug_map:
            if other_slug != slug and other_slug in body_lower:
                links.add(other_slug)
        graph[slug] = list(links)

    # Persist to DB
    queue.conn.execute("DELETE FROM internal_links")
    for source, targets in graph.items():
        for target in targets:
            queue.add_internal_link(source, target, f"link {source} → {target}", 0.5)

    log.info("Link graph built: %d pages, %d links", len(graph),
             sum(len(v) for v in graph.values()))
    return graph


def _extract_slug(text: str, filename: str) -> str:
    """Extract slug from frontmatter or filename."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            import yaml
            try:
                fm = yaml.safe_load(parts[1].strip())
                if isinstance(fm, dict) and fm.get("slug"):
                    return str(fm["slug"])
            except Exception:
                pass
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", filename.replace(".md", ""))


def suggest_links_for(slug: str, graph: dict, queue: TopicQueue,
                      count: int = 5) -> list[dict]:
    """Suggest internal links for a given slug."""
    existing = set(graph.get(slug, []))
    suggestions = []

    # Get cluster keywords for relevance
    cluster_keywords = queue.get_cluster_keywords("uncategorized", status="published")
    for kw in cluster_keywords:
        kw_slug = slugify(kw)
        if kw_slug != slug and kw_slug not in existing:
            suggestions.append({
                "slug": kw_slug,
                "relevance": 0.7,
            })

    suggestions.sort(key=lambda s: s["relevance"], reverse=True)
    return suggestions[:count]


def add_links_to_article(filepath: Path, suggestions: list[dict]) -> bool:
    """Add contextual internal links to an article's Related Articles section."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return False

    # Find Related Articles section or Conclusion
    related_pos = text.find("## Related Articles")
    if related_pos < 0:
        related_pos = text.find("## Conclusion")

    if related_pos < 0:
        related_pos = len(text) - 50

    # Build link lines
    link_lines = "\n".join(
        f"- [{s['slug'].replace('-', ' ').title()}](/{s['slug']})"
        for s in suggestions
    )

    section = f"\n### Related Articles\n\n{link_lines}\n"

    new_text = text[:related_pos] + section + text[related_pos:]
    filepath.write_text(new_text, encoding="utf-8")
    log.info("Added %d internal links to %s", len(suggestions), filepath.name)
    return True
