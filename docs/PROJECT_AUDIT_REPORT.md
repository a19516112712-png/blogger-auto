# Blogger Auto — Complete Project Audit Report

**Date:** 2026-07-03  
**Scope:** Read-only audit. No files modified.  
**Repository:** `/Users/yuanfeng/Documents/blogger/blogger-auto`  
**Blog:** https://babynameideas2026.blogspot.com  
**Blog ID:** `122799461405250161`  

---

## 1. Architecture

### Current Workflow

```
Keyword Discovery (keyword_discovery.py)
  ↓ Combinatorial templates (15 dimensions × 30+ values)
  ↓ Inserts into SQLite keywords table

Topic Queue (database/topic_queue.py)
  ↓ get_pending_topics() — ORDER BY RANDOM(), LIMIT N
  ↓ mark_generating() → mark_generated() → mark_published()

Content Generation (generate_content.py)
  ↓ Picks topics from SQLite queue
  ↓ Falls back to keyword_discovery if pool exhausted
  ↓ Generates articles via Agnes AI (OpenAI-compatible)
  ↓ Validates quality (quality_engine.py, MIN_SCORE=95)
  ↓ Saves to posts/*.md with frontmatter

Frontmatter Repair (repair_posts.py)
  ↓ Scans all posts/*.md
  ↓ Ensures valid YAML frontmatter (title, date, labels)

Publishing (publish.py)
  ↓ Authenticates via CI credentials (CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)
  ↓ Dedup check against existing Blogger titles
  ↓ posts().insert() for new articles
  ↓ Records in SQLite published table

Internal Linking (internal_linker.py)
  ↓ Builds link graph from posts/
  ↓ Persists to SQLite internal_links table

Content Evolution (content_evolver.py)
  ↓ Scheduled via refresh_queue
  ↓ Expands articles via AI (preserve URL/slug/date)

Self-Improving Loop (self_improving_loop.py)
  ↓ Growth detection → Content evolution → Link optimization → Index acceleration

SEO Graph (seo_graph.py)
  ↓ Topic cluster definitions (4 clusters: names_by_meaning, international_names, style_collections, seasonal_themes)
  ↓ Content gap detection
  ↓ Pillar page readiness scoring

Fingerprint Engine (fingerprint_engine.py)
  ↓ Structural hashing (intro, headings, FAQ, tables, conclusion)
  ↓ Similarity detection (threshold: 15%)

Quality Engine (content_quality_engine.py)
  ↓ 10-dimensional scoring (SEO, EEAT, Readability, Originality, Authority, Internal Links, Schema, Content Depth, Helpful Content, Overall)
  ↓ Stored in SQLite quality_scores table

Canonical Updater (update_canonical_posts.py)
  ↓ CI-only (GitHub Actions)
  ↓ posts().patch() for 6 pre-selected canonical articles
  ↓ Preserves Blogger ID, URL, slug, publish date, labels
```

### Execution Order (Orchestrator)

```
orchestrator.py:
  Phase 0: Pre-flight (API key check)
  Phase 1: Init DB + Build clusters
  Phase 2: Keyword discovery (×5 multiplier)
  Phase 3: Content generation (generate_content.py)
  Phase 4: Frontmatter repair (repair_posts.py)
  Phase 5: Blogger publish (publish.py) — if credentials present
  Phase 6: Content evolution scheduling
  Phase 7: Internal link graph (internal_linker.py)
  Phase 8: Content evolution (content_evolver.py)
  Phase 9: Daily report (reporter.py)
```

### GitHub Actions Workflows (5 total)

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `autonomous.yml` | Daily 1AM UTC + dispatch | Full pipeline (generate → repair → publish → evolve) |
| `generate.yml` | Daily midnight UTC + dispatch | Generate only (no publish) |
| `publish.yml` | On generate completion + dispatch | Publish to Blogger |
| `self_improving.yml` | Daily 3:30AM UTC + dispatch | Self-improving growth loop |
| `update-canonical.yml` | Dispatch + push to specific files | Update 6 canonical articles via patch |

---

## 2. Duplicate Topic Analysis

### Potential Duplicate Sources

