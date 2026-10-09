"""Login Google proprietario CRMEvent (OAuth 2.0 Authorization Code + PKCE + state + nonce).
Attivazione controllata: GOOGLE_LOGIN_PROVIDER=crmevent (default: emergent = login Google precedente invariato).
Client dedicato GOOGLE_LOGIN_CLIENT_ID/SECRET: NON usa GOOGLE_CLIENT_ID/SECRET di Google Calendar."""
import base64
import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from google.auth.transport import requests as g_requests
from google.oauth2 import id_token as g_id_token
from pydantic import BaseModel

log = logging.getLogger("crmevent.google_login")
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
STATE_COOKIE, LINK_COOKIE = "g_oauth_state", "g_oauth_link"
TTL = timedelta(minutes=10)
INTENTS = ("login", "register", "invite")


def config() -> dict:
    c = {"provider": os.environ.get("GOOGLE_LOGIN_PROVIDER", "emergent"), "client_id": os.environ.get("GOOGLE_LOGIN_CLIENT_ID", ""),
         "secret": os.environ.get("GOOGLE_LOGIN_CLIENT_SECRET", ""), "redirect": os.environ.get("GOOGLE_LOGIN_REDIRECT_URI", ""),
         "frontend": (os.environ.get("FRONTEND_URL") or "").rstrip("/")}
    c["enabled"] = c["provider"] == "crmevent" and all(c[k] for k in ("client_id", "secret", "redirect", "frontend"))
    return c


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _safe_next(n: Optional[str]) -> str:
    return n if n and n.startswith("/") and not n.startswith("//") and "\\" not in n else ""


def _lang(request: Request) -> str:
    """Italiano di default; se il browser preferisce un'altra lingua, Google usa quella dell'utente."""
    first = (request.headers.get("accept-language") or "").split(",")[0].split(";")[0].strip()
    return first if first and not first.lower().startswith("it") and len(first) <= 10 else "it"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def resolve_identity(db, ident: dict, intent: str) -> tuple:
    """Decide l'esito per un'identità Google gi\u00e0 verificata. Ritorna ("login", user) | ("link", user) | ("create", None) | ("error", code).
    Regole: 1) google_sub; 2) email verificata \u2192 collegamento automatico, tranne Super Admin o sub diverso gi\u00e0 collegato (serve la password);
    3) nuovo account solo per registrazione o invito."""
    if not ident.get("email_verified"):
        return "error", "unverified"
    user = await db.users.find_one({"google_sub": ident["sub"]}, {"_id": 0})
    if not user:
        user = await db.users.find_one({"email": ident["email"]}, {"_id": 0})
        if user and (user.get("role") == "superadmin" or (user.get("google_sub") and user["google_sub"] != ident["sub"])):
            return ("link", user) if user.get("password_hash") else ("error", "conflict")
    if user:
        return ("error", "disabled") if user.get("active") is False else ("login", user)
    return ("create", None) if intent in ("register", "invite") else ("error", "no_account")


