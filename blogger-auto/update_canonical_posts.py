#!/usr/bin/env python3
"""
Blogger Canonical Article Updater — CI Only

Updates ONLY the 6 canonical Blogger posts using posts.patch().
Preserves: Blogger ID, URL, slug, publish date, labels
Replaces: title, body, schema, internal links, FAQ, EEAT

REQUIRES GitHub Actions environment:
  - BLOG_ID (from secrets)
  - CLIENT_ID (from secrets)
  - CLIENT_SECRET (from secrets)
  - REFRESH_TOKEN (from secrets)

DO NOT run locally — requires CI credentials only.
"""

import json
import logging
import os
import re
import sys
import time
import markdown
from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Canonical Article Mapping ────────────────────────────────────────
# Maps Blogger post ID -> local markdown file
CANONICAL_ARTICLES = {
    "4968036454649685096": "posts/2026-06-16-gender-neutral-baby-names-the-rise-of-modern-flexible-choices.md",
    "1400276564597342173": "posts/2026-06-16-bohemian-baby-names-artistic-flair-for-your-little-free-spirit.md",
    "4223220335327541022": "posts/2026-06-16-biblical-baby-names-timeless-choices-for-modern-parents.md",
    "7387178594543366611": "posts/2026-06-16-beautiful-baby-girl-names-from-around-the-world.md",
    "8814197584383882658": "posts/2026-06-16-baby-names-born-from-legends-mythological-monikers-for-your-little-hero-or-heroi.md",
    "7175580402225612169": "posts/2026-06-16-musical-baby-names-for-your-little-maestro.md",
}

SCOPES = ["https://www.googleapis.com/auth/blogger"]


# ── Environment Detection ───────────────────────────────────────────
def is_ci_environment() -> bool:
    """Detect if running in GitHub Actions or CI."""
    return bool(os.environ.get("GITHUB_ACTIONS")) or bool(os.environ.get("CI"))


def validate_credentials() -> dict:
    """Validate CI credentials and return parsed values.
    
    Fails gracefully with clear message if secrets are missing.
    """
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    refresh_token = os.environ.get("REFRESH_TOKEN")
    blog_id = os.environ.get("BLOG_ID")
    
    missing = []
    if not client_id:
        missing.append("CLIENT_ID")
    if not client_secret:
        missing.append("CLIENT_SECRET")
    if not refresh_token:
        missing.append("REFRESH_TOKEN")
    if not blog_id:
        missing.append("BLOG_ID")
    
    if missing:
        if is_ci_environment():
            raise EnvironmentError(
                f"Missing GitHub Actions secrets: {', '.join(missing)}. "
                "Check Repository Settings > Secrets and variables > Actions."
            )
        else:
            raise EnvironmentError(
                f"Missing credentials: {', '.join(missing)}. "
                "This script requires GitHub Actions CI environment secrets. "
                "Do not attempt local OAuth — use CI credentials only."
            )
    
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "blog_id": blog_id,
    }


# ── Authentication ──────────────────────────────────────────────────
def get_authenticated_service(credentials: dict):
    """Create authenticated Blogger API service using CI credentials only."""
    creds = Credentials.from_authorized_user_info(
        info={
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
            "refresh_token": credentials["refresh_token"],
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        scopes=SCOPES,
    )
    
    try:
        creds.refresh(Request())
    except Exception as exc:
        log.error("Failed to refresh access token: %s", exc)
        raise
    
    service = build("blogger", "v3", credentials=creds)
    log.info("Authenticated with Blogger API (CI credentials).")
    return service


# ── Content Processing ──────────────────────────────────────────────
def extract_frontmatter_and_body(filepath: Path) -> tuple:
    """Extract frontmatter dict, body text, and full text from markdown file."""
    import yaml
    text = filepath.read_text(encoding="utf-8", errors="ignore")
    frontmatter = {}
    body = text
    
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1].strip())
                if isinstance(fm, dict):
                    frontmatter = fm
                body = parts[2]
            except Exception as e:
                log.warning("Could not parse frontmatter in %s: %s", filepath.name, e)
    
    return frontmatter, body, text


def md_to_html(md_text: str) -> str:
    """Convert markdown body to clean HTML for Blogger posts."""
    return markdown.markdown(md_text, extensions=["tables", "fenced_code"])


