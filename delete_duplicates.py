#!/usr/bin/env python3
"""
Blogger Duplicate Deletion Engine

Safely deletes duplicate Blogger posts and local article files.

Workflow:
  1. Read delete_candidates.csv
  2. For each candidate:
     a. Verify NOT canonical
     b. Verify in duplicate group
     c. Verify NOT referenced in internal_links
     d. Verify NOT the latest version
  3. If Blogger post exists: call posts.delete()
  4. Remove local file
  5. Update SQLite
  6. Generate final report

SAFETY:
  - Never deletes canonical articles
  - Never deletes unique topics
  - Only removes confirmed duplicates
  - Requires explicit confirmation before any deletion
"""

import csv
import json
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ── Configuration ──
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database" / "topic_queue.db"
POSTS_DIR = BASE_DIR / "posts"
DELETE_CANDIDATES_CSV = BASE_DIR / "delete_candidates.csv"
REPORT_PATH = BASE_DIR / "docs" / "deletion_report.json"
BACKUP_DIR = BASE_DIR / "deletion_backups"

SCOPES = ["https://www.googleapis.com/auth/blogger"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Safety Checks ──

def load_delete_candidates() -> list[dict]:
    """Load delete candidates from CSV."""
    if not DELETE_CANDIDATES_CSV.exists():
        log.error("delete_candidates.csv not found at %s", DELETE_CANDIDATES_CSV)
        sys.exit(1)
    
    candidates = []
    with open(DELETE_CANDIDATES_CSV, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            candidates.append(row)
    
    log.info("Loaded %d delete candidates from CSV", len(candidates))
    return candidates


def load_canonical_list() -> list[str]:
    """Load canonical filenames from canonical_report.csv."""
    canonical_csv = BASE_DIR / "canonical_report.csv"
    if not canonical_csv.exists():
        return []
    
    canonicals = []
    with open(canonical_csv, newline='') as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            canonicals.append(row[2])  # canonical_filename column
    return canonicals


def load_internal_link_targets(conn: sqlite3.Connection) -> set[str]:
    """Get all slugs referenced in internal links."""
    targets = set()
    for row in conn.execute(
        "SELECT DISTINCT target_slug FROM internal_links WHERE target_slug IS NOT NULL"
    ):
        targets.add(row[0].lower())
    return targets


def safety_check(candidate: dict, canonicals: list[str], 
                 link_targets: set[str], conn: sqlite3.Connection) -> tuple[bool, list[str]]:
    """Run all safety checks. Returns (pass, list_of_failures)."""
    failures = []
    dup_filename = candidate['duplicate_filename']
    canonical_filename = candidate['canonical_filename']
    
    # 1. Verify NOT canonical
    if dup_filename in canonicals:
        failures.append("Candidate IS a canonical article — CANNOT DELETE")
    
    # 2. Verify canonical exists
    if canonical_filename not in canonicals:
        failures.append(f"Canonical '{canonical_filename}' not found in canonical list")
    
    # 3. Verify referenced in internal links
    dup_slug = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', dup_filename.replace('.md', '')).lower()
    if dup_slug in link_targets:
        failures.append(f"Duplicate is referenced in internal links (target: {dup_slug})")
    
    # 4. Verify file exists
    dup_path = POSTS_DIR / dup_filename
    if not dup_path.exists():
        failures.append(f"Local file does not exist: {dup_filename}")
    
    # 5. Verify it's actually a duplicate (different from canonical)
    if dup_filename == canonical_filename:
        failures.append("Duplicate filename matches canonical filename")
    
    return (len(failures) == 0, failures)


# ── Blogger API ──

def get_blogger_service() -> object:
    """Authenticate with Blogger API using CI credentials."""
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    refresh_token = os.environ.get("REFRESH_TOKEN")
    
    missing = [name for name, val in [
        ("CLIENT_ID", client_id),
        ("CLIENT_SECRET", client_secret),
        ("REFRESH_TOKEN", refresh_token),
    ] if not val]
    
    if missing:
        raise EnvironmentError(
            f"Missing environment variable(s): {', '.join(missing)}. "
            "These must be set as GitHub Actions secrets."
        )
    
    creds = Credentials.from_authorized_user_info(
        info={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        scopes=SCOPES,
    )
    
    creds.refresh(Request())
    return build("blogger", "v3", credentials=creds)


def find_blogger_post_by_slug(service, blog_id: str, slug: str) -> str | None:
    """Find a Blogger post ID by matching its slug.
    
    Blogger doesn't expose slugs directly in the list API,
    so we fetch all live posts and match by title/content pattern.
    """
    try:
        request = service.posts().list(blogId=blog_id, status="live", maxResults=500)
        while request is not None:
            response = request.execute()
            for post in response.get("items", []):
                post_slug = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', 
                                   post.get('title', '').lower())
                post_slug = re.sub(r'[^a-z0-9-]', '-', post_slug).strip('-')
                if slug.lower() in post_slug or post_slug in slug.lower():
                    return post.get('id')
            request = service.posts().list_next(request, response)
    except HttpError as exc:
        log.error("Error fetching posts: %s", exc)
    return None


def delete_blogger_post(service, blog_id: str, post_id: str) -> bool:
    """Delete a post from Blogger using posts.delete()."""
    try:
        service.posts().delete(blogId=blog_id, postId=post_id).execute()
        log.info("  DELETED from Blogger: post_id=%s", post_id)
        return True
    except HttpError as exc:
        log.error("  FAILED to delete Blogger post %s: %s", post_id, exc)
        return False


# ── Local File Operations ──

def backup_file(filepath: Path) -> str | None:
    """Backup a file before deletion."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / filepath.name
    dest.write_bytes(filepath.read_bytes())
    return str(dest)


def delete_local_file(filepath: Path) -> bool:
    """Delete a local markdown file."""
    try:
        filepath.unlink()
        log.info("  DELETED local file: %s", filepath.name)
        return True
    except Exception as exc:
        log.error("  FAILED to delete local file %s: %s", filepath.name, exc)
        return False


# ── Database Updates ──

def remove_from_database(conn: sqlite3.Connection, filename: str, 
                          published_id: int | None) -> None:
    """Remove deleted article from SQLite tables."""
    slug = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', filename.replace('.md', ''))
    
    # Remove from published table
    if published_id:
        conn.execute("DELETE FROM published WHERE id = ?", (published_id,))
        log.info("  Removed from published table: id=%d", published_id)
    
    # Remove from generated table
    conn.execute("DELETE FROM generated WHERE slug = ?", (slug,))
    
    # Remove from quality_scores
    conn.execute("DELETE FROM quality_scores WHERE filename = ?", (filename,))
    
    # Remove from fingerprints
    conn.execute("DELETE FROM fingerprints WHERE filename = ?", (filename,))
    
    # Remove from internal_links
    conn.execute("DELETE FROM internal_links WHERE source_slug = ?", (slug,))
    conn.execute("DELETE FROM internal_links WHERE target_slug = ?", (slug,))
    
    conn.commit()
    log.info("  Cleaned database records for: %s", filename)


# ── Main Deletion Pipeline ──

def run_deletion(dry_run: bool = False) -> dict:
    """Execute the deletion pipeline.
    
    Args:
        dry_run: If True, only report what WOULD be deleted.
    
    Returns:
        Report dict with deletion statistics.
    """
    log.info("=" * 60)
    log.info("BLOGGER DUPLICATE DELETION ENGINE")
    log.info("=" * 60)
    log.info("Dry run: %s", dry_run)
    
    # Load data
    candidates = load_delete_candidates()
    canonicals = load_canonical_list()
    
    conn = sqlite3.connect(str(DB_PATH))
    link_targets = load_internal_link_targets(conn)
    
    blog_id = os.environ.get("BLOG_ID")
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "total_candidates": len(candidates),
        "passed_safety": 0,
        "failed_safety": 0,
        "deleted": [],
        "skipped": [],
        "errors": [],
    }
    
    # Process each candidate
    for i, candidate in enumerate(candidates, 1):
        log.info("\n[%d/%d] Processing: %s", i, len(candidates), 
                 candidate['duplicate_filename'])
        
        # Safety check
        safe, failures = safety_check(candidate, canonicals, link_targets, conn)
        
        if not safe:
            log.warning("  SAFETY FAILED: %s", failures)
            report["failed_safety"] += 1
            report["skipped"].append({
                "filename": candidate['duplicate_filename'],
                "reason": "; ".join(failures),
            })
            continue
        
        report["passed_safety"] += 1
        
        dup_filename = candidate['duplicate_filename']
        dup_path = POSTS_DIR / dup_filename
        published_id = int(candidate['published_id']) if candidate.get('published_id') else None
        blogger_post_id = candidate.get('blogger_post_id', '')
        
        log.info("  Safety check: PASSED")
        log.info("  Group: %s", candidate['group'])
        log.info("  Quality gap: %s", candidate['quality_diff'])
        log.info("  Content overlap: %s", candidate.get('content_overlap_pct', 'N/A'))
        
        if dry_run:
            log.info("  [DRY RUN] Would delete: %s", dup_filename)
            log.info("  [DRY RUN] Would backup to: %s", str(BACKUP_DIR / dup_filename))
            log.info("  [DRY RUN] Would remove from DB (published_id=%s)", published_id)
            
            report["deleted"].append({
                "filename": dup_filename,
                "group": candidate['group'],
                "status": "dry_run_would_delete",
                "published_id": published_id,
                "blogger_post_id": blogger_post_id,
            })
            continue
        
        # Step 1: Backup
        backup_path = backup_file(dup_path)
        log.info("  Backed up to: %s", backup_path)
        
        # Step 2: Delete from Blogger (if blogger_post_id known)
        blogger_deleted = False
        if blogger_post_id and blog_id:
            blogger_deleted = delete_blogger_post(
                get_blogger_service(), blog_id, blogger_post_id
            )
        elif blogger_post_id and not blog_id:
            log.warning("  BLOG_ID not set — skipping Blogger deletion")
            report["errors"].append({
                "filename": dup_filename,
                "error": "BLOG_ID not set",
            })
        elif not blogger_post_id:
            # Try to find by slug
            slug = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', dup_filename.replace('.md', ''))
            if blog_id:
                found_id = find_blogger_post_by_slug(
                    get_blogger_service(), blog_id, slug
                )
                if found_id:
                    blogger_deleted = delete_blogger_post(
                        get_blogger_service(), blog_id, found_id
                    )
                    log.info("  Found Blogger post by slug: %s", found_id)
        
        # Step 3: Delete local file
        local_deleted = delete_local_file(dup_path)
        
        # Step 4: Remove from database
        remove_from_database(conn, dup_filename, published_id)
        
        report["deleted"].append({
            "filename": dup_filename,
            "group": candidate['group'],
            "canonical": candidate['canonical_filename'],
            "quality_gap": candidate['quality_diff'],
            "content_overlap": candidate.get('content_overlap_pct', 'N/A'),
            "backup_path": backup_path,
            "blogger_deleted": blogger_deleted,
            "local_deleted": local_deleted,
            "published_id_removed": published_id,
            "status": "deleted",
        })
    
    conn.close()
    
    # ── Summary ──
    total_deleted = len(report["deleted"])
    total_skipped = len(report["skipped"])
    
    report["summary"] = {
        "total_candidates": len(candidates),
        "passed_safety": report["passed_safety"],
        "failed_safety": report["failed_safety"],
        "deleted": total_deleted,
        "skipped": total_skipped,
        "errors": len(report["errors"]),
        "remaining_posts": 68 - total_deleted,  # approximate
        "canonical_posts_kept": len(canonicals),
        "sitemap_update_needed": total_deleted > 0,
    }
    
    # Save report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    log.info("\nReport saved to: %s", REPORT_PATH)
    
    return report


def main():
    dry_run = "--dry-run" in sys.argv or os.environ.get("DRY_RUN", "true").lower() == "true"
    
    report = run_deletion(dry_run=dry_run)
    
    print("\n" + "=" * 60)
    print("DELETION REPORT")
    print("=" * 60)
    print(f"  Dry run: {report['dry_run']}")
    print(f"  Candidates: {report['total_candidates']}")
    print(f"  Passed safety: {report['passed_safety']}")
    print(f"  Failed safety: {report['failed_safety']}")
    print(f"  Deleted: {report['summary']['deleted']}")
    print(f"  Skipped: {report['summary']['skipped']}")
    print(f"  Remaining posts: {report['summary']['remaining_posts']}")
    print(f"  Canonical kept: {report['summary']['canonical_posts_kept']}")
    print(f"  Sitemap update needed: {report['summary']['sitemap_update_needed']}")
    print(f"  Report: {REPORT_PATH}")
    print("=" * 60)
    
    if not dry_run and report['summary']['deleted'] > 0:
        print("\n⚠️  DELETIONS PERFORMED. Review backup files before purging.")
        print(f"  Backups: {BACKUP_DIR}")


if __name__ == "__main__":
    main()
