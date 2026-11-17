"""Control Room: importazione delle postazioni già disegnate in Event Planner (nessuna anagrafica o postazione duplicata)."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

import event_routes as EVR
from controlroom_itv import _dist

# Mappatura deterministica dai nomi della libreria Event Planner alle categorie iniziali Control Room
NAME_MAP = {"ristoro": "ristoro", "punto acqua": "ristoro", "ambulanza": "ambulanza", "area medica": "sanitario", "primo soccorso": "sanitario",
            "postazione volontari": "volontari", "coordinamento": "volontari", "direzione gara": "volontari", "segreteria": "volontari",
            "punto controllo percorso": "controllo", "postazione di controllo": "controllo", "chiusura stradale": "chiusura", "estintore": "vigili_fuoco"}
CAT_MAP = {"viabilità": "viabilita", "sicurezza": "controllo", "staff": "volontari"}


class ImportIn(BaseModel):
    project_id: str
    feature_ids: list[str] = Field(min_length=1, max_length=1000)
    categories: dict[str, str] = {}
    with_staff: bool = True
    update_positions: bool = False


def _now():
    return datetime.now(timezone.utc).isoformat()


def _pos(f):
    p = f.get("properties") or {}
    g = f.get("geometry") or {}
    if p.get("center"):
        return p["center"][:2]
    if g.get("type") == "Point":
        return g["coordinates"][:2]
    return None


def _guess(p, keys):
    n = (p.get("nome") or "").lower()
    k = next((v for name, v in NAME_MAP.items() if name in n), None) or CAT_MAP.get((p.get("categoria") or "").lower(), "altro")
    return k if k in keys else ("altro" if "altro" in keys else next(iter(keys)))


def attach(r, db, deps, H):
    ctx, q, settings, touch = H["ctx"], H["q"], H["settings"], H["touch"]
    base = "/controlroom/events/{event_id}/ops/planner"

    async def resp(u, eid):
        _, pm = await ctx(u, eid, write=True)
        return pm

    async def route_km(u, eid):
        routes = await EVR.list_routes(db, u["org_id"], eid, deps["resolve_attachment"])
        rt = next((x for x in routes if x["format"] == "GPX"), None) or (routes[0] if routes else None)
        if not rt:
            return None
        try:
            data, _ = await deps["read_file_rec"](rt["_rec"])
            pts = [(p[0], p[1]) for p in EVR.coords(data, rt["filename"])]
        except Exception:
            return None
        acc = [0.0]
        for i in range(1, len(pts)):
            acc.append(acc[-1] + _dist(pts[i - 1], pts[i]))

        def km(c):
            best = min(range(len(pts)), key=lambda i: _dist(pts[i], c)) if pts else None
            return round(acc[best] / 1000, 1) if best is not None and _dist(pts[best], c) <= 500 else None
        return km

    @r.get(base)
    async def candidates(event_id: str, u: dict = Depends(deps["require_admin"])):
        await resp(u, event_id)
        s = await settings(u, event_id)
        keys = [c["key"] for c in s["categories"]]
        done = {p["planner_feature_id"]: p["id"] for p in await db.cr_posts.find(q(u, event_id, planner_feature_id={"$ne": None}), {"_id": 0, "planner_feature_id": 1, "id": 1}).to_list(5000) if p.get("planner_feature_id")}
        out = []
        for pr in await db.planner_projects.find({"org_id": u["org_id"], "evento_id": event_id, "archiviato": {"$ne": True}}, {"_id": 0, "id": 1, "nome": 1, "features": 1, "layers": 1}).sort("created_at", 1).to_list(50):
            layers = {x.get("id"): x.get("nome") for x in pr.get("layers") or []}
            staff = {}
            for sh in await db.shifts.find({"org_id": u["org_id"], "planner_project_id": pr["id"]}, {"_id": 0, "planner_station_id": 1}).to_list(5000):
                staff[sh["planner_station_id"]] = staff.get(sh["planner_station_id"], 0) + 1
            feats = []
            for f in pr.get("features") or []:
                p, c = f.get("properties") or {}, _pos(f)
                if not c or not p.get("id"):
                    continue
                feats.append({"id": p["id"], "nome": p.get("nome") or "Elemento", "categoria": p.get("categoria"), "livello": layers.get(p.get("layer_id")), "lng": c[0], "lat": c[1],
                              "persone": staff.get(p["id"], 0), "suggested": _guess(p, keys), "imported_post_id": done.get(p["id"])})
            out.append({"id": pr["id"], "nome": pr["nome"], "features": feats})
        return {"projects": out}

    @r.post(base + "/import")
    async def do_import(event_id: str, body: ImportIn, u: dict = Depends(deps["require_admin"])):
        await resp(u, event_id)
        pr = await db.planner_projects.find_one({"org_id": u["org_id"], "evento_id": event_id, "id": body.project_id}, {"_id": 0, "features": 1, "layers": 1, "nome": 1})
        if not pr:
            raise HTTPException(status_code=404, detail="Progetto Event Planner non trovato per questo evento")
        s = await settings(u, event_id)
        keys = {c["key"] for c in s["categories"]}
        feats = {(f.get("properties") or {}).get("id"): f for f in pr.get("features") or []}
        km = await route_km(u, event_id)
        staff_ids = {x["persona_id"]: x["id"] for x in await db.staff.find({"org_id": u["org_id"], "evento_id": event_id}, {"_id": 0, "persona_id": 1, "id": 1}).to_list(5000)}
        in_cr = {x["persona_id"]: x for x in await db.cr_resources.find(q(u, event_id, persona_id={"$ne": None}), {"_id": 0, "persona_id": 1, "id": 1, "post_id": 1}).to_list(5000) if x.get("persona_id")}
        created = updated = people = skipped = 0
        for fid in body.feature_ids:
            f = feats.get(fid)
            c = _pos(f) if f else None
            if not c:
                skipped += 1
                continue
            p = f["properties"]
            cur = await db.cr_posts.find_one(q(u, event_id, planner_feature_id=fid), {"_id": 0, "id": 1})
            if cur:
                if body.update_positions:
                    await db.cr_posts.update_one(q(u, event_id, id=cur["id"]), {"$set": {"lng": c[0], "lat": c[1], "updated_at": _now(), "updated_by": u.get("email")}, "$inc": {"version": 1}})
                    updated += 1
                post_id = cur["id"]
            else:
                cat = body.categories.get(fid) if body.categories.get(fid) in keys else _guess(p, keys)
                post_id = uuid.uuid4().hex
                await db.cr_posts.insert_one({"id": post_id, "org_id": u["org_id"], "event_id": event_id, "nome": (p.get("nome") or "Postazione")[:120], "codice": None, "categoria": cat,
                                              "sector_id": None, "km": km(c) if km else None, "lng": c[0], "lat": c[1], "responsabile": None, "telefono": None, "apertura": None, "chiusura": None,
                                              "previsti": 0, "presenti_manuali": 0, "attiva": True, "note": f"Da Event Planner · {pr['nome']}", "planner_project_id": body.project_id,
                                              "planner_feature_id": fid, "version": 1, "created_at": _now(), "created_by": u.get("email"), "updated_at": _now(), "updated_by": u.get("email")})
                created += 1
            if body.with_staff:
                shifts = await db.shifts.find({"org_id": u["org_id"], "planner_project_id": body.project_id, "planner_station_id": fid}, {"_id": 0, "id": 1, "persona_id": 1}).to_list(500)
                for sh in shifts:
                    pid = sh.get("persona_id")
                    if pid not in staff_ids:
                        continue
                    if pid in in_cr:
                        if not in_cr[pid].get("post_id"):
                            await db.cr_resources.update_one(q(u, event_id, id=in_cr[pid]["id"]), {"$set": {"post_id": post_id, "shift_id": sh["id"]}, "$inc": {"version": 1}})
                            in_cr[pid]["post_id"] = post_id
                            people += 1
                        continue
                    doc = {"id": uuid.uuid4().hex, "org_id": u["org_id"], "event_id": event_id, "kind": "persona", "persona_id": pid, "staff_id": staff_ids[pid], "tipologia": "Volontario",
                           "post_id": post_id, "sector_id": None, "shift_id": sh["id"], "caposquadra": False, "stato": "disponibile", "presente": False, "gps": None,
                           "version": 1, "created_at": _now(), "created_by": u.get("email"), "updated_at": _now(), "updated_by": u.get("email")}
                    await db.cr_resources.insert_one(doc)
                    in_cr[pid] = doc
                    people += 1
            if f and not cur:
                await db.cr_posts.update_one(q(u, event_id, id=post_id), {"$set": {"previsti": await db.cr_resources.count_documents(q(u, event_id, post_id=post_id, kind="persona"))}})
        if created or updated or people:
            await touch(u, event_id, "create", "postazione", None, f"Importazione Event Planner «{pr['nome']}»: {created} nuove, {updated} aggiornate, {people} persone")
        return {"created": created, "updated": updated, "people": people, "skipped": skipped}
