"""Abbonamenti CRMEvent BRONZE / SILVER / GOLD: configurazione piani, stato organizzazione, gating, Stripe, quote videochiamate."""
import asyncio
import copy
import logging
import math
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import stripe as stripe_sdk
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from email_utils import link_email, send_email

logger = logging.getLogger("subscriptions")
PLAN_KEYS = ("bronze", "silver", "gold")
PLAN_RANK = {"bronze": 1, "silver": 2, "gold": 3}
CYCLES = ("monthly", "yearly")
FEATURES = [  # (chiave, etichetta) — chiavi = sezioni permessi + funzioni trasversali
    ("dashboard", "Dashboard"), ("eventi", "Eventi"), ("staff", "Staff / Volontari"), ("pipeline", "Pipeline evento"),
    ("calendar", "Google Calendar"), ("aziende", "Aziende"), ("anagrafiche", "Anagrafiche"), ("attivita", "Attività"),
    ("mappe", "Percorsi"), ("ospitalita", "Ospitalità e Pasti"), ("sponsor", "Sponsor e Partner"),
    ("briefing", "Briefing"), ("followup", "Follow-up"),
]
FEATURE_KEYS = [k for k, _ in FEATURES]
_BRONZE = ["dashboard", "eventi", "staff", "pipeline", "calendar"]
_SILVER = _BRONZE + ["aziende", "anagrafiche", "attivita", "mappe"]
_GOLD = _SILVER + ["ospitalita", "sponsor", "briefing", "followup"]
DEFAULT_CONFIG = {
    "id": "config", "version": 1, "trial_days": 14, "trial_plan": "gold", "trial_video_quota": 3,
    "plans": {
        "bronze": {"label": "BRONZE", "color": "#B87333", "tagline": "Per organizzare e coordinare gli eventi.",
                   "monthly": 19.0, "yearly": 182.40, "features": _BRONZE, "video_quota": 0, "active": True},
        "silver": {"label": "SILVER", "color": "#A3A3A3", "tagline": "Per gestire le attività operative in modo più completo.",
                   "monthly": 49.0, "yearly": 470.40, "features": _SILVER, "video_quota": 3, "active": True},
        "gold": {"label": "GOLD", "color": "#D4AF37", "tagline": "Per avere a disposizione tutti gli strumenti di gestione dell'evento.",
                 "monthly": 79.0, "yearly": 758.40, "features": _GOLD, "video_quota": -1, "active": True},
    },
}
def _live_enabled() -> bool:
    """Abbonamenti LIVE attivi (interruttore di emergenza: SAAS_STRIPE_LIVE_ENABLED=0)."""
    return os.environ.get("SAAS_STRIPE_LIVE_ENABLED", "1").strip() != "0"


WRITE_EXEMPT = ("/saas", "/account", "/auth", "/notifications", "/my/", "/support", "/news")
SAFE = ("GET", "HEAD", "OPTIONS")
GOLD_NOTICE_HOURS = 4
_cfg_cache = {"at": 0.0, "cfg": None}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.astimezone(timezone.utc).isoformat() if d else None


def _parse(s) -> Optional[datetime]:
    if not s:
        return None
    if isinstance(s, (int, float)):
        return datetime.fromtimestamp(s, timezone.utc)
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _add_months(d: datetime, n: int) -> datetime:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    for day in (d.day, 30, 29, 28):
        try:
            return d.replace(year=y, month=m, day=day)
        except ValueError:
            continue
    return d


def monthly_period(anchor: Optional[datetime], now: Optional[datetime] = None) -> str:
    """Inizio del periodo mensile corrente calcolato dall'ancora dell'abbonamento (vale anche per l'annuale)."""
    now = now or _now()
    if not anchor or anchor > now:
        return f"m:{now.date().replace(day=1).isoformat()}"
    n = (now.year - anchor.year) * 12 + now.month - anchor.month
    start = _add_months(anchor, n)
    if start > now:
        start = _add_months(anchor, n - 1)
    return f"m:{start.date().isoformat()}"


def plan_label(cfg: dict, plan: Optional[str]) -> str:
    return (cfg["plans"].get(plan) or {}).get("label", (plan or "").upper())


def org_state(org: dict, cfg: dict) -> dict:
    """Stato commerciale (fonte autorevole: backend). enabled=False → organizzazione sul modello precedente."""
    s = (org or {}).get("saas")
    if not s or (org or {}).get("type", "cliente") != "cliente":
        return {"enabled": False}
    now = _now()
    trial_end = _parse(s.get("trial_end"))
    trial_active = bool(trial_end and trial_end > now)
    st = s.get("stripe_status")
    paid_plan = s.get("plan") if st in ("active", "trialing", "past_due") else None
    if trial_active:
        mode, eff = "trial", s.get("trial_plan") or cfg.get("trial_plan", "gold")
    elif paid_plan:
        mode, eff = ("past_due" if st == "past_due" else "active"), paid_plan
    else:
        mode, eff = ("canceled" if s.get("plan") else "expired"), None
    last = eff or s.get("plan") or s.get("trial_plan") or "gold"
    features = list((cfg["plans"].get(last) or {}).get("features") or [])
    days_left = max(0, math.ceil((trial_end - now).total_seconds() / 86400)) if trial_active else 0
    return {"enabled": True, "mode": mode, "plan": eff, "plan_label": plan_label(cfg, eff) if eff else None,
            "writable": eff is not None, "features": features,
            "trial_plan": s.get("trial_plan"), "trial_start": s.get("trial_start"), "trial_end": s.get("trial_end"),
            "trial_active": trial_active, "days_left": days_left,
            "paid_plan": s.get("plan"), "paid_plan_label": plan_label(cfg, s.get("plan")) if s.get("plan") else None,
            "purchased": bool(paid_plan), "billing_cycle": s.get("billing_cycle"), "stripe_status": st,
            "price_amount": s.get("price_amount"), "activated_at": s.get("activated_at"),
            "current_period_start": s.get("current_period_start"), "current_period_end": s.get("current_period_end"),
            "cancel_at_period_end": bool(s.get("cancel_at_period_end")), "pending_change": s.get("pending_change")}


