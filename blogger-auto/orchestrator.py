#!/usr/bin/env python3
"""
Autonomous SEO Content Engine — Generation Pipeline

Decoupled architecture:
  orchestrator.py  -> manages keywords, triggers generation, repairs, reports
  generate_content.py -> generates articles, saves markdown to posts/
  publish.py           -> reads posts/, publishes to Blogger (separate workflow)

Daily execution pipeline:
  1. Keyword discovery -> insert into SQLite (if pool < threshold)
  2. Generate articles via Agnes AI (saves markdown only)
  3. Repair frontmatter
  4. Build internal link graph
  5. Generate daily report

Publishing is handled by the dedicated publish.yml GitHub Actions workflow.
This orchestrator does NOT call publish.py.

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

# --- Logging ----------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("orchestrator")

# --- Config -----------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
ARTICLES_PER_RUN = int(os.environ.get("ARTICLES_PER_RUN", "3"))
MIN_KEYWORD_POOL = 100  # Minimum pending keywords before generating new ones


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
            log.info("OK %s completed in %.1fs", script_name, elapsed)
            return True
        else:
            log.error("FAIL %s FAILED (exit %d) after %.1fs", script_name, result.returncode, elapsed)
            if result.stderr:
                log.error("   stderr: %s", result.stderr.strip()[:300])
            return False
    except subprocess.TimeoutExpired:
        log.error("TIMEOUT %s TIMED OUT after %ds", script_name, timeout)
        return False
    except Exception as exc:
        log.error("CRASH %s crashed: %s", script_name, exc)
        return False


# --- MAIN -------------------------------------------------------------
def main():
    log.info("=" * 60)
    log.info("AUTONOMOUS SEO CONTENT ENGINE -- Generation Pipeline")
    log.info("=" * 60)
    log.info("Date: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("Target: %d articles per run", ARTICLES_PER_RUN)
    log.info("Database: %s", DB_PATH)
    log.info("Publishing: handled by separate publish.py workflow")
    log.info("")

    # -- Phase 0: Pre-flight --
    api_key = os.environ.get("AGNES_API_KEY")
    if not api_key:
        log.error("AGNES_API_KEY not set. Cannot generate content.")
        sys.exit(1)

    # -- Phase 1: Initialize database + clusters --
    log.info("--- Phase 1: Database & Clusters ---")
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

    # -- Phase 2: Keyword discovery (only if pool is low) --
    log.info("--- Phase 2: Keyword Pool Management ---")
    stats = queue.stats()
    pending_count = stats.get("pending", 0)
    log.info("Pending keywords: %d (threshold: %d)", pending_count, MIN_KEYWORD_POOL)

    if pending_count < MIN_KEYWORD_POOL:
        try:
            from keyword_discovery import discover_keywords
            extra_needed = min(ARTICLES_PER_RUN * 10, MIN_KEYWORD_POOL - pending_count + 500)
            keywords = discover_keywords(queue, count=extra_needed)
            inserted = queue.bulk_insert_keywords(keywords)
            log.info("Discovered and inserted %d new keywords.", inserted)
        except Exception as exc:
            log.warning("Keyword discovery failed: %s", exc)
    else:
        log.info("Keyword pool sufficient. Skipping discovery.")

    # -- Phase 3: Content generation (saves markdown only) --
    log.info("\n--- Phase 3: Content Generation ---")
    gen_ok = run_script("generate_content.py", timeout=1800)
    if not gen_ok:
        log.warning("Content generation had issues. Skipping downstream phases.")
        queue.close()
        sys.exit(1)

    # -- Phase 4: Repair frontmatter --
    log.info("\n--- Phase 4: Frontmatter Repair ---")
    repair_ok = run_script("repair_posts.py", timeout=300)
    if not repair_ok:
        log.warning("Frontmatter repair had issues.")

    # -- Phase 5: Internal link graph --
    log.info("\n--- Phase 5: Internal Link Graph ---")
    try:
        from internal_linker import build_link_graph
        graph = build_link_graph(queue)
        log.info("Link graph: %d pages, %d links",
                 len(graph), sum(len(v) for v in graph.values()))
    except Exception as exc:
        log.warning("Link graph build failed: %s", exc)

    # -- Phase 6: Daily report --
    log.info("\n--- Phase 6: Daily Report ---")
    report = generate_report(queue)
    log.info(report)

    # Save report
    report_path = BASE_DIR / "daily_report.txt"
    report_path.write_text(report, encoding="utf-8")

    queue.close()

    log.info("\n" + "=" * 60)
    log.info("DAILY AUTONOMOUS RUN COMPLETE")
    log.info("Next step: run publish.yml to publish generated articles to Blogger")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
