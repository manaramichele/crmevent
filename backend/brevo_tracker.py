"""Brevo Tracker: eventi server-side (API Events) e identità per il tracker JS. Solo utenti organizzatori: mai iscritti, staff o volontari."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pymongo.errors import DuplicateKeyError

import brevo_funnel
import brevo_subscriptions

log = logging.getLogger("brevo_tracker")
EVENTS = ("registration_completed", "login_completed", "trial_started", "event_created",
          "first_activity", "subscription_started", "subscription_renewed")
FIRST_ACTIVITY_COLLS = ("persons", "deals", "activities", "shifts", "teams")
EXCLUDED_ROLES = ("volunteer", "staff", "superadmin")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build(db, deps: dict):
    r = APIRouter(prefix="/api")

    async def ensure_indexes():
        await db.brevo_tracker_once.create_index("key", unique=True)
        await db.brevo_tracker_log.create_index("created_at_dt", expireAfterSeconds=90 * 86400)

    def _names(u: dict) -> dict:
        name = (u.get("name") or "").strip()
        return {"NOME": u.get("nome") or (name.split(" ")[0] if name else None),
                "COGNOME": u.get("cognome") or (" ".join(name.split(" ")[1:]) or None)}

    async def contact_props(u: dict) -> dict:
        """Attributi Brevo già esistenti (NOME/COGNOME + CRM_*), stessa scelta d'organizzazione della sync abbonamenti."""
        props = _names(u)
        cands = []
        for m in await db.memberships.find({"user_id": u["user_id"], "active": True}, {"_id": 0, "org_id": 1}).to_list(50):
            org = await db.organizations.find_one({"id": m["org_id"]}, {"_id": 0})
            if org:
                a = brevo_subscriptions.org_attrs(org, await deps["state_for"](org["id"]))
                cands.append(a or {"CRM_ORG_ID": org["id"], "CRM_ORGANIZZAZIONE": org.get("nome"), "CRM_STATO": "Scaduto"})
        if cands:
            props.update(brevo_subscriptions.pick(cands))
        return {k: v for k, v in props.items() if v is not None}

    async def _org_props(org_id: str) -> dict:
        if not org_id:
            return {}
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "id": 1, "nome": 1})
        if not org:
            return {}
        st = await deps["state_for"](org_id)
        return {k: v for k, v in {"org_id": org_id, "org_name": org.get("nome"), "plan": st.get("plan_label") or st.get("paid_plan_label"),
                                  "subscription_status": brevo_subscriptions.STATO.get(st.get("sub_status"))}.items() if v}

    async def _run(event: str, user_id: str, org_id: str, props: dict, once: str):
        claimed = False
        try:
            u = await db.users.find_one({"user_id": user_id}, {"_id": 0}) if user_id else None
            if not u or not u.get("email") or u.get("role") in EXCLUDED_ROLES:
                return
            if once:
                try:
                    await db.brevo_tracker_once.insert_one({"key": once, "event": event, "user_id": user_id, "org_id": org_id, "created_at": _now()})
                    claimed = True
                except DuplicateKeyError:
                    return
            entry = {"event": event, "email": u["email"], "user_id": user_id, "org_id": org_id, "created_at": _now(),
                     "created_at_dt": datetime.now(timezone.utc)}
            if not brevo_funnel.is_configured():
                await db.brevo_tracker_log.insert_one({**entry, "status": "non_configurato"})
                if claimed:
                    await db.brevo_tracker_once.delete_one({"key": once})
                return
            body = {"event_name": event, "event_date": _now(), "identifiers": {"email_id": u["email"]},
                    "contact_properties": await contact_props(u),
                    "event_properties": {**(await _org_props(org_id)), **(props or {})}}
            sc, _, err = await brevo_funnel._request("POST", "/v3/events", json=body)
            ok = sc is not None and sc < 300
            await db.brevo_tracker_log.insert_one({**entry, "status": "inviato" if ok else "errore", "http_status": sc, "error": None if ok else err})
            if not ok and claimed:
                await db.brevo_tracker_once.delete_one({"key": once})  # riprova alla prossima occasione utile
        except Exception as e:  # noqa: BLE001 - il tracking non blocca mai l'operazione
            log.error("brevo tracker %s failed: %s", event, type(e).__name__)
            if claimed:
                await db.brevo_tracker_once.delete_one({"key": once})

    def track(event: str, user_id: str, org_id: str = None, props: dict = None, once: str = None):
        asyncio.create_task(_run(event, user_id, org_id, props or {}, once))

    async def on_created(user: dict, coll: str, org_id: str):
        """Primo evento / prima attività operativa dell'organizzazione (una sola volta)."""
        if user.get("support") or not org_id:
            return
        if coll == "events" and await db.events.count_documents({"org_id": org_id}) == 1:
            track("event_created", user["user_id"], org_id, once=f"event_created:{org_id}")
        elif coll in FIRST_ACTIVITY_COLLS:
            total = 0
            for c in FIRST_ACTIVITY_COLLS:
                total += await db[c].count_documents({"org_id": org_id})
                if total > 1:
                    return
            if total == 1:
                track("first_activity", user["user_id"], org_id, {"activity_type": coll}, once=f"first_activity:{org_id}")

    async def _org_owner(org: dict):
        if org.get("owner_user_id"):
            return org["owner_user_id"]
        m = await db.memberships.find_one({"org_id": org["id"], "role": "admin_org", "active": True}, {"_id": 0, "user_id": 1})
        return (m or {}).get("user_id")

    async def on_payment(org: dict, inv, plan: str, cycle: str, test: bool):
        """Solo fatture Stripe pagate (>0 €): la prima è il primo abbonamento (anche dopo la prova), le successive rinnovi."""
        uid = await _org_owner(org)
        props = {"plan_code": plan, "billing_cycle": cycle, "amount": round((inv.get("total") or 0) / 100, 2),
                 "currency": (inv.get("currency") or "eur").upper(), "stripe_invoice_id": inv.get("id"), "test_mode": test}
        paid = await db.invoices.count_documents({"org_id": org["id"], "kind": "saas_subscription", "payment_status": "paid",
                                                  "stripe_invoice_id": {"$ne": inv.get("id")}})
        if not paid:
            track("subscription_started", uid, org["id"], props, once=f"subscription_started:{org['id']}")
        else:
            track("subscription_renewed", uid, org["id"], props, once=f"subscription_renewed:{inv.get('id')}")

    @r.get("/brevo-tracker/identity")
    async def identity(user: dict = Depends(deps["get_current_user"])):
        if user.get("support") or user.get("role") in EXCLUDED_ROLES or not user.get("email"):
            return {"identify": False}
        u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0}) or user
        return {"identify": True, "email": u["email"], "ext_id": u["user_id"], "attributes": await contact_props(u)}

    @r.get("/platform/brevo-tracker")
    async def overview(admin: dict = Depends(deps["require_superadmin"])):
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        counts = {}
        for ev in EVENTS:
            counts[ev] = {s: await db.brevo_tracker_log.count_documents({"event": ev, "status": s, "created_at": {"$gte": since}})
                          for s in ("inviato", "errore", "non_configurato")}
        recent = await db.brevo_tracker_log.find({}, {"_id": 0, "created_at_dt": 0}).sort("created_at", -1).to_list(50)
        return {"configured": brevo_funnel.is_configured(), "events": list(EVENTS), "counts_30d": counts, "recent": recent}

    return {"router": r, "track": track, "on_created": on_created, "on_payment": on_payment, "ensure_indexes": ensure_indexes}
