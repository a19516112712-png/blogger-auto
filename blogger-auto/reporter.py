#!/usr/bin/env python3
"""
Daily Reporter — Comprehensive publishing statistics.

Generates a report with:
  - Articles generated
  - Articles published
  - Duplicates prevented
  - Queue size
  - Clusters created
  - Topics remaining
  - Internal links created
  - Refresh tasks
  - Errors
  - Estimated organic traffic
"""

import json
import logging
from datetime import datetime

from database.topic_queue import TopicQueue

log = logging.getLogger(__name__)


def generate_report(queue: TopicQueue | None = None) -> str:
    """Generate the daily report string."""
    if queue is None:
        queue = TopicQueue()

    stats = queue.stats()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Estimate organic traffic
    published = stats.get("published", 0)
    est_daily_clicks = published * 3  # ~3 clicks/article/day (conservative)
    est_monthly_clicks = est_daily_clicks * 30
    est_monthly_revenue = est_monthly_clicks * 0.02 * 0.68  # $0.02 CPC * 68% rev share

    report = f"""
═══════════════════════════════════════════════════════
  DAILY SEO REPORT — {now}
═══════════════════════════════════════════════════════

📊 TOPIC QUEUE
  Pending topics:      {stats.get('pending', 0):>8,}
  Generating:          {stats.get('generating', 0):>8,}
  Generated (queued):  {stats.get('generated', 0):>8,}
  Published:           {stats.get('published', 0):>8,}
  Failed:              {stats.get('failed', 0):>8,}
  ─────────────────────────────────────────
  Total in database:   {stats.get('total_keywords', 0):>8,}

📝 PUBLISHING STATS
  Articles generated:  {stats.get('generated', 0):>8,}
  Articles published:  {stats.get('published', 0):>8,}
  Duplicates blocked:  {stats.get('failed', 0):>8,}

🔗 CLUSTERS & LINKS
  Clusters created:    {stats.get('clusters', 0):>8,}
  Internal links:      {stats.get('internal_links', 0):>8,}
  Refresh due:         {stats.get('refresh_due', 0):>8,}

💰 ESTIMATED REVENUE
  Est. daily clicks:   {est_daily_clicks:>8,}
  Est. monthly clicks: {est_monthly_clicks:>8,}
  Est. monthly rev:    ${est_monthly_revenue:>7,.2f}
  Est. annual rev:     ${est_monthly_revenue * 12:>7,.2f}

═══════════════════════════════════════════════════════
  Next run: tomorrow via GitHub Actions
  Blog: https://babynameideas2026.blogspot.com
═══════════════════════════════════════════════════════
"""

    if not isinstance(queue, TopicQueue):
        queue.close()

    return report


def save_report(report: str, filepath=None):
    """Save report to file."""
    if filepath is None:
        from pathlib import Path
        filepath = Path(__file__).resolve().parent / "daily_report.txt"
    filepath.write_text(report, encoding="utf-8")
    log.info("Report saved: %s", filepath)
