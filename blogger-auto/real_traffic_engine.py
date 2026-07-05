#!/usr/bin/env python3
"""
Real Traffic Engine — SEO Growth Orchestrator
===============================================
Grows real Google organic traffic by:
  STEP 1: Discover keywords from real search demand (SERP intent map)
  STEP 2: Analyze SERP intent (top 10 structure benchmarks)
  STEP 3: Identify content gaps (completeness vs. intent requirements)
  STEP 4: Create or improve content (intent-matched, not template)
  STEP 5: Optimize for readability + intent match
  STEP 6: Add internal links naturally (not manipulative)
  STEP 7: Ensure indexing readiness

This is NOT a content generator. This is a traffic growth engine.
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("traffic_engine")

BASE_DIR = Path(__file__).resolve().parent
BLOG_URL = "https://babynameideas2026.blogspot.com"

# ── Step runner ────────────────────────────────────────────────────────
def run_step(script: str, timeout: int = 600) -> bool:
    path = BASE_DIR / script
    if not path.exists():
        log.warning("Script not found: %s", script)
        return False
    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(BASE_DIR),
        )
        if result.returncode == 0:
            log.info("✅ %s completed", script)
            if result.stdout.strip():
                for line in result.stdout.strip().split("\n")[-3:]:
                    log.info("   %s", line[:120])
            return True
        log.error("❌ %s failed (exit %d)", script, result.returncode)
        return False
    except Exception as exc:
        log.error("❌ %s crashed: %s", script, exc)
        return False


# ── MAIN ────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("REAL TRAFFIC ENGINE — BOOTING")
    log.info("=" * 60)
    log.info("Date: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("Blog: %s", BLOG_URL)

    # ── STEP 1: Discover keywords from real search demand ──────────────
    log.info("\n─── STEP 1: Search Intent Discovery ───")
    try:
        from serp_intent_analyzer import INTENT_MAP, scan_all_intents, get_intent_gaps
        intents = scan_all_intents()
        gaps = get_intent_gaps()
        log.info("Intent types mapped: %d", len(INTENT_MAP))
        log.info("High-volume uncovered queries: %d",
                 len(gaps.get("high_volume_query_gaps", [])))
        for g in gaps.get("high_volume_query_gaps", [])[:5]:
            log.info("  GAP: \"%s\" (%s vol, %.2f CTR)",
                     g["query"], g["volume"], g["ctr_potential"])
    except Exception as exc:
        log.warning("Intent discovery failed: %s", exc)

    # ── STEP 2+3: Analyze SERP intent + Identify content gaps ─────────
    log.info("\n─── STEP 2+3: Content Gap Analysis ───")
    try:
        from content_gap_detector import run_full_gap_analysis, generate_improvement_plan
        gap_analysis = run_full_gap_analysis()
        plan = generate_improvement_plan(gap_analysis)
        log.info("Posts needing improvement: %d",
                 gap_analysis["posts_needing_improvement"])
        log.info("New content opportunities: %d",
                 len(gap_analysis.get("create_new", [])))
        log.info("Total actions in plan: %d", len(plan))
        for i, p in enumerate(plan[:5]):
            log.info("  %d. [%s] %s (%.2f)",
                     i + 1, p["action"], p["target"][:55], p["priority"])
    except Exception as exc:
        log.warning("Gap analysis failed: %s", exc)

    # ── STEP 4: Create or improve content ─────────────────────────────
    log.info("\n─── STEP 4: Content Creation & Improvement ───")
    api_key = os.environ.get("AGNES_API_KEY")
    if api_key and api_key != "placeholder":
        run_step("generate_content.py", timeout=1200)
    else:
        log.warning("AGNES_API_KEY not available. Skipping AI generation.")

    # ── STEP 5: Optimize readability + intent match ───────────────────
    log.info("\n─── STEP 5: Intent Match Optimization ───")
    run_step("repair_posts.py", timeout=300)

    # ── STEP 6: Add internal links naturally ──────────────────────────
    log.info("\n─── STEP 6: Natural Internal Linking ───")
    run_step("link_graph_optimizer.py", timeout=300)

    # ── STEP 7: Ensure indexing readiness ─────────────────────────────
    log.info("\n─── STEP 7: Indexing Readiness ───")
    run_step("index_accelerator.py", timeout=300)

    # ── SELF-IMPROVING: Evolve existing pages ─────────────────────────
    log.info("\n─── SELF-IMPROVING: Content Evolution ───")
    if api_key and api_key != "placeholder":
        run_step("content_evolver.py", timeout=1200)

    # ── FINAL REPORT ──────────────────────────────────────────────────
    log.info("\n" + "=" * 60)
    log.info("TRAFFIC ENGINE RUN COMPLETE")
    log.info("=" * 60)
    log.info("Next run: tomorrow (GitHub Actions)")
    log.info("Monitor: Google Search Console for impression/CTR changes")
    log.info("Sitemap: %s/sitemap.xml", BLOG_URL)


if __name__ == "__main__":
    main()
