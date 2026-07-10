"""Image uploader for Blogger articles.

Uploads a local WEBP image to a publicly accessible location (if needed)
and inserts it into the article content with proper HTML attributes.

Since Blogger natively hosts images through the Post content (base64-encoded
or via a public URL), this module:

1. Reads the local image file.
2. Converts it to a data URI as a fallback.
3. Returns the final ``<img>`` tag with all attributes.

For images that need a public URL, future versions can upload to an
external image host (e.g. Imgur, Cloudinary) before inserting.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from config.logging import get_logger

log = get_logger(__name__)


class ImageUploadError(Exception):
    """Raised when image upload/insertion fails."""


def build_image_tag(
    image_path: str,
    alt_text: str = "",
    title: str = "",
    caption: str = "",
    width: int = 0,
    height: int = 0,
    lazy_load: bool = True,
) -> dict[str, str]:
    """Build an image tag with all attributes, ready for article insertion.

    This is a two-step process:
    1. Convert the local image to an embeddable format.
    2. Return the HTML tag and the alternate text metadata.

    Args:
        image_path: Absolute or relative path to the local WEBP image.
        alt_text:   Alt attribute text.
        title:      Title attribute text.
        caption:    Optional caption displayed below the image.
        width:      Image width in pixels.
        height:     Image height in pixels.
        lazy_load:  Whether to add ``loading="lazy"``.

    Returns:
        A dict with keys:
        - ``html``: The full image HTML string.
        - ``alt_text``: The alt text (for metadata storage).
        - ``data_uri``: The base64 data URI (for embedding).
        - ``success``: Whether the operation succeeded.
        - ``error_message``: Error details if failed.

    Raises:
        ImageUploadError: If the image file cannot be read.
    """
    try:
        path = Path(image_path)
        if not path.exists():
            raise ImageUploadError(f"Image file not found: {image_path}")
        if not path.is_file():
            raise ImageUploadError(f"Path is not a file: {image_path}")

        # Read image bytes
        image_bytes = path.read_bytes()

        # Determine MIME type
        mime_type, _ = mimetypes.guess_type(str(path))
        if not mime_type:
            # Fallback to WEBP
            mime_type = "image/webp"

        # Create base64 data URI
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_uri = f"data:{mime_type};base64,{b64}"

        # Build HTML attributes
        attrs: list[str] = [f'src="{data_uri}"']
        if alt_text:
            attrs.append(f'alt="{_escape_attr(alt_text)}"')
        if title:
            attrs.append(f'title="{_escape_attr(title)}"')
        if width > 0:
            attrs.append(f'width="{width}"')
        if height > 0:
            attrs.append(f'height="{height}"')
        if lazy_load:
            attrs.append('loading="lazy"')

        img_tag = f'<img {" ".join(attrs)} />'

        html = img_tag
        if caption:
            html += f'\n<figcaption class="image-caption">{_escape_attr(caption)}</figcaption>'

        log.info(
            "Image tag built: %s (size=%d bytes, mime=%s, data_uri_len=%d)",
            path.name,
            len(image_bytes),
            mime_type,
            len(data_uri),
        )

        return {
            "html": html,
            "alt_text": alt_text,
            "data_uri": data_uri,
            "success": True,
            "error_message": "",
            "file_size_bytes": len(image_bytes),
        }

    except FileNotFoundError as exc:
        raise ImageUploadError(f"Image file not found: {image_path}") from exc
    except OSError as exc:
        raise ImageUploadError(
            f"Failed to read image file {image_path}: {exc}"
        ) from exc


def _escape_attr(text: str) -> str:
    """Escape text for safe use in HTML attributes.

    Args:
        text: Raw text.

    Returns:
        HTML-escaped text safe for attribute values.
    """
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
