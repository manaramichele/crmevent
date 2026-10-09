"""Normalizzazione maiuscole/minuscole delle anagrafiche (persone, organizzazioni/aziende, luoghi)."""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

CONNECTORS = {"di", "del", "della", "dello", "dei", "degli", "delle", "da", "dal", "dalla", "dallo", "dai", "dalle", "e", "ed",
              "a", "al", "alla", "allo", "ai", "agli", "alle", "in", "nel", "nella", "nello", "nei", "nelle", "per", "con", "su",
              "sul", "sulla", "sui", "il", "lo", "la", "i", "gli", "le", "l", "d", "un", "una", "uno", "of", "the", "and",
              "dell", "nell", "all", "dall", "sull", "coll", "quell"}
_SPLIT = re.compile(r"([-'\u2019])")


def _cap(part: str) -> str:
    low = part.lower()
    if len(low) > 2 and low.startswith("mc"):
        return "Mc" + low[2].upper() + low[3:]
    return low[:1].upper() + low[1:]


def _is_styled(w: str) -> bool:
    """Grafia intenzionale (McDonald, CRMEvent, DeLuca): iniziale maiuscola + altre maiuscole, non tutto maiuscolo."""
    letters = [c for c in w if c.isalpha()]
    return bool(letters) and w[0].isupper() and any(c.isupper() for c in letters[1:]) and not all(c.isupper() for c in letters)


def _word_person(w: str) -> str:
    if _is_styled(w):
        return w
    return "".join(p if _SPLIT.fullmatch(p) else _cap(p) for p in _SPLIT.split(w))


def person_name(s: Optional[str]) -> Optional[str]:
    if not isinstance(s, str) or not s.strip():
        return s
    return " ".join(_word_person(w) for w in s.split())


def _word_business(w: str, first: bool) -> str:
    letters = [c for c in w if c.isalpha()]
    if not letters or any(c.isdigit() for c in w):
        return w
    if len(letters) > 1 and all(c.isupper() for c in letters):
        return w  # sigle e marchi (ASD, IRONMAN)
    if _is_styled(w):
        return w
    parts = _SPLIT.split(w)
    out = []
    for i, p in enumerate(parts):
        if _SPLIT.fullmatch(p) or not p:
            out.append(p)
        elif p.lower() in CONNECTORS and not (first and i == 0):
            out.append(p.lower())
        else:
            out.append(_cap(p))
    return "".join(out)


def business_name(s: Optional[str]) -> Optional[str]:
    if not isinstance(s, str) or not s.strip():
        return s
    return " ".join(_word_business(w, i == 0) for i, w in enumerate(s.split()))


KINDS = {"person": person_name, "business": business_name, "place": business_name}
PLACE = {"citta": "place", "regione": "place", "nazione": "place"}
FIELD_RULES = {
    "persons": {"nome": "person", "cognome": "person", **PLACE},
    "companies": {"nome": "business", **PLACE},
    "structures": {"nome": "business", "citta": "place"},
    "teams": {"nome": "business"},
    "organizations": {"nome": "business"},
    "users": {"name": "person", "nome": "person", "cognome": "person"},
    "leads": {"nome": "person", "cognome": "person", "organizzazione": "business", "citta": "place"},
    "demo_requests": {"nome": "person", "organizzazione": "business"},
    "billing": {"ragione_sociale": "business", "nome": "person", "cognome": "person", "citta": "place"},
}


def normalize_fields(coll: str, data: dict) -> dict:
    rules = FIELD_RULES.get(coll)
    if not rules or not isinstance(data, dict):
        return data
    return {k: (KINDS[rules[k]](v) if k in rules and isinstance(v, str) else v) for k, v in data.items()}


class ApplyIn(BaseModel):
    items: list[dict]


def build_router(db, require_superadmin, record_audit) -> APIRouter:
    r = APIRouter(prefix="/api")
    preview_colls = [c for c in FIELD_RULES if c != "billing"]

    @r.get("/platform/normalize/preview")
    async def preview(admin: dict = Depends(require_superadmin)):
        out = []
        for coll in preview_colls:
            rules = FIELD_RULES[coll]
            key = "user_id" if coll == "users" else "id"
            async for d in db[coll].find({}, {"_id": 0, key: 1, "org_id": 1, **{f: 1 for f in rules}}):
                for f, kind in rules.items():
                    v = d.get(f)
                    if isinstance(v, str) and v.strip() and KINDS[kind](v) != v:
                        out.append({"coll": coll, "id": d.get(key), "field": f, "old": v, "new": KINDS[kind](v)})
                        if len(out) >= 2000:
                            return {"items": out, "truncated": True}
        return {"items": out, "truncated": False}

    @r.post("/platform/normalize/apply")
    async def apply(body: ApplyIn, admin: dict = Depends(require_superadmin)):
        done = 0
        for it in body.items[:2000]:
            coll, f = it.get("coll"), it.get("field")
            kind = FIELD_RULES.get(coll, {}).get(f)
            if coll not in preview_colls or not kind:
                raise HTTPException(status_code=400, detail="Elemento non valido")
            key = "user_id" if coll == "users" else "id"
            d = await db[coll].find_one({key: it.get("id")}, {"_id": 0, f: 1})
            if d and isinstance(d.get(f), str):
                new = KINDS[kind](d[f])
                if new != d[f]:
                    await db[coll].update_one({key: it["id"]}, {"$set": {f: new}})
                    done += 1
        await record_audit(admin, "normalize_apply", detail=f"{done} campi corretti")
        return {"updated": done}

    return r
