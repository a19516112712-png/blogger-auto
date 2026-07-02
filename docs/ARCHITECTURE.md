# Architecture — Blogger Auto SEO System

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub Actions (Cron)                        │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ generate.yml │  │ publish.yml  │  │ self_improving.yml   │  │
│  │ (daily 00:00)│  │(on generate  │  │ (daily 03:30)        │  │
│  │              │  │  complete)   │  │                      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                 │                      │              │
│         ▼                 ▼                      ▼              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │generate_     │  │  publish.py  │  │ self_improving_loop  │  │
│  │content.py    │  │              │  │                      │  │
│  └──────┬───────┘  └──────────────┘  └──────────┬───────────┘  │
│         │                                        │              │
│         ▼                                        ▼              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              SQLite Database (topic_queue.db)             │  │
│  │                                                           │  │
│  │  keywords  │  generated  │  published  │  refresh_queue  │  │
│  │  clusters  │  failed     │  internal_links                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│         ▲                                        │              │
│         │                                        ▼              │
│  ┌──────┴───────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │topic_cluster │  │quality_      │  │content_evolver       │  │
│  │keyword_      │  │engine         │  │internal_linker        │  │
│  │discovery      │  │seo_validator  │  │reporter               │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  Blogger API v3 (OAuth 2.0)               │  │
│  │              babynameideas2026.blogspot.com               │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Daily Execution Flow

```
┌─ Phase 0: Pre-flight ──────────────────────────────────────┐
│  1. Check AGNES_API_KEY                                    │
│  2. Initialize SQLite database                             │
│  3. Build topic clusters (if empty)                        │
└────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─ Phase 1: Keyword Discovery ───────────────────────────────┐
│  1. Run combinatorial keyword engine (10K+ combinations)   │
│  2. Score by CPC, intent, difficulty, volume               │
│  3. Bulk insert into keywords table (deduped)              │
└────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─ Phase 2: Topic Queue ─────────────────────────────────────┐
│  1. SELECT * FROM keywords WHERE status='pending'          │
│  2. ORDER BY priority DESC, RANDOM()                       │
│  3. LIMIT ARTICLES_PER_RUN                                 │
│  4. Mark selected as 'generating'                          │
└────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─ Phase 3: Content Generation ──────────────────────────────┐
│  1. For each topic:                                       │
│     a. Call Agnes AI (retry on 429/500/503)               │
│     b. Extract & enforce title rules                      │
│     c. Check duplicate (title/slug/keyword/hash)          │
│     d. Generate JSON-LD (Article, FAQ, Breadcrumb)        │
│     e. Save markdown to posts/                            │
│     f. Mark as 'generated' in DB                          │
└────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─ Phase 4: Quality Gate ────────────────────────────────────┐
│  1. Run seo_validator.py on each article                   │
│  2. Require score ≥ 95/100                                 │
│  3. Reject if: <2500 words, no FAQ, no schema, no table   │
└────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─ Phase 5: Frontmatter Repair ──────────────────────────────┐
│  1. repair_posts.py fixes any YAML issues                  │
│  2. Ensures all required fields present                    │
└────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─ Phase 6: Publish to Blogger ──────────────────────────────┐
│  1. Authenticate via OAuth 2.0 (auto-refresh)              │
│  2. Fetch existing posts (API dedup)                       │
│  3. For each valid post:                                   │
│     a. Check DB for duplicate slug/title                   │
│     b. Convert MD → HTML                                   │
│     c. Publish via Blogger API v3                          │
│     d. Store URL, labels, hash in published table          │
│     e. Mark keyword as 'published'                         │
│     f. Schedule refresh in 90 days                         │
└────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─ Phase 7: Post-Publish ────────────────────────────────────┐
│  1. Build internal link graph                              │
│  2. Run content evolution (refresh due articles)           │
│  3. Generate daily report                                  │
│  4. Commit to git (posts/*.md, database)                   │
└────────────────────────────────────────────────────────────┘
```

## Database Schema

```sql
keywords (master topic pool)
  id, keyword, intent, cluster, priority, difficulty,
  search_volume, cpc, status, created_at, published_at, last_updated

clusters (topic hierarchy)
  id, name, parent_cluster, pillar_keyword, depth, created_at

generated (produced articles)
  id, keyword_id, title, slug, url, word_count, quality_score,
  published, file_path, created_at, published_at

published (Blogger-published articles)
  id, keyword_id, generated_id, title, slug, url, publish_date,
  labels, content_hash, created_at

failed (generation/publish failures)
  id, keyword_id, title, slug, reason, attempt_count, created_at

refresh_queue (content evolution)
  id, published_id, scheduled_date, actual_date, actions, status, created_at

internal_links (persisted link graph)
  id, source_slug, target_slug, anchor_text, relevance_score, created_at
```

## Module Responsibility Map

| Module | Responsibility | Score |
|--------|---------------|-------|
| `database/topic_queue.py` | SQLite CRUD, topic lifecycle | ⭐⭐⭐⭐⭐ |
| `database/schema.py` | Table definitions, indexes | ⭐⭐⭐⭐⭐ |
| `keyword_discovery.py` | Combinatorial keyword generation | ⭐⭐⭐⭐⭐ |
| `topic_cluster.py` | Cluster hierarchy builder | ⭐⭐⭐⭐⭐ |
| `generate_content.py` | AI article generation + JSON-LD | ⭐⭐⭐⭐⭐ |
| `quality_engine.py` | Pre-publish quality gate | ⭐⭐⭐⭐⭐ |
| `seo_validator.py` | SEO scoring engine | ⭐⭐⭐⭐⭐ |
| `publish.py` | Blogger API publishing + DB storage | ⭐⭐⭐⭐⭐ |
| `repair_posts.py` | Frontmatter repair | ⭐⭐⭐⭐⭐ |
| `content_evolver.py` | 90-day article refresh | ⭐⭐⭐⭐⭐ |
| `internal_linker.py` | Smart contextual linking | ⭐⭐⭐⭐⭐ |
| `reporter.py` | Daily statistics report | ⭐⭐⭐⭐⭐ |
| `utils/helpers.py` | Shared utility functions | ⭐⭐⭐⭐⭐ |
| `utils/yaml_parser.py` | Frontmatter parsing | ⭐⭐⭐⭐⭐ |
| `orchestrator.py` | Master workflow coordinator | ⭐⭐⭐⭐⭐ |
