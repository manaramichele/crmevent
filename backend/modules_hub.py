"""Moduli e Attivazioni: vista unica dei moduli per organizzazione (Super Admin gestisce, organizzatore consulta)."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import addons

MODULES = [
    {"key": "planner", "name": "Event Planner", "route": "/event-planner",
     "description": "Planimetrie dell'evento su mappa: percorsi, aree, strutture e postazioni."},
    {"key": "eventmap", "name": "Event Map", "route": "/event-map",
     "description": "Mappe animate e video del percorso dell'evento da condividere."},
    {"key": "controlroom", "name": "Control Room", "route": "/control-room",
     "description": "Centrale operativa dell'evento: postazioni, risorse, interventi e report."},
]
KEYS = {m["key"] for m in MODULES}
MODE_LABEL = {"plan": "Incluso nell'abbonamento", "marketplace": "Acquistato dal Marketplace", "superadmin": "Concesso gratuitamente",
              "promo": "Promozione temporanea", "unrestricted": "Accesso completo (organizzazione interna o demo)"}


class StateIn(BaseModel):
    enabled: bool


class CrGrantIn(BaseModel):
    event_ids: list[str] = Field(min_length=1)
    note: Optional[str] = Field(None, max_length=300)


def _now():
    return datetime.now(timezone.utc).isoformat()


def build(db, deps):
    r = APIRouter(prefix="/api")
    member, sa, audit, summary = deps["require_member"], deps["require_superadmin"], deps["record_audit"], deps["addon_summary"]

    async def _org(org_id: str) -> dict:
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1, "nome": 1, "modules_disabled": 1})
        if not org:
            raise HTTPException(status_code=404, detail="Organizzazione non trovata")
        return org

    async def _plan_includes(product: str) -> list:
        cfg = (await db.addon_config.find_one({"id": "config"}, {"_id": 0}) or addons.DEFAULT_CONFIG).get(product) or {}
        return [{"plan": p.upper(), "events": int(n)} for p, n in (cfg.get("included") or {}).items() if int(n or 0) > 0]

    async def _addon(org_id: str, key: str, disabled: bool) -> dict:
        s = await summary(org_id, key)
        names = {e["id"]: e["nome"] for e in await db.events.find({"org_id": org_id}, {"_id": 0, "id": 1, "nome": 1}).to_list(1000)}
        covered = [a for a in s["activations"] if a["covered"]]
        now = _now()
        valid = [g for g in s["grants"] if addons._valid(g, now)]
        modes = set()
        if s["unrestricted"]:
            modes.add("unrestricted")
        if s["included"]:
            modes.add("plan")
        for g in valid:
            modes.add("marketplace" if g["source"] == "purchase" else g["source"])
        sub = s.get("org_subscription")
        active = not disabled and (s["unrestricted"] or bool(sub) or bool(covered) or s["included_free"] > 0 or s["grant_free"] > 0)
        dates = [a.get("assigned_at") for a in covered if a.get("assigned_at")] + [g.get("activated_at") or g.get("created_at") for g in valid]
        exps = [g["expires_at"] for g in valid if g.get("expires_at")]
        limits = {"included": s["included"], "included_used": s["included_used"], "purchased": s["purchased"], "granted": s["granted"],
                  "available": s["included_free"] + s["grant_free"]}
        if key == "eventmap":
            limits |= {k: s.get(k, 0) for k in ("videos_total", "videos_used", "videos_available")}
        if key == "planner":
            limits |= {"planimetrie": s.get("planimetrie", 0)}
        return {"active": active, "modes": sorted(modes), "plan": s.get("plan_label"), "plan_includes": await _plan_includes(key),
                "org_subscription": bool(sub), "activated_at": min(dates) if dates else None, "expires_at": (sub or {}).get("expires_at") or (min(exps) if exps else None),
                "limits": limits, "events": [{"id": a["event_id"], "nome": names.get(a["event_id"], "—"), "source": a.get("source"), "expires_at": a.get("expires_at")} for a in covered],
                "grants": [{k: g.get(k) for k in ("id", "source", "status", "scope", "events_total", "videos_total", "package_name", "expires_at", "created_at", "note")} for g in s["grants"]]}

    async def _controlroom(org_id: str, disabled: bool) -> dict:
        ps = await db.controlroom_purchases.find({"org_id": org_id, "status": {"$in": ["active", "revoked", "refunded"]}}, {"_id": 0, "history": 0}).sort("created_at", 1).to_list(1000)
        act = [p for p in ps if p["status"] == "active"]
        modes = sorted({"superadmin" if p.get("source") == "superadmin" else "marketplace" for p in act})
        dates = [p.get("activated_at") or p.get("created_at") for p in act]
        return {"active": not disabled and bool(act), "modes": modes, "plan": None, "plan_includes": [], "price_net": 119.0,
                "activated_at": min(dates) if dates else None, "expires_at": None,
                "limits": {"events_active": len(act), "purchased": sum(p.get("source") != "superadmin" for p in act), "granted": sum(p.get("source") == "superadmin" for p in act)},
                "events": [{"id": p["event_id"], "nome": p.get("event_name"), "source": p.get("source") or "purchase", "purchase_id": p["id"], "activated_at": p.get("activated_at")} for p in act],
                "grants": [{k: p.get(k) for k in ("id", "event_id", "event_name", "status", "source", "amount_net", "activated_at", "created_by", "note")} for p in ps]}

    async def _modules(org_id: str) -> list:
        org = await _org(org_id)
        off = set(org.get("modules_disabled") or [])
        out = []
        for m in MODULES:
            d = await (_controlroom(org_id, m["key"] in off) if m["key"] == "controlroom" else _addon(org_id, m["key"], m["key"] in off))
            out.append({**m, **d, "disabled": m["key"] in off, "mode_labels": [MODE_LABEL[x] for x in d["modes"]]})
        return out

    def _is_admin(u: dict) -> bool:
        return u.get("org_role") in ("admin_org", "superadmin")

    @r.get("/org/modules")
    async def org_modules(user: dict = Depends(member)):
        if not _is_admin(user):
            raise HTTPException(status_code=403, detail="Sezione riservata all'Admin Organizzazione")
        mods = await _modules(user["org_id"])
        for m in mods:
            m.pop("grants", None)
        return {"modules": mods}

    @r.get("/org/modules/access")
    async def org_access(user: dict = Depends(member)):
        return {m["key"]: m["active"] for m in await _modules(user["org_id"])}

    @r.get("/platform/orgs/{org_id}/modules")
    async def sa_modules(org_id: str, _: dict = Depends(sa)):
        hist = await db.audit_logs.find({"org_id": org_id, "action": {"$regex": "^(addon_|controlroom_|module_)"}}, {"_id": 0}).sort("created_at", -1).to_list(200)
        return {"modules": await _modules(org_id), "history": hist}

    @r.post("/platform/orgs/{org_id}/modules/{key}/state")
    async def sa_state(org_id: str, key: str, body: StateIn, admin: dict = Depends(sa)):
        if key not in KEYS:
            raise HTTPException(status_code=404, detail="Modulo non trovato")
        org = await _org(org_id)
        await db.organizations.update_one({"id": org_id}, {"$pull" if body.enabled else "$addToSet": {"modules_disabled": key}})
        name = next(m["name"] for m in MODULES if m["key"] == key)
        await audit(admin, "module_enabled" if body.enabled else "module_disabled", org_id=org_id, org_name=org.get("nome"),
                    detail=f"{name} · {'riattivato' if body.enabled else 'disattivato (dati conservati)'}", meta={"module": key})
        return {"ok": True}

    @r.post("/platform/orgs/{org_id}/modules/controlroom/grant")
    async def sa_cr_grant(org_id: str, body: CrGrantIn, admin: dict = Depends(sa)):
        org = await _org(org_id)
        evs = await db.events.find({"org_id": org_id, "id": {"$in": body.event_ids}}, {"_id": 0, "id": 1, "nome": 1}).to_list(500)
        if len(evs) != len(set(body.event_ids)):
            raise HTTPException(status_code=404, detail="Evento non trovato in questa organizzazione")
        created = 0
        for ev in evs:
            if await db.controlroom_purchases.find_one({"org_id": org_id, "event_id": ev["id"], "status": "active"}, {"_id": 1}):
                continue
            now = _now()
            await db.controlroom_purchases.insert_one({"id": uuid.uuid4().hex, "org_id": org_id, "event_id": ev["id"], "event_name": ev["nome"], "status": "active",
                                                       "source": "superadmin", "amount_net": 0, "note": body.note, "created_by": admin.get("email"),
                                                       "created_at": now, "activated_at": now})
            created += 1
            await audit(admin, "controlroom_granted", org_id=org_id, org_name=org.get("nome"), detail=f"{ev['nome']} · concessione gratuita{' · ' + body.note if body.note else ''}")
        return {"created": created}

    @r.post("/platform/orgs/{org_id}/modules/controlroom/{pid}/revoke")
    async def sa_cr_revoke(org_id: str, pid: str, admin: dict = Depends(sa)):
        org = await _org(org_id)
        p = await db.controlroom_purchases.find_one({"id": pid, "org_id": org_id}, {"_id": 0})
        if not p:
            raise HTTPException(status_code=404, detail="Attivazione non trovata")
        if p.get("source") != "superadmin" or p["status"] != "active":
            raise HTTPException(status_code=400, detail="Si possono revocare solo le concessioni gratuite attive: gli acquisti restano invariati")
        await db.controlroom_purchases.update_one({"id": pid}, {"$set": {"status": "revoked", "revoked_at": _now(), "revoked_by": admin.get("email")}})
        await audit(admin, "controlroom_grant_revoked", org_id=org_id, org_name=org.get("nome"), detail=f"{p.get('event_name')} · dati conservati")
        return {"ok": True}

    return {"router": r}
