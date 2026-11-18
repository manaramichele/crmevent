"""Anagrafica Staff/Volontari: luogo di nascita da codice catastale, indirizzo via Google Places, stato Da classificare."""
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException

_CAT = json.loads((Path(__file__).parent / "data" / "catastali.json").read_text(encoding="utf-8"))
_OMO = {"L": "0", "M": "1", "N": "2", "P": "3", "Q": "4", "R": "5", "S": "6", "T": "7", "U": "8", "V": "9"}
_CF_RE = re.compile(r"^[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]$")
PLACES = "https://places.googleapis.com/v1"


def _now():
    return datetime.now(timezone.utc).isoformat()


def catastale_of(cf: str) -> Optional[str]:
    cf = re.sub(r"[^A-Z0-9]", "", (cf or "").upper())
    if not _CF_RE.match(cf):
        return None
    return cf[11] + "".join(_OMO.get(c, c) for c in cf[12:15])


def lookup(code: str, birth: Optional[str] = None) -> Optional[dict]:
    rows = _CAT.get((code or "").upper())
    if not rows:
        return None
    pick = None
    if birth:
        pick = next((r for r in rows if (not r[2] or r[2] <= birth) and (not r[3] or birth <= r[3])), None)
    pick = pick or next((r for r in rows if not r[3]), None) or max(rows, key=lambda r: r[3])
    estero = pick[4] == "E"
    current = next((r for r in rows if not r[3]), None)
    return {"codice": code.upper(), "nome": pick[0], "provincia": None if estero else pick[1], "estero": estero,
            "soppresso": bool(pick[3]) and not current, "nome_attuale": current[0] if current and current[0] != pick[0] else None,
            "luogo": pick[0] if estero else f"{pick[0]} ({pick[1]})"}


def birth_place_from_cf(cf: str, birth: Optional[str] = None) -> Optional[str]:
    code = catastale_of(cf)
    hit = lookup(code, birth) if code else None
    return hit["luogo"] if hit else None


def _parse_components(comps: list) -> dict:
    by = {}
    for c in comps or []:
        for t in c.get("types", []):
            by.setdefault(t, c)
    g = lambda t, k="longText": (by.get(t) or {}).get(k) or None  # noqa: E731
    country = g("country", "shortText")
    via = g("route")
    out = {"indirizzo": f"{via} {g('street_number')}".strip() if via and g("street_number") else via,
           "cap": g("postal_code"),
           "citta": g("locality") or g("postal_town") or g("administrative_area_level_3"),
           "provincia": g("administrative_area_level_2", "shortText"),
           "regione": g("administrative_area_level_1"),
           "nazione": g("country")}
    if country == "IT" and out["provincia"] and not re.fullmatch(r"[A-Z]{2}", out["provincia"]):
        out["provincia"] = None
    return out


