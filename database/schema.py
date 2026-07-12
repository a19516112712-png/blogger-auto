#!/usr/bin/env python3
"""
SQLite schema for the Blogger Auto SEO system.

Tables:
  keywords       — Master topic pool (unlimited combinatorial generation)
  clusters       — Topic cluster definitions and hierarchy
  generated      — Articles that have been generated (pending publish)
  published      — Articles successfully published to Blogger
  failed         — Articles that failed generation/publish
  refresh_queue   — Articles scheduled for content evolution
  internal_links  — Persisted internal link graph
  topic_history   — Every generated topic stored forever (never regenerate)

All topic state lives here. No more JSON files.
"""

import sqlite3
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent / "topic_queue.db"

SCHEMA_SQL = """
-- Keywords: the master topic pool, populated by combinatorial engine
CREATE TABLE IF NOT EXISTS keywords (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword         TEXT    NOT NULL UNIQUE,
    intent          TEXT    NOT NULL DEFAULT 'LIST_INTENT',
    cluster         TEXT    NOT NULL DEFAULT 'uncategorized',
    priority        REAL    NOT NULL DEFAULT 50.0,
    difficulty      REAL    NOT NULL DEFAULT 50.0,
    search_volume   INTEGER NOT NULL DEFAULT 0,
    cpc             REAL    NOT NULL DEFAULT 0.0,
    status          TEXT    NOT NULL DEFAULT 'pending',
    created_at      TEXT    NOT NULL,
    published_at    TEXT,
    last_updated    TEXT    NOT NULL
);

-- Clusters: hierarchical topic organization
CREATE TABLE IF NOT EXISTS clusters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    parent_cluster  TEXT,
    pillar_keyword  TEXT,
    depth           INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL
);

-- Generated: articles produced but not yet published
CREATE TABLE IF NOT EXISTS generated (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id      INTEGER,
    title           TEXT    NOT NULL,
    slug            TEXT    NOT NULL UNIQUE,
    url             TEXT,
    word_count      INTEGER NOT NULL DEFAULT 0,
    quality_score   REAL    NOT NULL DEFAULT 0.0,
    published       INTEGER NOT NULL DEFAULT 0,
    file_path       TEXT,
    created_at      TEXT    NOT NULL,
    published_at    TEXT,
    FOREIGN KEY (keyword_id) REFERENCES keywords(id)
);

-- Published: successfully published to Blogger
CREATE TABLE IF NOT EXISTS published (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id      INTEGER,
    generated_id    INTEGER,
    title           TEXT    NOT NULL,
    slug            TEXT    NOT NULL UNIQUE,
    url             TEXT    NOT NULL,
    publish_date    TEXT    NOT NULL,
    labels          TEXT,
    content_hash    TEXT    NOT NULL,
    blogger_post_id TEXT,
    created_at      TEXT    NOT NULL,
    FOREIGN KEY (keyword_id) REFERENCES keywords(id),
    FOREIGN KEY (generated_id) REFERENCES generated(id)
);

-- Failed: articles that failed generation or publishing
CREATE TABLE IF NOT EXISTS failed (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id      INTEGER,
    title           TEXT,
    slug            TEXT,
    reason          TEXT    NOT NULL,
    attempt_count   INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL,
    FOREIGN KEY (keyword_id) REFERENCES keywords(id)
);

-- Refresh queue: articles scheduled for content evolution
CREATE TABLE IF NOT EXISTS refresh_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    published_id    INTEGER NOT NULL,
    scheduled_date  TEXT    NOT NULL,
    actual_date     TEXT,
    actions         TEXT,
    status          TEXT    NOT NULL DEFAULT 'pending',
    created_at      TEXT    NOT NULL,
    FOREIGN KEY (published_id) REFERENCES published(id)
);

-- Internal links: persisted link graph
CREATE TABLE IF NOT EXISTS internal_links (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_slug     TEXT    NOT NULL,
    target_slug     TEXT    NOT NULL,
    anchor_text     TEXT    NOT NULL,
    relevance_score REAL    NOT NULL DEFAULT 0.0,
    created_at      TEXT    NOT NULL,
    UNIQUE(source_slug, target_slug)
);

-- Fingerprints: structural fingerprint of every article
CREATE TABLE IF NOT EXISTS fingerprints (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    filename            TEXT    NOT NULL UNIQUE,
    content_hash        TEXT    NOT NULL,
    intro_hash          TEXT    NOT NULL,
    intro_signature     TEXT,
    heading_hierarchy   TEXT,
    heading_structure   TEXT,
    faq_hash            TEXT,
    table_structure     TEXT,
    paragraph_distribution TEXT,
    conclusion_hash     TEXT    NOT NULL,
    conclusion_signature TEXT,
    internal_links      TEXT,
    schema_types        TEXT,
    ai_patterns         TEXT,
    word_count          INTEGER NOT NULL DEFAULT 0,
    avg_paragraph_length REAL,
    unique_word_ratio   REAL,
    quality_score       REAL    NOT NULL DEFAULT 0.0,
    computed_at         TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fingerprints_intro ON fingerprints(intro_hash);
CREATE INDEX IF NOT EXISTS idx_fingerprints_conclusion ON fingerprints(conclusion_hash);
CREATE INDEX IF NOT EXISTS idx_fingerprints_content ON fingerprints(content_hash);
CREATE INDEX IF NOT EXISTS idx_fingerprints_quality ON fingerprints(quality_score);

-- Quality scores: per-article quality assessment
CREATE TABLE IF NOT EXISTS quality_scores (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    filename            TEXT    NOT NULL UNIQUE,
    seo                 REAL    NOT NULL DEFAULT 0.0,
    eeat                REAL    NOT NULL DEFAULT 0.0,
    readability         REAL    NOT NULL DEFAULT 0.0,
    originality         REAL    NOT NULL DEFAULT 0.0,
    authority           REAL    NOT NULL DEFAULT 0.0,
    internal_links      REAL    NOT NULL DEFAULT 0.0,
    schema              REAL    NOT NULL DEFAULT 0.0,
    content_depth       REAL    NOT NULL DEFAULT 0.0,
    helpful_content     REAL    NOT NULL DEFAULT 0.0,
    overall             REAL    NOT NULL DEFAULT 0.0,
    computed_at         TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quality_overall ON quality_scores(overall);
CREATE INDEX IF NOT EXISTS idx_quality_filename ON quality_scores(filename);

-- Topic History: every generated topic stored forever.
-- Never regenerated again. Enforces 100% uniqueness across all time.
CREATE TABLE IF NOT EXISTS topic_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic           TEXT    NOT NULL,
    normalized_topic TEXT   NOT NULL,
    top_level_cluster TEXT NOT NULL,
    leaf_cluster    TEXT    NOT NULL,
    fingerprint     TEXT    NOT NULL,
    source          TEXT    NOT NULL DEFAULT 'combinatorial',
    created_at      TEXT    NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_topic_history_normalized
    ON topic_history(normalized_topic);
CREATE INDEX IF NOT EXISTS idx_topic_history_cluster
    ON topic_history(top_level_cluster);
CREATE INDEX IF NOT EXISTS idx_topic_history_fingerprint
    ON topic_history(fingerprint);

-- Indexes for performance at scale (100K+ topics)
CREATE INDEX IF NOT EXISTS idx_keywords_status ON keywords(status);
CREATE INDEX IF NOT EXISTS idx_keywords_cluster ON keywords(cluster);
CREATE INDEX IF NOT EXISTS idx_keywords_priority ON keywords(priority DESC);
CREATE INDEX IF NOT EXISTS idx_keywords_keyword ON keywords(keyword);
CREATE INDEX IF NOT EXISTS idx_generated_slug ON generated(slug);
CREATE INDEX IF NOT EXISTS idx_generated_published ON generated(published);
CREATE INDEX IF NOT EXISTS idx_published_slug ON published(slug);
CREATE INDEX IF NOT EXISTS idx_published_url ON published(url);
CREATE INDEX IF NOT EXISTS idx_published_hash ON published(content_hash);
CREATE INDEX IF NOT EXISTS idx_refresh_scheduled ON refresh_queue(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_refresh_status ON refresh_queue(status);
CREATE INDEX IF NOT EXISTS idx_links_source ON internal_links(source_slug);
CREATE INDEX IF NOT EXISTS idx_links_target ON internal_links(target_slug);
"""


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Initialize the database and return a connection.

    Creates all tables and indexes if they don't exist.
    """
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")

    conn.executescript(SCHEMA_SQL)
    conn.commit()
    log.info("Database initialized: %s", path)
    return conn


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a database connection (caller must close it)."""
    return sqlite3.connect(str(db_path or DB_PATH))
