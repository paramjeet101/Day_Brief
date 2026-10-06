"""Google OAuth 2.0 flow and credential construction.

Authorization-code flow with ``access_type=offline`` so we receive a long-lived
refresh token. Only the refresh token is persisted (encrypted); short-lived
access tokens are minted on demand.
"""

from __future__ import annotations

from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"


def _client_config() -> dict:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise RuntimeError(
            "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
        )
    return {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": _AUTH_URI,
            "token_uri": _TOKEN_URI,
            "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
        }
    }


def _flow() -> Flow:
    return Flow.from_client_config(
        _client_config(),
        scopes=settings.GOOGLE_SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )


def build_authorization_url(state: str) -> str:
    """Return the Google consent-screen URL the user is redirected to."""
    auth_url, _ = _flow().authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # guarantee a refresh_token on every connect
        state=state,
    )
    return auth_url


def exchange_code(code: str) -> Credentials:
    """Swap a one-time authorization code for OAuth credentials."""
    flow = _flow()
    flow.fetch_token(code=code)
    return flow.credentials


def credentials_from_refresh_token(refresh_token: str) -> Credentials:
    """Rebuild credentials from a stored refresh token, minting a fresh access token."""
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=_TOKEN_URI,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=settings.GOOGLE_SCOPES,
    )
    creds.refresh(Request())
    return creds
