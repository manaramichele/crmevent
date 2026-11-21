"""Accessi e utilizzo: sessioni (heartbeat di sola interazione), statistiche Super Admin e promemoria Brevo di inattività."""
import asyncio
import hashlib
import hmac
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import brevo_funnel
import access_templates as AT

ROME = ZoneInfo("Europe/Rome")
HEARTBEAT_SEC = 60
MAX_ATTEMPTS = 3
SYSTEM_ACTOR = {"user_id": "system", "email": None, "name": "Automazione promemoria", "role": "system"}
STEPS = ("inactive_1", "inactive_2", "never_1", "never_2")
ROLE_LABELS = {"admin_org": "Amministratore", "user": "Utente", "superadmin": "Super Admin",
               "volunteer": "Volontario", "staff": "Staff", "member": "Membro"}
DEFAULT_CONFIG = {
    "id": "default", "enabled": False, "mode": "simulation",
    "inactivity_timeout_min": 5, "retention_months": 12, "run_hour": 9,
    "inactive_first_days": 7, "inactive_second_extra_days": 7,
    "never_enabled": True, "never_first_days": 7, "never_second_days": 14, "never_start_from": "registration",
    "templates": {s: None for s in STEPS},
    "kinds": {"inactive_1": "service", "inactive_2": "promotional", "never_1": "service", "never_2": "promotional"},
    "roles_include": ["admin_org"], "roles_exclude": [], "orgs_include": [], "orgs_exclude": [],
}
BREVO_ATTRS = [("CRM_EVENT_LAST_LOGIN", "date"), ("CRM_EVENT_LAST_ACTIVITY", "date"), ("CRM_EVENT_DAYS_INACTIVE", "float"),
               ("CRM_EVENT_LOGIN_COUNT", "float"), ("CRM_EVENT_ORGANIZATION", "text"), ("CRM_EVENT_USER_ROLE", "text")]


def _now():
    return datetime.now(timezone.utc)


def _iso(d=None):
    return (d or _now()).isoformat()


def _dt(v):
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _max_dt(*vals):
    ds = [d for d in (_dt(v) for v in vals) if d]
    return max(ds) if ds else None


class HeartbeatIn(BaseModel):
    client_id: str
    interacted: bool = False


class EndIn(BaseModel):
    client_id: str
    reason: str = "logout"


class ConfigIn(BaseModel):
    enabled: Optional[bool] = None
    inactivity_timeout_min: Optional[int] = None
    retention_months: Optional[int] = None
    run_hour: Optional[int] = None
    inactive_first_days: Optional[int] = None
    inactive_second_extra_days: Optional[int] = None
    never_enabled: Optional[bool] = None
    never_first_days: Optional[int] = None
    never_second_days: Optional[int] = None
    never_start_from: Optional[str] = None
    templates: Optional[dict] = None
    kinds: Optional[dict] = None
    roles_include: Optional[list] = None
    roles_exclude: Optional[list] = None
    orgs_include: Optional[list] = None
    orgs_exclude: Optional[list] = None


class ActivateIn(BaseModel):
    confirm: bool = False


