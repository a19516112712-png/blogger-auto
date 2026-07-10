"""OAuth2 authentication for the Blogger API v3.

Uses the *refresh token* grant flow.  Credentials are read from
environment variables via :mod:`config.settings` — never hardcoded.

Flow
----
1. Build a :class:`google.oauth2.credentials.Credentials` object from
   ``CLIENT_ID``, ``CLIENT_SECRET``, and ``REFRESH_TOKEN``.
2. Automatically refresh the access token when expired (handled by the
   Google client library).
"""

from __future__ import annotations

from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError

from config.logging import get_logger
from config.settings import (
    BLOGGER_SCOPE,
    BLOGGER_TOKEN_URI,
    CLIENT_ID,
    CLIENT_SECRET,
    REFRESH_TOKEN,
)

log = get_logger(__name__)


class AuthError(Exception):
    """Raised when authentication fails."""


def get_credentials() -> Credentials:
    """Build and return OAuth2 credentials from environment variables.

    The returned :class:`~google.oauth2.credentials.Credentials` object
    automatically refreshes the access token when needed.

    Returns:
        A :class:`~google.oauth2.credentials.Credentials` instance.

    Raises:
        AuthError: If any required credential is missing or refresh fails.
    """
    if not CLIENT_ID:
        raise AuthError(
            "CLIENT_ID is not set. "
            "Set the environment variable or add it to your .env file."
        )
    if not CLIENT_SECRET:
        raise AuthError(
            "CLIENT_SECRET is not set. "
            "Set the environment variable or add it to your .env file."
        )
    if not REFRESH_TOKEN:
        raise AuthError(
            "REFRESH_TOKEN is not set. "
            "Set the environment variable or add it to your .env file."
        )

    try:
        creds = Credentials(
            token=None,  # Will be refreshed on first use
            refresh_token=REFRESH_TOKEN,
            token_uri=BLOGGER_TOKEN_URI,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            scopes=[BLOGGER_SCOPE],
        )
        log.info(
            "OAuth2 credentials created (client_id=%s..., refresh_token=%s...)",
            CLIENT_ID[:8] if len(CLIENT_ID) > 8 else CLIENT_ID,
            REFRESH_TOKEN[:8] if len(REFRESH_TOKEN) > 8 else REFRESH_TOKEN,
        )
        return creds
    except Exception as exc:
        raise AuthError(f"Failed to create OAuth2 credentials: {exc}") from exc


def refresh_if_expired(creds: Credentials) -> Credentials:
    """Explicitly refresh the access token if it is expired or missing.

    The Google client library usually handles this automatically, but
    this helper can be called before an API request for extra safety.

    Args:
        creds: A :class:`~google.oauth2.credentials.Credentials` instance.

    Returns:
        The (possibly refreshed) credentials.

    Raises:
        AuthError: If the token refresh fails.
    """
    try:
        if not creds.valid:
            creds.refresh(Request())  # type: ignore[arg-type]
            log.info("Access token refreshed successfully")
        return creds
    except RefreshError as exc:
        raise AuthError(f"Failed to refresh access token: {exc}") from exc
    except Exception as exc:
        raise AuthError(f"Unexpected error during token refresh: {exc}") from exc
