"""Instagram Business Login (Instagram API with Instagram Login) — OAuth + Graph helpers.

Official Meta flow (graph.instagram.com). No Facebook Page required. Publishing stays
disabled in this phase: only connection, token lifecycle and compliance callbacks.
Secrets come exclusively from the environment (META_APP_ID / META_APP_SECRET) — never
hard-coded. Instagram username/password are never received or stored: only tokens.
"""
import os
import json
import base64
import hmac
import hashlib
from urllib.parse import urlencode

import httpx

APP_ID = os.environ.get("META_APP_ID", "")
APP_SECRET = os.environ.get("META_APP_SECRET", "")
BACKEND_PUBLIC_URL = os.environ.get("BACKEND_PUBLIC_URL", "").rstrip("/")
REDIRECT_URI = f"{BACKEND_PUBLIC_URL}/api/oauth/instagram/callback"

AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
TOKEN_URL = "https://api.instagram.com/oauth/access_token"
GRAPH = "https://graph.instagram.com"
# Scopes for Instagram API with Instagram Login (post-2025 naming).
SCOPES = "instagram_business_basic,instagram_business_content_publish"
DEFAULT_LL_EXPIRY = 5184000  # ~60 days, seconds


def configured() -> bool:
    return bool(APP_ID and APP_SECRET and BACKEND_PUBLIC_URL)


def authorize_url(state: str) -> str:
    q = urlencode({"client_id": APP_ID, "redirect_uri": REDIRECT_URI,
                   "response_type": "code", "scope": SCOPES, "state": state})
    return f"{AUTHORIZE_URL}?{q}"


async def exchange_code(code: str) -> dict:
    """Short-lived token + ig user_id."""
    data = {"client_id": APP_ID, "client_secret": APP_SECRET, "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI, "code": code}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(TOKEN_URL, data=data)
    r.raise_for_status()
    return r.json()


async def long_lived_token(short_token: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{GRAPH}/access_token", params={
            "grant_type": "ig_exchange_token", "client_secret": APP_SECRET, "access_token": short_token})
    r.raise_for_status()
    return r.json()


async def refresh_token(long_token: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{GRAPH}/refresh_access_token", params={
            "grant_type": "ig_refresh_token", "access_token": long_token})
    r.raise_for_status()
    return r.json()


async def me(token: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{GRAPH}/me", params={
            "fields": "user_id,username,account_type", "access_token": token})
    r.raise_for_status()
    return r.json()


def _b64url_decode(s: str) -> bytes:
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode())


def parse_signed_request(signed_request: str):
    """Validate & decode a Meta signed_request. Returns payload dict or None if invalid."""
    if not signed_request or "." not in signed_request or not APP_SECRET:
        return None
    try:
        enc_sig, payload = signed_request.split(".", 1)
        sig = _b64url_decode(enc_sig)
        expected = hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        return json.loads(_b64url_decode(payload))
    except Exception:
        return None


class GraphAPIError(RuntimeError):
    """Instagram Graph API error that preserves the upstream HTTP status."""
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code
        self.is_client_error = bool(status_code and 400 <= status_code < 500)


def _check(r):
    try:
        j = r.json()
    except Exception:
        j = {"error": {"message": (r.text or "")[:300]}}
    if r.status_code >= 400 or (isinstance(j, dict) and j.get("error")):
        msg = (j.get("error") or {}).get("message") if isinstance(j, dict) else None
        raise GraphAPIError(msg or f"HTTP {r.status_code}", status_code=r.status_code)
    return j


async def create_media(ig_user_id: str, image_url: str, caption: str, token: str) -> dict:
    """Step 1: create a single-image feed container. Returns {id: creation_id}."""
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{GRAPH}/{ig_user_id}/media",
                         data={"image_url": image_url, "caption": caption, "access_token": token})
    return _check(r)


async def publish_media(ig_user_id: str, creation_id: str, token: str) -> dict:
    """Step 2: publish the container. Returns {id: media_id}."""
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{GRAPH}/{ig_user_id}/media_publish",
                         data={"creation_id": creation_id, "access_token": token})
    return _check(r)
