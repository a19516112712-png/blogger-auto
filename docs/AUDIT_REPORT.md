# Audit Report — Blogger-Auto SEO System

> **Date:** 2026-07-02
> **Scope:** Full repository audit — read-only
> **Action:** Document findings, then remove confirmed dead code

---

## 1. Duplicate Functions (7 pairs)

| Function | File 1 | File 2 |
|----------|--------|--------|
| `slugify()` | `generate_content.py` | `publish.py` |
| `sanitize_labels()` | `publish.py` | `repair_posts.py` |
| `sanitize_title()` | `generate_content.py` | `publish.py` |
| `build_frontmatter()` | `generate_content.py` | `repair_posts.py` |
| `load_history()` | `generate_content.py` | `keyword_discovery.py` |
| `extract_title()` | `generate_content.py` | `repair_posts.py` |

## 2. Dead Code (Confirmed Unused)

| File / Symbol | Reason |
|---------------|--------|
| `gen_all.py` | Standalone hardcoded generator, never called |
| `gen_more.py` | Standalone hardcoded generator, never called |
| `publish_env.py` | Duplicate publisher at root level |
| `root/.github/workflows/publish.yml` | Parallel to blogger-auto version |
| `root/posts/` (10 files) | Separate from blogger-auto/posts/ |
| `root/articles/` (5 HTML) | Orphaned exports |
| `root/new_articles/` (5 HTML) | Orphaned exports |
| `root/articles_batch*.json` (5) | Leftover from gen_all.py |
| `root/articles_data.json` | Leftover |
| `root/articles_day*.json` (2) | Leftover |
| `root/generated_topics.json` | Separate copy from blogger-auto |
| `root/token.json` | OAuth token, security risk |
| `seo_graph.py::suggest_internal_links()` | Never called |
| `seo_graph.py::detect_content_gaps()` | Only in __main__ |
| `link_graph_optimizer.py::optimize_links()` | Only in __main__ |
| `content_gap_detector.py::generate_improvement_plan()` | Never called |
| `growth_detector.py::merge_search_console_data()` | Never called |
| `index_accelerator.py::generate_re_crawl_list()` | Never called |
| `index_accelerator.py::accelerate()` | Never called |
| `generate_content.py::RELATED_ARTICLES_POOL` | Never referenced |

## 3. Duplicate Systems

| System | Instance 1 | Instance 2 |
|--------|-----------|-----------|
| Publisher | `blogger-auto/publish.py` | `publish_env.py` |
| Workflow | `blogger-auto/.github/workflows/publish.yml` | `root/.github/workflows/publish.yml` |
| Posts dir | `blogger-auto/posts/` (68 files) | `root/posts/` (10 files) |
| Topic blacklist | `blogger-auto/generated_topics.json` (empty) | `root/generated_topics.json` (5 keys) |

## 4. SEO Gaps

- JSON-LD schema: 0% coverage (0/68 articles)
- Canonical URLs: 0%
- Author/EEAT blocks: 0%
- Average word count: 2,322 (target: 2,500+)
- 65/68 articles contain repetitive AI phrases

## 5. Action Plan

1. Remove dead code
2. Create `utils/helpers.py` — shared utilities
3. Create `database/topic_queue.db` — SQLite
4. Replace keyword_discovery.py — unlimited combinatorial engine
5. Refactor generate_content.py — SQLite + JSON-LD
6. Build topic_cluster.py, content_evolver.py, quality_engine.py
7. Build internal_linker.py, seo_validator.py, reporter.py
8. Update publish.py — store in SQLite
9. Update orchestrator.py — wire all modules
