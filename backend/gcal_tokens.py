"""Token OAuth Google Calendar: cifratura AES-256-GCM, rinnovo persistente, classificazione errori. Mai loggare i token."""
import base64
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger("gcal_tokens")
TOKEN_URL = "https://oauth2.googleapis.com/token"

MESSAGES = {
    "reauthorization_required": "La connessione con Google Calendar non è più attiva. Ricollega il tuo account.",
    "insufficient_scope": "CRMEvent non dispone delle autorizzazioni necessarie. Ricollega Google Calendar.",
    "temporary": "Google Calendar non è momentaneamente disponibile. Riprova tra qualche minuto.",
    "network": "Impossibile raggiungere Google Calendar. Riprova.",
    "config": "Configurazione OAuth Google Calendar non valida: contatta l'amministratore.",
    "not_connected": "Google Calendar non collegato",
    "key_missing": "Chiave di cifratura dei token non configurata sul server (GOOGLE_TOKEN_ENCRYPTION_KEY).",
}


class GCalError(Exception):
    def __init__(self, code: str):
        super().__init__(MESSAGES.get(code, code))
        self.code = code
        self.message = MESSAGES.get(code, code)


def _keys() -> list:
    """GOOGLE_TOKEN_ENCRYPTION_KEY = "kid:base64key[,kid:base64key...]": la prima cifra, tutte decifrano (rotazione)."""
    out = []
    for part in (os.environ.get("GOOGLE_TOKEN_ENCRYPTION_KEY") or "").split(","):
        kid, _, b64 = part.strip().partition(":")
        if kid and b64:
            key = base64.b64decode(b64)
            if len(key) != 32:
                raise ValueError(f"Chiave {kid}: servono 256 bit")
            out.append((kid, key))
    return out


def key_configured() -> bool:
    try:
        return bool(_keys())
    except Exception:  # noqa: BLE001
        return False


def encrypt(tokens: dict) -> dict:
    keys = _keys()
    if not keys:
        raise GCalError("key_missing")
    kid, key = keys[0]
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, json.dumps(tokens).encode(), kid.encode())
    return {"v": 1, "kid": kid, "nonce": base64.b64encode(nonce).decode(), "ct": base64.b64encode(ct).decode()}


def decrypt(enc: dict) -> dict:
    key = dict(_keys()).get(enc.get("kid"))
    if not key:
        raise GCalError("key_missing")
    try:
        raw = AESGCM(key).decrypt(base64.b64decode(enc["nonce"]), base64.b64decode(enc["ct"]), enc["kid"].encode())
    except Exception:  # noqa: BLE001 - tag non valido / chiave errata: nessun dettaglio sensibile
        log.error("gcal token decrypt failed kid=%s", enc.get("kid"))
        raise GCalError("key_missing")
    return json.loads(raw)


def tokens_of(conn: dict) -> dict:
    if conn.get("tokens_enc"):
        return decrypt(conn["tokens_enc"])
    return conn.get("tokens") or {}  # record legacy in chiaro (migrazione esplicita: scripts/migrate_gcal_tokens.py)


def expiry_from(tokens: dict) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=int(tokens.get("expires_in") or 3600))).isoformat()


def store_fields(tokens: dict) -> dict:
    """Campi da salvare: sempre cifrati; senza chiave il salvataggio fallisce (mai in chiaro)."""
    clean = {k: v for k, v in tokens.items() if k in ("access_token", "refresh_token", "token_type", "scope", "expires_in")}
    return {"tokens_enc": encrypt(clean), "expires_at": expiry_from(clean)}


def _refresh(refresh_token: str, client_id: str, client_secret: str) -> dict:
    try:
        resp = requests.post(TOKEN_URL, data={"grant_type": "refresh_token", "refresh_token": refresh_token,
                                              "client_id": client_id, "client_secret": client_secret}, timeout=20)
    except requests.RequestException:
        raise GCalError("network")
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code == 200 and data.get("access_token"):
        return data
    err = (data or {}).get("error")
    log.warning("gcal refresh failed http=%s error=%s", resp.status_code, err)
    if resp.status_code >= 500:
        raise GCalError("temporary")
    if err == "invalid_grant":
        raise GCalError("reauthorization_required")
    if err in ("invalid_client", "unauthorized_client"):
        raise GCalError("config")
    if err == "invalid_scope":
        raise GCalError("insufficient_scope")
    raise GCalError("temporary")


