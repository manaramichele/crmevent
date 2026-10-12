"""Sincronizzazione stato abbonamento CRMEvent → attributi contatto Brevo (promemoria di scadenza gestiti da automazioni Brevo)."""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import brevo_funnel

log = logging.getLogger("brevo_subscriptions")
ATTRS = {"CRM_PIANO": "text", "CRM_SCADENZA": "date", "CRM_INIZIO": "date", "CRM_DURATA": "float", "CRM_STATO": "text",
         "CRM_ORGANIZZAZIONE": "text", "CRM_ORG_ID": "text", "CRM_RINNOVO_AUTO": "boolean"}
STATO = {"trial": "Trial", "active": "Attivo", "expiring": "In scadenza", "expired": "Scaduto", "suspended": "Scaduto"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def org_attrs(org: dict, st: dict) -> Optional[dict]:
    if not st.get("enabled") or st.get("org_type") != "cliente":
        return None
    return {"CRM_PIANO": st.get("plan_label") or st.get("paid_plan_label"), "CRM_SCADENZA": (st.get("expires_at") or "")[:10] or None,
            "CRM_INIZIO": (st.get("activated_at") or st.get("trial_start") or "")[:10] or None,
            "CRM_DURATA": st.get("cycle_months") if st.get("cycle_months") in (6, 12) else None, "CRM_STATO": STATO.get(st.get("sub_status"), "Scaduto"),
            "CRM_ORGANIZZAZIONE": org.get("nome"), "CRM_ORG_ID": org["id"], "CRM_RINNOVO_AUTO": bool(st.get("auto_renew"))}


def pick(cands: list) -> dict:
    """Stessa email su più organizzazioni: prevale quella non scaduta con la scadenza più vicina (CRM_ORG_ID la identifica)."""
    return sorted(cands, key=lambda a: (a["CRM_STATO"] == "Scaduto", a.get("CRM_SCADENZA") or "9999", a["CRM_ORG_ID"]))[0]


class SyncAllIn(BaseModel):
    only_failed: bool = False


def build(db, deps: dict):
    r = APIRouter(prefix="/api")
    state_for = deps["state_for"]
    attrs_ok = {"done": False}

    async def _ensure_attrs():
        if attrs_ok["done"]:
            return
        sc, data, err = await brevo_funnel._request("GET", "/v3/contacts/attributes")
        if sc != 200:
            raise RuntimeError(err or f"Attributi Brevo non leggibili (HTTP {sc})")
        have = {a.get("name"): a for a in (data or {}).get("attributes", [])}
        for name, typ in ATTRS.items():
            if name not in have:
                sc2, _, err2 = await brevo_funnel._request("POST", f"/v3/contacts/attributes/normal/{name}", json={"type": typ})
                if sc2 not in (200, 201, 204):
                    raise RuntimeError(f"Creazione attributo {name}: {err2}")
                log.info("brevo attribute created: %s (%s)", name, typ)
        attrs_ok["done"] = True

    async def recipients(org_id: str) -> list:
        """Solo Admin Organizzatore, proprietario e utenti con permesso Gestione abbonamento."""
        q = {"org_id": org_id, "active": True, "$or": [{"role": "admin_org"}, {"permissions.subscription_manage": True}]}
        uids = set(await db.memberships.distinct("user_id", q))
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "owner_user_id": 1})
        if (org or {}).get("owner_user_id"):
            uids.add(org["owner_user_id"])
        return [u["email"].lower() for u in await db.users.find({"user_id": {"$in": list(uids)}}, {"_id": 0, "email": 1}).to_list(100) if u.get("email")]

    async def _attrs_for(org_id: str) -> Optional[dict]:
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1, "nome": 1})
        return org_attrs(org, await state_for(org_id)) if org else None

    async def _orgs_of(email: str) -> list:
        u = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1})
        if not u:
            return []
        q = {"user_id": u["user_id"], "active": True, "$or": [{"role": "admin_org"}, {"permissions.subscription_manage": True}]}
        ids = set(await db.memberships.distinct("org_id", q)) | set(await db.organizations.distinct("id", {"owner_user_id": u["user_id"]}))
        return list(ids)

    async def push(email: str, attrs: dict):
        clean = {k: v for k, v in attrs.items() if v is not None}
        sc, _, err = await brevo_funnel._request("POST", "/v3/contacts", json={"email": email, "updateEnabled": True, "attributes": clean})
        if sc not in (200, 201, 204):
            raise RuntimeError(err or f"HTTP {sc}")

    async def sync_org(org_id: str, source: str = "evento") -> dict:
        own = await _attrs_for(org_id)
        if not own:
            return {"ok": True, "skipped": True}
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "nome": 1})
        h = hashlib.sha1(json.dumps(own, sort_keys=True, default=str).encode()).hexdigest()
        rec, err, shown = await recipients(org_id), None, []
        try:
            if not brevo_funnel.is_configured():
                raise RuntimeError("Brevo non configurato (BREVO_API_KEY)")
            await _ensure_attrs()
            for email in rec:
                cands = [a for a in [await _attrs_for(o) for o in await _orgs_of(email)] if a] or [own]
                chosen = pick(cands)
                await push(email, chosen)
                shown.append({"email": email, "org_id": chosen["CRM_ORG_ID"]})
        except Exception as e:  # registrata per il nuovo tentativo (pulsante o controllo giornaliero)
            err = str(e)[:300] or type(e).__name__
            log.warning("brevo subscription sync failed org=%s: %s", org_id, err)
        doc = {"org_id": org_id, "org_name": (org or {}).get("nome"), "status": "error" if err else "ok", "error": err, "at": _now(),
               "source": source, "attrs": own, "hash": h if not err else None, "recipients": shown or [{"email": e} for e in rec]}
        await db.saas_brevo_sync.update_one({"org_id": org_id}, {"$set": doc}, upsert=True)
        return {"ok": not err, "error": err, "recipients": len(rec)}

    async def daily() -> dict:
        """Passaggi di stato dovuti al tempo (In scadenza / Scaduto) e nuovi tentativi: sincronizza solo ciò che è cambiato."""
        out = {"checked": 0, "synced": 0, "failed": 0}
        prev = {d["org_id"]: d for d in await db.saas_brevo_sync.find({}, {"_id": 0, "org_id": 1, "hash": 1, "status": 1}).to_list(10000)}
        for o in await db.organizations.find({"saas": {"$exists": True}, "type": {"$in": ["cliente", None]}}, {"_id": 0, "id": 1}).to_list(10000):
            out["checked"] += 1
            a = await _attrs_for(o["id"])
            if not a:
                continue
            h = hashlib.sha1(json.dumps(a, sort_keys=True, default=str).encode()).hexdigest()
            p = prev.get(o["id"]) or {}
            if p.get("status") == "ok" and p.get("hash") == h:
                continue
            res = await sync_org(o["id"], "controllo giornaliero")
            out["synced" if res["ok"] else "failed"] += 1
        return out

    sa = deps["require_superadmin"]

    @r.get("/platform/brevo/subscription-sync")
    async def overview(admin: dict = Depends(sa)):
        rows = await db.saas_brevo_sync.find({}, {"_id": 0, "hash": 0}).sort("at", -1).to_list(1000)
        total = await db.organizations.count_documents({"saas": {"$exists": True}, "type": {"$in": ["cliente", None]}})
        return {"configured": brevo_funnel.is_configured(), "attributes": ATTRS, "total_orgs": total,
                "synced_ok": sum(1 for x in rows if x["status"] == "ok"), "errors": sum(1 for x in rows if x["status"] == "error"),
                "last_sync_at": rows[0]["at"] if rows else None, "rows": rows}

    @r.post("/platform/brevo/subscription-sync/{org_id}")
    async def resync_one(org_id: str, admin: dict = Depends(sa)):
        if not await db.organizations.find_one({"id": org_id}, {"_id": 1}):
            raise HTTPException(status_code=404, detail="Organizzazione non trovata")
        res = await sync_org(org_id, "manuale")
        await deps["record_audit"](admin, "brevo_subscription_sync", org_id=org_id, detail="ok" if res["ok"] else res["error"])
        return res

    @r.post("/platform/brevo/subscription-sync")
    async def resync_all(body: SyncAllIn, admin: dict = Depends(sa)):
        q = {"saas": {"$exists": True}, "type": {"$in": ["cliente", None]}}
        ids = [o["id"] for o in await db.organizations.find(q, {"_id": 0, "id": 1}).to_list(10000)]
        if body.only_failed:
            ok = set(await db.saas_brevo_sync.distinct("org_id", {"status": "ok"}))
            ids = [i for i in ids if i not in ok]
        res = [await sync_org(i, "manuale") for i in ids]
        n_ok = sum(1 for x in res if x["ok"])
        await deps["record_audit"](admin, "brevo_subscription_sync_all", detail=f"{n_ok}/{len(ids)}")
        return {"total": len(ids), "ok": n_ok, "failed": len(ids) - n_ok, "errors": [x["error"] for x in res if not x["ok"]][:5]}

    return {"router": r, "sync_org": sync_org, "daily": daily}
