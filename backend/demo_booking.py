"""Prenotazione Demo: sincronizzazione Brevo (lista Lead esistente, nessun duplicato), email operative e promemoria."""
import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import brevo_funnel
import email_utils

logger = logging.getLogger("demo_booking")
ROME = ZoneInfo("Europe/Rome")
SOURCE = "Prenotazione Demo CRMEvent"
MAX_ATTEMPTS = 5
RETRY_EVERY = timedelta(hours=1)
NEW_ATTRS = ["TELEFONO", "DATA_RICHIESTA", "DATA_DEMO", "STATO_PRENOTAZIONE", "CONSENSO_MARKETING", "DATA_CONSENSO_MARKETING"]
STATUS_LABEL = {"da_confermare": "Da confermare", "confermata": "Confermata", "riprogrammata": "Riprogrammata", "annullata": "Annullata"}
_attrs_ready = {"ok": False}


def _now():
    return datetime.now(timezone.utc)


def fmt_slot(slot: str) -> str:
    try:
        return datetime.strptime(slot, "%Y-%m-%dT%H:%M").strftime("%d/%m/%Y alle %H:%M")
    except (TypeError, ValueError):
        return ""


async def lead_list_id(db):
    """ID reale della lista 'CRMEvent · Lead' (configurato): mai creare liste nuove da qui."""
    lid = os.environ.get("BREVO_LEAD_LIST_ID", "").strip() or (await db.settings.find_one({"key": "brevo_lead_list_id"}) or {}).get("value")
    return int(lid) if lid else None


async def sync_lead(db, lead: dict) -> dict:
    """Crea/aggiorna il contatto per email (updateEnabled) e lo aggiunge alla lista Lead; non tocca altre liste né i blocchi."""
    attempts = int((lead.get("brevo_sync") or {}).get("attempts") or 0) + 1
    state = {"attempts": attempts, "last_attempt_at": _now().isoformat()}
    if not brevo_funnel.is_configured():
        state.update({"status": "non_configurato", "error": "Brevo non configurato"})
    else:
        lid = await lead_list_id(db)
        if not lid:
            state.update({"status": "errore", "error": "ID lista Lead non configurato"})
        else:
            if not _attrs_ready["ok"]:
                for name in NEW_ATTRS:
                    await brevo_funnel._request("POST", f"/v3/contactAttributes/normal/{name}", json={"type": "text"})
                _attrs_ready["ok"] = True
            extra = {"TELEFONO": lead.get("telefono"), "DATA_RICHIESTA": (lead.get("requested_at") or "")[:10],
                     "DATA_DEMO": fmt_slot(lead.get("demo_slot")), "STATO_PRENOTAZIONE": STATUS_LABEL.get(lead.get("demo_status"), ""),
                     "CONSENSO_MARKETING": "si" if lead.get("marketing_consent") else None,
                     "DATA_CONSENSO_MARKETING": (lead.get("marketing_consent_at") or "")[:10] or None}
            res = await brevo_funnel.upsert_contact(email=lead["email"], nome=lead.get("nome"), cognome=lead.get("cognome"),
                                                    organizzazione=lead.get("organizzazione"), tipologia_eventi=lead.get("tipologia_eventi"),
                                                    source=SOURCE, list_ids=[lid], extra={k: v for k, v in extra.items() if v})
            state.update({"status": "sincronizzato" if res["ok"] else "errore", "error": None if res["ok"] else res.get("error"),
                          "list_id": lid, "synced_at": _now().isoformat() if res["ok"] else None})
    await db.leads.update_one({"id": lead["id"]}, {"$set": {"brevo_sync": state}})
    if state["status"] == "errore":
        logger.warning(f"brevo demo sync failed lead={lead['id']} attempt={attempts}: {state['error']}")
    return state


