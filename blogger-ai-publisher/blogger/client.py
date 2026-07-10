"""Blogger API v3 client wrapper.

Wraps ``googleapiclient.discovery.build`` for the Blogger v3 API.
Supports:

- Create post
- Update post
- Get post
- Delete post
- Retry on HTTP 429 (rate limit) and 5xx with exponential backoff

All operations use OAuth2 credentials from :mod:`blogger.auth`.
"""

from __future__ import annotations

import time
import random
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from blogger.auth import get_credentials
from config.logging import get_logger
from config.settings import (
    BLOG_ID,
    PUBLISHER_MAX_RETRIES,
    PUBLISHER_RETRY_DELAY_SECONDS,
    PUBLISHER_MAX_BACKOFF_SECONDS,
)

log = get_logger(__name__)

# Retryable HTTP status codes
RETRYABLE_STATUSES: set[int] = {429, 500, 502, 503, 504}


class ClientError(Exception):
    """Raised when a Blogger API operation fails."""


def _build_service() -> Any:
    """Build and return the Blogger API v3 service object.

    Returns:
        A Google API service resource for the Blogger v3 API.
    """
    creds = get_credentials()
    service = build("blogger", "v3", credentials=creds)
    log.info("Blogger API v3 service built successfully")
    return service


# ---------------------------------------------------------------------------
# Low-level request helper with retry + exponential backoff
# ---------------------------------------------------------------------------


def _execute_with_retry(
    request_builder: callable,
    operation: str,
) -> dict[str, Any]:
    """Execute a Google API request with retry and exponential backoff.

    Retries on HTTP 429 (rate limit) and 5xx server errors, up to
    ``PUBLISHER_MAX_RETRIES`` times.

    Unlike the previous implementation, this function accepts a **callable**
    that builds a fresh request object on each attempt.  Google API client
    request objects are single-use — calling ``execute()`` twice raises
    an error.

    Args:
        request_builder: A zero-argument callable that returns a new
            Google API request object (e.g. ``lambda: service.posts().insert(...)``).
        operation:       Human-readable description for logging
                         (e.g. ``"create post"``).

    Returns:
        The API response as a dictionary.

    Raises:
        ClientError: If all retries are exhausted or a non-retryable error occurs.
    """
    last_error: Exception | None = None
    max_retries = PUBLISHER_MAX_RETRIES
    base_delay = PUBLISHER_RETRY_DELAY_SECONDS
    max_backoff = PUBLISHER_MAX_BACKOFF_SECONDS

    for attempt in range(1, max_retries + 2):  # +1 for initial attempt
        try:
            request = request_builder()
            start = time.perf_counter()
            response: dict[str, Any] = request.execute()
            elapsed = int((time.perf_counter() - start) * 1000)
            log.info(
                "Blogger API %s succeeded in %d ms (attempt %d/%d)",
                operation,
                elapsed,
                attempt,
                max_retries + 1,
            )
            return response

        except HttpError as exc:
            status = exc.resp.status if exc.resp else 0
            elapsed = int((time.perf_counter() - start) * 1000)

            if status in RETRYABLE_STATUSES and attempt <= max_retries:
                delay = min(
                    base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1),
                    max_backoff,
                )
                log.warning(
                    "Blogger API %s HTTP %d (attempt %d/%d) — "
                    "retrying in %.1fs (elapsed=%dms)",
                    operation,
                    status,
                    attempt,
                    max_retries + 1,
                    delay,
                    elapsed,
                )
                time.sleep(delay)
                last_error = exc
                continue
            else:
                raise ClientError(
                    f"Blogger API {operation} failed with HTTP {status}: {exc}"
                ) from exc

        except Exception as exc:
            elapsed = int((time.perf_counter() - start) * 1000)
            if attempt <= max_retries:
                delay = min(
                    base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1),
                    max_backoff,
                )
                log.warning(
                    "Blogger API %s error (attempt %d/%d, elapsed=%dms) — "
                    "retrying in %.1fs: %s",
                    operation,
                    attempt,
                    max_retries + 1,
                    elapsed,
                    delay,
                    exc,
                )
                time.sleep(delay)
                last_error = exc
                continue
            raise ClientError(
                f"Blogger API {operation} failed after {max_retries} retries: {exc}"
            ) from exc

    # All retries exhausted
    error_msg = (
        f"Blogger API {operation} exhausted after {max_retries + 1} attempts"
    )
    log.error(error_msg)
    raise ClientError(error_msg) from last_error


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_post(
    title: str,
    content: str,
    labels: list[str] | None = None,
    is_draft: bool = False,
) -> dict[str, Any]:
    """Create a new blog post on Blogger.

    Args:
        title:    Post title (H1).
        content:  Full HTML content of the post.
        labels:   Optional list of label strings.
        is_draft: If ``True``, saves as a draft instead of publishing.

    Returns:
        The API response dict, including ``id``, ``url``, ``published``.

    Raises:
        ClientError: If the API call fails after all retries.
        AuthError: If authentication fails.
    """
    service = _build_service()
    body: dict[str, Any] = {
        "kind": "blogger#post",
        "title": title,
        "content": content,
    }
    if labels:
        body["labels"] = list(dict.fromkeys(labels))  # deduplicate, preserve order

    def _build():
        return service.posts().insert(
            blogId=BLOG_ID,
            body=body,
            isDraft=is_draft,
        )

    return _execute_with_retry(_build, "create post")


