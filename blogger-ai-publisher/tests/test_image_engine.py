"""Comprehensive tests for the AI Image Engine (Milestone 3).

Covers:
- Base provider interface
- MockProvider (full pipeline without network)
- PollinationsProvider (HTTP request validation, no real calls)
- HuggingFaceProvider (config validation, no real calls)
- ImageValidator
- ImageOptimizer
- ImageDeduplicator
- MetadataGenerator
- ImageManager orchestrator
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from image_engine.base import (
    BaseProvider,
    ConfigurationError,
    GeneratedImage,
    GenerationError,
)
from image_engine.deduplicator import ImageDeduplicator
from image_engine.manager import ImageManager
from image_engine.metadata import MetadataGenerator
from image_engine.optimizer import ImageOptimizer, OptimizationError
from image_engine.validator import ImageValidator, ValidationError

# ======================================================================
# Test fixtures
# ======================================================================


def _make_gradient_image(
    width: int,
    height: int,
    tmp_path: Path,
    name: str = "gradient.png",
) -> Path:
    """Create a PNG image with a horizontal gradient (passes all validations)."""
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for x in range(width):
        factor = x / max(width - 1, 1)
        arr[:, x, 0] = int(200 * factor + 55 * (1 - factor))  # R: 55→200
        arr[:, x, 1] = int(100 * factor + 150 * (1 - factor))  # G: 150→100
        arr[:, x, 2] = int(50 * factor + 200 * (1 - factor))   # B: 200→50
    img = Image.fromarray(arr, mode="RGB")
    path = tmp_path / name
    img.save(path)
    return path


@pytest.fixture
def test_image_path(tmp_path: Path) -> Path:
    """Create a valid 1600×900 multi-colour gradient image."""
    return _make_gradient_image(1600, 900, tmp_path, "test_image.png")


@pytest.fixture
def small_image_path(tmp_path: Path) -> Path:
    """Create an undersized 100×100 image (still a valid gradient)."""
    return _make_gradient_image(100, 100, tmp_path, "small.png")


@pytest.fixture
def blank_image_path(tmp_path: Path) -> Path:
    """Create a blank (all-white) image."""
    img = Image.new("RGB", (1600, 900), color=(255, 255, 255))
    path = tmp_path / "blank.png"
    img.save(path)
    return path


@pytest.fixture
def single_color_image_path(tmp_path: Path) -> Path:
    """Create a single-colour (all-blue) image with zero variance."""
    img = Image.new("RGB", (1600, 900), color=(0, 0, 255))
    path = tmp_path / "single_color.png"
    img.save(path)
    return path


@pytest.fixture
def corrup_image_path(tmp_path: Path) -> Path:
    """Create a corrupt (non-image) file."""
    path = tmp_path / "corrupt.png"
    path.write_text("not an image file")
    return path


@pytest.fixture
def empty_image_path(tmp_path: Path) -> Path:
    """Create an empty file."""
    path = tmp_path / "empty.png"
    path.touch()
    return path


# ======================================================================
# Base provider tests
# ======================================================================


class TestBaseProvider:
    """Test the abstract base provider interface."""

    def test_cannot_instantiate_base(self) -> None:
        """BaseProvider is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseProvider()  # type: ignore[abstract]

    def test_generated_image_named_tuple(self) -> None:
        """GeneratedImage stores provider metadata correctly."""
        gi = GeneratedImage(
            image_path=Path("/tmp/test.webp"),
            provider="mock",
            generation_seed=42,
            generation_time_ms=150,
        )
        assert gi.image_path == Path("/tmp/test.webp")
        assert gi.provider == "mock"
        assert gi.generation_seed == 42
        assert gi.generation_time_ms == 150

    def test_generated_image_defaults(self) -> None:
        """GeneratedImage has sensible defaults."""
        gi = GeneratedImage(image_path=Path("/tmp/test.webp"), provider="mock")
        assert gi.generation_seed == 0
        assert gi.generation_time_ms == 0


# ======================================================================
# MockProvider tests
# ======================================================================


