#!/usr/bin/env python3
"""
TopicQueue — SQLite-backed topic lifecycle manager.

Replaces all JSON-based topic tracking.

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

    def mark_generated(self, topic_id: int | None, title: str, slug: str,
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
        if topic_id:
            self.conn.execute(
                "UPDATE keywords SET status = 'generated', last_updated = ? WHERE id = ?",
                (now, topic_id),
            )
        self.conn.commit()
        log.info("mark_generated: topic_id=%s → generated_id=%d (%s)",
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

        if topic_id:
            self.conn.execute(
                "UPDATE keywords SET status = 'published', published_at = ?, last_updated = ? WHERE id = ?",
                (now, iso_now, topic_id),
            )
        self.conn.commit()
        log.info("mark_published: generated_id=%s → published_id=%d (blogger=%s)",
                 generated_id, published_id, blogger_id or "N/A")
        return published_id

    def mark_failed(self, topic_id: int | None, title: str | None,
                    slug: str | None, reason: str) -> None:
        """Record a failure."""
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT INTO failed (keyword_id, title, slug, reason, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (topic_id, title, slug, reason, now),
        )
        if topic_id:
            self.conn.execute(
                "UPDATE keywords SET status = 'failed', last_updated = ? WHERE id = ?",
                (now, topic_id),
            )
        self.conn.commit()
        log.info("mark_failed: topic_id=%s — %s", topic_id, reason)

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def is_duplicate_title(self, title: str) -> bool:
        """Check if a title already exists in published or generated tables."""
        norm = title.strip().lower()
        row = self.conn.execute(
            "SELECT 1 FROM published WHERE LOWER(title) = ? LIMIT 1",
            (norm,),
        ).fetchone()
        if row:
            return True
        row = self.conn.execute(
            "SELECT 1 FROM generated WHERE LOWER(title) = ? LIMIT 1",
            (norm,),
        ).fetchone()
        return bool(row)

    def is_duplicate_slug(self, slug: str) -> bool:
        """Check if a slug already exists."""
        row = self.conn.execute(
            "SELECT 1 FROM published WHERE slug = ? LIMIT 1",
            (slug,),
        ).fetchone()
        if row:
            return True
        row = self.conn.execute(
            "SELECT 1 FROM generated WHERE slug = ? LIMIT 1",
            (slug,),
        ).fetchone()
        return bool(row)

    # ------------------------------------------------------------------
    # Internal Links
    # ------------------------------------------------------------------

    def add_internal_link(self, source_slug: str, target_slug: str,
                          anchor_text: str, relevance: float) -> None:
        """Persist an internal link."""
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
    # Refresh Queue
    # ------------------------------------------------------------------

    def schedule_refresh(self, published_id: int, days: int = 90,
                         actions: str = "update") -> int:
        """Schedule an article for content refresh."""
        scheduled = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        now = datetime.now().isoformat()
        cur = self.conn.execute(
            """INSERT INTO refresh_queue (published_id, scheduled_date, actions, status, created_at)
               VALUES (?, ?, ?, 'pending', ?)""",
            (published_id, scheduled, actions, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_refresh_due(self, today: str | None = None) -> list[dict]:
        """Get articles due for refresh."""
        today = today or datetime.now().strftime("%Y-%m-%d")
        rows = self.conn.execute(
            """SELECT r.id, r.published_id, p.title, p.slug, r.actions, r.scheduled_date
               FROM refresh_queue r
               JOIN published p ON p.id = r.published_id
               WHERE r.status = 'pending' AND r.scheduled_date <= ?
               ORDER BY r.scheduled_date""",
            (today,),
        ).fetchall()
        return [
            {"id": r[0], "published_id": r[1], "title": r[2],
             "slug": r[3], "actions": r[4], "scheduled": r[5]}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Fingerprints
    # ------------------------------------------------------------------

    def save_fingerprint(self, filename: str, fp_data: dict) -> None:
        """Save a content fingerprint."""
        now = datetime.now().isoformat()
        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO fingerprints
                   (filename, content_hash, intro_hash, intro_signature,
                    heading_hierarchy, heading_structure, faq_hash, table_structure,
                    paragraph_distribution, conclusion_hash, conclusion_signature,
                    internal_links, schema_types, ai_patterns, word_count,
                    avg_paragraph_length, unique_word_ratio, quality_score, computed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    filename,
                    fp_data.get("content_hash", ""),
                    fp_data.get("intro_hash", ""),
                    fp_data.get("intro_signature", ""),
                    fp_data.get("heading_hierarchy", ""),
                    fp_data.get("heading_structure", ""),
                    fp_data.get("faq_hash", ""),
                    fp_data.get("table_structure", ""),
                    fp_data.get("paragraph_distribution", ""),
                    fp_data.get("conclusion_hash", ""),
                    fp_data.get("conclusion_signature", ""),
                    fp_data.get("internal_links", ""),
                    fp_data.get("schema_types", ""),
                    fp_data.get("ai_patterns", ""),
                    fp_data.get("word_count", 0),
                    fp_data.get("avg_paragraph_length", 0.0),
                    fp_data.get("unique_word_ratio", 0.0),
                    fp_data.get("quality_score", 0.0),
                    now,
                ),
            )
            self.conn.commit()
        except Exception as exc:
            log.warning("Failed to save fingerprint: %s", exc)

    # ------------------------------------------------------------------
    # Quality Scores
    # ------------------------------------------------------------------

    def save_quality_score(self, filename: str, scores: dict) -> None:
        """Save quality scores for an article."""
        now = datetime.now().isoformat()
        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO quality_scores
                   (filename, seo, eeat, readability, originality, authority,
                    internal_links, schema, content_depth, helpful_content,
                    overall, computed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    filename,
                    scores.get("seo", 0.0),
                    scores.get("eeat", 0.0),
                    scores.get("readability", 0.0),
                    scores.get("originality", 0.0),
                    scores.get("authority", 0.0),
                    scores.get("internal_links", 0.0),
                    scores.get("schema", 0.0),
                    scores.get("content_depth", 0.0),
                    scores.get("helpful_content", 0.0),
                    scores.get("overall", 0.0),
                    now,
                ),
            )
            self.conn.commit()
        except Exception as exc:
            log.warning("Failed to save quality score: %s", exc)

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

        Each tuple: (keyword, intent, cluster, priority, difficulty,
                     search_volume, cpc)
        Returns count of newly inserted rows.
        """
        now = datetime.now().isoformat()
        inserted = 0
        for kw_tuple in keywords:
            try:
                self.conn.execute(
                    """INSERT INTO keywords
                       (keyword, intent, cluster, priority, difficulty,
                        search_volume, cpc, status, created_at, last_updated)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                    (*kw_tuple, now, now),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass  # duplicate, skip
        self.conn.commit()
        log.info("bulk_insert_keywords: %d new topics inserted", inserted)
        return inserted

    def close(self):
        """Close the database connection."""
        self.conn.close()
