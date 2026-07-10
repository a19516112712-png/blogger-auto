"""Article HTML builder for Blogger publishing.

Automatically converts article content (Markdown + metadata) into a
complete, well-structured HTML document suitable for Blogger.

Structure
--------
::

    <article>
      <img> (hero image, immediately below H1)
      <h1> Title
      <div class="article-intro"> Introduction
      <div class="toc"> Table of Contents
      <div class="article-body"> Main content with H2/H3
      <div class="article-faq"> FAQ section
      <div class="article-conclusion"> Conclusion
      <div class="author-box"> Author metadata
    </article>
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import markdown

from config.logging import get_logger
from config.settings import BLOG_URL

log = get_logger(__name__)


class HtmlBuildError(Exception):
    """Raised when HTML building fails."""


def build_article_html(
    title: str,
    content_markdown: str,
    meta_description: str = "",
    hero_image_path: str = "",
    hero_alt: str = "",
    hero_caption: str = "",
    hero_width: int = 0,
    hero_height: int = 0,
    slug: str = "",
    labels: list[str] | None = None,
) -> str:
    """Convert article data to a complete HTML document for Blogger.

    Args:
        title:              Article H1 title.
        content_markdown:   Full article content in Markdown.
        meta_description:   SEO meta description.
        hero_image_path:    Filesystem path to the hero image (local).
        hero_alt:           Alt text for the hero image.
        hero_caption:       Caption for the hero image.
        hero_width:         Hero image width in pixels.
        hero_height:        Hero image height in pixels.
        slug:               URL slug for internal links.
        labels:             List of label strings.

    Returns:
        A complete HTML string ready for the Blogger API.

    Raises:
        HtmlBuildError: If required inputs are missing.
    """
    if not title:
        raise HtmlBuildError("Article title is required for HTML building")
    if not content_markdown:
        raise HtmlBuildError("Article content is required for HTML building")

    # Convert Markdown to HTML
    body_html = _markdown_to_html(content_markdown)

    # Parse sections
    sections = _parse_sections(title, body_html, meta_description)

    # Build complete HTML
    html = _assemble_html(
        title=title,
        hero_image_path=hero_image_path,
        hero_alt=hero_alt,
        hero_caption=hero_caption,
        hero_width=hero_width,
        hero_height=hero_height,
        sections=sections,
        slug=slug,
        labels=labels or [],
        meta_description=meta_description,
        body_html=body_html,
        published_at="",
    )

    return html


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _markdown_to_html(md: str) -> str:
    """Convert Markdown to sanitized HTML.

    Args:
        md: Raw Markdown string.

    Returns:
        HTML string.
    """
    try:
        html = markdown.markdown(
            md,
            extensions=[
                "markdown.extensions.extra",
                "markdown.extensions.codehilite",
                "markdown.extensions.toc",
                "markdown.extensions.smarty",
            ],
            output_format="html5",
        )
        return html
    except Exception as exc:
        raise HtmlBuildError(f"Markdown conversion failed: {exc}") from exc


def _parse_sections(
    title: str,
    body_html: str,
    meta_description: str,
) -> dict[str, str]:
    """Split the full HTML into introduction, body, FAQ, and conclusion sections.

    Uses heading markers (``<h2>FAQ</h2>``, ``<h2>Conclusion</h2>``) as
    delimiters.  If no FAQ/conclusion heading is found, treats everything
    as the body.

    Args:
        title:            Article title.
        body_html:        Full HTML from Markdown conversion.
        meta_description: Meta description.

    Returns:
        A dict with keys ``introduction``, ``body``, ``faq``, ``conclusion``.
    """
    sections: dict[str, str] = {
        "introduction": "",
        "body": "",
        "faq": "",
        "conclusion": "",
        "toc_items": "",
    }

    # Locate section boundaries by heading text
    faq_pos = _find_heading_pos(body_html, "FAQ")
    conclusion_pos = _find_heading_pos(body_html, "Conclusion")

    if faq_pos is not None:
        sections["introduction"] = body_html[:faq_pos]
        if conclusion_pos is not None and conclusion_pos > faq_pos:
            sections["faq"] = body_html[faq_pos:conclusion_pos]
            sections["conclusion"] = body_html[conclusion_pos:]
        else:
            sections["faq"] = body_html[faq_pos:]
    elif conclusion_pos is not None:
        sections["introduction"] = body_html[:conclusion_pos]
        sections["conclusion"] = body_html[conclusion_pos:]
    else:
        sections["introduction"] = body_html
        sections["body"] = body_html

    # Remaining body (everything that's not FAQ or conclusion)
    if sections["introduction"]:
        sections["body"] = _extract_body(sections["introduction"])

    # Generate table of contents items
    sections["toc_items"] = _generate_toc(body_html)

    return sections


def _find_heading_pos(html: str, heading_text: str) -> int | None:
    """Find the position of an H2 heading with specific text.

    Args:
        html:         HTML string to search.
        heading_text: Text inside the heading to match (case-insensitive).

    Returns:
        Byte offset or ``None``.
    """
    pattern = re.compile(
        r"<h2[^>]*>\s*" + re.escape(heading_text) + r"\s*</h2>",
        re.IGNORECASE,
    )
    match = pattern.search(html)
    return match.start() if match else None


def _extract_body(intro_html: str) -> str:
    """Split introduction into body text (everything except the first paragraph).

    Args:
        intro_html: HTML containing the introduction.

    Returns:
        The HTML after the first paragraph.
    """
    # Find the first closing </p> tag and return everything after it
    match = re.search(r"</p>", intro_html)
    if match:
        return intro_html[match.end():]
    return intro_html


def _generate_toc(html: str) -> str:
    """Generate table of contents items from H2 headings.

    Args:
        html: Full article HTML.

    Returns:
        An HTML unordered list of H2 headings, excluding FAQ and Conclusion.
    """
    headings = re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.IGNORECASE)
    items: list[str] = []
    for h in headings:
        # Strip HTML tags from heading text
        text = re.sub(r"<[^>]+>", "", h).strip()
        # Skip FAQ, Conclusion, and Table of Contents
        if text.lower() in ("faq", "conclusion", "table of contents", ""):
            continue
        anchor = text.lower().replace(" ", "-").replace("?", "")
        anchor = re.sub(r"[^a-z0-9-]", "", anchor)
        items.append(f'<li><a href="#{anchor}">{text}</a></li>')

    if not items:
        return ""
    return "<ul>\n" + "\n".join(items) + "\n</ul>"


# ---------------------------------------------------------------------------
# JSON-LD structured data (Schema.org)
# ---------------------------------------------------------------------------


def _build_json_ld(
    title: str,
    slug: str,
    meta_description: str,
    body_html: str,
    hero_image_path: str = "",
    hero_alt: str = "",
    published_at: str = "",
    labels: list[str] | None = None,
) -> str:
    """Build JSON-LD structured data script block.

    Generates ``Article``, ``BreadcrumbList``, ``FAQPage``, ``Organization``,
    and ``WebSite`` schema in a single ``application/ld+json`` block.

    Args:
        title:            Article title.
        slug:             URL slug.
        meta_description: Meta description.
        body_html:        Full article HTML (used to extract FAQ).
        hero_image_path:  Hero image URL.
        hero_alt:         Hero image alt text.
        published_at:     ISO publish timestamp.
        labels:           Article labels.

    Returns:
        A ``<script>`` tag containing JSON-LD.
    """
    from config.settings import BLOG_URL

    import json
    import re

    site_url = BLOG_URL.rstrip("/")
    article_url = f"{site_url}/{slug}" if slug else site_url
    today = published_at or __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d")

    # Build the schema graph
    schema: dict = {
        "@context": "https://schema.org",
        "@graph": [
            # --- WebSite ---
            {
                "@type": "WebSite",
                "@id": f"{site_url}/#website",
                "url": site_url,
                "name": "Baby Name Ideas",
                "description": "Discover Beautiful Baby Names From Around The World",
                "publisher": {"@id": f"{site_url}/#organization"},
            },
            # --- Organization ---
            {
                "@type": "Organization",
                "@id": f"{site_url}/#organization",
                "name": "Baby Name Ideas",
                "url": site_url,
                "logo": {
                    "@type": "ImageObject",
                    "url": f"{site_url}/favicon.ico",
                },
            },
            # --- BreadcrumbList ---
            {
                "@type": "BreadcrumbList",
                "@id": f"{article_url}/#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": site_url},
                    {"@type": "ListItem", "position": 2, "name": title, "item": article_url},
                ],
            },
            # --- Article ---
            {
                "@type": "Article",
                "@id": f"{article_url}/#article",
                "headline": title,
                "description": meta_description or title,
                "url": article_url,
                "mainEntityOfPage": article_url,
                "datePublished": today,
                "dateModified": today,
                "author": {
                    "@type": "Organization",
                    "name": "Baby Name Ideas",
                    "url": site_url,
                },
                "publisher": {"@id": f"{site_url}/#organization"},
            },
        ],
    }

    # Add image if present
    if hero_image_path:
        schema["@graph"][3]["image"] = {
            "@type": "ImageObject",
            "url": hero_image_path,
            "caption": hero_alt or title,
        }

    # --- FAQPage (extracted from the HTML) ---
    faq_entries = _extract_faq_from_html(body_html)
    if faq_entries:
        schema["@graph"].append({
            "@type": "FAQPage",
            "@id": f"{article_url}/#faq",
            "mainEntity": faq_entries,
        })

    json_str = json.dumps(schema, ensure_ascii=False, indent=2)
    return f"<script type=\"application/ld+json\">\n{json_str}\n</script>"


def _extract_faq_from_html(html: str) -> list[dict[str, object]]:
    """Extract FAQ entries from HTML content.

    Supports two common structures produced by Markdown FAQ sections:

    1. ``<p><strong>Question?</strong></p>``\n``<p>Answer.</p>``
    2. ``<h3>Q: Question?</h3>``\n``<p>Answer.</p>``

    Args:
        html: Full article HTML.

    Returns:
        List of dicts with ``@type``, ``name``, ``acceptedAnswer``.
    """
    import re as _re

    entries: list[dict[str, object]] = []

    # Strategy: find <h2>FAQ</h2> section, then find Q/A pairs within.
    # Pattern 1: <p><strong>question</strong></p><p>answer</p>
    # Pattern 2: <h3>Q: question</h3><p>answer</p>

    # First, isolate the FAQ section
    faq_match = _re.search(
        r"<h2[^>]*>\s*FAQ\s*</h2>(.*?)(?=<h2[^>]*>|$)",
        html,
        _re.IGNORECASE | _re.DOTALL,
    )
    if not faq_match:
        return entries

    faq_html = faq_match.group(1)

    # Pattern: <p><strong>question</strong></p>\n<p>answer</p>
    pattern1 = _re.compile(
        r"<p[^>]*>\s*<strong[^>]*>(.*?)</strong>\s*</p>\s*"
        r"<p[^>]*>(.*?)</p>",
        _re.IGNORECASE | _re.DOTALL,
    )

    for match in pattern1.finditer(faq_html):
        _add_faq_entry(entries, match.group(1), match.group(2))

    # Pattern 2: <h3>Q: question</h3>\n<p>answer</p>
    pattern2 = _re.compile(
        r"<h3[^>]*>\s*(?:Q\s*[\d.]*\s*[:.-]?\s*)?(.*?)</h3>\s*"
        r"<p[^>]*>(.*?)</p>",
        _re.IGNORECASE | _re.DOTALL,
    )

    for match in pattern2.finditer(faq_html):
        _add_faq_entry(entries, match.group(1), match.group(2))

    return entries


def _add_faq_entry(
    entries: list[dict[str, object]],
    question_html: str,
    answer_html: str,
) -> None:
    """Clean and append a FAQ entry if valid.

    Args:
        entries:        Mutable list to append to.
        question_html:  Raw HTML containing the question.
        answer_html:    Raw HTML containing the answer.
    """
    import re as _re
    question = _re.sub(r"<[^>]+>", "", question_html).strip()
    answer = _re.sub(r"<[^>]+>", "", answer_html).strip()
    if question and answer:
        entries.append({
            "@type": "Question",
            "name": question,
            "acceptedAnswer": {
                "@type": "Answer",
                "text": answer,
            },
        })


def _assemble_html(
    title: str,
    hero_image_path: str,
    hero_alt: str,
    hero_caption: str,
    hero_width: int,
    hero_height: int,
    sections: dict[str, str],
    slug: str,
    labels: list[str],
    meta_description: str = "",
    body_html: str = "",
    published_at: str = "",
) -> str:
    """Assemble the final HTML document.

    Args:
        title:       Article title.
        hero_image_path: Path to hero image (local or URL).
        sections:    Parsed HTML sections.
        slug:        URL slug.
        labels:      Article labels.

    Returns:
        Complete HTML string.
    """
    parts: list[str] = []

    # Title (H1) — main heading
    parts.append(f"<h1>{_escape_html(title)}</h1>")

    # Hero image (immediately after H1)
    if hero_image_path:
        parts.append(_hero_image_html(
            path=hero_image_path,
            alt=hero_alt,
            caption=hero_caption,
            width=hero_width,
            height=hero_height,
        ))

    # Table of Contents
    if sections.get("toc_items"):
        toc = (
            '<div class="table-of-contents">\n'
            "<h2>Table of Contents</h2>\n"
            f'{sections["toc_items"]}\n'
            "</div>\n"
        )
        parts.append(toc)

    # Introduction
    if sections.get("introduction"):
        parts.append(
            '<div class="article-introduction">\n'
            f'{sections["introduction"]}\n'
            "</div>\n"
        )

    # Body
    if sections.get("body"):
        parts.append(
            '<div class="article-body">\n'
            f'{sections["body"]}\n'
            "</div>\n"
        )

    # FAQ
    if sections.get("faq"):
        parts.append(
            '<div class="article-faq">\n'
            f'{sections["faq"]}\n'
            "</div>\n"
        )

    # Conclusion
    if sections.get("conclusion"):
        parts.append(
            '<div class="article-conclusion">\n'
            f'{sections["conclusion"]}\n'
            "</div>\n"
        )

    # Author Box
    parts.append(_author_box_html())

    # JSON-LD structured data
    json_ld = _build_json_ld(
        title=title,
        slug=slug,
        meta_description=meta_description,
        body_html=body_html or " ".join(parts),
        hero_image_path=hero_image_path,
        hero_alt=hero_alt,
        published_at=published_at,
        labels=labels,
    )
    parts.append(json_ld)

    return "\n".join(parts)


def _hero_image_html(
    path: str,
    alt: str,
    caption: str,
    width: int,
    height: int,
) -> str:
    """Generate the hero image HTML block.

    Args:
        path:   Image path or URL.
        alt:    Alt text.
        caption: Image caption.
        width:  Width in pixels.
        height: Height in pixels.

    Returns:
        HTML string for the hero image.
    """
    lazy = 'loading="lazy"'
    dims = f'width="{width}" height="{height}"' if width and height else ""
    alt_attr = _escape_html(alt) if alt else "Hero image"

    img = (
        f'<div class="hero-image">\n'
        f'  <img src="{_escape_html(path)}" alt="{alt_attr}" {dims} {lazy} />\n'
    )
    if caption:
        img += f'  <figcaption class="image-caption">{_escape_html(caption)}</figcaption>\n'
    img += "</div>\n"
    return img


def _author_box_html() -> str:
    """Generate the author box HTML.

    Returns:
        HTML string for the author box section.
    """
    return (
        '<div class="author-box">\n'
        '  <p><strong>About the Author</strong></p>\n'
        "  <p>"
        "Baby Name Ideas is your trusted resource for discovering "
        "beautiful baby names from around the world. "
        "We help parents find meaningful names with rich cultural "
        "backgrounds."
        '</p>\n'
        f'  <p><a href="{_escape_html(BLOG_URL)}">Baby Name Ideas</a></p>\n'
        "</div>\n"
    )


def _escape_html(text: str) -> str:
    """Escape HTML special characters for safe embedding.

    Args:
        text: Raw string to escape.

    Returns:
        HTML-escaped string.
    """
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