class TestMockProvider:
    """Test the MockProvider (full pipeline without network)."""

    def test_generate_returns_path(self) -> None:
        """MockProvider.generate returns a valid GeneratedImage."""
        from image_engine.providers.mock import MockProvider

        provider = MockProvider()
        result = provider.generate("Test baby name illustration")
        assert isinstance(result, GeneratedImage)
        assert result.image_path.exists()
        assert result.image_path.suffix == ".webp"
        assert result.provider == "mock"

    def test_generate_reproducible_seed(self) -> None:
        """Same seed should produce the same image (same hash)."""
        from image_engine.providers.mock import MockProvider

        provider = MockProvider()
        r1 = provider.generate("Test prompt", seed=12345)
        r2 = provider.generate("Test prompt", seed=12345)

        h1 = hashlib.md5(r1.image_path.read_bytes()).hexdigest()
        h2 = hashlib.md5(r2.image_path.read_bytes()).hexdigest()
        assert h1 == h2, "Same seed should produce identical image"

    def test_generate_different_seed_different_image(self) -> None:
        """Different seeds should produce different images."""
        from image_engine.providers.mock import MockProvider

        provider = MockProvider()
        r1 = provider.generate("Test prompt", seed=1)
        r2 = provider.generate("Test prompt", seed=99999)

        h1 = hashlib.md5(r1.image_path.read_bytes()).hexdigest()
        h2 = hashlib.md5(r2.image_path.read_bytes()).hexdigest()
        assert h1 != h2, "Different seeds should produce different images"

    def test_generate_image_dimensions(self) -> None:
        """Generated image should match configured dimensions."""
        from image_engine.providers.mock import MockProvider

        provider = MockProvider()
        result = provider.generate("Test")
        img = Image.open(result.image_path)
        assert img.width == 1600
        assert img.height == 900

    def test_generate_image_format(self) -> None:
        """Generated image should be WEBP format."""
        from image_engine.providers.mock import MockProvider

        provider = MockProvider()
        result = provider.generate("Test")
        img = Image.open(result.image_path)
        assert img.format == "WEBP"


# ======================================================================
# PollinationsProvider tests
# ======================================================================


class TestPollinationsProvider:
    """Test PollinationsProvider (config validation only — no real calls)."""

    def test_init_default_config(self) -> None:
        """Provider initialises without errors."""
        from image_engine.providers.pollinations import PollinationsProvider

        provider = PollinationsProvider()
        assert provider.name == "pollinations"


# ======================================================================
# HuggingFaceProvider tests
# ======================================================================


class TestHuggingFaceProvider:
    """Test HuggingFaceProvider config validation."""

    def test_init_missing_token_raises_config_error(self) -> None:
        """Provider raises ConfigurationError when token is missing."""
        from image_engine.providers.huggingface import HuggingFaceProvider

        import config.settings
        original = config.settings.HUGGINGFACE_API_TOKEN
        try:
            config.settings.HUGGINGFACE_API_TOKEN = ""
            with pytest.raises(ConfigurationError, match="HUGGINGFACE_API_TOKEN"):
                HuggingFaceProvider()
        finally:
            config.settings.HUGGINGFACE_API_TOKEN = original

    def test_init_with_token_succeeds(self) -> None:
        """Provider initialises successfully when token is provided."""
        from image_engine.providers.huggingface import HuggingFaceProvider

        provider = HuggingFaceProvider(
            api_token="hf_test_token_12345",
            model="test/model",
        )
        assert provider.name == "huggingface"
        assert provider._api_token == "hf_test_token_12345"
        assert provider._model == "test/model"


# ======================================================================
# ImageValidator tests
# ======================================================================