def build_router(db, deps: dict) -> APIRouter:
    r = APIRouter()

    def _front(path: str) -> str:
        return config()["frontend"] + path

    def _fail(code: str, intent: str = "login") -> RedirectResponse:
        page = "/registrati" if intent == "register" else "/login"
        resp = RedirectResponse(_front(f"{page}?google_error={code}"), status_code=302)
        resp.delete_cookie(STATE_COOKIE, path="/api/oauth/google")
        return resp

    async def _login(user: dict, ident: dict, dest: str) -> RedirectResponse:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"google_sub": ident["sub"], "last_login_at": deps["now_iso"](),
                                                                          **({"picture": ident["picture"]} if ident.get("picture") else {})}})
        if not dest:
            p = await deps["user_payload"](await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0}))
            dest = "/completa-organizzazione" if p.get("needs_org") else "/completa-profilo" if p.get("needs_phone") else "/app"
        resp = RedirectResponse(_front(dest), status_code=302)
        deps["set_auth_cookie"](resp, "access_token", deps["create_access_token"](user["user_id"], user["email"]), 7 * 24 * 3600)
        resp.delete_cookie(STATE_COOKIE, path="/api/oauth/google")
        log.info("google login ok user=%s", user["user_id"])
        return resp

    @r.get("/oauth/google/config")
    async def google_config():
        return {"provider": "crmevent" if config()["enabled"] else "emergent"}

    @r.get("/oauth/google/start")
    async def google_start(request: Request, intent: str = "login", next: str = "", invite: str = ""):
        c = config()
        if not c["enabled"]:
            raise HTTPException(status_code=404, detail="Login Google CRMEvent non attivo")
        intent = intent if intent in INTENTS else "login"
        state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(24), secrets.token_urlsafe(64)
        await db.oauth_login_states.create_index("expires_at", expireAfterSeconds=0)
        await db.oauth_login_links.create_index("expires_at", expireAfterSeconds=0)
        await db.oauth_login_states.insert_one({"state": state, "nonce": nonce, "verifier": verifier, "intent": intent, "next": _safe_next(next),
                                                "invite": invite[:200], "expires_at": _now() + TTL})
        q = urlencode({"response_type": "code", "client_id": c["client_id"], "redirect_uri": c["redirect"], "scope": "openid email profile",
                       "state": state, "nonce": nonce, "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
                       "code_challenge_method": "S256", "prompt": "select_account", "access_type": "online", "hl": _lang(request)})
        resp = RedirectResponse(f"{AUTH_URL}?{q}", status_code=302)
        resp.set_cookie(STATE_COOKIE, state, max_age=int(TTL.total_seconds()), httponly=True, secure=True, samesite="lax", path="/api/oauth/google")
        return resp

    @r.get("/oauth/google/callback")
    async def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
        c = config()
        if not c["enabled"]:
            raise HTTPException(status_code=404, detail="Login Google CRMEvent non attivo")
        doc = await db.oauth_login_states.find_one_and_delete({"state": state}) if state else None
        intent = (doc or {}).get("intent", "login")
        if error:
            return _fail("denied", intent)
        if not doc or request.cookies.get(STATE_COOKIE) != state or doc["expires_at"].replace(tzinfo=timezone.utc) < _now() or not code:
            return _fail("state", intent)
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                tr = await http.post(TOKEN_URL, data={"code": code, "client_id": c["client_id"], "client_secret": c["secret"],
                                                      "redirect_uri": c["redirect"], "grant_type": "authorization_code", "code_verifier": doc["verifier"]})
            raw = tr.json().get("id_token") if tr.status_code == 200 else None
            if not raw:
                log.warning("google token exchange failed status=%s", tr.status_code)
                return _fail("exchange", intent)
            claims = await run_in_threadpool(g_id_token.verify_oauth2_token, raw, g_requests.Request(), c["client_id"])
        except Exception as e:  # firma/aud/exp non validi o rete
            log.warning("google id_token invalid: %s", type(e).__name__)
            return _fail("invalid", intent)
        if claims.get("iss") not in ISSUERS or claims.get("nonce") != doc["nonce"] or claims.get("aud") != c["client_id"]:
            return _fail("invalid", intent)
        ident = {"sub": claims["sub"], "email": (claims.get("email") or "").lower(), "email_verified": claims.get("email_verified") is True,
                 "name": claims.get("name") or "", "picture": claims.get("picture") or ""}
        dest = f"/invito?token={doc['invite']}&google=ok" if intent == "invite" and doc.get("invite") else doc.get("next") or ""
        kind, user = await resolve_identity(db, ident, intent)
        if kind == "error":
            return _fail(user, intent)
        if kind == "link":
            lid = secrets.token_urlsafe(32)
            await db.oauth_login_links.insert_one({"id": lid, "user_id": user["user_id"], "sub": ident["sub"], "email": ident["email"],
                                                   "dest": dest, "attempts": 0, "expires_at": _now() + TTL})
            resp = RedirectResponse(_front("/login?google_link=1"), status_code=302)
            resp.set_cookie(LINK_COOKIE, lid, max_age=int(TTL.total_seconds()), httponly=True, secure=True, samesite="none", path="/api/oauth/google")
            resp.delete_cookie(STATE_COOKIE, path="/api/oauth/google")
            return resp
        if kind == "create":
            user = {"user_id": f"user_{uuid.uuid4().hex[:12]}", "email": ident["email"], "name": deps["person_name"](ident["name"]) or ident["email"],
                    "role": "admin", "auth_provider": "google", "google_sub": ident["sub"], "active": True,
                    "picture": ident["picture"], "created_at": deps["now_iso"]()}
            await db.users.insert_one(dict(user))
        return await _login(user, ident, dest)

    class LinkIn(BaseModel):
        password: str

    @r.post("/oauth/google/link")
    async def google_link(body: LinkIn, request: Request, response: Response):
        """Collegamento Google a un account esistente che richiede conferma con la password (Super Admin / conflitto)."""
        lid = request.cookies.get(LINK_COOKIE)
        doc = await db.oauth_login_links.find_one({"id": lid}) if lid else None
        if not doc or doc["expires_at"].replace(tzinfo=timezone.utc) < _now() or doc["attempts"] >= 5:
            raise HTTPException(status_code=410, detail="Richiesta di collegamento scaduta. Riprova l'accesso con Google.")
        user = await db.users.find_one({"user_id": doc["user_id"]}, {"_id": 0})
        if not user or not deps["verify_password"](body.password, user.get("password_hash") or ""):
            await db.oauth_login_links.update_one({"id": lid}, {"$inc": {"attempts": 1}})
            raise HTTPException(status_code=401, detail="Password non corretta")
        if user.get("active") is False:
            raise HTTPException(status_code=403, detail="Accesso disabilitato")
        await db.oauth_login_links.delete_one({"id": lid})
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"google_sub": doc["sub"], "last_login_at": deps["now_iso"]()}})
        deps["set_auth_cookie"](response, "access_token", deps["create_access_token"](user["user_id"], user["email"]), 7 * 24 * 3600)
        response.delete_cookie(LINK_COOKIE, path="/api/oauth/google")
        log.info("google account linked user=%s", user["user_id"])
        return {**await deps["user_payload"](user), "dest": doc.get("dest") or ""}

    return r
