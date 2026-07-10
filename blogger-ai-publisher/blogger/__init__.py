"""Blogger Publisher Engine v1.0 — production-ready publishing pipeline.

The Publisher Engine publishes one article (with one generated hero image)
to Google Blogger through the official API v3.

Pipeline
--------
::

    Article (from database)
      │
      ▼
    Publisher.publish_article(article_id)
      │
      ├─► Load article + image from DB/files
      ├─► Slug.generate()              — SEO-friendly URL
      ├─► Labels.generate()            — automatic label selection
      ├─► HtmlBuilder.build()          — full article HTML
      ├─► Auth.refresh_token()         — OAuth2 access token
      ├─► Client.create_post()         — Blogger API v3 POST
      │     ├─► Retry on 429/5xx (exponential backoff)
      │     └─► Max 3 attempts
      ├─► ImageUploader.upload()       — Insert image into post
      ├─► DB update                    — blogger_post_id, URL, status
      └─► Move article to published/   — archive
"""

from __future__ import annotations

from blogger.publisher import Publisher

__all__ = ["Publisher"]