async def meet_for_demo(db, lead: dict, action: str):
    """Link Google Meet per le demo confermate (stesso calendario e stessa simulazione dell'assistenza video)."""
    import gcal_utils
    import video_support
    eid = lead.get("demo_event_id")
    if video_support.simulation():
        if action == "cancel":
            return {"demo_meet_link": None, "demo_event_id": None}
        return {"demo_event_id": eid or f"sim-demo-{lead['id'][:10]}", "demo_meet_simulated": True,
                "demo_meet_link": lead.get("demo_meet_link") or f"https://meet.google.com/sim-{lead['id'][:3]}-{lead['id'][3:7]}-{lead['id'][7:10]}"}
    cfg = await db.video_support_config.find_one({"id": "config"}, {"_id": 0}) or {}
    conn = await db.calendar_connections.find_one({"user_id": cfg.get("calendar_user_id")}, {"_id": 0}) if cfg.get("calendar_user_id") else None
    if not (conn and gcal_utils.is_configured()):
        logger.warning("demo meet: calendario Super Admin non collegato")
        return {}
    cal = conn.get("calendar_id") or "primary"
    try:
        if action == "cancel":
            if eid:
                gcal_utils.delete_event(conn["tokens"], cal, eid)
            return {"demo_meet_link": None, "demo_event_id": None}
        start = datetime.strptime(lead["demo_slot"], "%Y-%m-%dT%H:%M")
        end = start + timedelta(minutes=30)
        times = {"start": {"dateTime": start.strftime("%Y-%m-%dT%H:%M:00"), "timeZone": "Europe/Rome"},
                 "end": {"dateTime": end.strftime("%Y-%m-%dT%H:%M:00"), "timeZone": "Europe/Rome"}}
        if eid:
            gcal_utils.patch_event(conn["tokens"], cal, eid, times)
            return {}
        body = {"summary": f"Demo CRMEvent · {lead.get('organizzazione') or lead.get('nome')}", **times,
                "description": f"Demo CRMEvent\n{lead.get('nome') or ''} {lead.get('cognome') or ''} ({lead['email']})",
                "attendees": [{"email": lead["email"]}]}
        ev = gcal_utils.create_meet_event(conn["tokens"], cal, body, f"demo-{lead['id']}")
        return {"demo_event_id": ev["id"], "demo_meet_link": ev.get("hangoutLink"), "demo_meet_simulated": False}
    except Exception as e:  # noqa: BLE001
        logger.error(f"demo meet {action} failed: {type(e).__name__}")
        return {}


async def send_operational(lead: dict, kind: str, app_url: str):
    """Email operative della prenotazione (indipendenti dal consenso marketing)."""
    slot = fmt_slot(lead.get("demo_slot"))
    texts = {
        "ricevuta": ("Abbiamo ricevuto la tua richiesta di demo CRMEvent",
                     f"Grazie! Abbiamo ricevuto la tua richiesta di demo{f' per il {slot}' if slot else ''}. Ti confermeremo l'appuntamento a breve. Nel frattempo puoi provare la demo interattiva."),
        "confermata": ("Demo CRMEvent confermata", f"La tua demo di CRMEvent è confermata per il {slot}. Ti aspettiamo!"),
        "riprogrammata": ("Demo CRMEvent riprogrammata", f"La tua demo di CRMEvent è stata spostata al {slot}."),
        "annullata": ("Demo CRMEvent annullata", "La tua demo di CRMEvent è stata annullata. Se vuoi, puoi richiederne una nuova quando preferisci."),
        "promemoria": ("Promemoria: domani la tua demo CRMEvent", f"Ti ricordiamo la demo di CRMEvent del {slot}."),
    }
    subject, intro = texts[kind]
    meet = lead.get("demo_meet_link") if kind in ("confermata", "riprogrammata", "promemoria") else None
    if meet:
        intro += " Al momento dell'appuntamento collegati con il link Google Meet qui sotto."
    try:
        await email_utils.send_email(to=lead["email"], subject=subject, html=email_utils.link_email(
            name=lead.get("nome") or "", intro=intro, cta_label="Apri Google Meet" if meet else "Guarda la demo interattiva",
            url=meet or f"{app_url}/demo",
            footer_note="Hai ricevuto questa email perché hai richiesto una demo su crmevent.it."))
        return True
    except Exception as e:  # noqa: BLE001
        logger.error(f"demo operational email '{kind}' failed: {type(e).__name__}")
        return False


async def tick(db, app_url: str):
    """Ogni tick del cron funnel: ritenta sync Brevo fallite (1/h, max 5) e invia i promemoria del giorno prima."""
    cutoff = (_now() - RETRY_EVERY).isoformat()
    for lead in await db.leads.find({"brevo_sync.status": "errore", "brevo_sync.attempts": {"$lt": MAX_ATTEMPTS},
                                     "brevo_sync.last_attempt_at": {"$lte": cutoff}}, {"_id": 0}).to_list(200):
        await sync_lead(db, lead)
    now_rome = _now().astimezone(ROME)
    lo, hi = now_rome.strftime("%Y-%m-%dT%H:%M"), (now_rome + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")
    for lead in await db.leads.find({"demo_status": {"$in": ["confermata", "riprogrammata"]}, "demo_slot": {"$gt": lo, "$lte": hi}},
                                    {"_id": 0}).to_list(200):
        if lead.get("demo_reminder_sent_for") == lead["demo_slot"]:
            continue
        res = await db.leads.update_one({"id": lead["id"], "demo_reminder_sent_for": {"$ne": lead["demo_slot"]}},
                                        {"$set": {"demo_reminder_sent_for": lead["demo_slot"]}})
        if res.modified_count:
            await send_operational(lead, "promemoria", app_url)
