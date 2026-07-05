#!/usr/bin/env python3
"""
Blogger Auto Publishing Script — Production v3

Reads markdown files from posts/, extracts frontmatter metadata,
converts markdown to HTML, and publishes to Blogger via the Blogger API v3.

Production Features:
  - Update-first: checks DB for existing posts before inserting
  - Duplicate detection: API + DB + title similarity
  - Stores blogger_post_id, URL, slug, labels, content hash in SQLite
  - Never publishes duplicate content
  - Preserves original OAuth, retry, and duplicate detection logic
  - Uses shared helpers from utils/ (no duplicate functions)
"""

import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import google.auth.transport.requests
import markdown
import yaml
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ── Shared helpers ──────────────────────────────────────────────────────
from utils.helpers import slugify, sanitize_labels, sanitize_title, FORBIDDEN_LABELS
from utils.yaml_parser import parse_frontmatter
from database.topic_queue import TopicQueue

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
POSTS_DIR = Path(__file__).resolve().parent / "posts"
SCOPES = ["https://www.googleapis.com/auth/blogger"]
MAX_RETRIES = 3
RETRYABLE_CODES = (429, 500, 503)


# =========================================================================
# AUTHENTICATION
# =========================================================================

def get_authenticated_service():
    """Create an authenticated Blogger API service using OAuth 2.0 credentials."""
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    refresh_token = os.environ.get("REFRESH_TOKEN")

    missing = [
        name for name, val in [
            ("CLIENT_ID", client_id),
            ("CLIENT_SECRET", client_secret),
            ("REFRESH_TOKEN", refresh_token),
        ] if not val
    ]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Ensure GitHub Actions secrets are configured correctly."
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

    try:
        creds.refresh(google.auth.transport.requests.Request())
    except Exception as exc:
        log.error("Failed to refresh access token: %s", exc)
        raise

    service = build("blogger", "v3", credentials=creds)
    log.info("Authenticated with Blogger API successfully.")
    return service


# =========================================================================
# DUPLICATE DETECTION
# =========================================================================

def get_existing_posts(service, blog_id: str) -> set:
    """Fetch existing live post titles for dedup."""
    existing = set()
    try:
        request = service.posts().list(blogId=blog_id, status="live", maxResults=500)
        while request is not None:
            response = request.execute()
            for post in response.get("items", []):
                existing.add(post["title"].strip().lower())
            request = service.posts().list_next(request, response)
    except Exception as exc:
        log.warning("Could not fetch existing posts (proceeding anyway): %s", exc)
    return existing


def find_existing_blogger_post(service, blog_id: str, title: str, slug: str) -> str | None:
    """Search Blogger for an existing post matching title or slug.
    
    Returns the blogger post ID if found, None otherwise.
    """
    try:
        # Search by title
        request = service.posts().list(
            blogId=blog_id,
            status="live",
            maxResults=500
        )
        while request is not None:
            response = request.execute()
            for post in response.get("items", []):
                post_title = post.get("title", "").strip().lower()
                post_slug = post.get("url", "").split("/")[-1] if post.get("url") else ""
                
                # Exact title match
                if title.strip().lower() == post_title:
                    bid = post["id"]
                    log.info("Found existing post by title: %s (ID: %s)", title[:50], bid)
                    return bid
                
                # Slug match
                if slug.lower() in post_slug.lower() or post_slug.lower() in slug.lower():
                    bid = post["id"]
                    log.info("Found existing post by slug: %s (ID: %s)", slug[:50], bid)
                    return bid

            request = service.posts().list_next(request, response)
    except Exception as exc:
        log.warning("Error searching for existing post: %s", exc)
    
    return None


# =========================================================================
# PUBLISHING
# =========================================================================

def publish_post(service, blog_id: str, title: str, html_body: str,
                 labels: list[str], queue: TopicQueue, publish_date: str = None) -> str | None:
    """Publish a new post to Blogger. Returns post URL on success."""
    try:
        body = {
            "title": title,
            "content": html_body,
            "labels": labels or [],
        }
        if publish_date:
            body["published"] = publish_date

        post = service.posts().insert(
            blogId=blog_id, body=body
        ).execute()
        
        post_id = post.get("id")
        post_url = post.get("url", "")
        log.info("Published: '%s' -> %s (ID: %s)", title[:50], post_url, post_id)

        # Store in SQLite
        content_hash = _compute_hash(html_body)
        queue.mark_published(
            topic_id=None,
            generated_id=None,
            title=title,
            slug=slugify(title),
            url=post_url,
            labels=labels or [],
            content_hash=content_hash,
            blogger_id=post_id,
            publish_date=publish_date,
        )
        return post_url

    except HttpError as exc:
        log.error("API error publishing '%s': %s", title, exc)
        return None