class TestImageValidator:
    """Test ImageValidator's ability to reject bad images."""

    def test_valid_image_passes(self, test_image_path: Path) -> None:
        """A valid gradient image passes validation."""
        validator = ImageValidator()
        result = validator.validate(test_image_path)
        assert result == test_image_path

    def test_small_image_rejected(self, small_image_path: Path) -> None:
        """An undersized image is rejected."""
        validator = ImageValidator()
        with pytest.raises(ValidationError, match="too small"):
            validator.validate(small_image_path)

    def test_blank_image_rejected(self, blank_image_path: Path) -> None:
        """A blank (all-white) image is rejected."""
        validator = ImageValidator()
        with pytest.raises(ValidationError, match="blank|white|variance"):
            validator.validate(blank_image_path)

    def test_single_color_rejected(self, single_color_image_path: Path) -> None:
        """A single-colour (all-blue) uniform image is rejected."""
        validator = ImageValidator()
        with pytest.raises(ValidationError, match="variance|single|uniform"):
            validator.validate(single_color_image_path)

    def test_corrupt_image_rejected(self, corrup_image_path: Path) -> None:
        """A corrupt (non-image) file is rejected."""
        validator = ImageValidator()
        with pytest.raises(ValidationError, match="identify|Failed"):
            validator.validate(corrup_image_path)

    def test_empty_image_rejected(self, empty_image_path: Path) -> None:
        """An empty file is rejected."""
        validator = ImageValidator()
        with pytest.raises(ValidationError, match="empty"):
            validator.validate(empty_image_path)

    def test_custom_dimensions(self, test_image_path: Path) -> None:
        """Validator uses custom min dimensions when provided."""
        validator = ImageValidator(min_width=2000, min_height=2000)
        with pytest.raises(ValidationError, match="too small"):
            validator.validate(test_image_path)

    def test_dimension_exact_match(self, tmp_path: Path) -> None:
        """Image exactly matching min dimensions passes."""
        path = _make_gradient_image(1600, 900, tmp_path, "exact.png")
        validator = ImageValidator(min_width=1600, min_height=900)
        result = validator.validate(path)
        assert result == path


# ======================================================================
# ImageOptimizer tests
# ======================================================================


class TestImageOptimizer:
    """Test ImageOptimizer's resize/compress/conversion pipeline."""

    def test_optimize_maintains_dimensions(self, test_image_path: Path, tmp_path: Path) -> None:
        """Optimized image matches target dimensions."""
        optimizer = ImageOptimizer(
            target_width=1600,
            target_height=900,
            quality=90,
        )
        out = tmp_path / "optimized.webp"
        result = optimizer.optimize(test_image_path, output_path=out)
        img = Image.open(result)
        assert img.width == 1600
        assert img.height == 900

    def test_optimize_converts_to_webp(self, test_image_path: Path, tmp_path: Path) -> None:
        """Optimized image is saved as WEBP."""
        optimizer = ImageOptimizer()
        out = tmp_path / "output.webp"
        result = optimizer.optimize(test_image_path, output_path=out)
        assert result.suffix == ".webp"
        img = Image.open(result)
        assert img.format == "WEBP"

    def test_optimize_compresses_file(self, test_image_path: Path, tmp_path: Path) -> None:
        """Optimized file is smaller than original PNG."""
        original_size = test_image_path.stat().st_size
        optimizer = ImageOptimizer(
            target_width=1600,
            target_height=900,
            quality=50,
        )
        out = tmp_path / "compressed.webp"
        result = optimizer.optimize(test_image_path, output_path=out)
        compressed_size = result.stat().st_size
        assert compressed_size < original_size or compressed_size < 100_000

    def test_optimize_in_place(self, test_image_path: Path) -> None:
        """Optimizing in-place overwrites the source file."""
        optimizer = ImageOptimizer(
            target_width=1600,
            target_height=900,
            quality=80,
        )
        import shutil
        work = test_image_path.parent / "inplace.png"
        shutil.copy(test_image_path, work)
        result = optimizer.optimize(work)
        assert result == work

    def test_optimize_non_existent_file(self) -> None:
        """Raises OptimizationError for non-existent files."""
        optimizer = ImageOptimizer()
        with pytest.raises(OptimizationError):
            optimizer.optimize(Path("/nonexistent/image.png"))

    def test_resize_crop_non_standard_ratio(self, tmp_path: Path) -> None:
        """Optimizer crops non-standard aspect ratios correctly."""
        path = _make_gradient_image(800, 1200, tmp_path, "tall.png")
        optimizer = ImageOptimizer(
            target_width=1600,
            target_height=900,
            quality=80,
        )
        out = tmp_path / "tall_out.webp"
        result = optimizer.optimize(path, output_path=out)
        im = Image.open(result)
        assert im.width == 1600
        assert im.height == 900

    def test_compression_info(self) -> None:
        """compression_info returns expected keys."""
        optimizer = ImageOptimizer(target_width=1600, target_height=900)
        info = optimizer.compression_info
        assert info["width"] == 1600
        assert info["height"] == 900
        assert "quality" in info
        assert "format" in info


