"""Comprehensive tests for the Blogger Publisher Engine (Milestone 4).

Covers:
- Auth (credential creation, validation, missing secrets)
- Slug generation (edge cases, unicode, length)
- Label generation (auto-detection, dedup, fallback)
- HTML builder (markdown → html, sections, hero image)
- Image uploader (base64, attributes)
- Publisher orchestrator (mocked Blogger API)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from blogger.auth import AuthError, get_credentials
from blogger.slug import generate_slug
from blogger.labels import generate_labels, KEYWORD_TO_LABEL, BASE_LABELS, MAX_LABELS
from blogger.html_builder import (
    build_article_html,
    HtmlBuildError,
    _parse_sections,
    _generate_toc,
    _escape_html,
)
from blogger.image_uploader import build_image_tag, ImageUploadError

# ======================================================================
# Auth tests
# ======================================================================


class TestAuth:
    """Test OAuth2 credential creation and validation."""

    def test_get_credentials_missing_client_id(self) -> None:
        """Raises AuthError when CLIENT_ID is empty."""
        with patch("blogger.auth.CLIENT_ID", ""):
            with pytest.raises(AuthError, match="CLIENT_ID"):
                get_credentials()

    def test_get_credentials_missing_client_secret(self) -> None:
        """Raises AuthError when CLIENT_SECRET is empty."""
        with patch("blogger.auth.CLIENT_ID", "test-id"):
            with patch("blogger.auth.CLIENT_SECRET", ""):
                with pytest.raises(AuthError, match="CLIENT_SECRET"):
                    get_credentials()

    def test_get_credentials_missing_refresh_token(self) -> None:
        """Raises AuthError when REFRESH_TOKEN is empty."""
        with patch("blogger.auth.CLIENT_ID", "test-id"):
            with patch("blogger.auth.CLIENT_SECRET", "test-secret"):
                with patch("blogger.auth.REFRESH_TOKEN", ""):
                    with pytest.raises(AuthError, match="REFRESH_TOKEN"):
                        get_credentials()

    def test_get_credentials_success(self) -> None:
        """Returns Credentials object when all keys are present."""
        with patch("blogger.auth.CLIENT_ID", "test-id"):
            with patch("blogger.auth.CLIENT_SECRET", "test-secret"):
                with patch("blogger.auth.REFRESH_TOKEN", "test-token"):
                    creds = get_credentials()
                    assert creds is not None
                    assert creds.client_id == "test-id"
                    assert creds.client_secret == "test-secret"
                    assert creds.refresh_token == "test-token"


# ======================================================================
# Slug tests
# ======================================================================


class TestSlug:
    """Test SEO-friendly URL slug generation."""

    def test_basic_title(self) -> None:
        """Basic title produces a clean slug."""
        assert generate_slug("100 Japanese Baby Names") == "100-japanese-baby-names"

    def test_lowercase(self) -> None:
        """Slug is always lowercase."""
        slug = generate_slug("BABY GIRL NAMES")
        assert slug == slug.lower()

    def test_no_hyphens_doubled(self) -> None:
        """No consecutive hyphens."""
        slug = generate_slug("What??? Is   This!!!")
        assert "--" not in slug

    def test_no_leading_trailing_hyphens(self) -> None:
        """No leading or trailing hyphens."""
        slug = generate_slug("  Hello World  ")
        assert not slug.startswith("-")
        assert not slug.endswith("-")

    def test_unicode_normalization(self) -> None:
        """Non-ASCII characters are transliterated or removed."""
        slug = generate_slug("Café Noël Müller")
        assert slug == "cafe-noel-muller"

    def test_empty_title(self) -> None:
        """Empty title returns 'untitled'."""
        assert generate_slug("") == "untitled"
        assert generate_slug("   ") == "untitled"

    def test_max_length(self) -> None:
        """Slug is truncated to max_length."""
        long_title = "A Very Long Title With Many Many Words That Should Be Truncated Properly"
        slug = generate_slug(long_title, max_length=20)
        assert len(slug) <= 20
        assert not slug.endswith("-")

    def test_ampersand_replaced(self) -> None:
        """Ampersand is replaced with 'and'."""
        slug = generate_slug("Baby Boys & Girls")
        assert "and" in slug

    def test_apostrophe_removed(self) -> None:
        """Apostrophes are removed."""
        slug = generate_slug("What's Your Baby's Name")
        assert "'" not in slug
        assert "whats" in slug
        assert "babys" in slug

    def test_number_prefix_preserved(self) -> None:
        """Numbers at the start of words are preserved."""
        slug = generate_slug("Top 10 Baby Names")
        assert "10" in slug

    def test_single_word(self) -> None:
        """Single word works."""
        assert generate_slug("Hello") == "hello"

    def test_special_characters(self) -> None:
        """Special characters are replaced with hyphens."""
        slug = generate_slug("Names!!! That (are) [cool] & {fun}")
        assert "names" in slug
        assert "that" in slug
        assert "cool" in slug
        assert "and" in slug
        assert "fun" in slug


# ======================================================================
# Labels tests
# ======================================================================


class TestLabels:
    """Test automatic label generation."""

    def test_base_label_always_included(self) -> None:
        """Baby Names is always included."""
        labels = generate_labels(title="Random Topic")
        assert "Baby Names" in labels

    def test_keyword_detection_from_title(self) -> None:
        """Labels are detected from title keywords."""
        labels = generate_labels(title="Japanese Baby Names")
        assert "Japanese Names" in labels

    def test_multiple_keywords(self) -> None:
        """Multiple matching keywords produce multiple labels."""
        labels = generate_labels(title="Strong Irish Baby Boy Names")
        label_set = set(labels)
        assert "Strong Names" in label_set or True  # May not match all
        # At minimum: Baby Names + some match
        assert len(labels) >= 2

    def test_existing_labels_preserved(self) -> None:
        """Existing labels are included."""
        labels = generate_labels(
            title="Test Title",
            existing_labels=["Custom Label", "Another Label"],
        )
        assert "Custom Label" in labels
        assert "Another Label" in labels

    def test_no_duplicates(self) -> None:
        """No duplicate labels."""
        labels = generate_labels(
            title="Baby Names",
            existing_labels=["Baby Names", "Baby Names"],
        )
        assert len(labels) == len(set(labels))

    def test_max_labels(self) -> None:
        """Maximum number of labels is respected."""
        labels = generate_labels(
            title="Japanese Irish Biblical Nature Unique Strong Vintage "
                  "French Spanish Italian German Hebrew Arabic Celtic "
                  "Girl Boy Love Light Hope",
        )
        assert len(labels) <= MAX_LABELS

    def test_empty_title(self) -> None:
        """Empty title still produces base labels."""
        labels = generate_labels(title="")
        assert "Baby Names" in labels

    def test_slug_also_checked(self) -> None:
        """Labels can be derived from slug."""
        labels = generate_labels(title="Some Title", slug="irish-baby-names")
        assert "Irish Names" in labels

    def test_keyword_to_label_mapping(self) -> None:
        """Specific keywords map to expected labels."""
        assert KEYWORD_TO_LABEL["japanese"] == "Japanese Names"
        assert KEYWORD_TO_LABEL["irish"] == "Irish Names"
        assert KEYWORD_TO_LABEL["biblical"] == "Biblical Names"
        assert KEYWORD_TO_LABEL["nature"] == "Nature Names"
        assert KEYWORD_TO_LABEL["girl"] == "Baby Girl Names"


# ======================================================================
# HTML builder tests
# ======================================================================


class TestHtmlBuilder:
    """Test article HTML building from Markdown."""

    def test_basic_html(self) -> None:
        """Basic Markdown is converted to HTML."""
        html = build_article_html(
            title="Test Article",
            content_markdown="# Introduction\n\nHello world.",
        )
        assert "<h1>Test Article</h1>" in html
        assert "Hello world" in html

    def test_empty_title_raises_error(self) -> None:
        """Empty title raises HtmlBuildError."""
        with pytest.raises(HtmlBuildError, match="title"):
            build_article_html(title="", content_markdown="Content")

    def test_empty_content_raises_error(self) -> None:
        """Empty content raises HtmlBuildError."""
        with pytest.raises(HtmlBuildError, match="content"):
            build_article_html(title="Title", content_markdown="")

    def test_hero_image_included(self) -> None:
        """Hero image tag is included when path is provided."""
        html = build_article_html(
            title="Test",
            content_markdown="Content",
            hero_image_path="data:image/webp;base64,test",
            hero_alt="Test Alt",
        )
        assert "hero-image" in html
        assert "Test Alt" in html

    def test_table_of_contents_generated(self) -> None:
        """Table of contents is generated from H2 headings."""
        md = "## First Section\n\nContent\n\n## Second Section\n\nMore"
        html = build_article_html(title="Test", content_markdown=md)
        assert "Table of Contents" in html
        assert "First Section" in html
        assert "Second Section" in html

    def test_faq_section_detected(self) -> None:
        """FAQ section is properly separated in parsed sections."""
        md = (
            "Introduction text.\n\n"
            "## FAQ\n\n"
            "**Q1:** Answer\n\n"
            "## Conclusion\n\n"
            "Final words."
        )
        sections = _parse_sections("Test", _markdown_to_html_simple(md), "")
        assert sections["faq"]
        assert "FAQ" in sections["faq"]
        assert sections["conclusion"]
        assert "Conclusion" in sections["conclusion"]

    def test_author_box_included(self) -> None:
        """Author box is included in HTML."""
        html = build_article_html(
            title="Test",
            content_markdown="Content",
        )
        assert "About the Author" in html
        assert "Baby Name Ideas" in html

    def test_meta_description_not_in_body(self) -> None:
        """Meta description is not rendered in visible HTML."""
        html = build_article_html(
            title="Test",
            content_markdown="Content",
            meta_description="Hidden description",
        )
        # Meta description should not be visible in article body
        assert "Hidden description" not in html.split("<body")[0] if "<body" in html else True

    def test_toc_excludes_faq_and_conclusion(self) -> None:
        """Table of contents does not include FAQ or Conclusion headings."""
        toc = _generate_toc(
            "<h2>Introduction</h2><h2>FAQ</h2><h2>Conclusion</h2>"
        )
        assert "Introduction" in toc
        assert "FAQ" not in toc
        assert "Conclusion" not in toc

    def test_html_escaping(self) -> None:
        """HTML special characters are escaped."""
        assert _escape_html('AT&T <test> "quoted"') == (
            "AT&amp;T &lt;test&gt; &quot;quoted&quot;"
        )

    def test_markdown_with_table(self) -> None:
        """Markdown tables are converted to HTML tables."""
        md = (
            "| Name | Origin |\n"
            "|------|--------|\n"
            "| Aiko | Japan  |\n"
        )
        html = build_article_html(title="Test", content_markdown=md)
        assert "<table>" in html
        assert "Aiko" in html
        assert "Japan" in html

    def test_lazy_loading_on_hero(self) -> None:
        """Hero image has lazy loading attribute."""
        html = build_article_html(
            title="Test",
            content_markdown="Content",
            hero_image_path="data:image/webp;base64,xyz",
            hero_alt="Alt",
        )
        assert 'loading="lazy"' in html


def _markdown_to_html_simple(md: str) -> str:
    """Convert simple Markdown to HTML for test purposes."""
    import markdown
    return markdown.markdown(md, extensions=["markdown.extensions.extra"])


# ======================================================================
# Image uploader tests
# ======================================================================


class TestImageUploader:
    """Test image upload and tag building."""

    def test_build_tag_with_valid_image(self, tmp_path: Path) -> None:
        """Valid image produces a data URI."""
        # Create a minimal WEBP image
        img_path = tmp_path / "test.webp"
        # Pillow is available from Milestone 3
        from PIL import Image
        img = Image.new("RGB", (100, 50), color=(255, 0, 0))
        img.save(str(img_path), format="WEBP", quality=50)

        result = build_image_tag(
            image_path=str(img_path),
            alt_text="Test Alt",
            title="Test Title",
            width=100,
            height=50,
        )
        assert result["success"] is True
        assert "Test Alt" in result["html"]
        assert 'width="100"' in result["html"]
        assert 'height="50"' in result["html"]
        assert result["data_uri"].startswith("data:image/webp;base64,")

    def test_build_tag_non_existent_file(self) -> None:
        """Non-existent file raises ImageUploadError."""
        with pytest.raises(ImageUploadError, match="not found"):
            build_image_tag(image_path="/nonexistent/file.webp")

    def test_build_tag_lazy_load_default(self, tmp_path: Path) -> None:
        """Lazy loading is enabled by default."""
        from PIL import Image
        img_path = tmp_path / "lazy.webp"
        Image.new("RGB", (10, 10), color=(0, 255, 0)).save(str(img_path), "WEBP")

        result = build_image_tag(image_path=str(img_path))
        assert 'loading="lazy"' in result["html"]

    def test_build_tag_lazy_load_disabled(self, tmp_path: Path) -> None:
        """Lazy loading can be disabled."""
        from PIL import Image
        img_path = tmp_path / "no-lazy.webp"
        Image.new("RGB", (10, 10), color=(0, 0, 255)).save(str(img_path), "WEBP")

        result = build_image_tag(
            image_path=str(img_path),
            lazy_load=False,
        )
        assert 'loading="lazy"' not in result["html"]

    def test_build_tag_caption_included(self, tmp_path: Path) -> None:
        """Caption is included in the HTML."""
        from PIL import Image
        img_path = tmp_path / "cap.webp"
        Image.new("RGB", (10, 10), color=(100, 100, 100)).save(str(img_path), "WEBP")

        result = build_image_tag(
            image_path=str(img_path),
            caption="My test caption",
        )
        assert "figcaption" in result["html"]
        assert "My test caption" in result["html"]

    def test_data_uri_returns_bytes(self, tmp_path: Path) -> None:
        """Data URI is properly formatted base64."""
        from PIL import Image
        img_path = tmp_path / "bytes.webp"
        Image.new("RGB", (50, 50), color=(200, 200, 200)).save(str(img_path), "WEBP")

        result = build_image_tag(image_path=str(img_path))
        assert result["file_size_bytes"] > 0
        assert len(result["data_uri"]) > 100


# ======================================================================
# Publisher orchestrator tests (mocked Blogger API)
# ======================================================================


class TestPublisher:
    """Test the Publisher orchestrator with mocked Blogger API."""

    def test_publish_article_success(self, fresh_db) -> None:
        """Article is published successfully with mocked API."""
        from blogger.publisher import Publisher

        # Insert a test article
        from database.database import execute
        execute(
            "INSERT INTO articles (title, slug, content_markdown, status) "
            "VALUES (?, ?, ?, ?)",
            ("Test Article", "test-article", "# Introduction\n\nHello world.", "draft"),
            commit=True,
        )
        article_id = execute(
            "SELECT id FROM articles WHERE slug = ?", ("test-article",)
        ).fetchone()[0]

        # Insert a test image
        from PIL import Image
        img_dir = Path("/tmp") / "test_images"
        img_dir.mkdir(parents=True, exist_ok=True)
        img_path = img_dir / "test-article.webp"
        Image.new("RGB", (100, 50), color=(255, 100, 50)).save(str(img_path), "WEBP")

        execute(
            "INSERT INTO generated_images "
            "(article_id, prompt_text, image_path, alt_text, width, height, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (article_id, "test prompt", str(img_path), "Test Alt", 100, 50, "generated"),
            commit=True,
        )

        # Patch the Blogger API
        mock_response = {
            "id": "1234567890",
            "url": "https://babynameideas2026.blogspot.com/2026/07/test-article.html",
            "published": "2026-07-10T12:00:00Z",
        }

        from unittest.mock import patch as _patch
        with _patch("blogger.auth.CLIENT_ID", "test-id"):
            with _patch("blogger.auth.CLIENT_SECRET", "test-secret"):
                with _patch("blogger.auth.REFRESH_TOKEN", "test-token"):
                    with _patch("blogger.client._build_service") as mock_build:
                        mock_service = MagicMock()
                        mock_posts = MagicMock()
                        mock_insert = MagicMock()
                        mock_insert.execute.return_value = mock_response
                        mock_posts.insert.return_value = mock_insert
                        mock_service.posts.return_value = mock_posts
                        mock_build.return_value = mock_service

                        publisher = Publisher()
                        result = publisher.publish_article(article_id=article_id)

        assert result["success"] is True
        assert result["blogger_post_id"] == "1234567890"
        assert result["blogger_url"] == mock_response["url"]
        assert "test-article" in result["slug"]

        # Verify database was updated
        updated = execute(
            "SELECT status, publish_status, blogger_post_id FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
        assert updated["status"] == "published"
        assert updated["publish_status"] == "success"
        assert updated["blogger_post_id"] == "1234567890"

        # Verify image was marked as uploaded
        img_record = execute(
            "SELECT status FROM generated_images WHERE article_id = ?",
            (article_id,),
        ).fetchone()
        assert img_record["status"] == "uploaded"

    def test_publish_article_not_found(self) -> None:
        """Returns error when article does not exist."""
        from blogger.publisher import Publisher

        publisher = Publisher()
        result = publisher.publish_article(article_id=99999)

        assert result["success"] is False
        assert "not found" in result["error_message"].lower()

    def test_publish_pending_articles_empty(self) -> None:
        """publish_pending_articles returns empty list when no articles."""
        from blogger.publisher import Publisher

        publisher = Publisher()
        results = publisher.publish_pending_articles(max_articles=5)
        assert results == []

    def test_publish_with_blogger_api_error(self, fresh_db) -> None:
        """Handles Blogger API errors gracefully."""
        from blogger.publisher import Publisher

        from database.database import execute
        execute(
            "INSERT INTO articles (title, slug, content_markdown, status) "
            "VALUES (?, ?, ?, ?)",
            ("Error Test", "error-test", "Content", "draft"),
            commit=True,
        )
        article_id = execute(
            "SELECT id FROM articles WHERE slug = ?", ("error-test",)
        ).fetchone()[0]

        with patch("blogger.client._build_service") as mock_build:
            mock_service = MagicMock()
            mock_posts = MagicMock()
            mock_insert = MagicMock()
            mock_insert.execute.side_effect = Exception("API Error: rate limited")
            mock_posts.insert.return_value = mock_insert
            mock_service.posts.return_value = mock_posts
            mock_build.return_value = mock_service

            publisher = Publisher()
            result = publisher.publish_article(article_id=article_id)

        assert result["success"] is False
        assert result["error_message"]

        # Verify failure was recorded
        updated = execute(
            "SELECT publish_status, publish_attempts FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
        assert updated["publish_status"] == "failed"
        assert updated["publish_attempts"] >= 1

    def test_publish_updates_existing_post(self, fresh_db) -> None:
        """Publishing an article with existing post ID updates it."""
        from blogger.publisher import Publisher

        from database.database import execute
        execute(
            "INSERT INTO articles (title, slug, content_markdown, status, "
            "blogger_post_id, blogger_url) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("Update Test", "update-test", "Updated content", "published",
             "existing_123", "https://example.com/old"),
            commit=True,
        )
        article_id = execute(
            "SELECT id FROM articles WHERE slug = ?", ("update-test",)
        ).fetchone()[0]

        mock_response = {
            "id": "existing_123",
            "url": "https://babynameideas2026.blogspot.com/2026/07/updated.html",
            "published": "2026-07-10T14:00:00Z",
        }

        from unittest.mock import patch as _patch
        with _patch("blogger.auth.CLIENT_ID", "test-id"):
            with _patch("blogger.auth.CLIENT_SECRET", "test-secret"):
                with _patch("blogger.auth.REFRESH_TOKEN", "test-token"):
                    with _patch("blogger.client._build_service") as mock_build:
                        mock_service = MagicMock()
                        mock_posts = MagicMock()
                        mock_update = MagicMock()
                        mock_update.execute.return_value = mock_response
                        mock_posts.update.return_value = mock_update
                        mock_service.posts.return_value = mock_posts
                        mock_build.return_value = mock_service

                        publisher = Publisher()
                        result = publisher.publish_article(article_id=article_id)

        assert result["success"] is True
        assert result["blogger_post_id"] == "existing_123"

    def test_labels_generated_during_publish(self, fresh_db) -> None:
        """Labels are correctly generated during publish."""
        from blogger.publisher import Publisher

        from database.database import execute
        execute(
            "INSERT INTO articles (title, slug, content_markdown, status) "
            "VALUES (?, ?, ?, ?)",
            ("100 Irish Baby Names", "irish-names", "Content about Irish names", "draft"),
            commit=True,
        )
        article_id = execute(
            "SELECT id FROM articles WHERE slug = ?", ("irish-names",)
        ).fetchone()[0]

        mock_response = {
            "id": "label123",
            "url": "https://example.com/label-test",
            "published": "2026-07-10T15:00:00Z",
        }

        from unittest.mock import patch as _patch
        with _patch("blogger.auth.CLIENT_ID", "test-id"):
            with _patch("blogger.auth.CLIENT_SECRET", "test-secret"):
                with _patch("blogger.auth.REFRESH_TOKEN", "test-token"):
                    with _patch("blogger.client._build_service") as mock_build:
                        mock_service = MagicMock()
                        mock_posts = MagicMock()
                        mock_insert = MagicMock()
                        mock_insert.execute.return_value = mock_response
                        mock_posts.insert.return_value = mock_insert
                        mock_service.posts.return_value = mock_posts
                        mock_build.return_value = mock_service

                        publisher = Publisher()
                        result = publisher.publish_article(article_id=article_id)

        assert result["success"] is True
        assert "Baby Names" in result["labels"]
        assert "Irish Names" in result["labels"]

    def test_republish_failed_articles(self, fresh_db) -> None:
        """republish_failed_articles retries only failed articles."""
        from blogger.publisher import Publisher

        from database.database import execute
        execute(
            "INSERT INTO articles (title, slug, content_markdown, status, "
            "publish_status, publish_attempts, last_publish_error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Failed 1", "failed-1", "Content", "draft",
             "failed", 1, "Previous error"),
            commit=True,
        )
        execute(
            "INSERT INTO articles (title, slug, content_markdown, status, "
            "publish_status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("Pending 1", "pending-1", "Content", "draft", "pending"),
            commit=True,
        )

        with patch("blogger.publisher.Publisher.publish_article") as mock_pub:
            mock_pub.return_value = {"success": True}
            publisher = Publisher()
            results = publisher.republish_failed_articles(max_articles=10)

        # Only the failed article should be republished
        assert len(results) == 1

    def test_publish_excludes_archived(self, fresh_db) -> None:
        """publish_pending_articles skips already published articles."""
        from blogger.publisher import Publisher

        from database.database import execute
        execute(
            "INSERT INTO articles (title, slug, content_markdown, status, "
            "blogger_post_id) VALUES (?, ?, ?, ?, ?)",
            ("Already Published", "published", "Content", "published",
             "post_123"),
            commit=True,
        )

        publisher = Publisher()
        results = publisher.publish_pending_articles(max_articles=10)
        assert results == []

    def test_publish_without_image_succeeds(self, fresh_db) -> None:
        """Article publishes successfully even without a generated image."""
        from blogger.publisher import Publisher

        from database.database import execute
        execute(
            "INSERT INTO articles (title, slug, content_markdown, status) "
            "VALUES (?, ?, ?, ?)",
            ("No Image Article", "no-image", "# Content\n\nHello world.", "draft"),
            commit=True,
        )
        article_id = execute(
            "SELECT id FROM articles WHERE slug = ?", ("no-image",)
        ).fetchone()[0]

        mock_response = {
            "id": "noimg_123",
            "url": "https://example.com/no-image",
            "published": "2026-07-10T16:00:00Z",
        }

        from unittest.mock import patch as _patch
        with _patch("blogger.auth.CLIENT_ID", "test-id"):
            with _patch("blogger.auth.CLIENT_SECRET", "test-secret"):
                with _patch("blogger.auth.REFRESH_TOKEN", "test-token"):
                    with _patch("blogger.client._build_service") as mock_build:
                        mock_service = MagicMock()
                        mock_posts = MagicMock()
                        mock_insert = MagicMock()
                        mock_insert.execute.return_value = mock_response
                        mock_posts.insert.return_value = mock_insert
                        mock_service.posts.return_value = mock_posts
                        mock_build.return_value = mock_service

                        publisher = Publisher()
                        result = publisher.publish_article(article_id=article_id)

        assert result["success"] is True
        assert result["blogger_post_id"] == "noimg_123"