def trial_doc(cfg: dict) -> dict:
    now = _now()
    return {"model": "tiered", "trial_plan": cfg.get("trial_plan", "gold"), "trial_status": "active", "trial_used": True,
            "trial_start": _iso(now), "trial_end": _iso(now + timedelta(days=int(cfg.get("trial_days", 14)))),
            "plan": None, "billing_cycle": None, "stripe_status": None, "stripe_subscription_id": None,
            "activated_at": None, "current_period_start": None, "current_period_end": None, "pending_change": None,
            "created_at": _iso(now)}


class CheckoutIn(BaseModel):
    plan: str
    cycle: str
    origin_url: str


class ChangeIn(BaseModel):
    plan: str
    cycle: str
    confirm_amount: Optional[float] = None


class ConfigPlanIn(BaseModel):
    label: str
    color: str
    tagline: str = ""
    monthly: float
    yearly: float
    features: list[str]
    video_quota: int
    active: bool = True


class ConfigIn(BaseModel):
    trial_days: int
    trial_video_quota: int
    plans: dict[str, ConfigPlanIn]


class AdjustIn(BaseModel):
    delta: int
    note: Optional[str] = None


class ExtendIn(BaseModel):
    days: int


def build(db, deps: dict):
    """deps: require_admin, require_org_admin, require_superadmin, record_audit, ensure_customer, billing_missing,
    record_invoice, stripe_mode, app_url, cron_secret."""
    r = APIRouter(prefix="/api")
    state = {"idx": False}

    async def _indexes():
        if not state["idx"]:
            await db.saas_video_quota.create_index([("org_id", 1), ("period", 1)], unique=True)
            await db.saas_emails.create_index("key", unique=True)
            await db.saas_stripe_prices.create_index([("plan", 1), ("cycle", 1), ("amount_cents", 1), ("mode", 1)])
            state["idx"] = True

    async def get_config() -> dict:
        if _cfg_cache["cfg"] and time.time() - _cfg_cache["at"] < 20:
            return _cfg_cache["cfg"]
        doc = await db.saas_config.find_one({"id": "config"}, {"_id": 0})
        if not doc:
            doc = copy.deepcopy(DEFAULT_CONFIG)
            await db.saas_config.update_one({"id": "config"}, {"$setOnInsert": doc}, upsert=True)
            doc = await db.saas_config.find_one({"id": "config"}, {"_id": 0})
        _cfg_cache.update(at=time.time(), cfg=doc)
        return doc

    async def state_for(org_id: str) -> dict:
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "saas": 1, "type": 1})
        return org_state(org, await get_config())

    async def is_saas(org_id: str) -> bool:
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "saas": 1, "type": 1})
        return bool((org or {}).get("saas")) and (org or {}).get("type", "cliente") == "cliente"

    def check(st: dict, secs, method: str, path: str) -> None:
        """Gating piano: funzionalità incluse + sola lettura a prova/abbonamento terminati."""
        if not st.get("enabled"):
            return
        if isinstance(secs, tuple) and not any(s in st["features"] for s in secs):
            raise HTTPException(status_code=403, detail={
                "code": "plan_feature", "plan": st.get("plan"),
                "message": f"Funzione non inclusa nel piano {st.get('plan_label') or ''}. Passa a un piano superiore per utilizzarla.".replace("  ", " ")})
        if method.upper() not in SAFE and not st["writable"] and not path.startswith(WRITE_EXEMPT):
            raise HTTPException(status_code=403, detail={
                "code": "plan_readonly", "message": "Prova terminata – Scegli il tuo piano. I tuoi dati restano consultabili."})

    async def init_trial(org_id: str, owner_user_id: Optional[str] = None):
        cfg = await get_config()
        await db.organizations.update_one({"id": org_id, "saas": {"$exists": False}}, {"$set": {"saas": trial_doc(cfg)}})
        asyncio.create_task(notify(org_id, "welcome", f"welcome:{org_id}"))

    # ---------------- email ----------------
    async def _recipients(org_id: str) -> list:
        uids = await db.memberships.distinct("user_id", {"org_id": org_id, "role": "admin_org", "active": True})
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "owner_user_id": 1})
        if (org or {}).get("owner_user_id"):
            uids = list(set(uids) | {org["owner_user_id"]})
        return await db.users.find({"user_id": {"$in": uids}}, {"_id": 0, "email": 1, "name": 1}).to_list(50) if uids else []

    async def notify(org_id: str, kind: str, key: str, extra: str = ""):
        """Email transazionali idempotenti (chiave univoca): nessun invio duplicato, nessuna lista Brevo toccata."""
        try:
            await _indexes()
            await db.saas_emails.insert_one({"key": key, "org_id": org_id, "kind": kind, "created_at": _iso(_now())})
        except DuplicateKeyError:
            return
        except Exception as e:
            logger.warning(f"saas notify index: {type(e).__name__}")
            return
        st = await state_for(org_id)
        cfg = await get_config()
        url = f"{deps['app_url']}/profilo?tab=abbonamento"
        days = cfg.get('trial_days', 14)
        texts = {
            "welcome": ("Benvenuto in CRMEvent: la tua prova gratuita è attiva", f"La tua prova gratuita di {days} giorni è attiva: puoi usare tutte le funzionalità di CRMEvent, con eventi e utenti illimitati. Nessuna carta di credito richiesta."),
            "trial_3d": ("La tua prova gratuita scade tra 3 giorni", "Mancano 3 giorni alla fine della prova gratuita. Scegli il piano più adatto per continuare a lavorare senza interruzioni: i tuoi dati restano al sicuro."),
            "trial_0d": ("La tua prova gratuita scade oggi", "La prova gratuita termina oggi. Dopo la scadenza i dati restano consultabili, ma per creare e modificare serve un piano attivo."),
            "purchase": ("Abbonamento CRMEvent confermato", f"Grazie! Il tuo abbonamento {extra} è confermato."),
            "renewal": ("Rinnovo abbonamento CRMEvent", f"Il tuo abbonamento {extra} è stato rinnovato correttamente."),
            "payment_failed": ("Pagamento abbonamento non riuscito", f"Non siamo riusciti a completare il pagamento dell'abbonamento {extra}. Aggiorna il metodo di pagamento da Gestisci abbonamento per evitare interruzioni."),
            "plan_changed": ("Cambio piano CRMEvent confermato", f"Il cambio piano è confermato: {extra}."),
            "canceled": ("Annullamento abbonamento CRMEvent", f"Abbiamo registrato l'annullamento dell'abbonamento. {extra}"),
        }
        subject, intro = texts[kind]
        for u in await _recipients(org_id):
            try:
                await send_email(to=u["email"], subject=subject, html=link_email(
                    name=u.get("name") or "", intro=intro, cta_label="Il mio abbonamento", url=url,
                    footer_note="Gestisci piano, pagamenti e fatture da Profilo & Account → Il mio abbonamento."))
            except Exception as e:
                logger.warning(f"saas email {kind} failed: {type(e).__name__}")

    # ---------------- Stripe ----------------
    def _assert_stripe():
        if deps["stripe_mode"] == "live" and not _live_enabled():
            raise HTTPException(status_code=503, detail="Gli abbonamenti non sono ancora attivi per i pagamenti reali. Riprova più tardi.")

    async def ensure_price(cfg: dict, plan: str, cycle: str) -> str:
        await _indexes()
        mode = deps["stripe_mode"]
        cents = int(round(float(cfg["plans"][plan][cycle]) * 100))
        row = await db.saas_stripe_prices.find_one({"plan": plan, "cycle": cycle, "amount_cents": cents, "mode": mode}, {"_id": 0})
        if row:
            return row["price_id"]
        prod = await db.saas_stripe_prices.find_one({"kind": "product", "plan": plan, "mode": mode}, {"_id": 0})
        if not prod:
            p = stripe_sdk.Product.create(name=f"CRMEvent {plan_label(cfg, plan)}", tax_code="txcd_10103001",
                                          metadata={"managed_by": "crmevent_saas", "saas_plan": plan})
            prod = {"kind": "product", "plan": plan, "mode": mode, "product_id": p.id}
            await db.saas_stripe_prices.insert_one({**prod})
        price = stripe_sdk.Price.create(product=prod["product_id"], unit_amount=cents, currency="eur",
                                        recurring={"interval": "month" if cycle == "monthly" else "year"},
                                        metadata={"saas_plan": plan, "saas_cycle": cycle, "config_version": str(cfg.get("version", 1))})
        await db.saas_stripe_prices.insert_one({"kind": "price", "plan": plan, "cycle": cycle, "amount_cents": cents, "mode": mode,
                                                "price_id": price.id, "product_id": prod["product_id"], "created_at": _iso(_now())})
        return price.id

    def _item(sub) -> dict:
        return sub["items"]["data"][0]

    async def sync_sub(sub, org_id: Optional[str] = None) -> Optional[str]:
        md = sub.get("metadata") or {}
        org_id = org_id or md.get("org_id")
        if not org_id:
            o = await db.organizations.find_one({"saas.stripe_subscription_id": sub.get("id")}, {"_id": 0, "id": 1})
            org_id = (o or {}).get("id")
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) if org_id else None
        if not org or not org.get("saas"):
            return None
        prev = org["saas"]
        it = _item(sub)
        price = it["price"]
        pmd = price.get("metadata") or {}
        plan = pmd.get("saas_plan") or md.get("plan")
        cycle = "yearly" if (price.get("recurring") or {}).get("interval") == "year" else "monthly"
        cps = sub.get("current_period_start") or it.get("current_period_start")
        cpe = sub.get("current_period_end") or it.get("current_period_end")
        status = sub.get("status")
        upd = {"saas.plan": plan, "saas.billing_cycle": cycle, "saas.stripe_status": status,
               "saas.stripe_subscription_id": sub.get("id"), "saas.price_amount": round((price.get("unit_amount") or 0) / 100, 2),
               "saas.current_period_start": _iso(_parse(cps)), "saas.current_period_end": _iso(_parse(cpe)),
               "saas.billing_anchor": _iso(_parse(sub.get("billing_cycle_anchor"))),
               "saas.cancel_at_period_end": bool(sub.get("cancel_at_period_end") or sub.get("cancel_at")),
               "saas.schedule_id": (sub.get("schedule") if isinstance(sub.get("schedule"), str) else (sub.get("schedule") or {}).get("id")),
               "subscription.stripe_customer_id": sub.get("customer"), "updated_at": _iso(_now())}
        if not prev.get("activated_at") and status in ("active", "trialing", "past_due"):
            upd["saas.activated_at"] = _iso(_now())
        pc = prev.get("pending_change") or {}
        if pc and pc.get("plan") == plan and pc.get("cycle") == cycle:
            upd["saas.pending_change"] = None
        if status in ("active", "trialing", "past_due"):
            upd["saas.trial_status"] = "converted" if prev.get("trial_status") == "active" else prev.get("trial_status")
        await db.organizations.update_one({"id": org_id}, {"$set": upd})
        cfg = await get_config()
        label = f"{plan_label(cfg, plan)} {'annuale' if cycle == 'yearly' else 'mensile'}"
        if prev.get("plan") and (prev.get("plan"), prev.get("billing_cycle")) != (plan, cycle) and status != "canceled":
            asyncio.create_task(notify(org_id, "plan_changed", f"plan:{sub.get('id')}:{plan}:{cycle}:{cps}", f"nuovo piano {label}"))
        if status == "canceled":
            asyncio.create_task(notify(org_id, "canceled", f"canceled:{sub.get('id')}", "I dati restano consultabili; puoi riattivare un piano in qualsiasi momento."))
        elif upd["saas.cancel_at_period_end"] and not prev.get("cancel_at_period_end"):
            end = (_parse(cpe) or _now()).strftime("%d/%m/%Y")
            asyncio.create_task(notify(org_id, "canceled", f"cancel_at_end:{sub.get('id')}:{cpe}", f"Il piano resta attivo fino al {end}."))
        return org_id

    def _invoice_sub_id(inv) -> Optional[str]:
        if inv.get("subscription"):
            s = inv["subscription"]
            return s if isinstance(s, str) else s.get("id")
        sd = ((inv.get("parent") or {}).get("subscription_details") or {})
        return sd.get("subscription")

    async def handle_webhook(t: str, obj) -> bool:
        """True se l'evento riguarda un abbonamento BRONZE/SILVER/GOLD (gestito qui)."""
        if t.startswith("customer.subscription."):
            if (obj.get("metadata") or {}).get("kind") != "saas":
                return False
            await sync_sub(stripe_sdk.Subscription.retrieve(obj["id"]))  # stato corrente: gli eventi possono arrivare fuori ordine
            return True
        if t == "checkout.session.completed":
            if (obj.get("metadata") or {}).get("kind") != "saas":
                return False
            if obj.get("subscription"):
                await sync_sub(stripe_sdk.Subscription.retrieve(obj["subscription"]), (obj.get("metadata") or {}).get("org_id"))
            return True
        if t in ("invoice.paid", "invoice.payment_succeeded", "invoice.payment_failed"):
            sid = _invoice_sub_id(obj)
            o = await db.organizations.find_one({"saas.stripe_subscription_id": sid}, {"_id": 0}) if sid else None
            if not o:
                return False
            await record_payment(o, obj, "payment_failed" if t == "invoice.payment_failed" else "paid")
            return True
        return False

    async def record_payment(org: dict, inv, status: str):
        total = (inv.get("total") or 0)
        if status == "paid" and total <= 0:
            return  # fattura a 0 € (avvio periodo di prova): nessun pagamento né documento fiscale
        await deps["record_invoice"](inv, status)
        cfg = await get_config()
        s = org.get("saas") or {}
        label = f"{plan_label(cfg, s.get('plan'))} {'annuale' if s.get('billing_cycle') == 'yearly' else 'mensile'}"
        test = deps["stripe_mode"] != "live"
        upd = {"kind": "saas_subscription", "saas_plan": s.get("plan"), "saas_cycle": s.get("billing_cycle"),
               "descrizione": f"Abbonamento CRMEvent {label}", "regime_fiscale": "forfettario",
               "aliquota_iva": 0.0, "importo_iva": 0.0, "iva": 0.0, "is_test": test}
        if test:
            upd.update({"fic_stato_documento": "test_non_inviata", "fic_stato_sdi": "non_inviato"})
        await db.invoices.update_one({"stripe_invoice_id": inv.get("id"), "fic_document_id": None}, {"$set": upd})
        if status == "paid" and not test:
            row = await db.invoices.find_one({"stripe_invoice_id": inv.get("id")}, {"_id": 0, "id": 1})
            if row:
                asyncio.create_task(deps["emit_invoice"](row["id"]))
        reason = inv.get("billing_reason")
        if status == "payment_failed":
            await db.organizations.update_one({"id": org["id"]}, {"$set": {"saas.stripe_status": "past_due"}})
            asyncio.create_task(notify(org["id"], "payment_failed", f"failed:{inv.get('id')}:{inv.get('attempt_count')}", label))
        elif reason == "subscription_cycle":
            asyncio.create_task(notify(org["id"], "renewal", f"renewal:{inv.get('id')}", label))
        elif reason == "subscription_create":
            asyncio.create_task(notify(org["id"], "purchase", f"purchase:{inv.get('id')}", label))

    async def _live_sub(org: dict):
        sid = (org.get("saas") or {}).get("stripe_subscription_id")
        if not sid:
            return None
        sub = stripe_sdk.Subscription.retrieve(sid)
        return sub if sub.get("status") in ("active", "trialing", "past_due") else None

    def _kind(cur_plan, cur_cycle, plan, cycle) -> str:
        if (cur_plan, cur_cycle) == (plan, cycle):
            return "same"
        if PLAN_RANK[plan] > PLAN_RANK[cur_plan] or (plan == cur_plan and cycle == "yearly"):
            return "upgrade"
        return "downgrade"

    def _validate(cfg, plan, cycle):
        if plan not in PLAN_KEYS or cycle not in CYCLES:
            raise HTTPException(status_code=400, detail="Piano o periodicità non validi")
        if not cfg["plans"][plan].get("active", True):
            raise HTTPException(status_code=400, detail="Piano non disponibile")

    # ---------------- Pubblico ----------------
    @r.get("/saas/plans-public")
    async def plans_public():
        cfg = await get_config()
        return {"trial_days": cfg.get("trial_days"), "trial_plan": cfg.get("trial_plan"), "trial_video_quota": cfg.get("trial_video_quota"),
                "features": [{"key": k, "label": l} for k, l in FEATURES],
                "plans": [{"key": k, **{f: cfg["plans"][k].get(f) for f in ("label", "color", "tagline", "monthly", "yearly", "features", "video_quota")}}
                          for k in PLAN_KEYS if cfg["plans"][k].get("active", True)]}

    # ---------------- Organizzazione ----------------
    @r.get("/saas/me")
    async def me(user: dict = Depends(deps["require_admin"])):
        st = await state_for(user["org_id"])
        if not st["enabled"]:
            return st
        out = {**st, "video": await video_policy(user["org_id"])}
        if (user.get("perm") or {}).get("admin"):
            out["payments"] = await db.invoices.find({"org_id": user["org_id"], "kind": "saas_subscription"}, {"_id": 0}).sort("data", -1).to_list(100)
        return out

    @r.post("/saas/checkout")
    async def checkout(body: CheckoutIn, user: dict = Depends(deps["require_org_admin"])):
        _assert_stripe()
        cfg = await get_config()
        _validate(cfg, body.plan, body.cycle)
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
        if not (org or {}).get("saas"):
            raise HTTPException(status_code=400, detail="La tua organizzazione usa ancora il modello a crediti")
        missing = deps["billing_missing"](org.get("billing") or {})
        if missing:
            raise HTTPException(status_code=400, detail={"code": "billing_missing", "missing": missing,
                                                         "message": "Completa i dati di fatturazione: " + ", ".join(missing)})
        if await _live_sub(org):
            raise HTTPException(status_code=400, detail="Hai già un abbonamento attivo: usa Cambia piano")
        price_id = await ensure_price(cfg, body.plan, body.cycle)
        cust = await deps["ensure_customer"](org, user)
        md = {"kind": "saas", "org_id": org["id"], "plan": body.plan, "cycle": body.cycle}
        sub_data = {"metadata": md}
        te = _parse(org["saas"].get("trial_end"))
        if te and te > _now():
            if te - _now() >= timedelta(hours=49):
                sub_data["trial_end"] = int(te.timestamp())
            else:
                sub_data["trial_period_days"] = 2
        origin = body.origin_url.rstrip("/")
        try:
            sess = stripe_sdk.checkout.Session.create(
                mode="subscription", customer=cust, line_items=[{"price": price_id, "quantity": 1}],
                success_url=f"{origin}/profilo?tab=abbonamento&checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{origin}/profilo?tab=abbonamento&checkout=cancel", metadata=md, subscription_data=sub_data,
                payment_method_collection="always")
        except stripe_sdk.error.StripeError as e:
            logger.error(f"saas checkout failed: {e}")
            raise HTTPException(status_code=502, detail="Non è stato possibile avviare il pagamento. Riprova più tardi.")
        await db.saas_checkouts.insert_one({"id": uuid.uuid4().hex, "org_id": org["id"], "session_id": sess.id, "plan": body.plan,
                                            "cycle": body.cycle, "user_id": user["user_id"], "created_at": _iso(_now())})
        return {"checkout_url": sess.url, "session_id": sess.id, "deferred_until": org["saas"].get("trial_end") if "trial_end" in sub_data or "trial_period_days" in sub_data else None}

    @r.get("/saas/checkout-confirmation")
    async def checkout_confirmation(session_id: str, user: dict = Depends(deps["require_admin"])):
        try:
            sess = stripe_sdk.checkout.Session.retrieve(session_id)
        except Exception:
            raise HTTPException(status_code=404, detail="Sessione non trovata")
        if (sess.get("metadata") or {}).get("org_id") != user["org_id"]:
            raise HTTPException(status_code=403, detail="Sessione non associata all'organizzazione")
        done = sess.get("status") == "complete" and bool(sess.get("subscription"))
        if done:
            await sync_sub(stripe_sdk.Subscription.retrieve(sess["subscription"]), user["org_id"])
        return {"complete": done, "state": await state_for(user["org_id"])}

    @r.get("/saas/change-preview")
    async def change_preview(plan: str, cycle: str, user: dict = Depends(deps["require_org_admin"])):
        _assert_stripe()
        cfg = await get_config()
        _validate(cfg, plan, cycle)
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
        sub = await _live_sub(org or {})
        if not sub:
            raise HTTPException(status_code=400, detail="Nessun abbonamento attivo: scegli un piano")
        s = org["saas"]
        kind = _kind(s.get("plan"), s.get("billing_cycle"), plan, cycle)
        out = {"kind": kind, "plan": plan, "cycle": cycle, "price": cfg["plans"][plan][cycle],
               "current_period_end": s.get("current_period_end"), "trialing": sub.get("status") == "trialing", "amount_due": 0.0}
        if kind == "upgrade" and sub.get("status") != "trialing":
            price_id = await ensure_price(cfg, plan, cycle)
            pv = stripe_sdk.Invoice.create_preview(customer=sub["customer"], subscription=sub["id"], subscription_details={
                "items": [{"id": _item(sub)["id"], "price": price_id}], "proration_behavior": "always_invoice"})
            out["amount_due"] = round((pv.get("amount_due") or 0) / 100, 2)
        return out

    @r.post("/saas/change")
    async def change(body: ChangeIn, user: dict = Depends(deps["require_org_admin"])):
        _assert_stripe()
        cfg = await get_config()
        _validate(cfg, body.plan, body.cycle)
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
        sub = await _live_sub(org or {})
        if not sub:
            raise HTTPException(status_code=400, detail="Nessun abbonamento attivo: scegli un piano")
        s = org["saas"]
        kind = _kind(s.get("plan"), s.get("billing_cycle"), body.plan, body.cycle)
        if kind == "same":
            raise HTTPException(status_code=400, detail="È già il tuo piano attuale")
        price_id = await ensure_price(cfg, body.plan, body.cycle)
        md = {"kind": "saas", "org_id": org["id"], "plan": body.plan, "cycle": body.cycle}
        trialing = sub.get("status") == "trialing"
        if kind == "upgrade" or trialing:
            if kind == "upgrade" and not trialing:
                pv = await change_preview(body.plan, body.cycle, user)
                if body.confirm_amount is None or abs(float(body.confirm_amount) - pv["amount_due"]) > 0.01:
                    raise HTTPException(status_code=409, detail={"code": "amount_changed", "amount_due": pv["amount_due"],
                                                                 "message": "L'importo del conguaglio è cambiato: conferma di nuovo"})
            if sub.get("schedule"):
                stripe_sdk.SubscriptionSchedule.release(sub["schedule"] if isinstance(sub["schedule"], str) else sub["schedule"]["id"])
            new = stripe_sdk.Subscription.modify(sub["id"], items=[{"id": _item(sub)["id"], "price": price_id}], metadata=md,
                                                 proration_behavior="none" if trialing else "always_invoice")
            await sync_sub(new, org["id"])
            await deps["record_audit"](user, "saas_plan_upgrade" if kind == "upgrade" else "saas_plan_change_trial", org_id=org["id"],
                                       detail=f"{s.get('plan')}/{s.get('billing_cycle')} → {body.plan}/{body.cycle}")
            return {"ok": True, "kind": kind, "immediate": True, "state": await state_for(org["id"])}
        # downgrade: alla scadenza del periodo già pagato (Subscription Schedule)
        sch_id = sub["schedule"] if isinstance(sub.get("schedule"), str) else (sub.get("schedule") or {}).get("id")
        sch = stripe_sdk.SubscriptionSchedule.retrieve(sch_id) if sch_id else stripe_sdk.SubscriptionSchedule.create(from_subscription=sub["id"])
        ph = sch["phases"][-1] if not sch_id else sch["phases"][0]
        cur_price = _item(sub)["price"]["id"]
        stripe_sdk.SubscriptionSchedule.modify(sch["id"], end_behavior="release", phases=[
            {"items": [{"price": cur_price, "quantity": 1}], "start_date": ph["start_date"], "end_date": ph["end_date"]},
            {"items": [{"price": price_id, "quantity": 1}], "metadata": md}])
        pc = {"plan": body.plan, "cycle": body.cycle, "effective_at": s.get("current_period_end"), "requested_at": _iso(_now())}
        await db.organizations.update_one({"id": org["id"]}, {"$set": {"saas.pending_change": pc, "saas.schedule_id": sch["id"]}})
        await deps["record_audit"](user, "saas_plan_downgrade_scheduled", org_id=org["id"],
                                   detail=f"{s.get('plan')}/{s.get('billing_cycle')} → {body.plan}/{body.cycle} dal {s.get('current_period_end', '')[:10]}")
        asyncio.create_task(notify(org["id"], "plan_changed", f"sched:{sch['id']}:{body.plan}:{body.cycle}",
                                   f"dal {(_parse(s.get('current_period_end')) or _now()).strftime('%d/%m/%Y')} passerai a {plan_label(cfg, body.plan)} {'annuale' if body.cycle == 'yearly' else 'mensile'}"))
        return {"ok": True, "kind": "downgrade", "immediate": False, "pending_change": pc}

    @r.post("/saas/change/cancel-pending")
    async def cancel_pending(user: dict = Depends(deps["require_org_admin"])):
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
        sch = ((org or {}).get("saas") or {}).get("schedule_id")
        if sch:
            try:
                stripe_sdk.SubscriptionSchedule.release(sch)
            except Exception as e:
                logger.warning(f"schedule release: {type(e).__name__}")
        await db.organizations.update_one({"id": user["org_id"]}, {"$set": {"saas.pending_change": None, "saas.schedule_id": None}})
        return {"ok": True}

    async def _set_cancel(user, flag: bool):
        _assert_stripe()
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
        sub = await _live_sub(org or {})
        if not sub:
            raise HTTPException(status_code=400, detail="Nessun abbonamento attivo")
        if sub.get("schedule"):
            stripe_sdk.SubscriptionSchedule.release(sub["schedule"] if isinstance(sub["schedule"], str) else sub["schedule"]["id"])
            await db.organizations.update_one({"id": org["id"]}, {"$set": {"saas.pending_change": None, "saas.schedule_id": None}})
        new = stripe_sdk.Subscription.modify(sub["id"], cancel_at_period_end=flag)
        await sync_sub(new, org["id"])
        await deps["record_audit"](user, "saas_cancel" if flag else "saas_resume", org_id=org["id"])
        return {"ok": True, "state": await state_for(org["id"])}

    @r.post("/saas/cancel")
    async def cancel(user: dict = Depends(deps["require_org_admin"])):
        return await _set_cancel(user, True)

    @r.post("/saas/resume")
    async def resume(user: dict = Depends(deps["require_org_admin"])):
        return await _set_cancel(user, False)

    @r.post("/saas/sync")
    async def sync_now(user: dict = Depends(deps["require_org_admin"])):
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
        sid = ((org or {}).get("saas") or {}).get("stripe_subscription_id")
        if sid:
            await sync_sub(stripe_sdk.Subscription.retrieve(sid), org["id"])
        return await state_for(user["org_id"])

    # ---------------- Videochiamate: quote per piano ----------------
    async def video_policy(org_id: str) -> dict:
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "saas": 1, "type": 1})
        cfg = await get_config()
        st = org_state(org, cfg)
        if not st["enabled"]:
            return {"mode": "credits"}
        base = {"mode": "plan", "plan": st["plan"], "plan_label": st["plan_label"], "trial": st["mode"] == "trial"}
        if not st["writable"]:
            return {**base, "allowed": False, "reason": "Prova terminata – Scegli il tuo piano per prenotare l'assistenza in videochiamata."}
        if st["mode"] == "trial":
            quota, period = int(cfg.get("trial_video_quota", 3)), "trial"
        else:
            quota = int(cfg["plans"][st["plan"]].get("video_quota", 0))
            s = org["saas"]
            period = monthly_period(_parse(s.get("billing_anchor") or s.get("current_period_start") or s.get("activated_at")))
        if quota == 0:
            return {**base, "allowed": False, "support": "email",
                    "reason": f"Il piano {st['plan_label']} include l'assistenza via email. Passa a SILVER o GOLD per prenotare le videochiamate."}
        q = await db.saas_video_quota.find_one({"org_id": org_id, "period": period}, {"_id": 0}) or {}
        used = int(q.get("used", 0))
        unlimited = quota < 0
        return {**base, "allowed": unlimited or used < quota, "unlimited": unlimited, "quota": None if unlimited else quota,
                "used": used, "remaining": None if unlimited else max(0, quota - used), "period": period,
                "priority": unlimited, "reason": None if unlimited or used < quota else
                ("Hai utilizzato tutte le videochiamate incluse nella prova." if period == "trial" else
                 "Hai utilizzato le videochiamate incluse questo mese: il conteggio si azzera con il nuovo periodo mensile.")}

    async def video_consume(org_id: str, period: str, quota: Optional[int]) -> bool:
        await _indexes()
        if quota is None:
            await db.saas_video_quota.update_one({"org_id": org_id, "period": period}, {"$inc": {"used": 1}}, upsert=True)
            return True
        try:
            res = await db.saas_video_quota.find_one_and_update({"org_id": org_id, "period": period, "used": {"$lt": quota}},
                                                                {"$inc": {"used": 1}}, upsert=True, return_document=ReturnDocument.AFTER)
        except DuplicateKeyError:
            return False
        return bool(res)

    async def video_release(org_id: str, period: str):
        await db.saas_video_quota.update_one({"org_id": org_id, "period": period, "used": {"$gt": 0}}, {"$inc": {"used": -1}})

    # ---------------- Cron: avvisi prova ----------------
    async def run_trial_notices() -> dict:
        now = _now()
        out = {"3d": 0, "0d": 0}
        rows = await db.organizations.find({"saas.trial_status": "active", "saas.plan": None}, {"_id": 0, "id": 1, "saas": 1}).to_list(5000)
        for o in rows:
            te = _parse(o["saas"].get("trial_end"))
            if not te:
                continue
            days = (te.date() - now.date()).days
            if days == 3:
                await notify(o["id"], "trial_3d", f"trial3:{o['id']}")
                out["3d"] += 1
            elif days == 0 or (te <= now and (now - te) < timedelta(days=1)):
                await notify(o["id"], "trial_0d", f"trial0:{o['id']}")
                out["0d"] += 1
            if te <= now:
                await db.organizations.update_one({"id": o["id"]}, {"$set": {"saas.trial_status": "expired"}})
        return out

    @r.post("/cron/saas-trial-tick")
    async def cron_trial(authorization: str = Header(default="")):
        # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
        import secrets as _s
        sec = deps["cron_secret"]
        if not sec or not _s.compare_digest(authorization or "", f"Bearer {sec}"):
            raise HTTPException(status_code=401, detail="unauthorized")
        asyncio.create_task(run_trial_notices())
        asyncio.create_task(deps["retry_invoices"]())  # nuovi tentativi fatture FIC non riuscite
        return {"accepted": True}

    # ---------------- Super Admin ----------------
    @r.get("/platform/saas/config")
    async def admin_config(admin: dict = Depends(deps["require_superadmin"])):
        return {**(await get_config()), "feature_catalog": [{"key": k, "label": l} for k, l in FEATURES],
                "stripe_mode": deps["stripe_mode"], "live_enabled": _live_enabled()}

    @r.put("/platform/saas/config")
    async def admin_put_config(body: ConfigIn, admin: dict = Depends(deps["require_superadmin"])):
        cur = await get_config()
        if set(body.plans) != set(PLAN_KEYS):
            raise HTTPException(status_code=400, detail="Devono essere presenti BRONZE, SILVER e GOLD")
        if not (1 <= body.trial_days <= 90) or body.trial_video_quota < 0:
            raise HTTPException(status_code=400, detail="Durata prova o limite videochiamate non validi")
        plans = {}
        for k, p in body.plans.items():
            if p.monthly <= 0 or p.yearly <= 0 or p.video_quota < -1:
                raise HTTPException(status_code=400, detail=f"Valori non validi per {k.upper()}")
            plans[k] = {**p.model_dump(), "features": [f for f in FEATURE_KEYS if f in p.features]}
        price_changed = any(round(plans[k][c], 2) != round(float(cur["plans"][k][c]), 2) for k in PLAN_KEYS for c in CYCLES)
        doc = {"trial_days": body.trial_days, "trial_video_quota": body.trial_video_quota, "plans": plans,
               "version": int(cur.get("version", 1)) + 1, "updated_at": _iso(_now()), "updated_by": admin.get("email")}
        await db.saas_config.update_one({"id": "config"}, {"$set": doc})
        await db.saas_config_history.insert_one({"id": uuid.uuid4().hex, "before": {k: cur.get(k) for k in ("plans", "trial_days", "trial_video_quota", "version")},
                                                 "after": doc, "by": admin.get("email"), "at": _iso(_now())})
        _cfg_cache["cfg"] = None
        await deps["record_audit"](admin, "saas_config_update", detail=f"versione {doc['version']}" + (" · prezzi aggiornati (solo nuovi abbonamenti)" if price_changed else ""))
        return await admin_config(admin)

    @r.get("/platform/saas/config/history")
    async def admin_history(admin: dict = Depends(deps["require_superadmin"])):
        return await db.saas_config_history.find({}, {"_id": 0}).sort("at", -1).to_list(50)

    @r.get("/platform/saas/organizations")
    async def admin_orgs(admin: dict = Depends(deps["require_superadmin"])):
        cfg = await get_config()
        orgs = await db.organizations.find({"type": {"$in": ["cliente", None]}}, {"_id": 0, "id": 1, "nome": 1, "type": 1, "saas": 1, "credits": 1, "created_at": 1}).to_list(5000)
        out = []
        for o in orgs:
            st = org_state(o, cfg)
            row = {"id": o["id"], "nome": o.get("nome"), "created_at": o.get("created_at"), "model": "abbonamento" if st["enabled"] else "crediti",
                   "credits_balance": (o.get("credits") or {}).get("balance")}
            if st["enabled"]:
                pay = await db.invoices.find({"org_id": o["id"], "kind": "saas_subscription"}, {"_id": 0, "totale": 1, "payment_status": 1}).to_list(500)
                vp = await video_policy(o["id"])
                row.update({k: st.get(k) for k in ("mode", "plan", "plan_label", "paid_plan", "billing_cycle", "price_amount", "activated_at",
                                                   "current_period_end", "trial_end", "days_left", "cancel_at_period_end", "pending_change", "stripe_status")})
                row.update({"payments_count": len([p for p in pay if p.get("payment_status") == "paid"]),
                            "payments_total": round(sum(float(p.get("totale") or 0) for p in pay if p.get("payment_status") == "paid"), 2),
                            "invoices_count": len(pay), "video_used": vp.get("used"), "video_quota": vp.get("quota"),
                            "video_unlimited": vp.get("unlimited"), "video_period": vp.get("period")})
            out.append(row)
        return out

    @r.post("/platform/saas/orgs/{org_id}/enable-trial")
    async def admin_enable(org_id: str, admin: dict = Depends(deps["require_superadmin"])):
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
        if not org or org.get("type", "cliente") != "cliente":
            raise HTTPException(status_code=404, detail="Organizzazione cliente non trovata")
        if org.get("saas"):
            raise HTTPException(status_code=400, detail="L'organizzazione è già sul modello ad abbonamento (prova già utilizzata)")
        await db.organizations.update_one({"id": org_id}, {"$set": {"saas": trial_doc(await get_config())}})
        await deps["record_audit"](admin, "saas_enable_trial", org_id=org_id, org_name=org.get("nome"))
        return await state_for(org_id)

    @r.post("/platform/saas/orgs/{org_id}/extend-trial")
    async def admin_extend(org_id: str, body: ExtendIn, admin: dict = Depends(deps["require_superadmin"])):
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "saas": 1, "nome": 1})
        if not (org or {}).get("saas") or not (1 <= body.days <= 60):
            raise HTTPException(status_code=400, detail="Operazione non valida")
        base = max(_parse(org["saas"].get("trial_end")) or _now(), _now())
        await db.organizations.update_one({"id": org_id}, {"$set": {"saas.trial_end": _iso(base + timedelta(days=body.days)), "saas.trial_status": "active"}})
        await deps["record_audit"](admin, "saas_extend_trial", org_id=org_id, org_name=org.get("nome"), detail=f"+{body.days} giorni")
        return await state_for(org_id)

    @r.post("/platform/saas/orgs/{org_id}/video-adjust")
    async def admin_video_adjust(org_id: str, body: AdjustIn, admin: dict = Depends(deps["require_superadmin"])):
        vp = await video_policy(org_id)
        if vp.get("mode") != "plan" or not vp.get("period") or body.delta not in (-1, 1):
            raise HTTPException(status_code=400, detail="Rettifica non applicabile")
        if body.delta < 0:
            await video_release(org_id, vp["period"])
        else:
            await db.saas_video_quota.update_one({"org_id": org_id, "period": vp["period"]}, {"$inc": {"used": 1}}, upsert=True)
        await deps["record_audit"](admin, "saas_video_adjust", org_id=org_id, detail=f"{body.delta:+d} · {vp['period']} · {body.note or ''}")
        return await video_policy(org_id)

    @r.get("/platform/saas/migration-report")
    async def migration_report(admin: dict = Depends(deps["require_superadmin"])):
        """Analisi in sola lettura del modello a crediti (nessuna modifica ai dati)."""
        orgs = await db.organizations.find({"type": {"$in": ["cliente", None]}}, {"_id": 0, "id": 1, "nome": 1, "credits": 1, "saas": 1}).to_list(5000)
        led = {}
        async for row in db.credit_ledger.aggregate([{"$match": {"status": {"$ne": "released"}}},
                                                     {"$group": {"_id": {"o": "$org_id", "r": "$reason_code"}, "n": {"$sum": 1}, "amt": {"$sum": "$amount"}}}]):
            led.setdefault(row["_id"]["o"], {})[row["_id"]["r"] or "altro"] = {"n": row["n"], "amount": row["amt"]}
        purchased = {r["_id"]: r for r in await db.credit_purchases.aggregate([{"$match": {"status": "paid"}},
                                                                                {"$group": {"_id": "$org_id", "n": {"$sum": 1}, "credits": {"$sum": "$credits_total"}}}]).to_list(5000)}
        ev = {r["_id"]: r for r in await db.events.aggregate([{"$group": {"_id": "$org_id", "attivi": {"$sum": {"$cond": [{"$eq": ["$credit_state", "attivo"]}, 1, 0]}},
                                                                            "rinnovi": {"$sum": {"$cond": [{"$ne": [{"$ifNull": ["$next_maintenance_at", None]}, None]}, 1, 0]}},
                                                                            "totali": {"$sum": 1}}}]).to_list(5000)}
        inv = {r["_id"]: r["n"] for r in await db.invoices.aggregate([{"$group": {"_id": "$org_id", "n": {"$sum": 1}}}]).to_list(5000)}
        rows = []
        for o in orgs:
            c = o.get("credits") or {}
            l = led.get(o["id"], {})
            ai = sum(v["n"] for k, v in l.items() if str(k).startswith("ai_"))
            rows.append({"id": o["id"], "nome": o.get("nome"), "model": "abbonamento" if o.get("saas") else "crediti",
                         "balance": c.get("balance", 0), "signup_bonus": bool(c.get("signup_bonus_granted")),
                         "purchased_credits": (purchased.get(o["id"]) or {}).get("credits", 0), "purchases": (purchased.get(o["id"]) or {}).get("n", 0),
                         "promo_credits": sum(v["amount"] for k, v in l.items() if k in ("signup_bonus", "admin_adjust", "promo", "migration")),
                         "events_total": (ev.get(o["id"]) or {}).get("totali", 0), "events_active": (ev.get(o["id"]) or {}).get("attivi", 0),
                         "renewals_scheduled": (ev.get(o["id"]) or {}).get("rinnovi", 0), "ai_uses": ai, "invoices": inv.get(o["id"], 0),
                         "ledger": l})
        tot = {k: sum(r[k] or 0 for r in rows) for k in ("balance", "purchased_credits", "events_active", "renewals_scheduled", "ai_uses", "invoices")}
        return {"generated_at": _iso(_now()), "totals": {**tot, "orgs": len(rows), "orgs_credits": len([r for r in rows if r["model"] == "crediti"])}, "orgs": rows}

    return {"router": r, "get_config": get_config, "state_for": state_for, "is_saas": is_saas, "check": check,
            "init_trial": init_trial, "handle_webhook": handle_webhook, "video_policy": video_policy,
            "video_consume": video_consume, "video_release": video_release, "gold_notice_hours": GOLD_NOTICE_HOURS,
            "run_trial_notices": run_trial_notices}