async def _mark(db, user_id: str, status: str, reason=None):
    await db.calendar_connections.update_one({"user_id": user_id}, {"$set": {"status": status, "status_reason": reason,
                                                                         "status_at": datetime.now(timezone.utc).isoformat()}})


async def load(db, user_id: str, force_refresh: bool = False) -> dict:
    """Connessione dell'utente con token decifrati e access token valido (rinnovato e salvato se scaduto)."""
    import gcal_utils
    conn = await db.calendar_connections.find_one({"user_id": user_id}, {"_id": 0}) if user_id else None
    if not conn:
        raise GCalError("not_connected")
    tokens = tokens_of(conn)
    exp = conn.get("expires_at")
    fresh = exp and datetime.fromisoformat(exp) > datetime.now(timezone.utc) + timedelta(seconds=90)
    if fresh and not force_refresh and tokens.get("access_token"):
        return {**conn, "tokens": tokens}
    if not tokens.get("refresh_token"):
        await _mark(db, user_id, "reauthorization_required", "missing_refresh_token")
        raise GCalError("reauthorization_required")
    try:
        new = _refresh(tokens["refresh_token"], gcal_utils.CLIENT_ID, gcal_utils.CLIENT_SECRET)
    except GCalError as e:
        if e.code in ("reauthorization_required", "insufficient_scope"):
            await _mark(db, user_id, "reauthorization_required", e.code)
        elif e.code in ("temporary", "network"):
            await _mark(db, user_id, "temporary_error", e.code)
        raise
    merged = {**tokens, **new, "refresh_token": new.get("refresh_token") or tokens["refresh_token"]}
    rev = conn.get("token_rev") or 0
    upd = {**store_fields(merged), "last_refresh_at": datetime.now(timezone.utc).isoformat(), "status": "connected", "status_reason": None}
    res = await db.calendar_connections.update_one({"user_id": user_id, "token_rev": conn.get("token_rev")},
                                                   {"$set": {**upd, "token_rev": rev + 1}, "$unset": {"tokens": ""}})
    if not res.matched_count:  # rinnovo concorrente già salvato: usa il più recente
        latest = await db.calendar_connections.find_one({"user_id": user_id}, {"_id": 0})
        return {**latest, "tokens": tokens_of(latest)} if latest else {**conn, "tokens": merged}
    return {**conn, **upd, "tokens": merged}


def classify_api_error(e: Exception) -> str:
    from googleapiclient.errors import HttpError
    if isinstance(e, GCalError):
        return e.code
    if isinstance(e, HttpError):
        st = getattr(e.resp, "status", 0)
        txt = str(getattr(e, "content", b"") or b"")[:400]
        if st == 401:
            return "auth"
        if st == 403 and ("insufficient" in txt.lower() or "SCOPE" in txt):
            return "insufficient_scope"
        if st >= 500 or st == 429:
            return "temporary"
        return "api"
    if isinstance(e, (requests.RequestException, OSError, TimeoutError)):
        return "network"
    return "api"


async def run(db, user_id: str, fn):
    """Esegue fn(conn) con token validi; su 401 rinnova una volta e riprova. Solleva GCalError con messaggio specifico."""
    conn = await load(db, user_id)
    try:
        return fn(conn)
    except Exception as e:  # noqa: BLE001
        code = classify_api_error(e)
        if code == "auth":
            conn = await load(db, user_id, force_refresh=True)
            try:
                return fn(conn)
            except Exception as e2:  # noqa: BLE001
                code = classify_api_error(e2)
                if code == "auth":
                    await _mark(db, user_id, "reauthorization_required", "api_401")
                    raise GCalError("reauthorization_required")
        if code == "insufficient_scope":
            await _mark(db, user_id, "reauthorization_required", code)
        if code in MESSAGES:
            raise GCalError(code)
        log.error("gcal api error: %s", type(e).__name__)
        raise