def build(db, deps: dict):
    r = APIRouter(prefix="/api")
    require_admin = deps["require_admin"]
    pref_label = deps["pref_label"]
    cf_valid = deps["cf_valid"]

    @r.get("/anagrafica/cf-lookup")
    async def cf_lookup(cf: str, data_nascita: Optional[str] = None, _: dict = Depends(require_admin)):
        code = catastale_of(cf) if cf_valid(cf) else None
        if not code:
            return {"valid": False, "detail": "Codice fiscale non valido"}
        hit = lookup(code, (data_nascita or "")[:10] or None)
        return {"valid": True, "codice": code, "found": bool(hit), **(hit or {})}

    def _key():
        return os.environ.get("GOOGLE_MAPS_API_KEY")

    @r.get("/anagrafica/places/status")
    async def places_status(_: dict = Depends(require_admin)):
        return {"enabled": bool(_key())}

    @r.get("/anagrafica/places/autocomplete")
    async def places_ac(q: str, session: Optional[str] = None, _: dict = Depends(require_admin)):
        if not _key():
            raise HTTPException(status_code=503, detail="Ricerca indirizzi Google non configurata")
        if len(q.strip()) < 3:
            return {"suggestions": []}
        body = {"input": q.strip()[:200], "languageCode": "it", "includedPrimaryTypes": ["street_address", "premise", "subpremise", "route", "locality", "postal_code"]}
        if session:
            body["sessionToken"] = session
        async with httpx.AsyncClient(timeout=8) as c:
            res = await c.post(f"{PLACES}/places:autocomplete", json=body, headers={"X-Goog-Api-Key": _key()})
        if res.status_code != 200:
            raise HTTPException(status_code=502, detail="Google non ha risposto alla ricerca dell'indirizzo")
        out = []
        for s in res.json().get("suggestions", []):
            p = s.get("placePrediction") or {}
            if p.get("placeId"):
                out.append({"place_id": p["placeId"], "text": (p.get("text") or {}).get("text", "")})
        return {"suggestions": out}

    @r.get("/anagrafica/places/{place_id}")
    async def places_detail(place_id: str, session: Optional[str] = None, _: dict = Depends(require_admin)):
        if not _key():
            raise HTTPException(status_code=503, detail="Ricerca indirizzi Google non configurata")
        if not re.fullmatch(r"[A-Za-z0-9_\-]{10,300}", place_id):
            raise HTTPException(status_code=400, detail="Indirizzo non valido")
        params = {"languageCode": "it", **({"sessionToken": session} if session else {})}
        async with httpx.AsyncClient(timeout=8) as c:
            res = await c.get(f"{PLACES}/places/{place_id}", params=params,
                              headers={"X-Goog-Api-Key": _key(), "X-Goog-FieldMask": "addressComponents,formattedAddress"})
        if res.status_code != 200:
            raise HTTPException(status_code=502, detail="Google non ha restituito i dettagli dell'indirizzo")
        d = res.json()
        return {"formatted": d.get("formattedAddress"), **_parse_components(d.get("addressComponents"))}

    async def ensure_link(org_id: str, person_id: str, evento_id: str, av: dict) -> None:
        """Inserisce la persona nell'elenco Staff/Volontari dell'evento come Da classificare (idempotente)."""
        cur = await db.staff.find_one({"org_id": org_id, "persona_id": person_id, "evento_id": evento_id}, {"_id": 0, "id": 1, "categoria": 1})
        team = None
        if av.get("ristoro_team_id"):
            team = await db.teams.find_one({"org_id": org_id, "evento_id": evento_id, "id": av["ristoro_team_id"]}, {"_id": 0, "id": 1, "nome": 1})
        team_set = {"team_id": team["id"], "ruolo": team["nome"], "mansione_auto": True} if team else {}
        if cur:
            upd = dict(team_set)
            if cur.get("categoria") == "da_classificare":
                upd["preferenza"] = pref_label(av) or ""
            if upd:
                await db.staff.update_one({"org_id": org_id, "id": cur["id"]}, {"$set": {**upd, "updated_at": _now()}})
            return
        cat = av.get("ruolo_evento") if av.get("ruolo_evento") in ("staff", "volontario") else "da_classificare"
        await db.staff.insert_one({"id": str(uuid.uuid4()), "org_id": org_id, "persona_id": person_id, "evento_id": evento_id,
                                   "categoria": cat, "stato": "confermato" if av.get("stato") == "confermata" else "da_contattare",
                                   "preferenza": pref_label(av) or "", "origine": "link_disponibilita", "availability_id": av.get("id"),
                                   **team_set, "created_at": _now()})

    async def migrate() -> dict:
        if await db.schema_meta.find_one({"id": "avail_to_staff_v1"}):
            return {"skipped": True}
        n = 0
        async for a in db.availabilities.find({}, {"_id": 0}):
            if not (a.get("persona_id") and a.get("evento_id")):
                continue
            if not await db.persons.find_one({"org_id": a["org_id"], "id": a["persona_id"]}, {"_id": 1}):
                continue
            before = await db.staff.count_documents({"org_id": a["org_id"], "persona_id": a["persona_id"], "evento_id": a["evento_id"]})
            await ensure_link(a["org_id"], a["persona_id"], a["evento_id"], a)
            n += 0 if before else 1
        await db.schema_meta.insert_one({"id": "avail_to_staff_v1", "applied_at": _now(), "created_links": n})
        return {"created_links": n}

    return {"router": r, "ensure_link": ensure_link, "migrate": migrate, "birth_place_from_cf": birth_place_from_cf}
