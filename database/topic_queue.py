#!/usr/bin/env python3
"""
TopicQueue — SQLite-backed topic lifecycle manager.

Replaces all JSON-based topic tracking (generated_topics.json,
published_topics.json, index_log.json).

State machine:
  pending → generating → generated → published
                      ↘ failed
  published → (after N days) → pending (refresh_queue)

Usage:
    q = TopicQueue()
    topics = q.get_pending_topics(limit=5)
    q.mark_generating(topics)
    # ... generate articles ...
    q.mark_generated(topics, titles, slugs)
    # ... publish to Blogger ...
    q.mark_published(topics, urls, hashes)
"""

import sqlite3
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .schema import init_db, DB_PATH, get_connection
from utils.helpers import normalize_title_for_dedup

log = logging.getLogger(__name__)


class TopicQueue:
    """Manages the full lifecycle of topics through SQLite."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        self.conn = init_db(self.db_path)

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------

    def get_pending_topics(self, limit: int = 5, cluster: str | None = None) -> list[dict]:
        """SELECT pending topics, ORDER BY RANDOM(), LIMIT N."""
        sql = """
            SELECT id, keyword, intent, cluster, priority, difficulty,
                   search_volume, cpc, status, created_at
            FROM keywords
            WHERE status = 'pending'
        """
        params: list = []
        if cluster:
            sql += " AND cluster = ?"
            params.append(cluster)
        sql += " ORDER BY priority DESC, RANDOM() LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        topics = []
        for row in rows:
            topics.append({
                "id": row[0],
                "keyword": row[1],
                "intent": row[2],
                "cluster": row[3],
                "priority": row[4],
                "difficulty": row[5],
                "search_volume": row[6],
                "cpc": row[7],
                "status": row[8],
                "created_at": row[9],
            })
        log.info("get_pending_topics: %d found (limit=%d, cluster=%s)",
                 len(topics), limit, cluster)
        return topics

    def mark_generating(self, topic_ids: list[int]) -> None:
        """SET status = 'generating' for topic IDs."""
        if not topic_ids:
            return
        placeholders = ",".join("?" for _ in topic_ids)
        now = datetime.now().isoformat()
        self.conn.execute(
            f"UPDATE keywords SET status = 'generating', last_updated = ? "
            f"WHERE id IN ({placeholders})",
            [now] + topic_ids,
        )
        self.conn.commit()
        log.info("mark_generating: %d topics", len(topic_ids))

    def mark_generated(self, topic_id: int, title: str, slug: str,
                       word_count: int, quality_score: float,
                       file_path: str) -> int:
        """Insert into generated table, link to keyword."""
        now = datetime.now().isoformat()
        cur = self.conn.execute(
            """INSERT INTO generated (keyword_id, title, slug, word_count,
                                       quality_score, file_path, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (topic_id, title, slug, word_count, quality_score, file_path, now),
        )
        generated_id = cur.lastrowid

        # Also mark keyword as generated
        self.conn.execute(
            "UPDATE keywords SET status = 'generated', last_updated = ? WHERE id = ?",
            (now, topic_id),
        )
        self.conn.commit()
        log.info("mark_generated: topic_id=%d → generated_id=%d (%s)",
                 topic_id, generated_id, slug)
        return generated_id

    def mark_published(self, topic_id: int | None, generated_id: int | None,
                       title: str, slug: str, url: str,
                       labels: list[str], content_hash: str,
                       blogger_id: str | None = None,
                       publish_date: str | None = None) -> int:
        """Insert into published table, mark keyword as published."""
        now = publish_date or datetime.now().strftime("%Y-%m-%d")
        iso_now = datetime.now().isoformat()
        cur = self.conn.execute(
            """INSERT INTO published (keyword_id, generated_id, title, slug,
                                      url, publish_date, labels, content_hash,
                                      blogger_post_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (topic_id, generated_id, title, slug, url, now,
             ",".join(labels), content_hash, blogger_id, iso_now),
        )
        published_id = cur.lastrowid

        if topic_id is not None:
            self.conn.execute(
                "UPDATE keywords SET status = 'published', published_at = ? "
                "WHERE id = ?",
                (iso_now, topic_id),
            )
        self.conn.commit()
        log.info("mark_published: topic_id=%d → published_id=%d (%s)",
                 topic_id, published_id, slug)
        return published_id

    def mark_failed(self, topic_id: int | None, title: str | None,
                    slug: str | None, reason: str) -> None:
        """Log a failure."""
        now = datetime.now().isoformat()
        if topic_id:
            self.conn.execute(
                "UPDATE keywords SET status = 'failed', last_updated = ? WHERE id = ?",
                (now, topic_id),
            )
        self.conn.execute(
            """INSERT INTO failed (keyword_id, title, slug, reason, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (topic_id, title, slug, reason, now),
        )
        self.conn.commit()
        log.warning("mark_failed: %s — %s", title or slug or topic_id, reason)

    # ------------------------------------------------------------------
    # Duplicate prevention
    # ------------------------------------------------------------------

    def is_duplicate_slug(self, slug: str) -> bool:
        """Check if slug exists in generated or published tables."""
        slug_lower = slug.lower()
        row = self.conn.execute(
            "SELECT 1 FROM generated WHERE slug = ? LIMIT 1",
            (slug_lower,),
        ).fetchone()
        if row:
            return True
        row = self.conn.execute(
            "SELECT 1 FROM published WHERE slug = ? LIMIT 1",
            (slug_lower,),
        ).fetchone()
        return bool(row)

    def is_duplicate_keyword(self, keyword: str) -> bool:
        """Check if keyword already exists in any state."""
        row = self.conn.execute(
            "SELECT 1 FROM keywords WHERE keyword = ? LIMIT 1",
            (keyword.lower().strip(),),
        ).fetchone()
        return bool(row)

    def is_duplicate_title(self, title: str) -> bool:
        """Check if title already exists, using normalized comparison.
        
        Strips trailing numeric suffixes so "Foo 1" matches "Foo".
        """
        norm = normalize_title_for_dedup(title)
        row = self.conn.execute(
            "SELECT 1 FROM generated WHERE LOWER(title) = ? LIMIT 1",
            (norm,),
        ).fetchone()
        if row:
            return True
        row = self.conn.execute(
            "SELECT 1 FROM published WHERE LOWER(title) = ? LIMIT 1",
            (norm,),
        ).fetchone()
        return bool(row)

    def is_duplicate_hash(self, content_hash: str) -> bool:
        """Check if content hash already published."""
        row = self.conn.execute(
            "SELECT 1 FROM published WHERE content_hash = ? LIMIT 1",
            (content_hash,),
        ).fetchone()
        return bool(row)

    # ------------------------------------------------------------------
    # Refresh queue (content evolution)
    # ------------------------------------------------------------------

    def schedule_refresh(self, published_id: int = 0, days: int = 90,
                         actions: list[str] | None = None) -> None:
        """Add to refresh_queue for future content evolution."""
        scheduled = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        self.conn.execute("PRAGMA foreign_keys = OFF")
        self.conn.execute(
            """INSERT INTO refresh_queue (published_id, scheduled_date, actions,
                                          status, created_at)
               VALUES (?, ?, ?, 'pending', ?)""",
            (published_id, scheduled,
             ",".join(actions or []), datetime.now().isoformat()),
        )
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()

    def get_refresh_due(self) -> list[dict]:
        """SELECT refresh_queue entries due today."""
        today = datetime.now().strftime("%Y-%m-%d")
        rows = self.conn.execute(
            """SELECT rq.id, rq.published_id, rq.scheduled_date, rq.actions,
                      p.title, p.slug, p.url
               FROM refresh_queue rq
               JOIN published p ON rq.published_id = p.id
               WHERE rq.scheduled_date <= ? AND rq.status = 'pending'
               ORDER BY rq.scheduled_date""",
            (today,),
        ).fetchall()
        return [
            {
                "id": r[0], "published_id": r[1], "scheduled_date": r[2],
                "actions": r[3].split(",") if r[3] else [],
                "title": r[4], "slug": r[5], "url": r[6],
            }
            for r in rows
        ]

    def mark_refresh_done(self, refresh_id: int) -> None:
        self.conn.execute(
            "UPDATE refresh_queue SET status = 'done', actual_date = ? WHERE id = ?",
            (datetime.now().isoformat(), refresh_id),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Internal links
    # ------------------------------------------------------------------

    def add_internal_link(self, source_slug: str, target_slug: str,
                          anchor_text: str, relevance: float) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO internal_links
               (source_slug, target_slug, anchor_text, relevance_score, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (source_slug.lower(), target_slug.lower(), anchor_text,
             relevance, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_internal_links_for(self, slug: str) -> list[dict]:
        """Get suggested internal links for a slug."""
        rows = self.conn.execute(
            """SELECT target_slug, anchor_text, relevance_score
               FROM internal_links
               WHERE source_slug = ?
               ORDER BY relevance_score DESC
               LIMIT 10""",
            (slug.lower(),),
        ).fetchall()
        return [
            {"target_slug": r[0], "anchor_text": r[1], "relevance": r[2]}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Clusters
    # ------------------------------------------------------------------

    def add_cluster(self, name: str, parent: str | None = None,
                    pillar_keyword: str | None = None, depth: int = 0) -> int:
        now = datetime.now().isoformat()
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO clusters (name, parent_cluster,
                                               pillar_keyword, depth, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (name, parent, pillar_keyword, depth, now),
        )
        self.conn.commit()
        return cur.lastrowid or self.conn.execute(
            "SELECT id FROM clusters WHERE name = ?", (name,)
        ).fetchone()[0]

    def get_cluster_keywords(self, cluster_name: str,
                             status: str = "pending") -> list[str]:
        rows = self.conn.execute(
            "SELECT keyword FROM keywords WHERE cluster = ? AND status = ?",
            (cluster_name, status),
        ).fetchall()
        return [r[0] for r in rows]

    def get_all_clusters(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, name, parent_cluster, pillar_keyword, depth FROM clusters ORDER BY depth, name"
        ).fetchall()
        return [
            {"id": r[0], "name": r[1], "parent": r[2],
             "pillar": r[3], "depth": r[4]} for r in rows
        ]

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Return topic pool statistics."""
        counts = {}
        for status in ("pending", "generating", "generated", "published", "failed"):
            row = self.conn.execute(
                "SELECT COUNT(*) FROM keywords WHERE status = ?", (status,)
            ).fetchone()
            counts[status] = row[0]

        total_keywords = counts.get("pending", 0) + counts.get("generating", 0) + \
                         counts.get("generated", 0) + counts.get("published", 0) + \
                         counts.get("failed", 0)

        return {
            "total_keywords": total_keywords,
            "pending": counts.get("pending", 0),
            "generating": counts.get("generating", 0),
            "generated": counts.get("generated", 0),
            "published": counts.get("published", 0),
            "failed": counts.get("failed", 0),
            "clusters": self.conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0],
            "refresh_due": self.conn.execute(
                "SELECT COUNT(*) FROM refresh_queue WHERE status = 'pending'"
            ).fetchone()[0],
            "internal_links": self.conn.execute(
                "SELECT COUNT(*) FROM internal_links"
            ).fetchone()[0],
        }

    # ------------------------------------------------------------------
    # Bulk insert keywords
    # ------------------------------------------------------------------

    def bulk_insert_keywords(self, keywords: list[tuple]) -> int:
        """Insert multiple keywords at once.

        Accepts both 7-tuple format (keyword, intent, cluster, priority,
        difficulty, search_volume, cpc) and 9-tuple format (adds
        top_level_cluster, leaf_cluster at positions 8-9).

        Returns count of newly inserted rows.
        """
        now = datetime.now().isoformat()
        inserted = 0
        for kw_tuple in keywords:
            try:
                # Always use first 7 fields for the INSERT (keyword through cpc)
                self.conn.execute(
                    """INSERT INTO keywords
                       (keyword, intent, cluster, priority, difficulty,
                        search_volume, cpc, status, created_at, last_updated)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                    (kw_tuple[0], kw_tuple[1], kw_tuple[2], kw_tuple[3],
                     kw_tuple[4], kw_tuple[5], kw_tuple[6], now, now),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass  # duplicate, skip
        self.conn.commit()
        log.info("bulk_insert_keywords: %d new topics inserted", inserted)
        return inserted

    # ------------------------------------------------------------------
    # Diversity Scoring (Rule 8)
    # ------------------------------------------------------------------

    def calculate_diversity_score(self, topics: list[dict]) -> float:
        """Calculate topic diversity score for a batch of topics.
        
        Returns 0-100 based on how many unique top-level clusters are represented.
        Score >95 required for publishing.
        
        Measures coverage of available top-level categories.
        With 19 available categories, having 15+ = ~95%+ diversity.
        """
        if not topics:
            return 0.0
        
        try:
            from keyword_discovery import TOP_LEVEL_CLUSTERS, _extract_top_level_cluster_v2
        except ImportError:
            return 0.0
        
        top_clusters = set()
        for topic in topics:
            keyword = topic.get("keyword", "")
            try:
                top_cluster = _extract_top_level_cluster_v2(keyword)
            except Exception:
                top_cluster = topic.get("cluster", "uncategorized").split("_")[0]
            top_clusters.add(top_cluster)
        
        num_unique = len(top_clusters)
        total_available = len(TOP_LEVEL_CLUSTERS)  # e.g., 19
        
        if total_available == 0:
            return 0.0
        
        # Score: percentage of available top-level categories covered
        base_score = (num_unique / total_available) * 100
        
        # Bonus for having many unique clusters relative to batch size
        # This rewards spreading topics across different clusters
        batch_size = len(topics)
        if batch_size > 0:
            uniqueness_ratio = num_unique / batch_size
            bonus = min(5.0, uniqueness_ratio * 10)
        else:
            bonus = 0.0
        
        return min(100.0, round(base_score + bonus, 1))

    def get_top_level_cluster(self, keyword: str) -> str:
        """Get the top-level cluster for a keyword.
        
        Uses the scoring system from keyword_discovery.
        Falls back to first part of cluster name if import fails.
        """
        try:
            from keyword_discovery import _extract_top_level_cluster
            return _extract_top_level_cluster(keyword)
        except ImportError:
            return "uncategorized"

    def get_daily_excluded_clusters(self, today_topics: list[dict]) -> set[str]:
        """Get top-level clusters that should be excluded for today.
        
        If today includes Nature cluster, exclude all nature-related sub-clusters:
        Nature, Plants, Flowers, Trees, Ocean, etc.
        """
        excluded = set()
        for topic in today_topics:
            keyword = topic.get("keyword", "")
            top_cluster = self.get_top_level_cluster(keyword)
            excluded.add(top_cluster)
            
            # Also exclude related sub-clusters
            related = {
                "nature": {"nature", "animals", "flowers"},
                "animals": {"nature", "animals"},
                "flowers": {"nature", "flowers"},
                "origin": {"origin"},
                "mythology": {"mythology"},
                "style": {"style"},
                "meaning": {"meaning"},
                "religion": {"religion"},
                "colors": {"colors"},
                "seasons": {"seasons"},
                "occupations": {"occupations"},
                "celebrity_trends": {"celebrity_trends"},
                "space_science": {"space_science"},
                "literature_fantasy": {"literature_fantasy"},
                "history_ancient": {"history_ancient"},
                "countries_cities": {"countries_cities"},
                "pronunciation_spelling": {"pronunciation_spelling"},
                "family_relationships": {"family_relationships"},
                "traits_qualities": {"traits_qualities"},
            }
            if top_cluster in related:
                excluded |= related[top_cluster]
        
        return excluded

    # ------------------------------------------------------------------
    # Topic History (Rule 7: Store every generated topic forever)
    # ------------------------------------------------------------------

    def record_topic_history(self, keyword: str, top_level_cluster: str,
                              leaf_cluster: str, source: str = "combinatorial") -> bool:
        """Record a topic in the history table. Never regenerate it again."""
        from keyword_discovery import _normalize, _keyword_hash
        
        normalized = _normalize(keyword)
        fingerprint = _keyword_hash(keyword)
        
        try:
            self.conn.execute(
                """INSERT INTO topic_history 
                   (topic, normalized_topic, top_level_cluster, leaf_cluster, 
                    fingerprint, source, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (keyword, normalized, top_level_cluster, leaf_cluster,
                 fingerprint, source, datetime.now().isoformat()),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Already recorded

    def is_in_topic_history(self, keyword: str) -> bool:
        """Check if a keyword has been generated before."""
        from keyword_discovery import _normalize
        
        normalized = _normalize(keyword)
        row = self.conn.execute(
            "SELECT 1 FROM topic_history WHERE normalized_topic = ? LIMIT 1",
            (normalized,),
        ).fetchone()
        return bool(row)

    def get_all_published_keywords(self) -> set[str]:
        """Get all keywords that have been published (from DB + topic_history)."""
        keywords = set()
        
        # From published table
        rows = self.conn.execute(
            """SELECT p.title FROM published p 
               UNION SELECT k.keyword FROM keywords k WHERE k.status = 'published'"""
        ).fetchall()
        for r in rows:
            keywords.add(r[0].lower().strip())
        
        # From topic_history
        rows = self.conn.execute(
            "SELECT normalized_topic FROM topic_history"
        ).fetchall()
        for r in rows:
            keywords.add(r[0])
        
        return keywords

    def get_all_generated_keywords(self) -> set[str]:
        """Get all keywords that have ever been generated (from topic_history)."""
        keywords = set()
        rows = self.conn.execute(
            "SELECT normalized_topic FROM topic_history"
        ).fetchall()
        for r in rows:
            keywords.add(r[0])
        return keywords

    def close(self):
        """Close the database connection."""
        self.conn.close()