**Source 1: Static CLUSTER_DEFINITIONS in topic_cluster.py**
- 5 categories × ~30 pillars × ~10 dimensions = ~1,500 predefined keywords
- No dedup check during cluster building — `add_cluster()` uses `INSERT OR IGNORE` but keyword generation doesn't check existing DB

**Source 2: Combinatorial keyword_discovery.py**
- 15 dimensions × 30+ values × 30+ templates = ~13,500+ theoretical combinations
- Duplicates are checked via `seen` set + DB query, BUT:
  - `_normalize()` lowercases and strips — could miss case-sensitive duplicates
  - No uniqueness guarantee on generated keywords (e.g., "Irish Boy baby names" vs "Irish baby names for boys")

**Source 3: Duplicate file slugs in posts/**
- `vintage-baby-names-making-a-comeback-timeless-charm-for-today.md`
- `vintage-baby-names-making-a-comeback-timeless-charm-for-your-little-one.md`
  → Same topic, different titles, both published
- `timeless-literary-baby-names-from-classic-novels.md`
- `timeless-literary-baby-names-from-classic-novels-1.md`
  → Same topic, numbered duplicate

**Source 4: SQLite published table**
- `blogger_post_id` is NULL for all 68 published records
- No dedup enforcement at publish time beyond title matching in `publish.py`

**Source 5: publish.py dedup logic**
- Checks `existing_titles` set (API fetch) + `queue.is_duplicate_title()` (DB check)
- Both use case-insensitive matching — BUT the API fetch only gets 500 results max
- If blog has 167 posts, this is fine. But at scale, pagination could miss duplicates.

**Source 6: Slug generation**
- `slugify()` truncates to 80 chars — two different titles could produce identical slugs
- No UNIQUE constraint enforcement in `publish.py` before inserting

### Duplicate Risk Assessment

| Risk Level | Source | Likelihood | Impact |
|------------|--------|------------|--------|
| HIGH | 2 vintage files (near-duplicate topics) | Confirmed | Medium |
| HIGH | 2 literary files (near-duplicate topics) | Confirmed | Medium |
| MEDIUM | Combinatorial keyword generation | Possible | Low |
| MEDIUM | Title normalization edge cases | Possible | Low |
| LOW | Blogger API dedup (500 limit) | Unlikely | High |
| LOW | Null blogger_post_id in DB | Confirmed | Medium |

---

## 3. Content Quality Analysis

### Metrics (68 articles)

| Metric | Min | Max | Average | Median |
|--------|-----|-----|---------|--------|
| Word Count | 810 | 6,166 | 2,961 | ~2,950 |
| H2 Headings | 3 | 27 | 7.6 | 7 |
| FAQ (schema Questions) | 5 | 10 | 5.4 | 5 |
| FAQ (markdown Q:) | 0 | ~12 | 1.7 | 0 |
| Table Rows | 0 | 435 | 97.4 | ~90 |
| Internal Links | 0 | 5 | 4.9 | 5 |
| Articles with 0 internal links | — | — | 2 | — |

### Quality Score Distribution (SQLite quality_scores)

| Range | Count | Percentage |
|-------|-------|------------|
| 50-60 | 3 | 4.4% |
| 60-70 | 11 | 16.2% |
| 70-80 | 50 | 73.5% |
| 80-90 | 4 | 5.9% |
| 90+ | 0 | 0% |

**Average Overall Quality: 69.2/100**

### Problems Identified

1. **62/68 articles have double-brace JSON-LD** (`{{` instead of `{`) — invalid for Google
2. **54/68 articles contain banned phrases** ("the rise of", "timeless choices", etc.)
3. **14 articles have YAML parse errors** in frontmatter (colons in unquoted titles)
4. **2 duplicate topic groups** (vintage names, literary names)
5. **2 articles with 0 internal links**
6. **9 articles with 0 table rows**
7. **15 articles with < 6 H2 headings**
8. **1 example.md file** (non-production content in posts/)
9. **68/68 have FAQPage schema but avg only 5.4 Questions** — most articles need 8-12
10. **No article reaches quality score >= 95**

---

## 4. SEO Audit

### Issue Severity Matrix

| Area | Issue | Severity | Affected Articles |
|------|-------|----------|-------------------|
| **Schema** | Double-brace JSON-LD (invalid JSON) | 🔴 CRITICAL | 62/68 |
| **Title** | Banned AI phrases in 79% of articles | 🟡 MEDIUM | 54/68 |
| **Title** | Missing number prefix in 8/68 | 🟡 MEDIUM | 8/68 |
| **Meta** | YAML parse errors in frontmatter | 🟡 MEDIUM | 14/68 |
| **Headings** | < 6 H2 sections in 22% | 🟢 LOW | 15/68 |
| **Internal Links** | 0 internal links in 3% | 🟡 MEDIUM | 2/68 |
| **FAQ** | Schema has only 5 Qs (need 8-12) | 🟡 MEDIUM | ~50/68 |
| **Tables** | 0 table rows in 13% | 🟡 MEDIUM | 9/68 |
| **Canonical** | No canonical URL in HTML | 🟢 LOW | 68/68 |
| **Image ALT** | No images in most articles | 🟢 LOW | — |
| **Sitemap** | Blogger auto-generates (OK) | ✅ OK | — |
| **Robots** | Standard Blogger robots (OK) | ✅ OK | — |
| **RSS** | Blogger auto-generates (OK) | ✅ OK | — |

### Title Quality
- Only 6 canonical articles have rewritten number-prefix titles (200+, 250+, 300+)
- 54 articles still use old AI-generated titles with banned phrases
- Titles without number prefixes have lower CTR potential

### Meta Descriptions
- Generated by `generate_meta_description()` — formulaic and repetitive
- All follow pattern: "Discover {topic}, including meanings, origins, pronunciation guides, and naming ideas."

### Slug Quality
- Slugs derived from titles via `slugify()` — generally good
- No duplicate slugs confirmed
- Some slugs are overly long (>80 chars truncated)

---

## 5. Blogger Publishing

### Authentication Flow
- ✅ Uses `Credentials.from_authorized_user_info()` — no browser OAuth
- ✅ Reads from environment variables (CI secrets)
- ✅ Fails with clear error if credentials missing
- ✅ No `InstalledAppFlow` anywhere in codebase

### Duplicate Prevention
- ⚠️ `get_existing_posts()` fetches max 500 posts — OK for 167 posts
- ⚠️ `blogger_post_id` is NULL in all 68 published records — no linking
- ⚠️ No semantic similarity check before publish
- ⚠️ Title dedup is case-insensitive string match only

### Retry Logic
- ✅ `publish.py` has no explicit retry — fails on first HTTP error
- ✅ `generate_content.py` has 3 retries with exponential backoff (5s, 15s, 30s)
- ✅ Retryable codes: 429, 500, 503

### Failed Publish Recovery
- ❌ No mechanism to retry failed publishes
- ❌ Failed articles not tracked in a recoverable queue
- ⚠️ `failed` table exists in schema but has 0 records

---

## 6. Keyword Engine

### Combinatorial Analysis

| Dimension | Values | Examples |
|-----------|--------|----------|
| MEANINGS | 50 | love, hope, light, peace, joy, strength... |
| ORIGINS | 38 | Irish, Japanese, French, Arabic... |
| GENDERS | 5 | baby, boy, girl, unisex, gender-neutral |
| POPULARITY | 15 | popular, trending, classic, modern... |
| RELIGIONS | 15 | biblical, christian, muslim, hindu... |
| NATURE | 28 | flower, tree, ocean, mountain... |
| ANIMALS | 45 | bird, eagle, lion, dragon... |
| FLOWERS | 20 | rose, lily, daisy, violet... |
| COLORS | 28 | red, blue, gold, silver... |
| SEASONS | 5 | spring, summer, autumn, winter... |
| LETTERS | 26 | a-z |
| ENDINGS | 35 | a, ia, ea, o, er, ley... |
| YEARS | 10 | 2025-2034 |
| MYTHOLOGIES | 23 | greek, roman, norse... |
| OCCUPATIONS | 20 | king, queen, warrior... |

### Theoretical Combinations
- Single-dimension templates: ~15 dimensions × ~25 avg values = **375**
- Two-dimension templates: ~100 combos × 625 = **62,500**
- Three-dimension templates: ~50 combos × 15,625 = **781,250**
- **Total theoretical: 800,000+ unique keywords**

### Actual State
- **68 keywords in SQLite** (all status: `published`)
- **0 pending** — topic pool exhausted
- **0 clusters** — cluster building failed or wasn't run
- **No keyword discovery ran** since all 68 are published

### Exhaustion Timeline
- At 5 articles/day: 68 topics = **13.6 days**
- At 10 articles/day: 68 topics = **6.8 days**
- Keyword discovery generates on-demand, so exhaustion is preventable

---

## 7. Internal Link Audit

### Current State
- **SQLite internal_links table: 0 records**
- **Link graph not built** — `build_link_graph()` hasn't been run since posts changed
- **2 articles with 0 internal links**
- **68 articles in posts/** but no cross-linking

### Orphan Analysis
| Type | Count | Details |
|------|-------|---------|
| Outgoing-only (no incoming) | ~66 | Most articles have 5 links but none bidirectional |
| Incoming-only (no outgoing) | 2 | `vintage-baby-names-making-a-comeback-*` files |
| Truly orphaned | 0 | All have at least 5 links |

### Issues
1. Internal links are hardcoded (5 per article) rather than contextual
2. No link graph in SQLite — `internal_links` table is empty
3. No bidirectional linking (A→B but not B→A)
4. `link_graph_optimizer.py` exists but hasn't been run

---

## 8. Dead Code

### Unused/Problematic Files

| File | Status | Reason |
|------|--------|--------|
| `example.md` | ⚠️ In posts/ | Non-production content, 810 words |
| `optimization_candidates.json` | 🗑️ Orphan | Leftover from optimization run |
| `optimization_report.json` | 🗑️ Orphan | Leftover from optimization run |
| `docs/sync_summary.md` | 🗑️ Stale | Outdated sync report |
| `versions/` directory | 🗑️ Empty | Content evolution backups not used |

### Unused Functions

| Module | Function | Reason |
|--------|----------|--------|
| `seo_graph.py` | `suggest_internal_links()` | Not called by any module |
| `seo_graph.py` | `detect_content_gaps()` | Not called by any module |
| `seo_graph.py` | `cluster_status()` | Only called in `__main__` block |
| `reporter.py` | `save_report()` | Not called anywhere |
| `internal_linker.py` | `suggest_links_for()` | Not called by any module |
| `internal_linker.py` | `add_links_to_article()` | Not called by any module |

### Legacy JSON Files
- ✅ `generated_topics.json` — **NOT FOUND** (good, migrated to SQLite)
- ✅ `published_topics.json` — **NOT FOUND** (good, migrated to SQLite)
- ✅ `index_log.json` — **NOT FOUND** (good)
- ✅ `improvement_log.json` — **NOT FOUND** (good)

### Deprecated Logic
- `generate_content.py` still has `discover_and_insert_new_keywords()` which duplicates `keyword_discovery.discover_keywords()`
- `quality_engine.py` and `content_quality_engine.py` both score articles — overlapping functionality

---

## 9. Performance

### Slow Operations

| Operation | Complexity | Issue |
|-----------|------------|-------|
| `quality_scores` calculation | O(n²) | Compares every article against every other |
| `fingerprint_engine.find_similar_articles()` | O(n²) | Full pairwise comparison |
| `publish.py` duplicate check | O(n) | Fetches ALL 167 posts from API on every publish |
| `content_optimizer.optimize_all()` | O(n²) | Fingerprint comparison for all pairs |
| `repair_posts.py` | O(n) | Reads every file twice |

### Memory Waste
- No connection pooling — each module opens its own SQLite connection
- `TopicQueue.__init__()` opens connection but never closes it (except in main())
- `quality_engine.py` loads all posts into memory simultaneously

### Repeated Scans
- `build_blacklist()` in `generate_content.py` rescans all posts on every run
- `parse_frontmatter()` called multiple times per file (once in repair, once in publish, once in quality)

---

## 10. Security

### Secrets Handling

| Secret | Location | Risk |
|--------|----------|------|
| `AGNES_API_KEY` | GitHub Actions secrets | ✅ Safe |
| `BLOG_ID` | GitHub Actions secrets | ✅ Safe |
| `CLIENT_ID` | GitHub Actions secrets | ✅ Safe |
| `CLIENT_SECRET` | GitHub Actions secrets | ✅ Safe |
| `REFRESH_TOKEN` | GitHub Actions secrets | ✅ Safe |
| `credentials.json` | Local filesystem (`/Users/yuanfeng/Documents/手工diy/`) | ⚠️ Not in repo (good) |

### GitHub Actions Security
- ✅ No secrets printed in logs
- ✅ `continue-on-error: true` on autonomous/self-improving workflows (prevents pipeline breaks)
- ✅ `permissions: contents: write` only where needed
- ⚠️ `update-canonical.yml` has `permissions: contents: read` — correct (no write needed)

### Sensitive Data in Logs
- ⚠️ `update_canonical_posts.py` logs `client_id[:20]` — partial exposure
- ✅ No full tokens or keys logged

---

## 11. Project Structure Rating

| Module | Rating | Notes |
|--------|--------|-------|
| `database/schema.py` | ⭐⭐⭐⭐⭐ | Clean, well-structured, comprehensive |
| `database/topic_queue.py` | ⭐⭐⭐⭐☆ | Good state machine, but connection leak risk |
| `generate_content.py` | ⭐⭐⭐☆☆ | Solid but has dual dedup logic (JSON + DB) |
| `publish.py` | ⭐⭐⭐⭐☆ | Good dedup, but no retry on publish failure |
| `keyword_discovery.py` | ⭐⭐⭐⭐☆ | Excellent combinatorial engine |
| `sync_from_blogger.py` | ⭐⭐⭐⭐⭐ | Comprehensive, well-structured |
| `update_canonical_posts.py` | ⭐⭐⭐⭐⭐ | CI-only, clean, safe |
| `fingerprint_engine.py` | ⭐⭐⭐⭐☆ | Good structure, O(n²) comparison |
| `content_quality_engine.py` | ⭐⭐⭐⭐☆ | Comprehensive scoring |
| `quality_engine.py` | ⭐⭐☆☆☆ | Overlaps with content_quality_engine.py |
| `content_optimizer.py` | ⭐⭐⭐☆☆ | Works but slow pairwise comparison |
| `content_evolver.py` | ⭐⭐⭐☆☆ | Good concept, limited practical use |
| `repair_posts.py` | ⭐⭐⭐☆☆ | Basic but functional |
| `orchestrator.py` | ⭐⭐⭐⭐☆ | Good pipeline orchestration |
| `self_improving_loop.py` | ⭐⭐⭐☆☆ | Complex but mostly unused |
| `internal_linker.py` | ⭐⭐☆☆☆ | Functions defined but not called |
| `link_graph_optimizer.py` | ⭐⭐⭐☆☆ | Works but modifies files in-place |
| `seo_graph.py` | ⭐⭐⭐☆☆ | Good cluster definitions, unused functions |
| `reporter.py` | ⭐⭐⭐⭐☆ | Clean daily reports |
| `index_accelerator.py` | ⭐⭐⭐☆☆ | Blogger-specific (sitemap auto-gen) |
| `growth_detector.py` | ⭐⭐⭐⭐☆ | Good urgency scoring |
| `content_gap_detector.py` | ⭐⭐⭐☆☆ | Depends on serp_intent_analyzer |
| `serp_intent_analyzer.py` | ⭐⭐⭐⭐☆ | Comprehensive intent mapping |
| `real_traffic_engine.py` | ⭐⭐⭐☆☆ | Good orchestration wrapper |
| `topic_cluster.py` | ⭐⭐⭐⭐☆ | Good hierarchical builder |
| `utils/helpers.py` | ⭐⭐⭐⭐⭐ | Excellent shared utilities |
| `utils/yaml_parser.py` | ⭐⭐⭐⭐☆ | Clean parsing, good error handling |

---

## 12. Overall Scores (0-100)

| Category | Score | Justification |
|----------|-------|---------------|
| **Architecture** | 72 | Well-organized modular design, but overlapping quality engines, unused functions |
| **SEO** | 58 | Critical JSON-LD issues (62/68 invalid), banned phrases in 79%, missing canonical URLs |
| **Content Quality** | 65 | Avg quality 69.2/100, 9 articles with 0 tables, 15 with <6 H2s |
| **Performance** | 60 | O(n²) comparisons, no connection pooling, repeated file scans |
| **Maintainability** | 75 | Good separation of concerns, shared helpers, clear naming |
| **Scalability** | 65 | Keyword engine can generate 800K+ topics, but DB queries lack indexing at scale |
| **Automation** | 80 | 5 GitHub workflows, daily schedules, self-improving loop |
| **Revenue Readiness** | 55 | Invalid JSON-LD kills rich snippets, banned phrases hurt CTR, no internal link graph |

---

## 13. Priority Roadmap

### 🔴 Critical (Fix Immediately)
1. **Fix double-brace JSON-LD** in 62 articles — replace `{{` with `{`
2. **Remove banned phrases** from 54 articles — rewrite titles and body text
3. **Fix YAML parse errors** in 14 articles — quote colons in titles
4. **Link canonical Blogger post IDs** to published records in SQLite
5. **Delete example.md** from posts/

### 🟡 High Priority
6. **Build internal link graph** — populate SQLite `internal_links` table
7. **Deduplicate vintage/literary articles** — merge or remove near-duplicates
8. **Increase FAQ count** — most articles have only 5 schema questions (target: 8-12)
9. **Add canonical URLs** to all articles
10. **Implement publish retry logic** — handle transient API failures

### 🟢 Medium Priority
11. **Consolidate quality engines** — merge `quality_engine.py` into `content_quality_engine.py`
12. **Add database connection pooling** — reduce memory waste
13. **Run keyword discovery** — repopulate pending topics
14. **Fix `blogger_post_id` NULL** in all published records
15. **Add bidirectional internal linking**

### ⚪ Low Priority
16. **Remove unused functions** from `seo_graph.py`, `internal_linker.py`
17. **Add semantic similarity check** before publish
18. **Implement failed publish recovery queue**
19. **Clean up orphan JSON files**
20. **Add rate limiting awareness** to sync operations

---

## 14. File Inventory

### Core Modules (25 Python files)
- `generate_content.py` — Article generation
- `publish.py` — Blogger publishing
- `sync_from_blogger.py` — Download from Blogger
- `update_canonical_posts.py` — CI-only canonical updates
- `keyword_discovery.py` — Combinatorial keyword generation
- `topic_cluster.py` — Topic cluster builder
- `orchestrator.py` — Master pipeline
- `self_improving_loop.py` — Autonomous improvement loop
- `content_optimizer.py` — Article optimization
- `content_evolver.py` — Content evolution
- `content_quality_engine.py` — 10-dimensional quality scoring
- `quality_engine.py` — Pre-publish validation (legacy)
- `fingerprint_engine.py` — Structural deduplication
- `seo_graph.py` — Topic clusters and gap detection
- `seo_validator.py` — SEO scoring
- `internal_linker.py` — Internal linking
- `link_graph_optimizer.py` — Link graph reinforcement
- `reporter.py` — Daily reports
- `growth_detector.py` — Improvement candidate detection
- `content_gap_detector.py` — SERP competitive analysis
- `serp_intent_analyzer.py` — Search intent mapping
- `real_traffic_engine.py` — Traffic growth orchestrator
- `index_accelerator.py` — Sitemap and re-crawl
- `repair_posts.py` — Frontmatter repair

### Database
- `database/schema.py` — SQLite schema definition
- `database/topic_queue.py` — Topic lifecycle manager
- `database/topic_queue.db` — 377KB SQLite database

### Utilities
- `utils/helpers.py` — Shared utilities
- `utils/yaml_parser.py` — Frontmatter parsing

### Workflows
- `.github/workflows/autonomous.yml`
- `.github/workflows/generate.yml`
- `.github/workflows/publish.yml`
- `.github/workflows/self_improving.yml`
- `.github/workflows/update-canonical.yml`

### Content
- `posts/` — 68 markdown files (66 production + 1 example + 1 backup reference)
- `optimization_backups/` — 26 backup files

### Documentation
- `docs/ARCHITECTURE.md`
- `docs/AUDIT_REPORT.md`
- `docs/COMPLETE_AUDIT_REPORT.md`
- `docs/canonical_optimization_report.md`
- `docs/optimization_final_report.md`
- `docs/sync_summary.md`

---

*End of audit report. No files were modified.*