def build(db, deps: dict):
    r = APIRouter(prefix="/api")
    get_user, require_sa, audit = deps["get_current_user"], deps["require_superadmin"], deps["record_audit"]
    app_url, cron_secret, secret = deps["app_url"], deps["cron_secret"], deps["secret"]
    fake_send = os.environ.get("ACCESS_REMINDERS_FAKE_SEND") == "1"

    async def ensure_indexes():
        await db.access_sessions.create_index([("user_id", 1), ("client_id", 1), ("last_activity_at", -1)])
        await db.access_logins.create_index([("user_id", 1), ("at", -1)])
        await db.access_users.create_index("user_id", unique=True)
        await db.access_reminders.create_index([("cycle_id", 1), ("step", 1)], unique=True)
        await db.access_reminders.create_index([("user_id", 1), ("created_at", -1)])
        await db.access_runs.create_index("day", unique=True)
        if not await db.settings.find_one({"key": "access_monitor_started_at"}):
            await db.settings.update_one({"key": "access_monitor_started_at"}, {"$setOnInsert": {"value": _iso()}}, upsert=True)

    async def get_config():
        c = await db.access_reminder_config.find_one({"id": "default"}, {"_id": 0}) or {}
        out = {**DEFAULT_CONFIG, **c}
        out["templates"] = {**DEFAULT_CONFIG["templates"], **(c.get("templates") or {})}
        out["kinds"] = {**DEFAULT_CONFIG["kinds"], **(c.get("kinds") or {})}
        return out

    # ---------------- login / sessioni ----------------
    async def on_login(user_id: str, method: str):
        """Chiamato dopo ogni login riuscito: registra l'accesso e avvia un nuovo periodo di monitoraggio."""
        now = _iso()
        await db.access_logins.insert_one({"id": uuid.uuid4().hex, "user_id": user_id, "at": now, "method": method})
        await db.access_users.update_one({"user_id": user_id}, {
            "$set": {"last_login_at": now, "updated_at": now},
            "$setOnInsert": {"first_login_at": now, "total_seconds": 0},
            "$inc": {"login_count": 1}}, upsert=True)

    @r.post("/access/heartbeat")
    async def heartbeat(body: HeartbeatIn, user: dict = Depends(get_user)):
        if user.get("support") or not body.interacted or not body.client_id:
            return {"ok": True, "counted": False}
        cfg = await get_config()
        timeout = timedelta(minutes=max(int(cfg["inactivity_timeout_min"]), 1))
        now = _now()
        cid = body.client_id[:64]
        sess = await db.access_sessions.find_one({"user_id": user["user_id"], "client_id": cid, "ended_at": None},
                                                 {"_id": 0}, sort=[("last_activity_at", -1)])
        if sess and now - _dt(sess["last_activity_at"]) <= timeout:
            inc = min(int((now - _dt(sess["last_activity_at"])).total_seconds()), HEARTBEAT_SEC)
            await db.access_sessions.update_one({"id": sess["id"]}, {"$set": {"last_activity_at": _iso(now)}, "$inc": {"active_seconds": inc}})
        else:
            if sess:
                await db.access_sessions.update_one({"id": sess["id"]}, {"$set": {"ended_at": sess["last_activity_at"], "end_reason": "timeout"}})
            await db.access_sessions.insert_one({"id": uuid.uuid4().hex, "user_id": user["user_id"], "client_id": cid,
                                                 "started_at": _iso(now), "last_activity_at": _iso(now), "active_seconds": 0,
                                                 "ended_at": None, "end_reason": None})
        # Totale utente: un solo conteggio anche con più schede o dispositivi contemporanei.
        au = await db.access_users.find_one({"user_id": user["user_id"]}, {"_id": 0, "last_counted_at": 1}) or {}
        last = _dt(au.get("last_counted_at"))
        uinc = min(int((now - last).total_seconds()), HEARTBEAT_SEC) if last and now - last <= timeout else 0
        await db.access_users.update_one({"user_id": user["user_id"]}, {
            "$set": {"last_activity_at": _iso(now), "last_counted_at": _iso(now), "updated_at": _iso(now)},
            "$inc": {"total_seconds": max(uinc, 0)}, "$setOnInsert": {"login_count": 0}}, upsert=True)
        return {"ok": True, "counted": True}

    @r.post("/access/end")
    async def end_session(body: EndIn, user: dict = Depends(get_user)):
        if user.get("support"):
            return {"ok": True}
        reason = body.reason if body.reason in ("logout", "close") else "logout"
        await db.access_sessions.update_many({"user_id": user["user_id"], "client_id": body.client_id[:64], "ended_at": None},
                                             [{"$set": {"ended_at": "$last_activity_at", "end_reason": reason}}])
        return {"ok": True}

    # ---------------- utenti e statistiche ----------------
    async def _memberships():
        mems = await db.memberships.find({"active": True}, {"_id": 0, "user_id": 1, "org_id": 1, "role": 1}).to_list(100000)
        orgs = {o["id"]: o.get("nome") for o in await db.organizations.find({}, {"_id": 0, "id": 1, "nome": 1}).to_list(10000)}
        by_user = {}
        for m in mems:
            if m.get("org_id") in orgs:
                by_user.setdefault(m["user_id"], []).append({"org_id": m["org_id"], "org_name": orgs[m["org_id"]], "role": m.get("role")})
        return by_user, orgs

    def _row(u, au, mems, timeout, now):
        last_login = au.get("last_login_at") or u.get("last_login_at")
        last_act = au.get("last_activity_at")
        ref = _max_dt(last_login, last_act)
        never = not ref
        online = bool(last_act and now - _dt(last_act) <= timeout)
        roles = sorted({m["role"] for m in mems if m.get("role")} or {u.get("role")})
        return {"user_id": u["user_id"], "name": u.get("name") or "", "email": u.get("email") or "",
                "active": u.get("active") is not False, "user_role": u.get("role"),
                "orgs": mems, "org_names": [m["org_name"] for m in mems], "roles": roles,
                "role_labels": [ROLE_LABELS.get(x, x) for x in roles],
                "registered_at": u.get("registered_at") or u.get("created_at"),
                "first_login_at": au.get("first_login_at"), "last_login_at": last_login,
                "last_login_legacy": bool(last_login and not au.get("last_login_at")),
                "last_activity_at": last_act, "login_count": au.get("login_count", 0),
                "total_seconds": au.get("total_seconds", 0),
                "days_inactive": None if never else (now - ref).days,
                "status": "never" if never else ("online" if online else "offline")}

    async def _rows(org_id: Optional[str] = None):
        cfg = await get_config()
        timeout = timedelta(minutes=int(cfg["inactivity_timeout_min"]))
        now = _now()
        by_user, _ = await _memberships()
        users = await db.users.find({}, {"_id": 0, "password_hash": 0, "activation_token": 0}).to_list(100000)
        aus = {a["user_id"]: a for a in await db.access_users.find({}, {"_id": 0}).to_list(100000)}
        out = []
        for u in users:
            mems = by_user.get(u["user_id"], [])
            if org_id:
                mems = [m for m in mems if m["org_id"] == org_id]
                if not mems:
                    continue
            out.append(_row(u, aus.get(u["user_id"], {}), mems, timeout, now))
        return out

    async def _close_stale():
        cfg = await get_config()
        cutoff = _iso(_now() - timedelta(minutes=int(cfg["inactivity_timeout_min"])))
        await db.access_sessions.update_many({"ended_at": None, "last_activity_at": {"$lt": cutoff}},
                                             [{"$set": {"ended_at": "$last_activity_at", "end_reason": "timeout"}}])

    @r.get("/platform/access/overview")
    async def overview(request: Request, scope: str = "all", date_from: Optional[str] = None, date_to: Optional[str] = None,
                       admin: dict = Depends(require_sa)):
        org_id = None
        if scope == "active":
            org_id = request.headers.get("X-Org-Id")
            if not org_id or not await db.organizations.find_one({"id": org_id}, {"_id": 1}):
                raise HTTPException(status_code=400, detail="Seleziona un'organizzazione attiva nella tendina gialla")
        rows = await _rows(org_id)
        await _close_stale()
        uids = [x["user_id"] for x in rows]
        sq = {"user_id": {"$in": uids}}
        if date_from or date_to:
            sq["started_at"] = {**({"$gte": date_from} if date_from else {}), **({"$lte": date_to + "T23:59:59.999999"} if date_to else {})}
        sess = await db.access_sessions.find(sq, {"_id": 0, "active_seconds": 1}).to_list(200000)
        # Senza periodo: tempo deduplicato per utente (più schede/dispositivi contati una volta sola).
        tot = sum(x["total_seconds"] for x in rows) if not (date_from or date_to) else sum(s.get("active_seconds", 0) for s in sess)
        logged = [x for x in rows if x["status"] != "never"]
        k = {"users": len(rows), "logged": len(logged),
             "active_7": sum(1 for x in logged if x["days_inactive"] < 7),
             "inactive_7": sum(1 for x in logged if x["days_inactive"] >= 7),
             "inactive_14": sum(1 for x in logged if x["days_inactive"] >= 14),
             "inactive_30": sum(1 for x in logged if x["days_inactive"] >= 30),
             "never": len(rows) - len(logged), "online": sum(1 for x in rows if x["status"] == "online"),
             "sessions": len(sess), "avg_session_seconds": int(tot / len(sess)) if sess else 0, "total_seconds": tot}
        started = (await db.settings.find_one({"key": "access_monitor_started_at"}) or {}).get("value")
        return {"kpis": k, "users": rows, "monitoring_started_at": started, "org_id": org_id}

    @r.get("/platform/access/users/{user_id}")
    async def user_detail(user_id: str, admin: dict = Depends(require_sa)):
        u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0, "activation_token": 0})
        if not u:
            raise HTTPException(status_code=404, detail="Utente non trovato")
        cfg = await get_config()
        by_user, _ = await _memberships()
        au = await db.access_users.find_one({"user_id": user_id}, {"_id": 0}) or {}
        await _close_stale()
        row = _row(u, au, by_user.get(user_id, []), timedelta(minutes=int(cfg["inactivity_timeout_min"])), _now())
        sessions = await db.access_sessions.find({"user_id": user_id}, {"_id": 0, "client_id": 0}).sort("started_at", -1).to_list(500)
        logins = await db.access_logins.find({"user_id": user_id}, {"_id": 0}).sort("at", -1).to_list(500)
        reminders = await db.access_reminders.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
        n = len(sessions)
        row["avg_session_seconds"] = int(sum(s.get("active_seconds", 0) for s in sessions) / n) if n else 0
        started = (await db.settings.find_one({"key": "access_monitor_started_at"}) or {}).get("value")
        return {"user": row, "sessions": sessions, "logins": logins, "reminders": reminders, "monitoring_started_at": started}

    # ---------------- configurazione ----------------
    @r.get("/platform/access/config")
    async def config_get(admin: dict = Depends(require_sa)):
        return {**await get_config(), "fake_send": fake_send, "brevo_configured": brevo_funnel.is_configured()}

    @r.put("/platform/access/config")
    async def config_put(body: ConfigIn, admin: dict = Depends(require_sa)):
        upd = body.model_dump(exclude_none=True)
        ints = {"inactivity_timeout_min": (1, 120), "retention_months": (1, 60), "run_hour": (0, 23), "inactive_first_days": (1, 365),
                "inactive_second_extra_days": (1, 365), "never_first_days": (1, 365), "never_second_days": (2, 730)}
        for key, (lo, hi) in ints.items():
            if key in upd and not lo <= int(upd[key]) <= hi:
                raise HTTPException(status_code=400, detail=f"Valore non valido per {key} ({lo}-{hi})")
        cur = await get_config()
        if upd.get("never_second_days", cur["never_second_days"]) <= upd.get("never_first_days", cur["never_first_days"]):
            raise HTTPException(status_code=400, detail="Il secondo promemoria per chi non è mai entrato deve venire dopo il primo")
        if "never_start_from" in upd and upd["never_start_from"] not in ("registration", "activation"):
            raise HTTPException(status_code=400, detail="Data di partenza non valida")
        if "templates" in upd:
            upd["templates"] = {s: (int(v) if str(v or "").strip().isdigit() else None) for s, v in {**cur["templates"], **upd["templates"]}.items() if s in STEPS}
        if "kinds" in upd:
            upd["kinds"] = {s: v for s, v in {**cur["kinds"], **upd["kinds"]}.items() if s in STEPS and v in ("service", "promotional")}
        await db.access_reminder_config.update_one({"id": "default"}, {"$set": {**upd, "updated_at": _iso()}}, upsert=True)
        await audit(admin, "access_reminders_config", detail=", ".join(sorted(upd.keys())))
        return await config_get(admin)

    @r.post("/platform/access/activate")
    async def activate(body: ActivateIn, admin: dict = Depends(require_sa)):
        if not body.confirm:
            raise HTTPException(status_code=400, detail="Conferma esplicita richiesta")
        cfg = await get_config()
        missing = [s for s in STEPS if not cfg["templates"].get(s) and (s.startswith("inactive") or cfg["never_enabled"])]
        if missing:
            raise HTTPException(status_code=400, detail="Associa prima un template Brevo a ogni promemoria: " + ", ".join(missing))
        await db.access_reminder_config.update_one({"id": "default"}, {"$set": {"mode": "live", "enabled": True, "activated_at": _iso(),
                                                                                 "activated_by": admin.get("email")}}, upsert=True)
        await audit(admin, "access_reminders_live", detail="Invio reale dei promemoria attivato")
        return await config_get(admin)

    @r.post("/platform/access/deactivate")
    async def deactivate(admin: dict = Depends(require_sa)):
        await db.access_reminder_config.update_one({"id": "default"}, {"$set": {"mode": "simulation"}}, upsert=True)
        await audit(admin, "access_reminders_simulation", detail="Ritorno alla modalità simulazione")
        return await config_get(admin)

    # ---------------- motore promemoria ----------------
    def _filter_reason(cfg, row):
        if not row["active"]:
            return "Account disabilitato"
        if row["user_role"] == "superadmin":
            return "Super Admin escluso"
        if not row["email"]:
            return "Email mancante"
        mems = row["orgs"]
        if not mems:
            return "Nessuna organizzazione attiva"
        if cfg["orgs_exclude"] and any(m["org_id"] in cfg["orgs_exclude"] for m in mems):
            return "Organizzazione esclusa"
        if cfg["orgs_include"]:
            mems = [m for m in mems if m["org_id"] in cfg["orgs_include"]]
            if not mems:
                return "Organizzazione non inclusa"
        roles = {m["role"] for m in mems} | {row["user_role"]}
        if cfg["roles_exclude"] and roles & set(cfg["roles_exclude"]):
            return "Ruolo escluso"
        if cfg["roles_include"] and not roles & set(cfg["roles_include"]):
            return "Ruolo non incluso"
        return None

    async def _plan(cfg, now):
        """Calcola i promemoria dovuti oggi dai dati del backend. Non scrive nulla."""
        rows = await _rows()
        users = {u["user_id"]: u for u in await db.users.find({}, {"_id": 0, "user_id": 1, "password_hash": 1, "auth_provider": 1,
                                                                   "google_sub": 1, "created_at": 1, "registered_at": 1,
                                                                   "marketing_consent": 1, "reminders_opt_out": 1}).to_list(100000)}
        sent = {}
        for x in await db.access_reminders.find({"status": {"$in": ["sent", "test_sent", "sending"]}}, {"_id": 0, "cycle_id": 1, "step": 1, "sent_at": 1, "created_at": 1}).to_list(200000):
            sent[(x["cycle_id"], x["step"])] = _dt(x.get("sent_at") or x.get("created_at"))
        out = []
        for row in rows:
            u = users.get(row["user_id"], {})
            step, cycle, days = None, None, None
            if row["status"] == "never":
                if not cfg["never_enabled"]:
                    continue
                start = u.get("created_at") if cfg["never_start_from"] == "registration" else (u.get("registered_at") or u.get("created_at"))
                if not _dt(start):
                    continue
                days = (now - _dt(start)).days
                cycle = f"never:{row['user_id']}"
                if days >= cfg["never_second_days"] and (cycle, "never_1") in sent and (cycle, "never_2") not in sent \
                        and now - sent[(cycle, "never_1")] >= timedelta(days=cfg["never_second_days"] - cfg["never_first_days"]):
                    step = "never_2"
                elif days >= cfg["never_first_days"] and (cycle, "never_1") not in sent:
                    step = "never_1"
            else:
                ref = _max_dt(row["last_login_at"], row["last_activity_at"])
                days = row["days_inactive"]
                cycle = f"inactive:{row['user_id']}:{ref.isoformat()}"
                first, extra = cfg["inactive_first_days"], cfg["inactive_second_extra_days"]
                if days >= first + extra and (cycle, "inactive_1") in sent and (cycle, "inactive_2") not in sent \
                        and now - sent[(cycle, "inactive_1")] >= timedelta(days=extra):
                    step = "inactive_2"
                elif days >= first and (cycle, "inactive_1") not in sent:
                    step = "inactive_1"
            if not step:
                continue
            reason = _filter_reason(cfg, row)
            if not reason and row["status"] == "never" and not (u.get("password_hash") or u.get("google_sub") or u.get("auth_provider") == "google"):
                reason = "Account non ancora attivato"
            if not reason and u.get("reminders_opt_out"):
                reason = "Ha disattivato i promemoria"
            if not reason and cfg["kinds"].get(step) == "promotional" and not u.get("marketing_consent"):
                reason = "Comunicazione promozionale senza consenso marketing"
            if not reason and not cfg["templates"].get(step):
                reason = "Template Brevo non associato"
            out.append({"user_id": row["user_id"], "name": row["name"], "email": row["email"], "org_names": row["org_names"],
                        "roles": row["role_labels"], "step": step, "cycle_id": cycle, "days": days,
                        "template_id": cfg["templates"].get(step), "kind": cfg["kinds"].get(step), "excluded": reason})
        return out

    async def _brevo_block_reason(email):
        if fake_send or not brevo_funnel.is_configured():
            return None
        from urllib.parse import quote
        sc, data, err = await brevo_funnel._request("GET", f"/v3/contacts/{quote(email, safe='')}")
        if sc == 200 and isinstance(data, dict) and data.get("emailBlacklisted"):
            return "Opposizione/blocco presente in Brevo"
        return None

    def _unsub_token(uid):
        return hmac.new(secret.encode(), f"acc-unsub:{uid}".encode(), hashlib.sha256).hexdigest()[:32]

    async def _send(item):
        params = {"NOME": (item["name"] or "").split(" ")[0] or "ciao", "APP_URL": app_url, "LOGIN_URL": f"{app_url}/login",
                  "DEMO_URL": f"{app_url}/demo", "SUPPORT_URL": f"{app_url}/app",
                  "UNSUB_URL": f"{app_url}/api/access/unsubscribe?u={item['user_id']}&t={_unsub_token(item['user_id'])}",
                  "GIORNI": item["days"], "ORGANIZZAZIONE": ", ".join(item["org_names"])}
        if fake_send:
            return {"ok": True, "status": "test", "messageId": f"<test-{uuid.uuid4().hex[:10]}@preview>", "error": None}
        return await brevo_funnel.send_template(template_id=item["template_id"], to_email=item["email"],
                                                to_name=item["name"] or None, params=params)

    async def _deliver(item, rec_id):
        res = await _send(item)
        ok = res.get("ok")
        status = ("test_sent" if res.get("status") == "test" else "sent") if ok else "failed"
        await db.access_reminders.update_one({"id": rec_id}, {"$set": {
            "status": status, "brevo_status": res.get("status"), "brevo_message_id": res.get("messageId"),
            "error": res.get("error"), "sent_at": _iso() if ok else None, "updated_at": _iso()}, "$inc": {"attempts": 1}})
        await audit(SYSTEM_ACTOR, "access_reminder_sent" if ok else "access_reminder_failed", target_email=item["email"],
                    target_name=item["name"], detail=f"{AT.LABELS[item['step']]} · {item['days']} giorni · template {item['template_id']}"
                    + (f" · errore: {res.get('error')}" if not ok else ""),
                    meta={"cycle_id": item["cycle_id"], "step": item["step"], "message_id": res.get("messageId")})
        return ok

    async def run_reminders(force_day: Optional[str] = None):
        cfg = await get_config()
        if not cfg["enabled"] or cfg["mode"] != "live":
            return {"skipped": "simulation"}
        now = _now()
        stats = {"sent": 0, "failed": 0, "excluded": 0, "retried": 0}
        # Retry controllati: solo errori, massimo MAX_ATTEMPTS, una volta per esecuzione.
        for rec in await db.access_reminders.find({"status": "failed", "attempts": {"$lt": MAX_ATTEMPTS}}, {"_id": 0}).to_list(1000):
            claimed = await db.access_reminders.find_one_and_update({"id": rec["id"], "status": "failed"}, {"$set": {"status": "sending"}},
                                                                    return_document=ReturnDocument.AFTER)
            if not claimed:
                continue
            u = await db.users.find_one({"user_id": rec["user_id"]}, {"_id": 0, "active": 1})
            if not u or u.get("active") is False:
                await db.access_reminders.update_one({"id": rec["id"]}, {"$set": {"status": "canceled", "error": "Account non più attivo"}})
                continue
            if await db.access_logins.find_one({"user_id": rec["user_id"], "at": {"$gt": rec["created_at"]}}, {"_id": 1}):
                await db.access_reminders.update_one({"id": rec["id"]}, {"$set": {"status": "canceled", "error": "Nuovo accesso: sequenza interrotta"}})
                continue
            stats["retried"] += 1
            await _deliver(rec, rec["id"])
        for item in await _plan(cfg, now):
            if item["excluded"]:
                stats["excluded"] += 1
                continue
            block = await _brevo_block_reason(item["email"])
            if block:
                stats["excluded"] += 1
                continue
            rec = {"id": uuid.uuid4().hex, **item, "status": "sending", "attempts": 0, "created_at": _iso(), "brevo_message_id": None, "error": None}
            try:
                await db.access_reminders.insert_one(rec)  # indice unico (cycle_id, step): nessun doppio invio tra processi
            except DuplicateKeyError:
                continue
            ok = await _deliver(item, rec["id"])
            stats["sent" if ok else "failed"] += 1
        return stats

    async def daily_tick():
        cfg = await get_config()
        local = _now().astimezone(ROME)
        if local.hour < int(cfg["run_hour"]):
            return {"skipped": "not_yet"}
        day = local.strftime("%Y-%m-%d")
        try:
            await db.access_runs.insert_one({"day": day, "started_at": _iso()})
        except DuplicateKeyError:
            return {"skipped": "already_ran"}
        cutoff = _iso(_now() - timedelta(days=30 * int(cfg["retention_months"])))
        await db.access_sessions.delete_many({"started_at": {"$lt": cutoff}})
        await db.access_logins.delete_many({"at": {"$lt": cutoff}})
        await _close_stale()
        stats = await run_reminders()
        if cfg["enabled"] and cfg["mode"] == "live":
            await sync_brevo()
        await db.access_runs.update_one({"day": day}, {"$set": {"finished_at": _iso(), "stats": stats}})
        return stats

    @r.post("/cron/access-reminders-tick")
    async def cron_tick(authorization: str = Header(default="")):
        # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
        if not cron_secret or not hmac.compare_digest(authorization or "", f"Bearer {cron_secret}"):
            raise HTTPException(status_code=401, detail="unauthorized")
        asyncio.create_task(daily_tick())
        return {"accepted": True}

    @r.post("/platform/access/simulate")
    async def simulate(admin: dict = Depends(require_sa)):
        cfg = await get_config()
        items = await _plan(cfg, _now())
        return {"mode": cfg["mode"], "enabled": cfg["enabled"], "items": items,
                "counts": {s: sum(1 for i in items if i["step"] == s and not i["excluded"]) for s in STEPS},
                "excluded": sum(1 for i in items if i["excluded"])}

    @r.post("/platform/access/run-now")
    async def run_now(admin: dict = Depends(require_sa)):
        cfg = await get_config()
        if not cfg["enabled"] or cfg["mode"] != "live":
            raise HTTPException(status_code=400, detail="Invio reale non attivo: usa «Simula automazione»")
        stats = await run_reminders()
        await audit(admin, "access_reminders_run", detail=str(stats))
        return stats

    @r.get("/platform/access/reminders")
    async def reminders_log(admin: dict = Depends(require_sa)):
        recs = await db.access_reminders.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
        for x in recs:
            after = x.get("sent_at") or x.get("created_at")
            nxt = await db.access_logins.find_one({"user_id": x["user_id"], "at": {"$gt": after}}, {"_id": 0, "at": 1}, sort=[("at", 1)])
            x["next_login_at"] = (nxt or {}).get("at")
            x["step_label"] = AT.LABELS.get(x["step"], x["step"])
        return recs

    # ---------------- Brevo: template e attributi ----------------
    @r.get("/platform/access/templates")
    async def templates_status(admin: dict = Depends(require_sa)):
        cfg = await get_config()
        out = []
        for s in STEPS:
            tid, info = cfg["templates"].get(s), None
            if tid and brevo_funnel.is_configured():
                sc, data, err = await brevo_funnel._request("GET", f"/v3/smtp/templates/{int(tid)}")
                info = {"name": data.get("name"), "active": data.get("isActive"), "subject": data.get("subject")} if sc == 200 and isinstance(data, dict) else {"error": err}
            out.append({"step": s, "label": AT.LABELS[s], "template_id": tid, "kind": cfg["kinds"].get(s), "brevo": info,
                        "default_name": AT.TEMPLATES[s]["name"]})
        return out

    @r.post("/platform/access/templates/setup")
    async def templates_setup(admin: dict = Depends(require_sa)):
        """Crea i 4 template come BOZZE (non attivi) in Brevo; se esistono già per nome li collega senza sovrascriverli."""
        if not brevo_funnel.is_configured():
            raise HTTPException(status_code=400, detail="Brevo non configurato")
        cfg = await get_config()
        tpl, res = dict(cfg["templates"]), []
        for s in STEPS:
            t = AT.TEMPLATES[s]
            tid = tpl.get(s) or await brevo_funnel._find_template_id_by_name(t["name"])
            created = False
            if not tid:
                sc, data, err = await brevo_funnel._request("POST", "/v3/smtp/templates", json={
                    "templateName": t["name"], "subject": t["subject"], "sender": brevo_funnel.SENDER,
                    "htmlContent": AT.build_html(s, cfg["kinds"].get(s)), "tag": "crmevent-access-reminders", "isActive": False})
                tid = (data or {}).get("id") if sc in (200, 201) and isinstance(data, dict) else None
                created = bool(tid)
                if not tid:
                    res.append({"step": s, "ok": False, "error": err})
                    continue
            tpl[s] = int(tid)
            res.append({"step": s, "ok": True, "id": int(tid), "created": created})
        await db.access_reminder_config.update_one({"id": "default"}, {"$set": {"templates": tpl}}, upsert=True)
        await audit(admin, "access_templates_setup", detail=", ".join(f"{x['step']}={x.get('id')}" for x in res))
        return res

    async def _ensure_brevo_attrs():
        sc, data, err = await brevo_funnel._request("GET", "/v3/contacts/attributes")
        existing = {a.get("name") for a in (data or {}).get("attributes", [])} if sc == 200 and isinstance(data, dict) else None
        if existing is None:
            raise HTTPException(status_code=502, detail=f"Brevo non raggiungibile: {err}")
        created = []
        for name, typ in BREVO_ATTRS:
            if name not in existing:
                sc2, _, _ = await brevo_funnel._request("POST", f"/v3/contactAttributes/normal/{name}", json={"type": typ})
                if sc2 in (200, 201, 204):
                    created.append(name)
        return created

    async def sync_brevo():
        if not brevo_funnel.is_configured() or fake_send:
            return {"skipped": True, "reason": "Brevo non configurato" if not fake_send else "Ambiente di prova: sincronizzazione simulata"}
        cfg = await get_config()
        created = await _ensure_brevo_attrs()
        ok = fail = 0
        for row in await _rows():
            if _filter_reason({**cfg, "orgs_include": [], "orgs_exclude": []}, row):
                continue
            attrs = {"CRM_EVENT_LAST_LOGIN": (row["last_login_at"] or "")[:10] or None,
                     "CRM_EVENT_LAST_ACTIVITY": (row["last_activity_at"] or "")[:10] or None,
                     "CRM_EVENT_DAYS_INACTIVE": row["days_inactive"], "CRM_EVENT_LOGIN_COUNT": row["login_count"],
                     "CRM_EVENT_ORGANIZATION": "; ".join(row["org_names"]), "CRM_EVENT_USER_ROLE": "; ".join(row["role_labels"])}
            body = {"email": row["email"], "updateEnabled": True, "attributes": {k: v for k, v in attrs.items() if v is not None}}
            sc, _, _ = await brevo_funnel._request("POST", "/v3/contacts", json=body)
            ok, fail = (ok + 1, fail) if sc in (200, 201, 204) else (ok, fail + 1)
        await db.settings.update_one({"key": "access_brevo_last_sync"}, {"$set": {"value": _iso()}}, upsert=True)
        return {"attributes_created": created, "synced": ok, "failed": fail}

    @r.post("/platform/access/brevo-sync")
    async def brevo_sync(admin: dict = Depends(require_sa)):
        res = await sync_brevo()
        await audit(admin, "access_brevo_sync", detail=str(res))
        return res

    @r.get("/access/unsubscribe", response_class=HTMLResponse)
    async def unsubscribe(u: str, t: str):
        if not hmac.compare_digest(t or "", _unsub_token(u)):
            return HTMLResponse("<p>Link non valido.</p>", status_code=400)
        res = await db.users.update_one({"user_id": u}, {"$set": {"reminders_opt_out": True, "reminders_opt_out_at": _iso()}})
        if res.matched_count:
            usr = await db.users.find_one({"user_id": u}, {"_id": 0, "email": 1, "name": 1}) or {}
            await audit(SYSTEM_ACTOR, "access_reminders_opt_out", target_email=usr.get("email"), target_name=usr.get("name"))
        return HTMLResponse("<div style='font-family:Arial;max-width:480px;margin:60px auto;text-align:center'>"
                            "<h2>Promemoria disattivati</h2><p>Non riceverai più i promemoria automatici di CRMEvent.</p></div>")

    return {"router": r, "on_login": on_login, "ensure_indexes": ensure_indexes, "daily_tick": daily_tick,
            "run_reminders": run_reminders}
