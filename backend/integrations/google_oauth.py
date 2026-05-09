"""Google OAuth 2.0 flow for per-practitioner Calendar access.

Setup (see README):
1. In Google Cloud Console → APIs & Services → OAuth consent screen, configure
   the consent screen (External, Testing mode is fine for first 100 users).
2. Credentials → Create Credentials → OAuth client ID → Web application.
3. Add the redirect URI: <PUBLIC_BASE_URL>/practitioner/api/gcal/callback
4. Copy the Client ID + Client Secret into env vars:
   - GOOGLE_OAUTH_CLIENT_ID
   - GOOGLE_OAUTH_CLIENT_SECRET
   - GOOGLE_OAUTH_REDIRECT_URI (or rely on PUBLIC_BASE_URL)
"""
import logging
import secrets
from typing import Optional, Tuple
from urllib.parse import urlencode

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def is_configured() -> bool:
    return bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)


def _redirect_uri() -> str:
    if settings.google_oauth_redirect_uri:
        return settings.google_oauth_redirect_uri
    base = settings.public_base_url.rstrip("/")
    return f"{base}/practitioner/api/gcal/callback"


def make_authorize_url(state: Optional[str] = None) -> Tuple[str, str]:
    """Returns (url, state). Caller should store `state` in a cookie/session
    and verify it on callback to prevent CSRF."""
    state = state or secrets.token_urlsafe(24)
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",  # force refresh_token issuance every time
        "state": state,
        "include_granted_scopes": "true",
    }
    return f"{AUTH_URL}?{urlencode(params)}", state


async def exchange_code(code: str) -> dict:
    """Exchange authorization code for tokens. Returns the raw token response.
    Includes 'refresh_token' (the durable credential we store), 'access_token',
    and 'id_token'. May raise on HTTP error."""
    async with httpx.AsyncClient(timeout=15) as http:
        r = await http.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": _redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
    if r.status_code >= 300:
        logger.error(f"OAuth exchange failed {r.status_code}: {r.text}")
        r.raise_for_status()
    return r.json()


async def fetch_userinfo(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as http:
        r = await http.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    if r.status_code >= 300:
        return {}
    return r.json()


def build_credentials(refresh_token: str):
    """Build a google-auth Credentials object from a stored refresh token.
    Returns None if the Google libs aren't installed or if oauth isn't configured."""
    if not is_configured() or not refresh_token:
        return None
    try:
        from google.oauth2.credentials import Credentials
    except ImportError:
        return None
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=TOKEN_URL,
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        scopes=SCOPES,
    )


def build_calendar_service(refresh_token: str):
    """Build a Calendar v3 service for a practitioner using their refresh token."""
    creds = build_credentials(refresh_token)
    if not creds:
        return None
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return None
    try:
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error(f"build_calendar_service failed: {e}")
        return None
