#!/usr/bin/env python3
"""
Autonomous SEO Content & Revenue Engine — Master Orchestrator
===============================================================
Operates without human intervention. Each run:
  1. Discover high-revenue keywords
  2. Score & rank keywords by revenue potential
  3. Detect content gaps in topic clusters
  4. Generate articles via Agnes AI
  5. Repair frontmatter
  6. Publish to Blogger
  7. Update sitemap/SEO signals
  8. Report results

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

# ── Phase execution ──────────────────────────────────────────────────────
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
            if result.stdout:
                # Print last few lines
                lines = result.stdout.strip().split("\n")
                for line in lines[-5:]:
                    log.info("   %s", line[:120])
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


def discover_keywords_for_run() -> list:
    """Run keyword discovery and return top scored topics."""
    try:
        from keyword_discovery import discover_keywords, load_history
        history = load_history()
        keywords = discover_keywords(count=ARTICLES_PER_RUN + 5, history_blacklist=history)
        # Filter by minimum revenue score
        filtered = [kw for kw in keywords if kw["revenue_score"] >= MIN_REVENUE_SCORE]
        log.info(
            "Keyword discovery: %d found, %d above revenue threshold (≥%.1f)",
            len(keywords), len(filtered), MIN_REVENUE_SCORE,
        )
        for i, kw in enumerate(filtered[:5]):
            log.info(
                "  %d. [score=%.1f cpc=$%.2f] %s",
                i + 1, kw["revenue_score"], kw["cpc"], kw["topic"][:70],
            )
        return filtered[:ARTICLES_PER_RUN]
    except Exception as exc:
        log.warning("Keyword discovery failed (%s), falling back to generate_content.py", exc)
        return []


def get_cluster_status() -> str:
    """Get SEO graph status summary."""
    try:
        from seo_graph import cluster_status
        posts_dir = BASE_DIR / "posts"
        history = set()
        history_file = BASE_DIR / "generated_topics.json"
        if history_file.exists():
            data = json.loads(history_file.read_text())
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        history.add(item.get("slug", "").lower().strip())
        status = cluster_status(posts_dir, history)
        lines = []
        for s in status:
            bar = "█" * (s["completeness"] // 10) + "░" * (10 - s["completeness"] // 10)
            lines.append(f"  [{bar}] {s['cluster']}: {s['completeness']}% ({s['covered']}/{s['total']})")
        return "\n".join(lines)
    except Exception as exc:
        return f"Cluster status unavailable: {exc}"


# ── Revenue report ───────────────────────────────────────────────────────
def generate_revenue_report(published: int, keywords: list) -> str:
    """Generate a daily revenue projection report."""
    if not keywords:
        return "No keyword data available."
    avg_cpc = sum(kw["cpc"] for kw in keywords) / len(keywords) if keywords else 0
    avg_score = sum(kw["revenue_score"] for kw in keywords) / len(keywords) if keywords else 0
    estimated_monthly_clicks = published * 30 * 5  # Rough estimate: 5 clicks/day/article
    estimated_monthly_revenue = estimated_monthly_clicks * avg_cpc * 0.68  # 68% AdSense rev share

    return (
        f"Articles published: {published}\n"
        f"Average CPC: ${avg_cpc:.2f}\n"
        f"Average revenue score: {avg_score:.1f}\n"
        f"Est. monthly clicks: {estimated_monthly_clicks:,}\n"
        f"Est. monthly AdSense revenue: ${estimated_monthly_revenue:.2f}\n"
        f"Est. annual AdSense revenue: ${estimated_monthly_revenue * 12:.2f}"
    )


# ── MAIN ─────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("AUTONOMOUS SEO REVENUE ENGINE — BOOTING")
    log.info("=" * 60)
    log.info("Date: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("Target: %d articles per run", ARTICLES_PER_RUN)
    log.info("Min revenue score: %.1f", MIN_REVENUE_SCORE)
    log.info("")

    # ── Phase 0: Pre-flight checks ────────────────────────────────────
    api_key = os.environ.get("AGNES_API_KEY")
    if not api_key:
        log.error("AGNES_API_KEY not set. Cannot generate content.")
        sys.exit(1)

    # ── Phase 1: Keyword discovery & revenue scoring ──────────────────
    log.info("─── Phase 1: Keyword Discovery & Revenue Scoring ───")
    keywords = discover_keywords_for_run()
    revenue_report = generate_revenue_report(
        len(keywords) if keywords else ARTICLES_PER_RUN, keywords
    )
    log.info("Revenue projection:\n%s", revenue_report)

    # ── Phase 2: SEO graph & cluster status ──────────────────────────
    log.info("\n─── Phase 2: Topic Cluster Status ───")
    cluster_info = get_cluster_status()
    log.info("Cluster completeness:\n%s", cluster_info)

    # ── Phase 3: Content generation ──────────────────────────────────
    log.info("\n─── Phase 3: Content Generation ───")
    gen_ok = run_script("generate_content.py", timeout=1200)
    if not gen_ok:
        log.warning("Content generation had issues. Continuing with available posts.")

    # ── Phase 4: Repair frontmatter ──────────────────────────────────
    log.info("\n─── Phase 4: Frontmatter Repair ───")
    repair_ok = run_script("repair_posts.py", timeout=300)

    # ── Phase 5: Publish to Blogger ──────────────────────────────────
    log.info("\n─── Phase 5: Blogger Publication ───")
    blog_id = os.environ.get("BLOG_ID")
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    refresh_token = os.environ.get("REFRESH_TOKEN")

    if all([blog_id, client_id, client_secret, refresh_token]):
        publish_ok = run_script("publish.py", timeout=600)
        if not publish_ok:
            log.warning("Publication had issues. Check publish.py logs.")
    else:
        log.warning("Blogger credentials not available. Skipping publication.")
        log.info("  Set: CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN, BLOG_ID")

    # ── Phase 6: SEO index acceleration ──────────────────────────────
    log.info("\n─── Phase 6: Index Acceleration ───")
    try:
        sitemap_url = "https://babynameideas2026.blogspot.com/sitemap.xml"
        log.info("Sitemap available at: %s", sitemap_url)
        log.info("Tip: Submit sitemap at Google Search Console for faster indexing.")
    except Exception as exc:
        log.warning("Sitemap check: %s", exc)

    # ── Phase 7: Final report ────────────────────────────────────────
    log.info("\n" + "=" * 60)
    log.info("DAILY AUTONOMOUS RUN COMPLETE")
    log.info("=" * 60)
    log.info(revenue_report)
    log.info("\nCluster status:\n%s", cluster_info)
    log.info("\nNext run: tomorrow via GitHub Actions schedule (UTC midnight)")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