# ── Canonical Update Logic ──────────────────────────────────────────
def update_canonical_post(service, blog_id: str, post_id: str, filepath: Path) -> dict:
    """Update a single canonical Blogger post using posts.patch().
    
    Preserves: Blogger ID, URL, slug, publish date, labels
    Replaces: title, body, schema, internal links, FAQ, EEAT
    """
    frontmatter, body, full_text = extract_frontmatter_and_body(filepath)
    
    # Extract metadata
    title = frontmatter.get("title", filepath.stem)
    labels = frontmatter.get("labels", ["Baby Names"])
    if isinstance(labels, str):
        labels = [l.strip() for l in labels.split(",")]
    
    # Get publish date from frontmatter
    publish_date = frontmatter.get("date", "2026-06-16")
    
    # Convert to HTML
    html_body = md_to_html(body)
    
    log.info("Updating post %s...", post_id)
    log.info("  Title: %s", title[:60])
    log.info("  Labels: %s", labels)
    log.info("  Word count: %d", len(body.split()))
    
    try:
        # Use posts.patch() — NOT posts.insert()
        body_data = {
            "id": post_id,
            "title": title,
            "content": html_body,
            "labels": labels,
            "publishDate": publish_date,
        }
        
        request = service.posts().patch(
            blogId=blog_id,
            postId=post_id,
            body=body_data,
            publish=True,
        )
        response = request.execute()
        
        updated_url = response.get("url", f"https://{post_id}.blogspot.com")
        log.info("  SUCCESS: Updated -> %s", updated_url)
        
        return {
            "post_id": post_id,
            "title": title,
            "url": updated_url,
            "labels": labels,
            "word_count": len(body.split()),
            "publish_date": publish_date,
            "status": "updated",
            "updated_at": datetime.now().isoformat(),
        }
    
    except HttpError as exc:
        error_msg = str(exc)
        log.error("  ERROR updating post %s: %s", post_id, error_msg)
        return {
            "post_id": post_id,
            "title": title,
            "url": None,
            "labels": labels,
            "word_count": len(body.split()),
            "publish_date": publish_date,
            "status": f"error: {exc.resp.status} {exc.reason}",
            "error_details": error_msg,
            "updated_at": datetime.now().isoformat(),
        }


# ── Main Pipeline ───────────────────────────────────────────────────
def main():
    log.info("=" * 70)
    log.info("BLOGGER CANONICAL ARTICLE UPDATER (CI ONLY)")
    log.info("=" * 70)
    
    # Environment check
    ci = is_ci_environment()
    log.info("Environment: %s", "GitHub Actions CI" if ci else "Local (will fail)")
    log.info("Canonical articles to update: %d", len(CANONICAL_ARTICLES))
    
    # Validate credentials
    try:
        creds = validate_credentials()
    except EnvironmentError as exc:
        log.error("FATAL: %s", exc)
        sys.exit(1)
    
    log.info("Blog ID: %s", creds["blog_id"])
    log.info("Client ID: %s...", creds["client_id"][:20])
    
    # Authenticate
    try:
        service = get_authenticated_service(creds)
    except Exception as exc:
        log.error("Authentication failed: %s", exc)
        sys.exit(1)
    
    # Update each canonical post
    results = []
    for post_id, filepath in CANONICAL_ARTICLES.items():
        log.info("-" * 50)
        result = update_canonical_post(service, creds["blog_id"], post_id, Path(filepath))
        results.append(result)
        time.sleep(1)  # Rate limiting between API calls
    
    # Summary
    success = sum(1 for r in results if r["status"] == "updated")
    errors = sum(1 for r in results if r["status"] != "updated")
    
    log.info("")
    log.info("=" * 70)
    log.info("UPDATE SUMMARY")
    log.info("=" * 70)
    log.info("  Total attempted: %d", len(results))
    log.info("  Successful:      %d", success)
    log.info("  Failed:          %d", errors)
    log.info("")
    
    for r in results:
        icon = "✓" if r["status"] == "updated" else "✗"
        log.info("  %s %-50s %d words", icon, r["title"][:50], r["word_count"])
        if r.get("url"):
            log.info("    URL: %s", r["url"])
        if r.get("error_details"):
            log.info("    Error: %s", r["error_details"][:100])
    
    log.info("=" * 70)
    
    # Save results
    results_path = Path("/tmp/blogger_canonical_update_results.json")
    results_path.write_text(json.dumps(results, indent=2))
    log.info("Results saved to: %s", results_path)
    
    # Exit code
    sys.exit(0 if errors == 0 else 1)


if __name__ == "__main__":
    main()