# ======================================================================
# ImageDeduplicator tests
# ======================================================================


class TestImageDeduplicator:
    """Test perceptual hash deduplication."""

    def test_compute_phash_valid_image(self, test_image_path: Path) -> None:
        """pHash is computed for a valid gradient image."""
        dedup = ImageDeduplicator()
        phash = dedup.compute_phash(test_image_path)
        assert isinstance(phash, str)
        assert len(phash) == 16

    def test_same_image_same_hash(self, test_image_path: Path, tmp_path: Path) -> None:
        """The same image should produce the same pHash."""
        dedup = ImageDeduplicator()
        h1 = dedup.compute_phash(test_image_path)

        copy = tmp_path / "copy.png"
        copy.write_bytes(test_image_path.read_bytes())
        h2 = dedup.compute_phash(copy)
        assert h1 == h2

    def test_different_images_different_hashes(self, tmp_path: Path) -> None:
        """Different gradient images should produce different pHashes."""
        dedup = ImageDeduplicator()

        # Image 1: blue→green gradient
        img1 = _make_gradient_image(1600, 900, tmp_path, "img1.png")

        # Image 2: red→yellow gradient (different colors)
        arr = np.zeros((900, 1600, 3), dtype=np.uint8)
        for x in range(1600):
            factor = x / 1599
            arr[:, x, 0] = 255
            arr[:, x, 1] = int(200 * factor)
            arr[:, x, 2] = int(50 * (1 - factor))
        path2 = tmp_path / "img2.png"
        Image.fromarray(arr, mode="RGB").save(path2)

        h1 = dedup.compute_phash(img1)
        h2 = dedup.compute_phash(path2)
        assert h1 != h2, "Different images should produce different pHashes"

    def test_exact_match_is_duplicate(self, test_image_path: Path) -> None:
        """An exact same hash is detected as duplicate."""
        dedup = ImageDeduplicator(threshold=0)
        phash = dedup.compute_phash(test_image_path)
        assert dedup.is_duplicate(phash, [phash])

    def test_different_hash_not_duplicate(self, tmp_path: Path) -> None:
        """A different image's hash should not match at threshold=0."""
        dedup = ImageDeduplicator(threshold=0)

        img1 = _make_gradient_image(1600, 900, tmp_path, "dup_a.png")
        phash1 = dedup.compute_phash(img1)

        # Different gradient arrangement (vertical instead of horizontal)
        arr = np.zeros((900, 1600, 3), dtype=np.uint8)
        for y in range(900):
            factor = y / 899
            arr[y, :, 0] = int(100 * factor + 200 * (1 - factor))
            arr[y, :, 1] = int(200 * factor)
            arr[y, :, 2] = int(50 + 150 * factor)
        path2 = tmp_path / "dup_b.png"
        Image.fromarray(arr, mode="RGB").save(path2)
        phash2 = dedup.compute_phash(path2)

        assert not dedup.is_duplicate(phash2, [phash1]), (
            "Different gradient images should not be duplicates at threshold=0"
        )

    def test_empty_existing_list(self, test_image_path: Path) -> None:
        """No existing hashes means no duplicate."""
        dedup = ImageDeduplicator()
        phash = dedup.compute_phash(test_image_path)
        assert not dedup.is_duplicate(phash, [])

    def test_load_existing_hashes(self) -> None:
        """load_existing_hashes returns a list (possibly empty)."""
        dedup = ImageDeduplicator()
        hashes = dedup.load_existing_hashes()
        assert isinstance(hashes, list)

    def test_compute_phash_nonexistent_file(self) -> None:
        """Raises DeduplicationError for non-existent files."""
        from image_engine.deduplicator import DeduplicationError
        dedup = ImageDeduplicator()
        with pytest.raises(DeduplicationError):
            dedup.compute_phash(Path("/nonexistent.png"))


# ======================================================================
# MetadataGenerator tests
# ======================================================================


