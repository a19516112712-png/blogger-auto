#!/usr/bin/env python3
"""
Autonomous SEO Content & Revenue Engine — Master Orchestrator (Refactored)

Operates without human intervention. Each run:
  1. Build topic clusters
  2. Discover keywords → insert into SQLite
  3. Pick pending topics (ORDER BY RANDOM())
  4. Generate articles via Agnes AI
  5. Validate quality (≥95 score)
  6. Repair frontmatter
  7. Publish to Blogger
  8. Record in SQLite (URL, hash, labels)
  9. Schedule content evolution (90-day refresh)
  10. Build internal link graph
  11. Generate daily report

Designed for daily GitHub Actions execution.
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from database.topic_queue import TopicQueue
from database.schema import DB_PATH
from reporter import generate_report

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("orchestrator")

# ── Config ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
ARTICLES_PER_RUN = int(os.environ.get("ARTICLES_PER_RUN", "10"))
MIN_REVENUE_SCORE = float(os.environ.get("MIN_REVENUE_SCORE", "30.0"))


def run_script(script_name: str, timeout: int = 600) -> bool:
    """Run a Python script and return True if it succeeded."""
    path = BASE_DIR / script_name
    if not path.exists():
        log.warning("Script not found: %s", script_name)
        return False
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(BASE_DIR),
        )
        elapsed = time.time() - start
        if result.returncode == 0:
            log.info("✅ %s completed in %.1fs", script_name, elapsed)
            return True
        else:
            log.error("❌ %s FAILED (exit %d) after %.1fs", script_name, result.returncode, elapsed)
            if result.stderr:
                log.error("   stderr: %s", result.stderr.strip()[:300])
            return False
    except subprocess.TimeoutExpired:
        log.error("⏰ %s TIMED OUT after %ds", script_name, timeout)
        return False
    except Exception as exc:
        log.error("💥 %s crashed: %s", script_name, exc)
        return False


# ── MAIN ─────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("AUTONOMOUS SEO REVENUE ENGINE — BOOTING")
    log.info("=" * 60)
    log.info("Date: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("Target: %d articles per run", ARTICLES_PER_RUN)
    log.info("Database: %s", DB_PATH)
    log.info("")

    # ── Phase 0: Pre-flight ──
    api_key = os.environ.get("AGNES_API_KEY")
    if not api_key:
        log.error("AGNES_API_KEY not set. Cannot generate content.")
        sys.exit(1)

    # ── Phase 1: Initialize database + clusters ──
    log.info("─── Phase 1: Database & Clusters ───")
    queue = TopicQueue()

    # Build topic clusters if empty
    clusters = queue.get_all_clusters()
    if not clusters:
        log.info("Building topic clusters...")
        try:
            from topic_cluster import build_clusters
            stats = build_clusters(queue)
            log.info("Clusters built: %d clusters, %d keywords",
                     stats["clusters_created"], stats["keywords_added"])
        except Exception as exc:
            log.warning("Cluster build failed: %s", exc)

    # ── Phase 2: Keyword discovery ──
    log.info("─── Phase 2: Keyword Discovery ───")
    try:
        from keyword_discovery import discover_keywords
        keywords = discover_keywords(queue, count=ARTICLES_PER_RUN * 5)
        inserted = queue.bulk_insert_keywords(keywords)
        log.info("Discovered and inserted %d new keywords.", inserted)
    except Exception as exc:
        log.warning("Keyword discovery failed: %s", exc)

    # ── Phase 3: Content generation ──
    log.info("\n─── Phase 3: Content Generation ───")
    gen_ok = run_script("generate_content.py", timeout=1200)

    # ── Phase 4: Repair frontmatter ──
    log.info("\n─── Phase 4: Frontmatter Repair ───")
    repair_ok = run_script("repair_posts.py", timeout=300)

    # ── Phase 5: Publish to Blogger ──
    log.info("\n─── Phase 5: Blogger Publication ───")
    blog_id = os.environ.get("BLOG_ID")
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    refresh_token = os.environ.get("REFRESH_TOKEN")

    if all([blog_id, client_id, client_secret, refresh_token]):
        publish_ok = run_script("publish.py", timeout=600)
        if not publish_ok:
            log.warning("Publication had issues.")
    else:
        log.warning("Blogger credentials not available. Skipping publication.")

    # ── Phase 6: Schedule content evolution ──
    log.info("\n─── Phase 6: Content Evolution Scheduling ───")
    try:
        published_count = queue.stats().get("published", 0)
        # Schedule oldest unpublished articles for refresh after 90 days
        due = queue.get_refresh_due()
        log.info("Articles due for refresh: %d", len(due))
    except Exception as exc:
        log.warning("Refresh scheduling failed: %s", exc)

    # ── Phase 7: Internal link graph ──
    log.info("\n─── Phase 7: Internal Link Graph ───")
    try:
        from internal_linker import build_link_graph
        graph = build_link_graph(queue)
        log.info("Link graph: %d pages, %d links",
                 len(graph), sum(len(v) for v in graph.values()))
    except Exception as exc:
        log.warning("Link graph build failed: %s", exc)

    # ── Phase 8: Content evolution ──
    log.info("\n─── Phase 8: Content Evolution ───")
    try:
        from content_evolver import run_evolution_cycle
        results = run_evolution_cycle(queue, max_articles=3)
        log.info("Evolution: evolved=%d, failed=%d",
                 results.get("evolved", 0), results.get("failed", 0))
    except Exception as exc:
        log.warning("Evolution failed: %s", exc)

    # ── Phase 9: Daily report ──
    log.info("\n─── Phase 9: Daily Report ───")
    report = generate_report(queue)
    log.info(report)

    # Save report
    report_path = BASE_DIR / "daily_report.txt"
    report_path.write_text(report, encoding="utf-8")

    queue.close()

    log.info("\n" + "=" * 60)
    log.info("DAILY AUTONOMOUS RUN COMPLETE")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
