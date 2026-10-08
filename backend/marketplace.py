"""Marketplace CRMEvent: catalogo servizi extra (fuori dagli abbonamenti), acquisti per organizzazione, Stripe e fatture."""
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import stripe as stripe_sdk
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("marketplace")
CATEGORIES = ["Siti web", "Comunicazione", "Documenti", "Logistica", "Altro"]
PRICE_TYPES = ("one_time", "monthly", "yearly", "usage")
STATUSES = ("coming_soon", "available", "suspended")
ACTIVE = ("active", "past_due")
SEED = [
    ("sito-organizzazione", "Sito web organizzazione", "Siti web", "Globe", "org",
     "Un sito dedicato alla tua organizzazione: template preconfigurati, logo e colori personalizzati, informazioni, elenco eventi, contatti, dominio o sottodominio e contenuti gestiti da CRMEvent."),
    ("sito-evento", "Sito web evento", "Siti web", "MonitorSmartphone", "event",
     "Un sito per il singolo evento: nome e logo, data e luogo, descrizione, programma, percorsi e mappe, sponsor, informazioni operative e collegamenti alle iscrizioni. Acquistabile anche senza il sito dell'organizzazione."),
    ("newsletter", "Newsletter", "Comunicazione", "Mail", "org",
     "Crea e invia newsletter alle liste della tua organizzazione, con gestione dei consensi e completo isolamento dei dati tra organizzazioni."),
    ("whatsapp", "WhatsApp", "Comunicazione", "MessageCircle", "org",
     "Invia comunicazioni via WhatsApp tramite l'infrastruttura ufficiale CRMEvent, senza dover acquistare una SIM dedicata. Condizioni e costi dipendono dal provider WhatsApp Business."),
    ("contratti", "Generazione contratti", "Documenti", "FileSignature", "org",
     "Genera accordi sponsor, contratti fornitori, collaborazioni e incarichi da modelli personalizzabili, con compilazione automatica dei dati ed esportazione PDF. I documenti vanno sempre verificati da un professionista."),
    ("magazzino", "Magazzino", "Logistica", "Warehouse", "org",
     "Gestisci i materiali dell'organizzazione: anagrafica e categorie, quantità, carico e scarico, assegnazione agli eventi, prestiti e restituzioni, inventario, storico movimenti e materiali mancanti."),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ServiceIn(BaseModel):
    name: str
    description: str = ""
    icon: str = "Package"
    image: Optional[str] = None
    category: str = "Altro"
    price: Optional[float] = None
    price_type: str = "one_time"
    usage_unit: Optional[str] = None
    usage_limits: Optional[str] = None
    terms: Optional[str] = None
    status: str = "coming_soon"
    visible: bool = True
    purchasable: bool = False
    tech_ready: bool = False
    billing_method: str = "stripe"
    scope: str = "org"
    sort: int = 100


class CheckoutIn(BaseModel):
    origin_url: str
    event_id: Optional[str] = None


class PurchaseStatusIn(BaseModel):
    status: str


def can_buy(svc: dict) -> Optional[str]:
    """Motivo per cui il servizio NON è acquistabile (None = acquistabile)."""
    if not svc.get("visible") or svc.get("status") != "available":
        return "Servizio non disponibile"
    if not svc.get("tech_ready"):
        return "Servizio non ancora pronto"
    if not svc.get("purchasable"):
        return "Acquisto non abilitato"
    if svc.get("price_type") == "usage":
        return "Servizio a consumo: attivazione commerciale da approvare"
    if not svc.get("price") or float(svc["price"]) <= 0:
        return "Prezzo non configurato"
    return None


def build(db, deps: dict):
    r = APIRouter(prefix="/api")

    async def _seed():
        if await db.marketplace_services.count_documents({}) == 0:
            for i, (key, name, cat, icon, scope, desc) in enumerate(SEED):
                await db.marketplace_services.update_one({"key": key}, {"$setOnInsert": {
                    "id": uuid.uuid4().hex, "key": key, "name": name, "description": desc, "icon": icon, "image": None,
                    "category": cat, "price": None, "price_type": "monthly" if key not in ("contratti",) else "usage",
                    "usage_unit": None, "usage_limits": None, "terms": None, "status": "coming_soon", "visible": True,
                    "purchasable": False, "tech_ready": False, "billing_method": "stripe", "scope": scope, "sort": (i + 1) * 10,
                    "created_at": _now()}}, upsert=True)

    def _can_purchase(user: dict) -> bool:
        p = user.get("perm") or {}
        return user.get("org_role") in ("admin_org", "superadmin") or bool(p.get("admin")) or bool(p.get("marketplace_purchase"))

    def _public(s: dict, purchases: list) -> dict:
        mine = [p for p in purchases if p["service_id"] == s["id"]]
        return {**{k: s.get(k) for k in ("id", "key", "name", "description", "icon", "image", "category", "price", "price_type",
                                          "usage_unit", "usage_limits", "terms", "status", "scope")},
                "purchasable_now": can_buy(s) is None, "reason": can_buy(s),
                "active": any(p["status"] in ACTIVE for p in mine), "purchases": mine}

    async def _org_purchases(org_id: str) -> list:
        return await db.marketplace_purchases.find({"org_id": org_id}, {"_id": 0}).sort("created_at", -1).to_list(500)

    @r.get("/marketplace/services")
    async def services(user: dict = Depends(deps["require_admin"])):
        await _seed()
        rows = await db.marketplace_services.find({"visible": True}, {"_id": 0}).sort("sort", 1).to_list(200)
        pur = await _org_purchases(user["org_id"])
        return {"services": [_public(s, pur) for s in rows], "categories": CATEGORIES, "can_purchase": _can_purchase(user)}

    @r.get("/marketplace/my")
    async def my(user: dict = Depends(deps["require_admin"])):
        pur = await _org_purchases(user["org_id"])
        names = {s["id"]: s for s in await db.marketplace_services.find({}, {"_id": 0, "id": 1, "name": 1, "icon": 1}).to_list(200)}
        evs = {e["id"]: e.get("nome") for e in await db.events.find({"org_id": user["org_id"]}, {"_id": 0, "id": 1, "nome": 1}).to_list(2000)}
        return [{**p, "service_name": (names.get(p["service_id"]) or {}).get("name"), "event_name": evs.get(p.get("event_id"))}
                for p in pur if p["status"] != "pending"]

    @r.post("/marketplace/services/{sid}/checkout")
    async def checkout(sid: str, body: CheckoutIn, user: dict = Depends(deps["require_admin"])):
        if not _can_purchase(user):
            raise HTTPException(status_code=403, detail="Non hai il permesso di acquistare servizi Marketplace")
        svc = await db.marketplace_services.find_one({"id": sid}, {"_id": 0})
        if not svc:
            raise HTTPException(status_code=404, detail="Servizio non trovato")
        why = can_buy(svc)
        if why:
            raise HTTPException(status_code=400, detail=why)
        if deps["stripe_mode"] == "live" and os.environ.get("MARKETPLACE_STRIPE_LIVE_ENABLED", "").strip() != "1":
            raise HTTPException(status_code=503, detail="Acquisti Marketplace non ancora attivi per i pagamenti reali")
        ev = None
        if svc.get("scope") == "event":
            ev = await db.events.find_one({"id": body.event_id or "", "org_id": user["org_id"]}, {"_id": 0, "id": 1, "nome": 1})
            if not ev:
                raise HTTPException(status_code=400, detail="Seleziona l'evento a cui associare il servizio")
        dup = {"org_id": user["org_id"], "service_id": sid, "status": {"$in": list(ACTIVE)}}
        if ev:
            dup["event_id"] = ev["id"]
        if svc["price_type"] != "one_time" and await db.marketplace_purchases.find_one(dup):
            raise HTTPException(status_code=400, detail="Servizio già attivo")
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
        missing = deps["billing_missing"](org.get("billing") or {})
        if missing:
            raise HTTPException(status_code=400, detail="Completa i dati di fatturazione: " + ", ".join(missing))
        pid = uuid.uuid4().hex
        md = {"kind": "marketplace", "purchase_id": pid, "org_id": org["id"], "service_id": sid}
        cents = int(round(float(svc["price"]) * 100))
        pdata = {"currency": "eur", "unit_amount": cents, "product_data": {"name": f"CRMEvent · {svc['name']}", "tax_code": "txcd_10103001"}}
        if svc["price_type"] in ("monthly", "yearly"):
            pdata["recurring"] = {"interval": "month" if svc["price_type"] == "monthly" else "year"}
        origin = body.origin_url.rstrip("/")
        kw = dict(customer=await deps["ensure_customer"](org, user), line_items=[{"price_data": pdata, "quantity": 1}], metadata=md,
                  success_url=f"{origin}/marketplace?purchase={pid}&session_id={{CHECKOUT_SESSION_ID}}", cancel_url=f"{origin}/marketplace")
        if svc["price_type"] == "one_time":
            kw.update(mode="payment", invoice_creation={"enabled": True, "invoice_data": {"metadata": md}})
        else:
            kw.update(mode="subscription", subscription_data={"metadata": md})
        try:
            sess = stripe_sdk.checkout.Session.create(**kw)
        except stripe_sdk.error.StripeError as e:
            logger.error(f"marketplace checkout: {e}")
            raise HTTPException(status_code=502, detail="Non è stato possibile avviare il pagamento. Riprova più tardi.")
        await db.marketplace_purchases.insert_one({
            "id": pid, "org_id": org["id"], "service_id": sid, "service_name": svc["name"], "event_id": (ev or {}).get("id"),
            "status": "pending", "price": float(svc["price"]), "price_type": svc["price_type"], "stripe_session_id": sess.id,
            "stripe_subscription_id": None, "activated_at": None, "current_period_end": None, "created_by": user["user_id"],
            "created_at": _now(), "history": [{"at": _now(), "status": "pending", "by": user.get("email")}]})
        return {"checkout_url": sess.url}

    async def _activate_from_session(sess) -> Optional[dict]:
        """Attivazione solo dopo verifica server-side su Stripe (pagamento riuscito). Idempotente."""
        pid = (sess.get("metadata") or {}).get("purchase_id")
        p = await db.marketplace_purchases.find_one({"id": pid}, {"_id": 0}) if pid else None
        if not p or sess.get("status") != "complete" or sess.get("payment_status") not in ("paid", "no_payment_required"):
            return p
        upd = {"status": "active", "activated_at": p.get("activated_at") or _now(), "updated_at": _now()}
        if sess.get("subscription"):
            sub = stripe_sdk.Subscription.retrieve(sess["subscription"])
            it = sub["items"]["data"][0]
            cpe = sub.get("current_period_end") or it.get("current_period_end")
            upd.update(stripe_subscription_id=sub["id"], current_period_end=datetime.fromtimestamp(cpe, timezone.utc).isoformat() if cpe else None)
        res = await db.marketplace_purchases.update_one({"id": pid, "status": "pending"}, {"$set": upd, "$push": {"history": {"at": _now(), "status": "active", "by": "stripe"}}})
        if res.modified_count:
            await deps["record_audit"]({"user_id": "stripe", "email": "stripe", "role": "system"}, "marketplace_activated",
                                       org_id=p["org_id"], detail=p.get("service_name"))
        return await db.marketplace_purchases.find_one({"id": pid}, {"_id": 0})

    @r.get("/marketplace/checkout-confirmation")
    async def confirmation(session_id: str, user: dict = Depends(deps["require_admin"])):
        sess = stripe_sdk.checkout.Session.retrieve(session_id)
        if (sess.get("metadata") or {}).get("org_id") != user["org_id"]:
            raise HTTPException(status_code=403, detail="Sessione non associata all'organizzazione")
        p = await _activate_from_session(sess)
        return {"status": (p or {}).get("status")}

    async def _invoice(inv, status: str):
        md = inv.get("metadata") or {}
        sid = inv.get("subscription") or ((inv.get("parent") or {}).get("subscription_details") or {}).get("subscription")
        p = await db.marketplace_purchases.find_one({"id": md.get("purchase_id")} if md.get("kind") == "marketplace" else {"stripe_subscription_id": sid or "-"}, {"_id": 0})
        if not p:
            return False
        if status == "paid" and (inv.get("total") or 0) > 0:
            await deps["record_invoice"](inv, status)
            test = deps["stripe_mode"] != "live"
            upd = {"kind": "marketplace", "marketplace_purchase_id": p["id"], "descrizione": f"CRMEvent · {p.get('service_name')}",
                   "regime_fiscale": "forfettario", "aliquota_iva": 0.0, "importo_iva": 0.0, "iva": 0.0, "is_test": test}
            if test:
                upd.update({"fic_stato_documento": "test_non_inviata", "fic_stato_sdi": "non_inviato"})
            await db.invoices.update_one({"stripe_invoice_id": inv.get("id"), "fic_document_id": None}, {"$set": upd})
            row = await db.invoices.find_one({"stripe_invoice_id": inv.get("id")}, {"_id": 0, "id": 1})
            if row and not test:
                await deps["emit_invoice"](row["id"])
        elif status == "payment_failed":
            await db.marketplace_purchases.update_one({"id": p["id"], "status": "active"}, {"$set": {"status": "past_due"}, "$push": {"history": {"at": _now(), "status": "past_due", "by": "stripe"}}})
        return True

    async def handle_webhook(t: str, obj) -> bool:
        md = obj.get("metadata") or {}
        if t == "checkout.session.completed" and md.get("kind") == "marketplace":
            await _activate_from_session(obj)
            return True
        if t.startswith("customer.subscription.") and md.get("kind") == "marketplace":
            sub = stripe_sdk.Subscription.retrieve(obj["id"])
            it = sub["items"]["data"][0]
            cpe = sub.get("current_period_end") or it.get("current_period_end")
            st = {"active": "active", "trialing": "active", "past_due": "past_due", "unpaid": "past_due", "canceled": "canceled"}.get(sub["status"])
            upd = {"current_period_end": datetime.fromtimestamp(cpe, timezone.utc).isoformat() if cpe else None,
                   "cancel_at_period_end": bool(sub.get("cancel_at_period_end")), "stripe_subscription_id": sub["id"]}
            q = {"id": md.get("purchase_id"), "status": {"$nin": ["pending", "suspended"]}}
            if st:
                upd["status"] = st
            await db.marketplace_purchases.update_one(q, {"$set": upd})
            return True
        if t in ("invoice.paid", "invoice.payment_failed"):
            return await _invoice(obj, "paid" if t == "invoice.paid" else "payment_failed")
        return False

    # ---------------- Super Admin ----------------
    def _clean(body: ServiceIn) -> dict:
        d = body.model_dump()
        if d["price_type"] not in PRICE_TYPES or d["status"] not in STATUSES or d["scope"] not in ("org", "event") \
                or d["billing_method"] not in ("stripe", "credits"):
            raise HTTPException(status_code=400, detail="Valori non validi")
        if d["image"] and len(d["image"]) > 400_000:
            raise HTTPException(status_code=400, detail="Immagine troppo grande (max 300 KB)")
        if d["purchasable"] and not d["tech_ready"]:
            raise HTTPException(status_code=400, detail="Un servizio non può essere acquistabile se il modulo non è tecnicamente pronto")
        if d["status"] == "coming_soon":
            d["purchasable"] = False
        return d

    @r.get("/platform/marketplace/services")
    async def admin_list(admin: dict = Depends(deps["require_superadmin"])):
        await _seed()
        rows = await db.marketplace_services.find({}, {"_id": 0}).sort("sort", 1).to_list(500)
        counts = {c["_id"]: c["n"] for c in await db.marketplace_purchases.aggregate([{"$match": {"status": {"$in": list(ACTIVE)}}}, {"$group": {"_id": "$service_id", "n": {"$sum": 1}}}]).to_list(500)}
        return {"services": [{**s, "active_count": counts.get(s["id"], 0), "purchasable_now": can_buy(s) is None} for s in rows], "categories": CATEGORIES}

    @r.post("/platform/marketplace/services")
    async def admin_create(body: ServiceIn, admin: dict = Depends(deps["require_superadmin"])):
        d = {**_clean(body), "id": uuid.uuid4().hex, "key": uuid.uuid4().hex[:10], "created_at": _now()}
        await db.marketplace_services.insert_one({**d})
        await deps["record_audit"](admin, "marketplace_service_create", detail=d["name"])
        return d

    @r.put("/platform/marketplace/services/{sid}")
    async def admin_update(sid: str, body: ServiceIn, admin: dict = Depends(deps["require_superadmin"])):
        d = _clean(body)
        res = await db.marketplace_services.update_one({"id": sid}, {"$set": {**d, "updated_at": _now()}})
        if not res.matched_count:
            raise HTTPException(status_code=404, detail="Servizio non trovato")
        await deps["record_audit"](admin, "marketplace_service_update", detail=f"{d['name']} · {d['status']} · acquistabile {d['purchasable']}")
        return await db.marketplace_services.find_one({"id": sid}, {"_id": 0})

    @r.get("/platform/marketplace/purchases")
    async def admin_purchases(admin: dict = Depends(deps["require_superadmin"])):
        rows = await db.marketplace_purchases.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
        orgs = {o["id"]: o.get("nome") for o in await db.organizations.find({"id": {"$in": list({r["org_id"] for r in rows})}}, {"_id": 0, "id": 1, "nome": 1}).to_list(1000)}
        return [{**r, "org_name": orgs.get(r["org_id"])} for r in rows]

    @r.put("/platform/marketplace/purchases/{pid}/status")
    async def admin_purchase_status(pid: str, body: PurchaseStatusIn, admin: dict = Depends(deps["require_superadmin"])):
        if body.status not in ("active", "suspended"):
            raise HTTPException(status_code=400, detail="Stato non valido")
        p = await db.marketplace_purchases.find_one({"id": pid}, {"_id": 0})
        if not p or p["status"] == "pending":
            raise HTTPException(status_code=400, detail="Acquisto non modificabile")
        await db.marketplace_purchases.update_one({"id": pid}, {"$set": {"status": body.status}, "$push": {"history": {"at": _now(), "status": body.status, "by": admin.get("email")}}})
        await deps["record_audit"](admin, "marketplace_purchase_status", org_id=p["org_id"], detail=f"{p.get('service_name')} → {body.status}")
        return {"ok": True}

    return {"router": r, "handle_webhook": handle_webhook}