class TestMetadataGenerator:
    """Test SEO metadata generation."""

    def test_generate_basic(self) -> None:
        """Metadata is generated with correct fields."""
        gen = MetadataGenerator()
        meta = gen.generate(
            title="100 Japanese Baby Names",
            slug="japanese-baby-names",
        )
        assert meta.filename == "japanese-baby-names.webp"
        assert "Japanese" in meta.alt_text
        assert meta.title
        assert meta.caption
        assert meta.description
        assert len(meta.seo_keywords) > 0

    def test_filename_from_slug(self) -> None:
        """Filename is derived from the slug."""
        gen = MetadataGenerator()
        meta = gen.generate(title="Test", slug="my-test-slug")
        assert meta.filename == "my-test-slug.webp"

    def test_alt_text_contains_title(self) -> None:
        """Alt text includes the article title."""
        gen = MetadataGenerator()
        meta = gen.generate(title="Baby Girl Names", slug="baby-girl-names")
        assert "Baby Girl Names" in meta.alt_text

    def test_seo_keywords_no_duplicates(self) -> None:
        """SEO keywords are deduplicated."""
        gen = MetadataGenerator()
        meta = gen.generate(title="Baby Baby Baby Names", slug="baby-names")
        lower = [k.lower() for k in meta.seo_keywords]
        assert len(lower) == len(set(lower))

    def test_seo_keywords_max_ten(self) -> None:
        """SEO keywords are capped at 10."""
        gen = MetadataGenerator()
        meta = gen.generate(
            title="A B C D E F G H I J K L M N O P Q R S T U V W X Y Z",
            slug="a-b-c-d-e-f",
        )
        assert len(meta.seo_keywords) <= 10

    def test_empty_title(self) -> None:
        """Generator handles empty titles gracefully."""
        gen = MetadataGenerator()
        meta = gen.generate(title="", slug="empty")
        assert meta.filename == "empty.webp"

    def test_to_dict(self) -> None:
        """to_dict returns all expected keys."""
        gen = MetadataGenerator()
        meta = gen.generate(title="Test", slug="test")
        d = meta.to_dict()
        assert "filename" in d
        assert "alt_text" in d
        assert "title" in d
        assert "caption" in d
        assert "description" in d
        assert "seo_keywords" in d


# ======================================================================
# ImageManager orchestrator tests
# ======================================================================


@pytest.fixture(autouse=False)
def _mock_only_providers(monkeypatch):
    """Override IMAGE_PROVIDERS to only use mock for test isolation."""
    import config.settings
    monkeypatch.setattr(config.settings, "IMAGE_PROVIDERS", ["mock"])


class TestImageManager:
    """Test the ImageManager orchestrator (using MockProvider)."""

    def test_generate_success(self, _mock_only_providers) -> None:
        """Manager generates a valid image with MockProvider."""
        mgr = ImageManager()
        result = mgr.generate(
            title="Test Baby Names",
            slug="test-baby-names",
            prompt="A beautiful illustration of baby names",
        )
        assert result["success"] is True
        assert result["image_path"]
        assert Path(result["image_path"]).exists()
        assert result["provider"] == "mock"
        assert result["width"] == 1600
        assert result["height"] == 900
        assert result["phash"]
        assert result["generation_seed"] > 0
        assert result["optimized"] is True
        assert result["quality"] > 0

    def test_generate_all_providers_fail(self, monkeypatch) -> None:
        """Manager returns error when all providers fail."""
        mgr = ImageManager()
        import config.settings
        monkeypatch.setattr(config.settings, "IMAGE_PROVIDERS", [])
        result = mgr.generate(
            title="Test",
            slug="test",
            prompt="test",
        )
        assert result["success"] is False
        assert "exhausted" in result["error_message"] or result["error_message"]

    def test_generate_stores_database_record(self, _mock_only_providers, fresh_db) -> None:
        """Manager stores the generated image record in the database."""
        from database.database import execute, fetch_one
        execute(
            "INSERT INTO articles (title, slug, status) VALUES (?, ?, ?)",
            ("DB Article", "db-article", "draft"),
            commit=True,
        )
        article_id = fetch_one(
            "SELECT id FROM articles WHERE slug = ?", ("db-article",)
        )[0]
        mgr = ImageManager()
        result = mgr.generate(
            title="DB Test Names",
            slug="db-test-names",
            prompt="Test database storage",
            article_id=article_id,
        )
        assert result["success"] is True

        from database.database import fetch_all
        rows = fetch_all(
            "SELECT * FROM generated_images WHERE alt_text LIKE ?",
            ("%DB Test Names%",),
        )
        assert len(rows) == 1
        assert rows[0]["provider"] == "mock"
        assert rows[0]["phash"] == result["phash"]

    def test_generate_with_article_id(self, _mock_only_providers, fresh_db) -> None:
        """Article ID is correctly stored in the database."""
        from database.database import execute, last_insert_rowid
        execute(
            "INSERT INTO articles (title, slug, status) VALUES (?, ?, ?)",
            ("Test Article", "test-article", "draft"),
            commit=True,
        )
        article_id = execute(
            "SELECT id FROM articles WHERE slug = ?",
            ("test-article",)
        ).fetchone()[0]
        mgr = ImageManager()
        result = mgr.generate(
            title="Article Test",
            slug="article-test",
            prompt="Test",
            article_id=article_id,
        )
        assert result["success"] is True
        from database.database import fetch_one
        row = fetch_one(
            "SELECT article_id FROM generated_images WHERE phash = ?",
            (result["phash"],),
        )
        assert row is not None
        assert row["article_id"] == article_id

    def test_generate_multiple_unique_images(self, _mock_only_providers) -> None:
        """Multiple generations produce unique, non-duplicate images."""
        mgr = ImageManager()
        results = []
        for i in range(3):
            r = mgr.generate(
                title=f"Unique Test {i}",
                slug=f"unique-test-{i}",
                prompt=f"Unique generation {i}",
            )
            results.append(r)

        assert all(r["success"] for r in results)
        phashes = [r["phash"] for r in results]
        assert len(set(phashes)) == len(phashes), (
            "All images should have unique phash values"
        )


