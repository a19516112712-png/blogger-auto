#!/usr/bin/env python3
"""
Blogger Auto Publishing Script

Reads markdown files from the posts/ directory, extracts frontmatter metadata,
converts markdown to HTML, and publishes them to Blogger via the Blogger API v3.

Supports automatic access token refresh and duplicate post detection.
"""

import logging
import os
import sys
from pathlib import Path

import google.auth.transport.requests
import markdown
import yaml
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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
DUPLICATE_REASON = "duplicate"  # Reason code from Blogger API for duplicates


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def get_authenticated_service():
    """Create an authenticated Blogger API service using OAuth 2.0 credentials.

    Credentials are sourced from environment variables expected to be set
    via GitHub Secrets.

    Returns:
        googleapiclient.discovery.Resource: Authenticated Blogger API v3 service.
    """
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
            "Ensure GitHub Secrets are configured correctly."
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

    # Auto-refresh if needed
    try:
        creds.refresh(google.auth.transport.requests.Request())
    except Exception as exc:
        log.error("Failed to refresh access token: %s", exc)
        raise

    service = build("blogger", "v3", credentials=creds)
    log.info("Authenticated with Blogger API successfully.")
    return service


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------
def sanitize_title(raw_title: str | None, filename: str) -> str | None:
    """Clean and validate a title extracted from frontmatter.

    Strips leading YAML key prefixes (e.g. 'title:'), trims whitespace,
    and rejects titles that look like raw YAML keys.

    Args:
        raw_title: The title value from frontmatter (may be None or prefixed).
        filename: The source filename (for logging).

    Returns:
        Cleaned title string, or None if the title is invalid.
    """
    if not raw_title:
        log.warning("Title extraction failed for %s: empty or None.", filename)
        return None

    title = raw_title.strip()

    # Guard: reject titles that are raw YAML key-value lines
    YAML_KEY_PREFIXES = ("title:", "date:", "labels:", "meta_description:", "---", "# ")
    for prefix in YAML_KEY_PREFIXES:
        if title.lower().startswith(prefix):
            if prefix in ("date:", "labels:", "meta_description:", "---", "# "):
                log.warning(
                    "Title extraction failed for %s: title begins with '%s' — skipping.",
                    filename, prefix.rstrip(": "),
                )
                return None
            # "title:" prefix — strip it and re-trim
            title = title.split(":", 1)[1].strip()
            log.info(
                "Stripped 'title:' prefix from %s → '%s'",
                filename, title,
            )
            break

    # Final whitespace/normalization check
    title = title.strip()
    if not title:
        log.warning("Title extraction failed for %s: empty after sanitization.", filename)
        return None

    log.info("[INFO] Final title: %s", title)
    return title


def parse_frontmatter_and_body(filepath: Path):
    """Parse a markdown file, splitting frontmatter YAML from markdown body.

    Args:
        filepath: Path to the markdown file.

    Returns:
        tuple[dict | None, str]: (frontmatter_dict, markdown_body).
        Returns (None, full_content) if no frontmatter delimiter is found.
    """
    text = filepath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        log.warning("No frontmatter found in %s", filepath.name)
        return None, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        log.warning("Malformed frontmatter in %s", filepath.name)
        return None, text

    frontmatter_raw = parts[1].strip()
    body = parts[2].strip()
    frontmatter = yaml.safe_load(frontmatter_raw) or {}
    return frontmatter, body


def md_to_html(md_text: str) -> str:
    """Convert markdown text to HTML.

    Args:
        md_text: Raw markdown string.

    Returns:
        str: HTML string.
    """
    extensions = [
        "markdown.extensions.extra",      # tables, fenced_code, codehilite, etc.
        "markdown.extensions.toc",        # table of contents
        "markdown.extensions.sane_lists", # sane list handling
    ]
    return markdown.markdown(md_text, extensions=extensions)