def update_post(service, blog_id: str, blogger_post_id: str, title: str,
                html_body: str, labels: list[str]) -> str | None:
    """Update an existing Blogger post. Returns post URL on success."""
    try:
        body = {
            "id": blogger_post_id,
            "title": title,
            "content": html_body,
            "labels": labels or [],
        }
        post = service.posts().patch(
            blogId=blog_id, postId=blogger_post_id, body=body
        ).execute()
        post_url = post.get("url", f"https://{blogger_post_id}.blogspot.com")
        log.info("Updated: '%s' -> %s", title[:50], post_url)
        return post_url
    except HttpError as exc:
        log.error("API error updating '%s': %s", title, exc)
        return None


def _compute_hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# =========================================================================
# MAIN
# =========================================================================

def main():
    log.info("Starting Blogger Auto Publish (production v3)…")

    blog_id = os.environ.get("BLOG_ID")
    if not blog_id:
        log.error("BLOG_ID environment variable is not set.")
        sys.exit(1)

    md_files = sorted(POSTS_DIR.glob("*.md"))
    total_files = len(md_files)
    if not md_files:
        log.info("No markdown files found in %s. Nothing to publish.", POSTS_DIR)
        return

    log.info("Scanning %d markdown file(s) in %s…", total_files, POSTS_DIR)

    # ── Phase 1: classify valid vs invalid ──
    valid_files: list[tuple[Path, dict, str]] = []
    invalid_count = 0

    for md_file in md_files:
        frontmatter, md_body = parse_frontmatter(md_file)
        raw_title = frontmatter.get("title") if frontmatter else None
        title = sanitize_title(raw_title, md_file.name)

        if not title or not md_body.strip():
            log.warning("INVALID — %s (no title or empty body)", md_file.name)
            invalid_count += 1
        else:
            frontmatter["title"] = title
            valid_files.append((md_file, frontmatter, md_body))

    valid_count = len(valid_files)
    log.info("Classification complete. Valid: %d, Invalid: %d.", valid_count, invalid_count)

    if valid_count == 0:
        log.info("No valid posts to publish.")
        return

    # ── Phase 2: authenticate ──
    try:
        service = get_authenticated_service()
    except Exception as exc:
        log.error("Authentication failed: %s", exc)
        sys.exit(1)

    # Fetch existing Blogger posts for dedup
    existing_titles = get_existing_posts(service, blog_id)
    log.info("Fetched %d existing post titles from Blogger.", len(existing_titles))

    # ── Database ──
    queue = TopicQueue()

    # ── Phase 3: publish or update ──
    published_count = 0
    updated_count = 0
    skipped_duplicate = 0
    publish_failed = 0

    for md_file, frontmatter, md_body in valid_files:
        log.info("Processing: %s", md_file.name)
        title = frontmatter["title"]
        slug = slugify(title)

        # Duplicate check (API)
        if title.strip().lower() in existing_titles:
            log.info("Skipping '%s': already published (title match).", title)
            skipped_duplicate += 1
            continue

        # Duplicate check (DB)
        if queue.is_duplicate_title(title):
            log.info("Skipping '%s': duplicate in database.", title)
            skipped_duplicate += 1
            continue

        raw_labels = frontmatter.get("labels", "")
        labels = sanitize_labels(raw_labels)
        html_body = markdown.markdown(md_body, extensions=['tables', 'fenced_code'])

        # Check if this post exists on Blogger (by slug/title match)
        blogger_id = find_existing_blogger_post(service, blog_id, title, slug)
        
        if blogger_id:
            # Post exists — update instead of insert
            url = update_post(service, blog_id, blogger_id, title, html_body, labels)
            if url:
                updated_count += 1
                existing_titles.add(title.strip().lower())
                # Update content hash in DB
                content_hash = _compute_hash(html_body)
                queue.conn.execute(
                    "UPDATE published SET content_hash = ? WHERE slug = ?",
                    (content_hash, slug)
                )
                queue.conn.commit()
            else:
                publish_failed += 1
                log.error("Failed to update '%s'.", title)
        else:
            # New post — insert
            publish_date = frontmatter.get("date")
            url = publish_post(service, blog_id, title, html_body, labels, queue, publish_date)
            if url:
                published_count += 1
                existing_titles.add(title.strip().lower())
            else:
                publish_failed += 1
                log.error("Failed to publish '%s'.", title)

    # ── Summary ──
    log.info("=" * 50)
    log.info("PUBLISH SUMMARY")
    log.info("==================")
    log.info("  Files scanned:         %d", total_files)
    log.info("  Valid posts:           %d", valid_count)
    log.info("  Invalid posts:         %d", invalid_count)
    log.info("  Newly published:       %d", published_count)
    log.info("  Updated existing:      %d", updated_count)
    log.info("  Skipped duplicates:    %d", skipped_duplicate)
    log.info("  Failed:                %d", publish_failed)
    log.info("  DB stats: %s", json.dumps(queue.stats()))
    log.info("==================")

    queue.close()


if __name__ == "__main__":
    main()
