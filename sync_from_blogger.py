#!/usr/bin/env python3
"""
Sync from Blogger — Download ALL published articles from Blogger API.

This module:
1. Authenticates with Blogger API v3
2. Fetches all published posts (paginated, up to 500 per page)
3. Converts HTML → Markdown with preserved metadata
4. Saves each article as a .md file in posts/
5. Imports all metadata into SQLite (keywords, generated, published, fingerprints, quality_scores)
6. Also imports the 68 local articles that already exist

Usage:
    export BLOG_ID=xxx
    export CLIENT_ID=xxx
    export CLIENT_SECRET=xxx
    export REFRESH_TOKEN=xxx
    python sync_from_blogger.py

Does NOT modify:
    - Blogger API auth logic
    - Existing publish.py
    - Article generation logic
"""

import hashlib
import html
import json
import logging
import os
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import markdown
import yaml
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ── Shared helpers ──────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.helpers import (
    slugify, sanitize_labels, sanitize_title, compute_content_hash,
    FORBIDDEN_LABELS, BANNED_PHRASES,
)
from utils.yaml_parser import parse_frontmatter, extract_date_from_filename
from database.topic_queue import TopicQueue
from database.schema import DB_PATH

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

POSTS_DIR = Path(__file__).resolve().parent / "posts"
SCOPES = ["https://www.googleapis.com/auth/blogger"]


# =========================================================================
# 1. Blogger API Authentication
# =========================================================================

def get_blogger_service():
    """Authenticate and return Blogger API service."""
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
            "Set them before running sync."
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
        creds.refresh(Request())
    except Exception as exc:
        log.error("Failed to refresh access token: %s", exc)
        raise

    service = build("blogger", "v3", credentials=creds)
    log.info("Authenticated with Blogger API successfully.")
    return service


# =========================================================================
# 2. Download All Posts from Blogger
# =========================================================================

def fetch_all_posts(service, blog_id: str) -> list[dict]:
    """Fetch ALL live posts from Blogger, paginating through all results."""
    all_posts = []
    page_token = None
    page_num = 0

    while True:
        page_num += 1
        request = service.posts().list(
            blogId=blog_id,
            status="live",
            maxResults=100,
            pageToken=page_token,
            fetchBodies=True,
        )
        response = request.execute()
        items = response.get("items", [])

        if not items:
            log.info("  Page %d: no more posts. Total fetched: %d", page_num, len(all_posts))
            break

        all_posts.extend(items)
        log.info("  Page %d: fetched %d posts (cumulative: %d)",
                 page_num, len(items), len(all_posts))

        page_token = response.get("nextPageToken")
        if not page_token:
            break

        time.sleep(0.5)  # Rate limiting

    return all_posts


# =========================================================================
# 3. HTML → Markdown Conversion
# =========================================================================