# ---------------------------------------------------------------------------
# Blogger publishing
# ---------------------------------------------------------------------------
def get_existing_posts(service, blog_id: str):
    """Fetch all published post titles from the blog to detect duplicates.

    Args:
        service: Authenticated Blogger API service.
        blog_id: The Blogger blog ID.

    Returns:
        set[str]: Set of existing post titles (case-insensitive).
    """
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


def publish_post(service, blog_id: str, title: str, html_body: str, labels: list[str]):
    """Publish a single post to Blogger.

    Args:
        service: Authenticated Blogger API service.
        blog_id: The Blogger blog ID.
        title: Post title.
        html_body: Post body in HTML.
        labels: List of label strings.

    Returns:
        str | None: Published post URL, or None on failure.
    """
    body = {
        "title": title,
        "content": html_body,
        "labels": labels or [],
    }
    try:
        post = service.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
        post_url = post.get("url", f"https://{post['id']}.blogspot.com")
        log.info("Published: '%s' -> %s", title, post_url)
        return post_url
    except HttpError as exc:
        log.error("API error publishing '%s': %s", title, exc)
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    log.info("Starting Blogger Auto Publish…")

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

    # --- Phase 1: classify valid vs invalid ---
    valid_files: list[tuple[Path, dict, str]] = []
    invalid_count = 0

    for md_file in md_files:
        frontmatter, md_body = parse_frontmatter_and_body(md_file)
        raw_title = frontmatter.get("title") if frontmatter else None
        title = sanitize_title(raw_title, md_file.name)

        if not title or not md_body.strip():
            log.warning("INVALID — %s (no title or empty body)", md_file.name)
            invalid_count += 1
        else:
            # Persist the sanitized title back into the frontmatter dict
            frontmatter["title"] = title
            valid_files.append((md_file, frontmatter, md_body))

    valid_count = len(valid_files)
    log.info("Classification complete. Valid: %d, Invalid: %d.", valid_count, invalid_count)

    if valid_count == 0:
        log.info("No valid posts to publish.")
        if invalid_count > 0:
            log.warning("%d invalid post(s) detected — run repair_posts.py to fix.", invalid_count)
        return

    # --- Phase 2: authenticate ---
    try:
        service = get_authenticated_service()
    except Exception as exc:
        log.error("Authentication failed: %s", exc)
        sys.exit(1)

    existing_titles = get_existing_posts(service, blog_id)
    log.info("Fetched %d existing post title(s) for dedup.", len(existing_titles))

    # --- Phase 3: publish ---
    published_count = 0
    skipped_duplicate = 0
    publish_failed = 0

    for md_file, frontmatter, md_body in valid_files:
        log.info("Processing: %s", md_file.name)
        title = frontmatter["title"]

        # Duplicate check
        if title.strip().lower() in existing_titles:
            log.info("Skipping '%s': already published (title match).", title)
            skipped_duplicate += 1
            continue

        labels = frontmatter.get("labels", "")
        if isinstance(labels, str):
            labels = [lbl.strip() for lbl in labels.split(",") if lbl.strip()]
        elif not isinstance(labels, list):
            labels = []

        html_body = md_to_html(md_body)

        url = publish_post(service, blog_id, title, html_body, labels)
        if url:
            published_count += 1
            existing_titles.add(title.strip().lower())
        else:
            publish_failed += 1
            log.error("Failed to publish '%s'.", title)

    # --- Summary ---
    total_skipped = invalid_count + skipped_duplicate + publish_failed
    log.info("=" * 50)
    log.info("PUBLISH SUMMARY")
    log.info("===============")
    log.info("  Files scanned:         %d", total_files)
    log.info("  Valid posts:           %d", valid_count)
    log.info("  Invalid posts:         %d", invalid_count)
    log.info("  Published:             %d", published_count)
    log.info("  Skipped duplicates:    %d", skipped_duplicate)
    log.info("  Failed:                %d", publish_failed)
    log.info("=======")


if __name__ == "__main__":
    main()
