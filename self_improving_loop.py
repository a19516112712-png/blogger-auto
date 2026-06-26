#!/usr/bin/env python3
"""
Self-Improving SEO Growth Loop — Autonomous Empire Engine
===========================================================
Runs continuously to detect, improve, and amplify content.

Loop phases:
  1. GROWTH DETECTION — scan all posts, identify improvement candidates
  2. OPPORTUNITY MINING — classify into HIGH GROWTH / POTENTIAL GROWTH
  3. CONTENT EVOLUTION — expand top candidates via AI
  4. LINK GRAPH OPTIMIZATION — strengthen internal links
  5. INDEX ACCELERATION — update sitemaps, re-crawl signals
  6. REPORT — log improvements, track velocity, update graphs
  7. LOOP — schedule next run, feed improved pages back

Designed for daily GitHub Actions execution.
Can also run locally: python self_improving_loop.py
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
log = logging.getLogger("self_improving")

BASE_DIR = Path(__file__).resolve().parent
MAX_IMPROVEMENTS_PER_RUN = int(os.environ.get("MAX_IMPROVEMENTS", "5"))
BLOG_URL = "https://babynameideas2026.blogspot.com"


def run_module(module_name: str, timeout: int = 600) -> tuple[bool, str]:
    """Run a module script. Returns (success, output_summary)."""
    script_path = BASE_DIR / module_name
    if not script_path.exists():
        return False, f"Script not found: {module_name}"

    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(BASE_DIR),
        )
        elapsed = time.time() - start
        if result.returncode == 0:
            output = result.stdout.strip()
            summary = output[-500:] if len(output) > 500 else output
            log.info("✅ %s — %.1fs", module_name, elapsed)
            return True, summary
        else:
            log.error("❌ %s FAILED (exit %d) — %.1fs", module_name, result.returncode, elapsed)
            return False, result.stderr[:500] if result.stderr else ""
    except subprocess.TimeoutExpired:
        log.error("⏰ %s TIMED OUT after %ds", module_name, timeout)
        return False, "Timeout"
    except Exception as exc:
        log.error("💥 %s crashed: %s", module_name, exc)
        return False, str(exc)


def phase_growth_detection() -> dict:
    """Phase 1+2: Detect growth and mine opportunities."""
    log.info("─── GROWTH DETECTION + OPPORTUNITY MINING ───")

    try:
        from growth_detector import scan_all_posts, classify_candidates
        candidates = scan_all_posts(BASE_DIR / "posts")
        buckets = classify_candidates(candidates)

        log.info(
            "Scanned %d posts. HIGH GROWTH: %d, POTENTIAL: %d",
            buckets["total"],
            len(buckets["high_growth"]),
            len(buckets["potential_growth"]),
        )
        for i, c in enumerate(buckets["high_growth"][:5]):
            log.info(
                "  %d. [score=%d] %s (%dw) → %d actions",
                i + 1, c.urgency_score, c.title[:55], c.word_count, len(c.actions),
            )

        return {
            "total": buckets["total"],
            "high_growth": len(buckets["high_growth"]),
            "potential_growth": len(buckets["potential_growth"]),
            "top_candidates": [
                {"title": c.title, "score": c.urgency_score, "wc": c.word_count,
                 "actions": [a["action"] for a in c.actions]}
                for c in buckets["high_growth"][:MAX_IMPROVEMENTS_PER_RUN]
            ],
        }
    except Exception as exc:
        log.warning("Growth detection failed: %s", exc)
        return {"error": str(exc)}


def phase_content_evolution() -> dict:
    """Phase 3: Expand and improve top candidates."""
    log.info("─── CONTENT EVOLUTION ───")

    api_key = os.environ.get("AGNES_API_KEY")
    if not api_key:
        log.warning("AGNES_API_KEY not set. Skipping AI-powered evolution.")
        return {"skipped": "No AGNES_API_KEY"}

    if api_key == "placeholder":
        log.warning("AGNES_API_KEY is placeholder. Skipping evolution.")
        return {"skipped": "Placeholder key"}

    ok, output = run_module("content_evolver.py", timeout=1200)
    if ok:
        # Parse results
        improved = output.count("✅") if "✅" in output else output.count("EVOLVED:")
        return {"ran": True, "output_preview": output[:300]}
    return {"ran": False, "error": output[:200]}


def phase_link_optimization() -> dict:
    """Phase 4: Strengthen internal link graph."""
    log.info("─── LINK GRAPH OPTIMIZATION ───")
    ok, output = run_module("link_graph_optimizer.py", timeout=300)
    if ok:
        optimized = output.count("OPTIMIZED:")
        return {"ran": True, "pages_optimized": optimized}
    return {"ran": False, "error": output[:200]}


def phase_index_acceleration() -> dict:
    """Phase 5: Accelerate indexing."""
    log.info("─── INDEX ACCELERATION ───")
    ok, output = run_module("index_accelerator.py", timeout=300)
    if ok:
        return {"ran": True}
    return {"ran": False, "error": output[:200]}


def generate_report(phases: dict) -> str:
    """Generate a comprehensive growth report."""
    lines = []
    lines.append("=" * 60)
    lines.append("SELF-IMPROVING SEO GROWTH REPORT")
    lines.append("=" * 60)
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Blog: {BLOG_URL}")
    lines.append("")

    for phase_name, data in phases.items():
        status = "✅" if data.get("ran") or data.get("total") else "⚠️"
        lines.append(f"{status} {phase_name}")
        for k, v in data.items():
            if k not in ("top_candidates",):
                lines.append(f"   {k}: {v}")
        if "top_candidates" in data:
            for i, c in enumerate(data["top_candidates"][:3]):
                lines.append(f"   #{i+1}: [{c['score']}] {c['title'][:50]} ({c['wc']}w)")
        lines.append("")

    lines.append("=" * 60)
    lines.append("NEXT RUN: Tomorrow (GitHub Actions schedule)")
    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    log.info("=" * 60)
    log.info("SELF-IMPROVING SEO GROWTH LOOP — BOOTING")
    log.info("=" * 60)
    log.info("Max improvements per run: %d", MAX_IMPROVEMENTS_PER_RUN)

    phases = {}

    # Phase 1+2: Detect + Mine
    phases["growth_detection"] = phase_growth_detection()

    # Phase 3: Evolve
    phases["content_evolution"] = phase_content_evolution()

    # Phase 4: Link graph
    phases["link_optimization"] = phase_link_optimization()

    # Phase 5: Index acceleration
    phases["index_acceleration"] = phase_index_acceleration()

    # Phase 6: Report
    report = generate_report(phases)
    log.info("\n" + report)

    # Save report
    report_path = BASE_DIR / "growth_report.txt"
    report_path.write_text(report)
    log.info("Report saved: %s", report_path)

    return phases


if __name__ == "__main__":
    main()