def update_post(
    post_id: str,
    title: str,
    content: str,
    labels: list[str] | None = None,
    is_draft: bool = False,
) -> dict[str, Any]:
    """Update an existing blog post on Blogger.

    Args:
        post_id:  The Blogger post ID to update.
        title:    Updated title.
        content:  Updated HTML content.
        labels:   Updated label list.
        is_draft: If ``True``, saves as draft.

    Returns:
        The API response dict.

    Raises:
        ClientError: If the API call fails.
    """
    service = _build_service()
    body: dict[str, Any] = {
        "kind": "blogger#post",
        "id": post_id,
        "title": title,
        "content": content,
    }
    if labels:
        body["labels"] = list(dict.fromkeys(labels))

    def _build():
        return service.posts().update(
            blogId=BLOG_ID,
            postId=post_id,
            body=body,
            isDraft=is_draft,
        )

    return _execute_with_retry(_build, "update post")


def get_post(post_id: str) -> dict[str, Any]:
    """Retrieve a single post by its Blogger ID.

    Args:
        post_id: The Blogger post ID.

    Returns:
        The API response dict.

    Raises:
        ClientError: If the post is not found or the API call fails.
    """
    service = _build_service()
    def _build():
        return service.posts().get(blogId=BLOG_ID, postId=post_id)
    return _execute_with_retry(_build, "get post")


def delete_post(post_id: str) -> None:
    """Delete a blog post by its Blogger ID.

    Args:
        post_id: The Blogger post ID to delete.

    Raises:
        ClientError: If the API call fails.
    """
    service = _build_service()
    def _build():
        return service.posts().delete(blogId=BLOG_ID, postId=post_id)
    _execute_with_retry(_build, "delete post")


def list_posts(
    max_results: int = 50,
    status: str = "live",
) -> list[dict[str, Any]]:
    """List published posts on the blog.

    Args:
        max_results: Maximum number of posts to return (1–500).
        status:      Post status filter (``"live"``, ``"draft"``, ``"scheduled"``).

    Returns:
        A list of post dicts.

    Raises:
        ClientError: If the API call fails.
    """
    service = _build_service()
    def _build():
        return service.posts().list(
            blogId=BLOG_ID,
            maxResults=min(max_results, 500),
            status=status,
        )
    result = _execute_with_retry(_build, "list posts")
    return result.get("items", [])