# ======================================================================
# Regression: configuration via settings
# ======================================================================


class TestImageEngineSettings:
    """Test that image engine settings are correctly loaded."""

    def test_image_output_settings(self) -> None:
        """Default image output settings are present."""
        from config.settings import (
            IMAGE_OUTPUT_WIDTH,
            IMAGE_OUTPUT_HEIGHT,
            IMAGE_OUTPUT_FORMAT,
            IMAGE_OUTPUT_QUALITY,
            IMAGE_MAX_FILE_SIZE,
            IMAGE_PHASH_THRESHOLD,
            IMAGE_MAX_RETRIES,
            IMAGE_PROVIDERS,
        )
        assert IMAGE_OUTPUT_WIDTH == 1600
        assert IMAGE_OUTPUT_HEIGHT == 900
        assert IMAGE_OUTPUT_FORMAT == "WEBP"
        assert IMAGE_OUTPUT_QUALITY == 90
        assert IMAGE_MAX_FILE_SIZE > 0
        assert IMAGE_PHASH_THRESHOLD > 0
        assert IMAGE_MAX_RETRIES > 0
        assert len(IMAGE_PROVIDERS) > 0


# ======================================================================
# Performance and edge cases
# ======================================================================


class TestImageEngineEdgeCases:
    """Test edge cases for the image engine."""

    def test_optimizer_handles_rgba_to_rgb(self, tmp_path: Path) -> None:
        """Optimizer correctly handles RGBA images by converting to RGB."""
        img = Image.new("RGBA", (1600, 900), color=(100, 150, 200, 128))
        path = tmp_path / "rgba.png"
        img.save(path, format="PNG")
        optimizer = ImageOptimizer(target_width=1600, target_height=900)
        out = tmp_path / "rgba_out.webp"
        result = optimizer.optimize(path, output_path=out)
        im = Image.open(result)
        assert im.mode == "RGB"

    def test_validator_rejects_nonexistent_file(self) -> None:
        """Validator rejects non-existent files."""
        validator = ImageValidator()
        with pytest.raises(ValidationError, match="does not exist"):
            validator.validate(Path("/nonexistent"))

    def test_deduplicator_threshold_zero(self) -> None:
        """Threshold=0 means only exact matches are duplicates."""
        dedup = ImageDeduplicator(threshold=0)
        h = "0123456789abcdef"
        assert dedup.is_duplicate(h, [h])
        h2 = "0123456789abcdee"
        assert not dedup.is_duplicate(h2, [h])