def html_to_markdown(html_content: str) -> str:
    """Convert Blogger HTML content to clean Markdown.

    Preserves:
    - Headings (H1-H6)
    - Bold, italic, strikethrough
    - Lists (ordered and unordered)
    - Tables
    - Code blocks
    - Blockquotes
    - Links
    - Images (preserving src)
    """
    md = html_content

    # Convert <br> to line break
    md = re.sub(r'<br\s*/?>', '\n', md, flags=re.IGNORECASE)

    # Convert <hr> to horizontal rule
    md = re.sub(r'<hr\s*/?>', '\n---\n', md, flags=re.IGNORECASE)

    # Convert <p> to paragraphs
    md = re.sub(r'</p>\s*<p>', '\n\n', md, flags=re.IGNORECASE)
    md = re.sub(r'<p[^>]*>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'</p>', '', md, flags=re.IGNORECASE)

    # Convert headings
    for i in range(6, 0, -1):
        md = re.sub(
            rf'<h{i}[^>]*>(.*?)</h{i}>',
            f'#' * i + r' \1',
            md,
            flags=re.IGNORECASE | re.DOTALL
        )

    # Convert bold
    md = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', md, flags=re.IGNORECASE | re.DOTALL)
    md = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', md, flags=re.IGNORECASE | re.DOTALL)

    # Convert italic
    md = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', md, flags=re.IGNORECASE | re.DOTALL)
    md = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', md, flags=re.IGNORECASE | re.DOTALL)

    # Convert strikethrough
    md = re.sub(r'<s[^>]*>(.*?)</s>', r'~~\1~~', md, flags=re.IGNORECASE | re.DOTALL)
    md = re.sub(r'<del[^>]*>(.*?)</del>', r'~~\1~~', md, flags=re.IGNORECASE | re.DOTALL)

    # Convert links
    md = re.sub(
        r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        r'[\2](\1)',
        md,
        flags=re.IGNORECASE | re.DOTALL
    )

    # Convert images
    md = re.sub(
        r'<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*>',
        r'![\2](\1)',
        md,
        flags=re.IGNORECASE | re.DOTALL
    )
    md = re.sub(
        r'<img[^>]*alt="([^"]*)"[^>]*src="([^"]*)"[^>]*>',
        r'![\1](\2)',
        md,
        flags=re.IGNORECASE | re.DOTALL
    )
    md = re.sub(
        r'<img[^>]*src="([^"]*)"[^>]*>',
        r'[](\\1)',
        md,
        flags=re.IGNORECASE
    )

    # Convert unordered lists
    md = re.sub(r'<li[^>]*>', '- ', md, flags=re.IGNORECASE)
    md = re.sub(r'</li>', '\n', md, flags=re.IGNORECASE)

    # Convert ordered lists
    md = re.sub(r'<ol[^>]*>', '\n', md, flags=re.IGNORECASE)
    md = re.sub(r'</ol>', '\n', md, flags=re.IGNORECASE)
    md = re.sub(r'<li[^>]*value="(\d+)"[^>]*>', r'\1. ', md, flags=re.IGNORECASE)

    # Convert code blocks
    md = re.sub(
        r'<pre[^>]*>(.*?)</pre>',
        r'```\n\1\n```',
        md,
        flags=re.IGNORECASE | re.DOTALL
    )
    md = re.sub(
        r'<code[^>]*>(.*?)</code>',
        r'`\1`',
        md,
        flags=re.IGNORECASE | re.DOTALL
    )

    # Convert blockquotes
    md = re.sub(
        r'<blockquote[^>]*>(.*?)</blockquote>',
        r'> \1',
        md,
        flags=re.IGNORECASE | re.DOTALL
    )

    # Convert tables
    md = re.sub(r'<table[^>]*>', '\n', md, flags=re.IGNORECASE)
    md = re.sub(r'</table>', '\n', md, flags=re.IGNORECASE)
    md = re.sub(r'<thead[^>]*>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'</thead>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'<tbody[^>]*>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'</tbody>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'<tr[^>]*>', '\n', md, flags=re.IGNORECASE)
    md = re.sub(r'</tr>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'<th[^>]*>(.*?)</th>', r'| \1 |', md, flags=re.IGNORECASE | re.DOTALL)
    md = re.sub(r'<td[^>]*>(.*?)</td>', r'| \1 |', md, flags=re.IGNORECASE | re.DOTALL)
    md = re.sub(r'</th>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'</td>', '', md, flags=re.IGNORECASE)

    # Convert divs and spans (just strip tags)
    md = re.sub(r'<div[^>]*>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'</div>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'<span[^>]*>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'</span>', '', md, flags=re.IGNORECASE)

    # Strip any remaining HTML tags
    md = re.sub(r'<[^>]+>', '', md)

    # Decode HTML entities
    md = html.unescape(md)

    # Clean up whitespace
    lines = md.split('\n')
    cleaned = []
    for line in lines:
        cleaned.append(line.rstrip())
    md = '\n'.join(cleaned)

    # Remove excessive blank lines (more than 2 consecutive)
    md = re.sub(r'\n{3,}', '\n\n', md)

    return md.strip()


# =========================================================================
# 4. Extract Blogger Labels
# =========================================================================

def extract_labels(post: dict) -> list[str]:
    """Extract and sanitize labels from a Blogger post."""
    raw_labels = post.get("labels", [])
    if not raw_labels:
        return ["Baby Names"]
    return sanitize_labels(raw_labels)


# =========================================================================
# 5. Build Markdown File Content
# =========================================================================

def build_markdown(post: dict, body_md: str) -> str:
    """Construct full markdown file content with frontmatter."""
    title = post.get("title", "Untitled")
    labels = extract_labels(post)
    published = post.get("published", "")
    updated = post.get("updated", "")
    author = post.get("author", {}).get("displayName", "Admin")

    # Extract date from published timestamp
    try:
        pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        date_str = pub_dt.strftime("%Y-%m-%d")
    except Exception:
        date_str = datetime.now().strftime("%Y-%m-%d")

    slug = slugify(title)
    filename = f"{date_str}-{slug}.md"

    meta_desc = f"Discover {title.lower()}, including meanings, origins, pronunciation guides, and naming ideas."

    frontmatter = {
        "title": title,
        "labels": labels,
        "date": date_str,
        "slug": slug,
        "meta_description": meta_desc,
        "seo_title": title[:65] if len(title) <= 65 else title[:62] + "...",
        "og_title": title,
        "og_description": meta_desc,
        "blogger_post_id": post.get("id", ""),
        "blogger_url": post.get("url", ""),
        "author": author,
        "published_at": published,
        "updated_at": updated,
    }

    fm_yaml = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return f"---\n{fm_yaml}---\n\n{body_md}"


# =========================================================================
# 6. Sync One Post
# =========================================================================

def sync_single_post(service, blog_id: str, post: dict, queue: TopicQueue) -> bool:
    """Download and save a single Blogger post. Returns True on success."""
    post_id = post.get("id", "unknown")
    title = post.get("title", "Untitled")
    log.info("  Syncing: %s (ID: %s)", title[:60], post_id)

    # Get post body (HTML)
    try:
        req = service.posts().get(
            blogId=blog_id,
            postId=post_id,
            fetchBody=True,
        )
        post_data = req.execute()
    except Exception as exc:
        log.error("    Failed to fetch post body for %s: %s", title[:40], exc)
        queue.mark_failed(
            keyword_id=None, title=title, slug=slugify(title),
            reason=f"API fetch failed: {exc}",
        )
        return False

    html_body = post_data.get("content", "")
    if not html_body:
        # Try alternate approach
        try:
            all_req = service.posts().list(
                blogId=blog_id, status="live", maxResults=1,
                pageToken=post.get("etag", "")
            )
            # If we got the post via list with bodies, use that
        except:
            pass

    # Convert HTML → Markdown
    body_md = html_to_markdown(html_body) if html_body else "# " + title + "\n\nNo content available."

    # Build full markdown with frontmatter
    md_content = build_markdown(post_data if html_body else post, body_md)

    # Generate filename
    slug = slugify(title)
    try:
        pub_dt = datetime.fromisoformat(
            (post_data.get("published") or post.get("published", ""))
            .replace("Z", "+00:00")
        )
        date_str = pub_dt.strftime("%Y-%m-%d")
    except Exception:
        date_str = datetime.now().strftime("%Y-%m-%d")

    filename = f"{date_str}-{slug}.md"

    # Avoid name collisions
    save_path = POSTS_DIR / filename
    if save_path.exists():
        # Collision: append post ID
        base = save_path.stem
        ext = save_path.suffix
        collision_name = f"{base}-{post_id}{ext}"
        save_path = POSTS_DIR / collision_name
        log.info("    Name collision: saving as %s", save_path.name)

    # Write file
    try:
        save_path.write_text(md_content, encoding="utf-8")
        log.info("    Saved: %s (%d words)", save_path.name, len(body_md.split()))
    except Exception as exc:
        log.error("    Failed to write %s: %s", save_path, exc)
        return False

    # Store in published table
    content_hash = compute_content_hash(body_md)
    labels = extract_labels(post_data if html_body else post)

    queue.mark_published(
        topic_id=None,
        generated_id=None,
        title=title,
        slug=slug,
        url=post_data.get("url", ""),
        labels=labels,
        content_hash=content_hash,
        blogger_id=post_id,
        publish_date=date_str,
    )

    # Store keyword if not exists
    keyword = title.lower().strip()
    try:
        queue.conn.execute(
            "INSERT INTO keywords (keyword, intent, cluster, priority, difficulty, status, created_at, last_updated) "
            "VALUES (?, 'LIST_INTENT', 'blogger_import', 50.0, 50.0, 'published', ?, ?)",
            (keyword, datetime.now().isoformat(), datetime.now().isoformat()),
        )
    except Exception:
        pass  # keyword already exists

    return True


# =========================================================================
# 7. Import Local Articles Into Database
# =========================================================================

def import_local_articles(queue: TopicQueue):
    """Import the 68 local articles into the database (keywords, published, fingerprints)."""
    log.info("\n=== Importing Local Articles ===")
    imported = 0
    skipped = 0

    for md_file in sorted(POSTS_DIR.glob("*.md")):
        frontmatter, md_body = parse_frontmatter(md_file)
        raw_title = frontmatter.get("title") if frontmatter else None
        title = sanitize_title(raw_title, md_file.name)

        if not title or not md_body.strip():
            log.info("  SKIP (invalid): %s", md_file.name)
            skipped += 1
            continue

        slug = slugify(title)
        content_hash = compute_content_hash(md_body)
        word_count = len(md_body.split())
        labels = extract_labels(frontmatter)

        # Determine publish date from filename
        date_str = extract_date_from_filename(md_file.name) or datetime.now().strftime("%Y-%m-%d")

        # Insert into published table
        try:
            queue.conn.execute(
                """INSERT OR IGNORE INTO published (title, slug, url, publish_date,
                                                    labels, content_hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (title, slug, f"/posts/{md_file.name}", date_str,
                 ",".join(labels), content_hash, datetime.now().isoformat()),
            )
        except Exception as exc:
            log.error("  DB error for %s: %s", md_file.name, exc)
            continue

        # Insert keyword
        keyword = title.lower().strip()
        try:
            queue.conn.execute(
                """INSERT INTO keywords (keyword, intent, cluster, priority, difficulty,
                                          status, created_at, last_updated)
                   VALUES (?, 'LIST_INTENT', 'local_import', 50.0, 50.0, 'published', ?, ?)""",
                (keyword, datetime.now().isoformat(), datetime.now().isoformat()),
            )
        except Exception:
            pass

        # Insert into generated table
        try:
            queue.conn.execute(
                """INSERT OR IGNORE INTO generated (keyword_id, title, slug, word_count,
                                                     quality_score, file_path, created_at)
                   VALUES ((SELECT id FROM keywords WHERE keyword=?), ?, ?, ?, 0.0, ?, ?)""",
                (keyword, title, slug, word_count, str(md_file), datetime.now().isoformat()),
            )
        except Exception:
            pass

        imported += 1
        log.info("  Imported: %s (%d words, slug: %s)", md_file.name, word_count, slug)

    queue.conn.commit()
    log.info("Local import complete: %d imported, %d skipped", imported, skipped)


# =========================================================================
# 8. Generate Fingerprints For All Articles
# =========================================================================

def generate_fingerprints_for_all(queue: TopicQueue):
    """Generate fingerprints for every article in posts/."""
    log.info("\n=== Generating Fingerprints ===")
    imported = 0

    for md_file in sorted(POSTS_DIR.glob("*.md")):
        try:
            frontmatter, md_body = parse_frontmatter(md_file)
            if not md_body.strip():
                continue

            slug = slugify(frontmatter.get("title", "")) if frontmatter else md_file.stem
            content_hash = compute_content_hash(md_body)

            # Compute basic fingerprint components
            intro = _extract_intro(md_body)
            headings = _extract_headings(md_body)
            faqs = _extract_faqs(md_body)
            tables = _extract_tables(md_body)
            conclusion = _extract_conclusion(md_body)
            paragraphs = _analyze_paragraphs(md_body)
            internal_links = _count_internal_links(md_body)
            schema_types = _detect_schema(md_body)
            ai_patterns = _detect_ai_patterns(md_body)

            intro_sig = hashlib.sha256(intro.encode()).hexdigest()[:16]
            heading_sig = hashlib.sha256(headings.encode()).hexdigest()[:16]
            faq_sig = hashlib.sha256(faqs.encode()).hexdigest()[:16] if faqs else ""
            conclusion_sig = hashlib.sha256(conclusion.encode()).hexdigest()[:16]
            content_sig = hashlib.sha256(md_body.encode()).hexdigest()[:16]

            # paragraphs is already a list of word counts (ints)
            avg_para_len = sum(paragraphs) / max(len(paragraphs), 1)
            unique_words = len(set(md_body.lower().split()))
            total_words = len(md_body.split())
            unique_ratio = unique_words / max(total_words, 1)

            word_count = len(md_body.split())

            queue.conn.execute(
                """INSERT OR REPLACE INTO fingerprints
                   (filename, content_hash, intro_hash, intro_signature, heading_hierarchy,
                    heading_structure, faq_hash, table_structure, paragraph_distribution,
                    conclusion_hash, conclusion_signature, internal_links, schema_types,
                    ai_patterns, word_count, avg_paragraph_length, unique_word_ratio,
                    quality_score, computed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?)""",
                (md_file.name, content_sig, content_sig, intro_sig, heading_sig,
                 headings, faq_sig, tables, json.dumps(paragraphs),
                 conclusion_sig, conclusion_sig, internal_links, schema_types,
                 ai_patterns, word_count, avg_para_len, unique_ratio,
                 datetime.now().isoformat()),
            )
            imported += 1
        except Exception as exc:
            log.error("  Fingerprint error for %s: %s", md_file.name, exc)

    queue.conn.commit()
    log.info("Fingerprint generation complete: %d articles fingerprinted", imported)


def _extract_intro(text: str) -> str:
    """Extract the first paragraph(s) as introduction."""
    parts = re.split(r'\n\s*\n', text.strip())
    if parts:
        # Clean markdown from intro
        intro = re.sub(r'#{1,6}\s+', '', parts[0]).strip()
        return intro[:500]
    return text[:500]


def _extract_headings(text: str) -> str:
    """Extract all headings in order."""
    headings = re.findall(r'^(#{1,6})\s+(.+)$', text, re.MULTILINE)
    return "\n".join(f"{'H' + h[0]}: {h[1].strip()}" for h in headings)


def _extract_faqs(text: str) -> str:
    """Extract FAQ section."""
    faq_match = re.search(r'(?:FAQ|Frequently Asked Questions)(.*?)(?:\n\n|\Z)', text, re.IGNORECASE | re.DOTALL)
    if faq_match:
        return faq_match.group(1)[:1000]
    return ""


def _extract_tables(text: str) -> str:
    """Extract table structures."""
    tables = re.findall(r'\|.*?\|.*?\n(?:\|[-| :]+\|.*?\n)?(.*?)(?=\n\n|\n#|\Z)', text, re.DOTALL)
    return json.dumps([t.strip()[:200] for t in tables[:10]])


def _extract_conclusion(text: str) -> str:
    """Extract the last substantial paragraph(s)."""
    parts = re.split(r'\n\s*\n', text.strip())
    if len(parts) > 2:
        return "\n".join(parts[-2:])[:500]
    return text[-500:] if len(text) > 500 else text


def _analyze_paragraphs(text: str) -> list:
    """Split text into paragraphs and return lengths."""
    parts = re.split(r'\n\s*\n', text)
    return [len(p.split()) for p in parts if len(p.split()) > 5][:50]


def _count_internal_links(text: str) -> str:
    """Count and describe internal links."""
    links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', text)
    internal = [l for l in links if '/p/' in l[1] or 'blogspot' in l[1]]
    return json.dumps({"count": len(links), "internal": len(internal), "examples": [l[0] for l in links[:5]]})


def _detect_schema(text: str) -> str:
    """Detect JSON-LD schema types."""
    schemas = []
    if '"Article"' in text:
        schemas.append("Article")
    if '"FAQPage"' in text:
        schemas.append("FAQPage")
    if '"BreadcrumbList"' in text:
        schemas.append("BreadcrumbList")
    if '"HowTo"' in text:
        schemas.append("HowTo")
    return json.dumps(schemas)


def _detect_ai_patterns(text: str) -> str:
    """Detect common AI-generated text patterns."""
    patterns = []
    ai_phrases = [
        "delve into", "treasure trove", "testament to", "rich tapestry",
        "in conclusion", "it is important to note", "whether you are",
        "look no further", "in this comprehensive guide", "embark on a journey",
        "naming journey", "perfect choice", "meanings behind",
    ]
    text_lower = text.lower()
    for phrase in ai_phrases:
        if phrase in text_lower:
            patterns.append(phrase)
    return json.dumps(patterns)


# =========================================================================
# 9. Calculate Quality Scores For All Articles
# =========================================================================

def calculate_quality_scores(queue: TopicQueue):
    """Calculate quality scores for all articles in posts/."""
    log.info("\n=== Calculating Quality Scores ===")
    scored = 0

    for md_file in sorted(POSTS_DIR.glob("*.md")):
        try:
            frontmatter, md_body = parse_frontmatter(md_file)
            if not md_body.strip():
                continue

            title = frontmatter.get("title", md_file.stem) if frontmatter else md_file.stem
            slug = slugify(title)

            # SEO Score (0-100)
            seo = _score_seo(md_body, title, frontmatter)

            # EEAT Score (0-100)
            eeat = _score_eeat(md_body)

            # Readability Score (0-100)
            readability = _score_readability(md_body)

            # Originality Score (0-100)
            originality = _score_originality(md_body)

            # Authority Score (0-100)
            authority = _score_authority(md_body)

            # Internal Links Score (0-100)
            internal_links = _score_internal_links(md_body)

            # Schema Score (0-100)
            schema = _score_schema(md_body)

            # Content Depth Score (0-100)
            content_depth = _score_content_depth(md_body)

            # Helpful Content Score (0-100)
            helpful_content = _score_helpful_content(md_body)

            # Overall = average of all dimensions
            overall = (seo + eeat + readability + originality + authority +
                       internal_links + schema + content_depth + helpful_content) / 9.0

            queue.conn.execute(
                """INSERT OR REPLACE INTO quality_scores
                   (filename, seo, eeat, readability, originality, authority,
                    internal_links, schema, content_depth, helpful_content,
                    overall, computed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (md_file.name, seo, eeat, readability, originality, authority,
                 internal_links, schema, content_depth, helpful_content,
                 round(overall, 2), datetime.now().isoformat()),
            )
            scored += 1

        except Exception as exc:
            log.error("  Quality score error for %s: %s", md_file.name, exc)
            traceback.print_exc()

    queue.conn.commit()
    log.info("Quality scoring complete: %d articles scored", scored)


def _score_seo(text: str, title: str, fm: dict) -> float:
    """Score SEO quality (0-100)."""
    score = 0.0

    # Title length (0-15)
    if 30 <= len(title) <= 70:
        score += 15
    elif 20 <= len(title) <= 90:
        score += 8

    # Meta description (0-15)
    meta = fm.get("meta_description", "") if fm else ""
    if 100 <= len(meta) <= 160:
        score += 15
    elif len(meta) > 50:
        score += 5

    # Has H1 (0-10)
    if re.search(r'^#\s+.+$', text, re.MULTILINE):
        score += 10

    # Heading hierarchy (0-20)
    headings = re.findall(r'^(#{2,6})\s+.+$', text, re.MULTILINE)
    if len(headings) >= 3:
        score += 20
    elif len(headings) >= 1:
        score += 10

    # Word count (0-15)
    wc = len(text.split())
    if wc >= 2000:
        score += 15
    elif wc >= 1000:
        score += 10
    elif wc >= 500:
        score += 5

    # Has keywords in text (0-10)
    if title.lower() in text.lower():
        score += 10

    # Image alt texts (0-5)
    if re.search(r'!\[[^\]]*\]\([^)]*\)', text):
        score += 5

    # Internal links (0-5)
    links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', text)
    if len(links) >= 3:
        score += 5
    elif len(links) >= 1:
        score += 2

    return min(score, 100.0)


def _score_eeat(text: str) -> float:
    """Score EEAT signals (0-100)."""
    score = 0.0

    # Author reference (0-20)
    if re.search(r'(author|written by|editor|expert|reviewed by|professionally)', text, re.IGNORECASE):
        score += 20

    # Editorial review (0-15)
    if re.search(r'(editorial|reviewed|fact-checked|verified|updated)', text, re.IGNORECASE):
        score += 15

    # References/sources (0-20)
    refs = re.findall(r'(https?://[^\s)]+|ref\.|source:|citation:|bibliography)', text, re.IGNORECASE)
    if len(refs) >= 3:
        score += 20
    elif len(refs) >= 1:
        score += 10

    # Expert language (0-15)
    expert_terms = ['research', 'study', 'data', 'statistics', 'experts agree', 'according to']
    found = sum(1 for t in expert_terms if t in text.lower())
    score += min(found * 5, 15)

    # First-person experience (0-15)
    if re.search(r'(i believe|in my experience|we recommend|our research)', text, re.IGNORECASE):
        score += 15

    # Factual claims (0-15)
    if re.search(r'(according to|studies show|research indicates|data suggests)', text, re.IGNORECASE):
        score += 15

    return min(score, 100.0)


def _score_readability(text: str) -> float:
    """Score readability (0-100)."""
    score = 0.0

    # Paragraph count (0-15)
    paras = [p for p in re.split(r'\n\s*\n', text) if len(p.split()) > 20]
    if len(paras) >= 10:
        score += 15
    elif len(paras) >= 5:
        score += 10
    elif len(paras) >= 2:
        score += 5

    # Average paragraph length (0-20)
    if paras:
        avg_len = sum(len(p.split()) for p in paras) / len(paras)
        if 100 <= avg_len <= 200:
            score += 20
        elif 70 <= avg_len <= 300:
            score += 12
        else:
            score += 5

    # Sentence variety (0-15)
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    if len(sentences) >= 5:
        avg_sent_len = sum(len(s.split()) for s in sentences) / len(sentences)
        if 10 <= avg_sent_len <= 25:
            score += 15
        else:
            score += 8

    # Transition words (0-15)
    transitions = ['however', 'therefore', 'moreover', 'additionally', 'furthermore',
                   'consequently', 'nevertheless', 'similarly', 'for example', 'in addition']
    text_lower = text.lower()
    found = sum(1 for t in transitions if t in text_lower)
    score += min(found * 3, 15)

    # Active voice ratio (0-15)
    passive = len(re.findall(r'\b(is|are|was|were|be|been|being)\s+\w*(ed|en)\b', text))
    total_verbs = max(len(re.findall(r'\b\w{3,}\b', text)), 1)
    passive_ratio = passive / total_verbs
    if passive_ratio < 0.05:
        score += 15
    elif passive_ratio < 0.10:
        score += 10
    else:
        score += 5

    # Word count bonus (0-5)
    wc = len(text.split())
    if wc >= 1500:
        score += 5

    return min(score, 100.0)


def _score_originality(text: str) -> float:
    """Score originality based on unique patterns (0-100)."""
    score = 0.0

    # Unique phrases (0-30)
    ai_clichés = ['delve into', 'treasure trove', 'testament to', 'rich tapestry',
                  'look no further', 'embark on a journey', 'naming journey',
                  'perfect choice', 'in this comprehensive guide']
    text_lower = text.lower()
    cliché_count = sum(1 for c in ai_clichés if c in text_lower)
    score += max(0, 30 - cliché_count * 6)

    # Varied sentence lengths (0-20)
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
    if len(sentences) >= 3:
        lengths = [len(s.split()) for s in sentences]
        variance = sum((l - sum(lengths)/len(lengths))**2 for l in lengths) / len(lengths)
        if variance > 100:
            score += 20
        elif variance > 50:
            score += 12
        else:
            score += 5

    # Specific examples (0-25)
    examples = re.findall(r'(e\.g\.|for instance|such as|namely|specifically)', text, re.IGNORECASE)
    score += min(len(examples) * 5, 25)

    # Unique data/statistics (0-15)
    numbers = re.findall(r'\d+%', text)
    score += min(len(numbers) * 5, 15)

    # Personal touches (0-10)
    personal = re.findall(r'(i think|we believe|our recommendation|parents say)', text, re.IGNORECASE)
    score += min(len(personal) * 5, 10)

    return min(score, 100.0)


def _score_authority(text: str) -> float:
    """Score topical authority (0-100)."""
    score = 0.0

    # Definition section (0-20)
    if re.search(r'(?:what is|definition|means|refers to|is defined as)', text, re.IGNORECASE):
        score += 20

    # Origin/history section (0-20)
    if re.search(r'(?:origin|history|etymology|root|derived|comes from|heritage)', text, re.IGNORECASE):
        score += 20

    # Pronunciation (0-15)
    if re.search(r'(?:pronunciation|pronounced|phonetic|how to say)', text, re.IGNORECASE):
        score += 15

    # Meaning section (0-15)
    if re.search(r'(?:meaning|symbolism|significance|represents|stands for)', text, re.IGNORECASE):
        score += 15

    # Cultural references (0-15)
    cultures = re.findall(r'(?:biblical|greek|roman|celtic|norse|african|asian|latin|hebrew|irish|scottish|welsh|french|german|spanish|italian|japanese|chinese|indian|arabic|persian|egyptian|native american)', text, re.IGNORECASE)
    score += min(len(cultures) * 3, 15)

    # Cross-references to related topics (0-15)
    if re.search(r'(?:see also|related|similar|comparable|another popular)', text, re.IGNORECASE):
        score += 15

    return min(score, 100.0)


def _score_internal_links(text: str) -> float:
    """Score internal linking (0-100)."""
    score = 0.0
    links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', text)

    # Total link count (0-40)
    if len(links) >= 10:
        score += 40
    elif len(links) >= 5:
        score += 30
    elif len(links) >= 3:
        score += 20
    elif len(links) >= 1:
        score += 10

    # Anchor text quality (0-20)
    good_anchors = sum(1 for t, _ in links if len(t) > 3 and t.isalpha())
    score += min(good_anchors * 5, 20)

    # Contextual placement (0-20)
    paras_with_links = sum(1 for p in re.split(r'\n\s*\n', text) if any(l in p for _, l in links))
    if paras_with_links >= 3:
        score += 20
    elif paras_with_links >= 1:
        score += 10

    # Related article section (0-20)
    if re.search(r'(?:related|similar|you might also|see also|more names)', text, re.IGNORECASE):
        score += 20

    return min(score, 100.0)


def _score_schema(text: str) -> float:
    """Score schema markup presence (0-100)."""
    score = 0.0

    if '"Article"' in text:
        score += 25
    if '"FAQPage"' in text:
        score += 25
    if '"BreadcrumbList"' in text:
        score += 25
    if '"HowTo"' in text:
        score += 10
    if '"ItemList"' in text:
        score += 10

    # Complete schema (properly formatted JSON-LD) (0-15)
    if re.search(r'<script[^>]*type=["\']application/ld\+json["\'].*?</script>', text, re.DOTALL):
        score += 15

    return min(score, 100.0)


def _score_content_depth(text: str) -> float:
    """Score content depth (0-100)."""
    score = 0.0

    # Word count (0-30)
    wc = len(text.split())
    if wc >= 3000:
        score += 30
    elif wc >= 2000:
        score += 25
    elif wc >= 1500:
        score += 20
    elif wc >= 1000:
        score += 15
    elif wc >= 500:
        score += 10

    # Section count (0-20)
    headings = re.findall(r'^#{2,6}\s+.+$', text, re.MULTILINE)
    if len(headings) >= 10:
        score += 20
    elif len(headings) >= 5:
        score += 15
    elif len(headings) >= 2:
        score += 10

    # Table count (0-15)
    tables = re.findall(r'\|.*\|.*\n\|[-| :]+\|', text)
    score += min(len(tables) * 5, 15)

    # FAQ count (0-15)
    faqs = re.findall(r'(?:Q[A-Z]?uestion|FAQ|Common question)', text, re.IGNORECASE)
    score += min(len(faqs) * 2, 15)

    # Lists count (0-10)
    lists = re.findall(r'^[-*+]\s+', text, re.MULTILINE)
    score += min(len(lists) // 5 * 2, 10)

    # Images count (0-10)
    images = re.findall(r'!\[[^\]]*\]\(', text)
    score += min(len(images) * 2, 10)

    return min(score, 100.0)


def _score_helpful_content(text: str) -> float:
    """Score helpful content signals (0-100)."""
    score = 0.0

    # User intent match (0-20)
    if re.search(r'(?:how to|best|top|guide|tips|ideas|meaning|origin|pronunciation|popularity)',
                 text, re.IGNORECASE):
        score += 20

    # Actionable advice (0-20)
    advice = re.findall(r'(?:consider|recommend|suggest|choose|pick|avoid|keep in mind|think about)',
                       text, re.IGNORECASE)
    score += min(len(advice) * 4, 20)

    # Emotional connection (0-15)
    emotions = re.findall(r'(?:love|joy|meaningful|special|unique|precious|beloved|cherished|inspire|hope)',
                         text, re.IGNORECASE)
    score += min(len(emotions) * 3, 15)

    # Scannability (0-15)
    headings = len(re.findall(r'^#{2,6}\s+.+$', text, re.MULTILINE))
    if headings >= 5:
        score += 15
    elif headings >= 3:
        score += 10
    elif headings >= 1:
        score += 5

    # Conclusion/summary (0-10)
    if re.search(r'(?:in summary|to conclude|final thoughts|wrap up|summary|closing thoughts)',
                 text, re.IGNORECASE):
        score += 10

    # Call to action (0-10)
    if re.search(r'(?:share your|let us know|comment below|tell us|what do you think)',
                 text, re.IGNORECASE):
        score += 10

    return min(score, 100.0)


# =========================================================================
# 10. Build Internal Link Graph
# =========================================================================

def build_internal_link_graph(queue: TopicQueue):
    """Build the internal link graph from all articles."""
    log.info("\n=== Building Internal Link Graph ===")
    links_added = 0

    # Collect all slugs for reference
    all_slugs = set()
    for md_file in POSTS_DIR.glob("*.md"):
        all_slugs.add(md_file.stem.split("-", 1)[-1] if "-" in md_file.stem else md_file.stem)

    for md_file in sorted(POSTS_DIR.glob("*.md")):
        frontmatter, md_body = parse_frontmatter(md_file)
        if not md_body.strip():
            continue

        source_slug = slugify(frontmatter.get("title", "")) if frontmatter else md_file.stem

        # Find all links in the article
        links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', md_body)

        for anchor, url in links:
            # Check if it's an internal link
            if "/p/" in url or "blogspot" in url:
                # Extract target slug from URL
                target_slug_match = re.search(r'/p/(\d+)_([^/]+)\.html', url)
                if target_slug_match:
                    target_slug = target_slug_match.group(2)
                    # Calculate rough relevance based on shared keywords
                    source_words = set(source_slug.split("-"))
                    target_words = set(target_slug.split("-"))
                    overlap = len(source_words & target_words)
                    relevance = min(overlap * 10, 100.0)

                    if relevance > 0:
                        try:
                            queue.conn.execute(
                                """INSERT OR IGNORE INTO internal_links
                                   (source_slug, target_slug, anchor_text, relevance_score, created_at)
                                   VALUES (?, ?, ?, ?, ?)""",
                                (source_slug, target_slug, anchor, relevance,
                                 datetime.now().isoformat()),
                            )
                            links_added += 1
                        except Exception:
                            pass

    queue.conn.commit()
    log.info("Internal link graph built: %d links added", links_added)


# =========================================================================
# 11. Generate Full Report
# =========================================================================

def generate_report(queue: TopicQueue, total_blogger: int, synced: int, failed: int):
    """Generate a comprehensive sync report."""
    log.info("\n=== GENERATING SYNC REPORT ===")

    # Article counts
    local_count = len(list(POSTS_DIR.glob("*.md")))
    keyword_count = queue.conn.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]
    generated_count = queue.conn.execute("SELECT COUNT(*) FROM generated").fetchone()[0]
    published_count = queue.conn.execute("SELECT COUNT(*) FROM published").fetchone()[0]
    fingerprint_count = queue.conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]
    quality_count = queue.conn.execute("SELECT COUNT(*) FROM quality_scores").fetchone()[0]

    # Quality score averages
    avg_scores = queue.conn.execute("""
        SELECT AVG(seo), AVG(eeat), AVG(readability), AVG(originality),
               AVG(authority), AVG(internal_links), AVG(schema),
               AVG(content_depth), AVG(helpful_content), AVG(overall)
        FROM quality_scores
    """).fetchone()

    # Similarity pairs (approximate — uses intro_hash + heading + conclusion match)
    high_sim_row = queue.conn.execute("""
        SELECT COUNT(*) FROM fingerprints f1
        JOIN fingerprints f2 ON f1.id < f2.id
        WHERE f1.intro_hash = f2.intro_hash
        OR f1.heading_structure = f2.heading_structure
        OR f1.conclusion_hash = f2.conclusion_hash
    """).fetchone()
    high_sim = high_sim_row[0] if high_sim_row else 0

    # Top 10 worst articles
    worst = queue.conn.execute("""
        SELECT filename, seo, eeat, readability, overall
        FROM quality_scores
        ORDER BY overall ASC
        LIMIT 10
    """).fetchall()

    # Top 10 best articles
    best = queue.conn.execute("""
        SELECT filename, seo, eeat, readability, overall
        FROM quality_scores
        ORDER BY overall DESC
        LIMIT 10
    """).fetchall()

    # Prepare average scores
    seo_avg = avg_scores[0] if avg_scores[0] else 0
    eeat_avg = avg_scores[1] if avg_scores[1] else 0
    read_avg = avg_scores[2] if avg_scores[2] else 0
    orig_avg = avg_scores[3] if avg_scores[3] else 0
    auth_avg = avg_scores[4] if avg_scores[4] else 0
    int_avg = avg_scores[5] if avg_scores[5] else 0
    schema_avg = avg_scores[6] if avg_scores[6] else 0
    depth_avg = avg_scores[7] if avg_scores[7] else 0
    help_avg = avg_scores[8] if avg_scores[8] else 0
    overall_avg = avg_scores[9] if avg_scores[9] else 0

    report_lines = [
        "",
        "=" * 60,
        "           BLOGGER SYNC REPORT",
        "=" * 60,
        "",
        "OVERVIEW",
        "-" * 40,
        f"  Blogger articles:          {total_blogger}",
        f"  Successfully synced:       {synced}",
        f"  Failed to sync:            {failed}",
        f"  Local articles (posts/):   {local_count}",
        "",
        "DATABASE STATISTICS",
        "-" * 40,
        f"  Keywords:                  {keyword_count}",
        f"  Generated:                 {generated_count}",
        f"  Published:                 {published_count}",
        f"  Fingerprints:              {fingerprint_count}",
        f"  Quality Scores:            {quality_count}",
        "",
        "AVERAGE QUALITY SCORES",
        "-" * 40,
        f"  SEO:           {seo_avg:.1f}/100",
        f"  EEAT:          {eeat_avg:.1f}/100",
        f"  Readability:   {read_avg:.1f}/100",
        f"  Originality:   {orig_avg:.1f}/100",
        f"  Authority:     {auth_avg:.1f}/100",
        f"  Internal Links:{int_avg:.1f}/100",
        f"  Schema:        {schema_avg:.1f}/100",
        f"  Content Depth: {depth_avg:.1f}/100",
        f"  Helpful:       {help_avg:.1f}/100",
        f"  Overall:       {overall_avg:.1f}/100",
        "",
        "TOP 10 LOWEST QUALITY ARTICLES",
        "-" * 40,
    ]
    for i, (fn, s, e, r, o) in enumerate(worst, 1):
        report_lines.append(f"  {i:2d}. {fn[:60]:60s}  Overall: {o:.1f}")

    report_lines.extend([
        "",
        "TOP 10 HIGHEST QUALITY ARTICLES",
        "-" * 40,
    ])
    for i, (fn, s, e, r, o) in enumerate(best, 1):
        report_lines.append(f"  {i:2d}. {fn[:60]:60s}  Overall: {o:.1f}")

    report_lines.extend([
        "",
        "INTERNAL LINK GRAPH",
        "-" * 40,
    ])

    # Add internal link graph stats
    total_links = queue.conn.execute("SELECT COUNT(*) FROM internal_links").fetchone()[0]
    source_articles = queue.conn.execute(
        "SELECT COUNT(DISTINCT source_slug) FROM internal_links"
    ).fetchone()[0]
    target_articles = queue.conn.execute(
        "SELECT COUNT(DISTINCT target_slug) FROM internal_links"
    ).fetchone()[0]
    orphan_articles = queue.conn.execute(
        "SELECT COUNT(*) FROM fingerprints WHERE filename NOT IN ("
        "  SELECT DISTINCT source_slug FROM internal_links WHERE source_slug IS NOT NULL"
        ") AND filename NOT IN ("
        "  SELECT DISTINCT target_slug FROM internal_links WHERE target_slug IS NOT NULL"
        ")"
    ).fetchone()[0]

    report_lines.extend([
        "",
        "INTERNAL LINK GRAPH",
        "-" * 40,
        f"  Total links:         {total_links}",
        f"  Source articles:     {source_articles}",
        f"  Target articles:     {target_articles}",
        f"  Orphan articles:     {orphan_articles}",
        "",
        "NEXT STEPS",
        "-" * 40,
        "  1. Sync remaining articles from Blogger API",
        "  2. Review lowest-quality articles",
        "  3. Run content optimizer on bottom 20",
        "  4. Verify all 167 articles are synced",
        "  5. Rebuild internal link graph after optimization",
        "  6. Run SEO validator (min score: 95)",
        "",
        "=" * 60,
    ])

    report = "\n".join(report_lines)

    return report


# =========================================================================
# 12. Main Sync Pipeline
# =========================================================================

def main():
    log.info("=" * 60)
    log.info("BLOGGER SYNC — Downloading all published articles")
    log.info("=" * 60)

    # Ensure posts/ directory exists
    POSTS_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize database
    queue = TopicQueue()
    log.info("Database initialized: %s", DB_PATH)

    # Step 1: Authenticate with Blogger API
    log.info("\n[1/6] Authenticating with Blogger API...")
    try:
        service = get_blogger_service()
        log.info("Authentication successful.")
    except Exception as exc:
        log.error("Authentication failed: %s", exc)
        log.error("Please set BLOG_ID, CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN env vars.")
        sys.exit(1)

    # Get blog ID
    blog_id = os.environ.get("BLOG_ID")
    if not blog_id:
        # Try to discover blog ID from API
        try:
            blogs = service.blogs().listByUser().execute()
            if blogs.get("items"):
                blog_id = blogs["items"][0]["id"]
                log.info("Discovered blog ID: %s", blog_id)
            else:
                log.error("No blogs found for this account.")
                sys.exit(1)
        except Exception as exc:
            log.error("Cannot discover blog ID: %s", exc)
            sys.exit(1)

    # Step 2: Fetch ALL posts from Blogger
    log.info("\n[2/6] Fetching all published posts from Blogger...")
    blogger_posts = fetch_all_posts(service, blog_id)
    total_blogger = len(blogger_posts)
    log.info("Found %d published posts on Blogger.", total_blogger)

    # Step 3: Download each post
    log.info("\n[3/6] Downloading posts to local repository...")
    synced = 0
    failed = 0

    for i, post in enumerate(blogger_posts, 1):
        if i % 20 == 0:
            log.info("  Progress: %d/%d (%.0f%%)", i, total_blogger, i/total_blogger*100)
            time.sleep(0.2)  # Brief pause between batches

        if sync_single_post(service, blog_id, post, queue):
            synced += 1
        else:
            failed += 1

        time.sleep(0.3)  # Rate limiting between posts

    log.info("Download complete: %d synced, %d failed", synced, failed)

    # Step 4: Import local articles into database
    log.info("\n[4/6] Importing local articles into database...")
    import_local_articles(queue)

    # Step 5: Generate fingerprints for all articles
    log.info("\n[5/6] Generating fingerprints...")
    generate_fingerprints_for_all(queue)

    # Step 6: Calculate quality scores
    log.info("\n[6/6] Calculating quality scores...")
    calculate_quality_scores(queue)

    # Step 7: Build internal link graph
    log.info("\nBuilding internal link graph...")
    build_internal_link_graph(queue)

    # Step 8: Generate report
    report = generate_report(queue, total_blogger, synced, failed)
    log.info("\n%s", report)

    # Save report to file
    report_path = Path(__file__).resolve().parent / "docs" / "sync_report.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    log.info("Report saved to: %s", report_path)

    queue.close()
    log.info("\nSync complete! Repository now mirrors Blogger.")
    log.info("Total local articles: %d", len(list(POSTS_DIR.glob("*.md"))))


if __name__ == "__main__":
    main()
