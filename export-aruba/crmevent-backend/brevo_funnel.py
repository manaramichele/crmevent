"""Brevo Demo Funnel — CRMEvent is the source of truth for lead/funnel state.
Brevo is used only for: contact management, email delivery (templates), stats.
The API key is read from the environment and never returned, logged, or exposed."""
import os
import logging
from html import escape

import httpx

logger = logging.getLogger("crmevent.brevo_funnel")

BREVO_BASE = "https://api.brevo.com"
TIFFANY = "#81D8D0"
TIFFANY_DARK = "#59C1B7"
INK = "#0f172a"
MUTED = "#475569"
FAINT = "#94a3b8"
LOGO_URL = ("https://customer-assets-jai6qajn.emergentagent.net/job_manage-events-12/"
            "artifacts/6flsyynu_ChatGPT%20Image%2023%20set%202026%2C%2014_52_43.png")

FUNNEL_KEY = "demo"
FUNNEL_NAME = "Funnel Demo CRMEvent"
BREVO_TAG = "crmevent-funnel-demo"

# funnel_status values that immediately STOP the demo funnel
STOP_FUNNEL_STATUSES = {"trial_started", "cliente"}

# Steps: delay_days measured from enrollment (demo_requested). require_not_engaged means
# "send only if the lead has NOT started a trial and is NOT a customer" (re-checked at send time).
FUNNEL_STEPS = [
    {"step": 1, "template_key": "demo_1", "name": "CRMEvent · Funnel Demo · Email 1",
     "subject": "La tua demo di CRMEvent è pronta", "delay_days": 0, "require_not_engaged": False},
    {"step": 2, "template_key": "demo_2", "name": "CRMEvent · Funnel Demo · Email 2",
     "subject": "Tutto il tuo evento, in un unico posto", "delay_days": 1, "require_not_engaged": True},
    {"step": 3, "template_key": "demo_3", "name": "CRMEvent · Funnel Demo · Email 3",
     "subject": "Quante informazioni servono per organizzare un evento?", "delay_days": 3, "require_not_engaged": True},
    {"step": 4, "template_key": "demo_4", "name": "CRMEvent · Funnel Demo · Email 4",
     "subject": "Ora porta il tuo evento su CRMEvent", "delay_days": 6, "require_not_engaged": True},
]

SENDER = {"name": "CRMEvent", "email": "hello@crmevent.it"}
CONTACT_ATTRIBUTES = ["NOME", "COGNOME", "ORGANIZZAZIONE", "TIPOLOGIA_EVENTI", "SOURCE", "FUNNEL_STATUS"]
LIST_NAME = "CRMEvent · Lead"
FOLDER_NAME = "CRMEvent"


def _key() -> str:
    return os.environ.get("BREVO_API_KEY", "").strip()


def is_configured() -> bool:
    return bool(_key())


async def _request(method: str, path: str, *, json=None, params=None):
    """Return (status_code, data, error). status_code is None on transport errors."""
    key = _key()
    if not key:
        return None, None, "BREVO_API_KEY non configurata"
    headers = {"api-key": key, "accept": "application/json"}
    if json is not None:
        headers["content-type"] = "application/json"
    try:
        async with httpx.AsyncClient(base_url=BREVO_BASE, timeout=httpx.Timeout(20.0, connect=5.0),
                                     follow_redirects=False) as client:
            resp = await client.request(method, path, headers=headers, json=json, params=params)
    except httpx.TimeoutException:
        return None, None, "Timeout nella richiesta a Brevo"
    except httpx.HTTPError:
        return None, None, "Impossibile raggiungere Brevo"
    data = None
    if resp.content:
        try:
            data = resp.json()
        except Exception:
            data = None
    err = None
    if resp.status_code >= 400:
        err = (data or {}).get("message") or (data or {}).get("code") if isinstance(data, dict) else None
        err = err or f"HTTP {resp.status_code}"
    return resp.status_code, data, err


# ---------------- contacts ----------------
async def ensure_attributes():
    """Create the CRMEvent contact attributes on Brevo if missing (idempotent)."""
    for name in CONTACT_ATTRIBUTES:
        # category 'normal', type 'text'. Existing attribute returns 400; ignore.
        await _request("POST", f"/v3/contactAttributes/normal/{name}", json={"type": "text"})


async def upsert_contact(*, email, nome=None, cognome=None, organizzazione=None,
                         tipologia_eventi=None, source=None, funnel_status=None, list_ids=None):
    """Create or update a Brevo contact by email (no duplicates). Optionally add to lists."""
    attrs = {k: v for k, v in {
        "NOME": nome, "COGNOME": cognome, "ORGANIZZAZIONE": organizzazione,
        "TIPOLOGIA_EVENTI": tipologia_eventi, "SOURCE": source, "FUNNEL_STATUS": funnel_status,
    }.items() if v}
    body = {"email": email, "updateEnabled": True, "attributes": attrs}
    if list_ids:
        body["listIds"] = [int(x) for x in list_ids]
    sc, data, err = await _request("POST", "/v3/contacts", json=body)
    return {"ok": sc in (200, 201, 204), "status": sc, "error": err}


# ---------------- lists ----------------
async def _ensure_folder():
    sc, data, err = await _request("GET", "/v3/contacts/folders", params={"limit": 50, "offset": 0})
    if sc == 200 and isinstance(data, dict):
        folders = data.get("folders") or []
        for f in folders:
            if (f.get("name") or "") == FOLDER_NAME:
                return f.get("id")
        if folders:
            return folders[0].get("id")
    sc2, d2, e2 = await _request("POST", "/v3/contacts/folders", json={"name": FOLDER_NAME})
    return (d2 or {}).get("id") if isinstance(d2, dict) else None


async def _find_list_by_name(name):
    offset = 0
    while True:
        sc, data, err = await _request("GET", "/v3/contacts/lists", params={"limit": 50, "offset": offset})
        if sc != 200 or not isinstance(data, dict):
            return None
        lists = data.get("lists") or []
        for lst in lists:
            if (lst.get("name") or "") == name:
                return lst.get("id")
        count = data.get("count", 0)
        offset += len(lists)
        if not lists or offset >= count:
            return None


async def ensure_list():
    """Find or create the 'CRMEvent · Lead' list. Returns {ok, id, name, created, error}."""
    lid = await _find_list_by_name(LIST_NAME)
    if lid:
        return {"ok": True, "id": lid, "name": LIST_NAME, "created": False, "error": None}
    folder_id = await _ensure_folder()
    if not folder_id:
        return {"ok": False, "id": None, "name": LIST_NAME, "created": False,
                "error": "Impossibile creare/trovare la cartella su Brevo"}
    sc, data, err = await _request("POST", "/v3/contacts/lists", json={"name": LIST_NAME, "folderId": folder_id})
    nid = (data or {}).get("id") if isinstance(data, dict) else None
    return {"ok": sc in (200, 201) and bool(nid), "id": nid, "name": LIST_NAME, "created": True, "error": err}


async def blocklist_contact(email):
    """Blocklist a contact for marketing (unsubscribe)."""
    from urllib.parse import quote
    sc, data, err = await _request("PUT", f"/v3/contacts/{quote(str(email), safe='')}",
                                   json={"emailBlacklisted": True})
    return {"ok": sc in (200, 204), "status": sc, "error": err}


# ---------------- templates ----------------
def _shell(*, preview_text: str, body_html: str, unsub: bool = True) -> str:
    """Responsive branded CRMEvent shell. Placeholders use Brevo params: {{params.X}}."""
    footer = (
        f'<tr><td style="padding:20px 32px 28px;border-top:1px solid #edf2f7">'
        f'<p style="color:{FAINT};font-size:12px;line-height:1.6;margin:0">'
        f'CRMEvent · La piattaforma per organizzare i tuoi eventi.<br>'
    )
    if unsub:
        footer += (
            f'Non vuoi più ricevere queste email? '
            f'<a href="{{{{params.UNSUB_URL}}}}" style="color:{TIFFANY_DARK}">Disiscriviti qui</a>.'
        )
    footer += '</p></td></tr>'
    return (
        f'<!doctype html><html lang="it"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="color-scheme" content="light"></head>'
        f'<body style="margin:0;background:#f1f5f9;">'
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0">{escape(preview_text)}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:24px 12px">'
        f'<tr><td align="center">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="max-width:560px;background:#ffffff;border-radius:16px;overflow:hidden;'
        f'border:1px solid #e2e8f0;font-family:Arial,Helvetica,sans-serif">'
        f'<tr><td style="padding:28px 32px 8px">'
        f'<img src="{LOGO_URL}" alt="CRMEvent" width="150" style="display:block;height:auto;border:0" />'
        f'</td></tr>'
        f'<tr><td style="height:4px;background:{TIFFANY}"></td></tr>'
        f'<tr><td style="padding:24px 32px 8px">{body_html}</td></tr>'
        f'{footer}'
        f'</table></td></tr></table></body></html>'
    )


def _p(text: str) -> str:
    return f'<p style="color:{MUTED};font-size:15px;line-height:1.7;margin:0 0 16px">{text}</p>'


def _cta(label: str, url_param: str, primary: bool = True) -> str:
    if primary:
        return (
            f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 20px">'
            f'<tr><td style="border-radius:10px;background:{TIFFANY}">'
            f'<a href="{{{{params.{url_param}}}}}" style="display:inline-block;padding:14px 30px;'
            f'color:{INK};font-size:15px;font-weight:700;text-decoration:none;border-radius:10px">{label}</a>'
            f'</td></tr></table>'
        )
    return (
        f'<p style="margin:0 0 20px"><a href="{{{{params.{url_param}}}}}" '
        f'style="color:{TIFFANY_DARK};font-size:14px;font-weight:600;text-decoration:underline">{label}</a></p>'
    )


def _greeting() -> str:
    return f'<p style="color:{INK};font-size:16px;font-weight:600;margin:0 0 14px">Ciao {{{{params.NOME}}}},</p>'


def _closing() -> str:
    return f'<p style="color:{MUTED};font-size:15px;line-height:1.7;margin:18px 0 0">A presto,<br>Il team CRMEvent</p>'


def build_html(template_key: str) -> str:
    if template_key == "demo_1":
        body = (
            _greeting()
            + _p("grazie per aver richiesto la demo di CRMEvent.")
            + _p("Abbiamo preparato una breve esperienza interattiva per mostrarti come puoi gestire "
                 "eventi, persone, staff, volontari, sponsor, attività e informazioni operative da "
                 "un'unica piattaforma.")
            + _p("Guarda la demo e scopri CRMEvent in pochi minuti.")
            + _cta("Guarda la demo", "DEMO_URL")
            + _closing()
        )
        return _shell(preview_text="La tua demo interattiva di CRMEvent è pronta.", body_html=body)
    if template_key == "demo_2":
        body = (
            _greeting()
            + _p("organizzare un evento significa gestire molte informazioni contemporaneamente.")
            + _p("Persone, staff, volontari, sponsor, aziende, attività, turni, ospitalità, pasti, "
                 "briefing e scadenze.")
            + _p("CRMEvent nasce per raccogliere tutto questo in un'unica piattaforma. "
                 "Meno informazioni sparse. Più controllo sull'organizzazione.")
            + _p("Se non hai ancora esplorato la demo, puoi farlo ora.")
            + _cta("Guarda la demo", "DEMO_URL")
            + _cta("Prova CRMEvent gratis", "TRIAL_URL", primary=False)
            + _closing()
        )
        return _shell(preview_text="Tutto il tuo evento, in un unico posto.", body_html=body)
    if template_key == "demo_3":
        body = (
            _greeting()
            + _p("un file per lo staff.<br>Un altro per gli sponsor.<br>Messaggi per organizzare i "
                 "volontari.<br>Email per le strutture.<br>Chat per i turni.<br>Documenti diversi per "
                 "briefing e attività.")
            + _p("Quando le informazioni aumentano, tenerle tutte sotto controllo diventa complicato.")
            + _p("CRMEvent nasce per semplificare questo lavoro. Un'unica piattaforma dove organizzare "
                 "le informazioni del tuo evento e ritrovarle quando servono.")
            + _cta("Scopri CRMEvent", "DEMO_URL")
            + _p(f'Vuoi provarlo direttamente con il tuo evento? '
                 f'<a href="{{{{params.TRIAL_URL}}}}" style="color:{TIFFANY_DARK};font-weight:600">Inizia gratuitamente.</a>')
            + _closing()
        )
        return _shell(preview_text="Quante informazioni servono per organizzare un evento?", body_html=body)
    if template_key == "demo_4":
        body = (
            _greeting()
            + _p("hai visto cosa può fare CRMEvent.")
            + _p("Ora puoi provarlo direttamente con il tuo evento. Crea il tuo spazio di lavoro, "
                 "inserisci il primo evento e scopri come gestire tutte le informazioni operative da "
                 "un'unica piattaforma.")
            + _p("Puoi iniziare con la prova gratuita.")
            + _cta("Prova CRMEvent gratis", "TRIAL_URL")
            + _closing()
        )
        return _shell(preview_text="Ora porta il tuo evento su CRMEvent.", body_html=body)
    raise ValueError(f"template sconosciuto: {template_key}")


async def _find_template_id_by_name(name: str):
    offset = 0
    while True:
        sc, data, err = await _request("GET", "/v3/smtp/templates",
                                       params={"limit": 200, "offset": offset, "sort": "asc"})
        if sc != 200 or not isinstance(data, dict):
            return None
        items = data.get("templates", []) or []
        for it in items:
            if (it.get("name") or "") == name:
                return it.get("id")
        count = data.get("count", 0)
        offset += len(items)
        if not items or offset >= count:
            return None


async def create_or_update_template(step: dict, existing_id=None, force=False):
    """Link an existing Brevo template (by name) or create it if missing.
    IMPORTANT: existing templates are NOT overwritten unless force=True — this protects
    manual graphic edits made directly in Brevo. Returns {ok, id, status, error, created, skipped}."""
    name = step["name"]
    subject = step["subject"]
    tid = existing_id or await _find_template_id_by_name(name)
    if tid and not force:
        # Non-destructive: just confirm/link the existing template, keep its Brevo HTML intact.
        return {"ok": True, "id": tid, "status": 200, "error": None, "created": False, "skipped": True}
    html = build_html(step["template_key"])
    payload = {"templateName": name, "subject": subject, "sender": SENDER,
               "htmlContent": html, "tag": BREVO_TAG, "isActive": True}
    if tid:
        sc, data, err = await _request("PUT", f"/v3/smtp/templates/{tid}", json=payload)
        return {"ok": sc in (200, 204), "id": tid, "status": sc, "error": err, "created": False, "skipped": False}
    sc, data, err = await _request("POST", "/v3/smtp/templates", json=payload)
    new_id = (data or {}).get("id") if isinstance(data, dict) else None
    return {"ok": sc in (200, 201) and bool(new_id), "id": new_id, "status": sc, "error": err, "created": True}


async def send_template(*, template_id: int, to_email: str, to_name: str = None, params: dict):
    """Send a transactional email via a Brevo template. Returns {ok, status, messageId, error}."""
    to = {"email": to_email}
    if to_name:
        to["name"] = to_name
    body = {"to": [to], "templateId": int(template_id), "params": params, "sender": SENDER}
    sc, data, err = await _request("POST", "/v3/smtp/email", json=body)
    mid = (data or {}).get("messageId") if isinstance(data, dict) else None
    return {"ok": sc == 201, "status": sc, "messageId": mid, "error": err}


def normalize_event(raw_event: str) -> str:
    e = (raw_event or "").strip().lower().replace("-", "_")
    mapping = {
        "delivered": "delivered", "request": "request",
        "opened": "opened", "unique_opened": "opened", "open": "opened",
        "click": "clicked", "clicks": "clicked", "clicked": "clicked",
        "hard_bounce": "hard_bounce", "hardbounce": "hard_bounce",
        "soft_bounce": "soft_bounce", "softbounce": "soft_bounce",
        "unsubscribe": "unsubscribed", "unsubscribed": "unsubscribed",
        "spam": "spam", "complaint": "spam", "spam_complaint": "spam",
        "blocked": "blocked", "invalid_email": "invalid_email", "error": "error", "deferred": "deferred",
    }
    return mapping.get(e, e)


WEBHOOK_EVENTS = ["delivered", "opened", "uniqueOpened", "click", "hardBounce",
                  "softBounce", "blocked", "spam", "unsubscribed", "invalid", "deferred", "error"]


# ===================== Utenti registrati CRMEvent (lista separata dai Lead) =====================
REGISTERED_LIST_NAME = "CRMEvent · Utenti registrati"
# Attributi sincronizzati per gli utenti registrati (utili ai funnel di onboarding). Nessun dato sensibile.
USER_ATTRIBUTES = ["NOME", "COGNOME", "ORGANIZZAZIONE", "DATA_REGISTRAZIONE",
                   "CREDITI_DISPONIBILI", "EVENTI_CREATI", "EVENTI_ATTIVATI", "ULTIMO_ACCESSO",
                   "CELLULARE", "RUOLO_UTENTE"]


async def ensure_user_attributes():
    """Crea gli attributi contatto per gli utenti registrati su Brevo (idempotente)."""
    for name in ["NOME", "COGNOME", "ORGANIZZAZIONE", "DATA_REGISTRAZIONE", "ULTIMO_ACCESSO", "CELLULARE", "RUOLO_UTENTE"]:
        await _request("POST", f"/v3/contactAttributes/normal/{name}", json={"type": "text"})
    for name in ["CREDITI_DISPONIBILI", "EVENTI_CREATI", "EVENTI_ATTIVATI"]:
        await _request("POST", f"/v3/contactAttributes/normal/{name}", json={"type": "float"})


async def ensure_registered_list():
    """Trova o crea la lista 'CRMEvent · Utenti registrati'. Ritorna {ok, id, name, created, error}."""
    lid = await _find_list_by_name(REGISTERED_LIST_NAME)
    if lid:
        return {"ok": True, "id": lid, "name": REGISTERED_LIST_NAME, "created": False, "error": None}
    folder_id = await _ensure_folder()
    if not folder_id:
        return {"ok": False, "id": None, "name": REGISTERED_LIST_NAME, "created": False,
                "error": "Impossibile creare/trovare la cartella su Brevo"}
    sc, data, err = await _request("POST", "/v3/contacts/lists", json={"name": REGISTERED_LIST_NAME, "folderId": folder_id})
    nid = (data or {}).get("id") if isinstance(data, dict) else None
    return {"ok": sc in (200, 201) and bool(nid), "id": nid, "name": REGISTERED_LIST_NAME, "created": True, "error": err}


async def list_contact_count(list_id):
    """Numero di contatti nella lista (totalSubscribers)."""
    sc, data, err = await _request("GET", f"/v3/contacts/lists/{int(list_id)}")
    if sc == 200 and isinstance(data, dict):
        return data.get("totalSubscribers", data.get("uniqueSubscribers"))
    return None


async def upsert_registered_contact(*, email, attributes: dict, list_ids=None):
    """Crea/aggiorna (updateEnabled) un contatto per email senza duplicati e lo aggiunge alla lista
    Utenti registrati. Aggiorna SOLO gli attributi forniti: SOURCE/FUNNEL_STATUS/origine restano intatti.
    Non rimuove il contatto da altre liste (es. Lead)."""
    attrs = {k: v for k, v in (attributes or {}).items() if v is not None}
    body = {"email": email, "updateEnabled": True, "attributes": attrs}
    if list_ids:
        body["listIds"] = [int(x) for x in list_ids]
    sc, data, err = await _request("POST", "/v3/contacts", json=body)
    return {"ok": sc in (200, 201, 204), "status": sc, "error": err}


async def register_webhook(callback_url: str):
    """Create or update the transactional Brevo webhook for the given callback URL (idempotent).
    The callback URL (which contains the secret token) is never returned to the caller."""
    sc, data, err = await _request("GET", "/v3/webhooks", params={"type": "transactional"})
    existing_id = None
    if sc == 200 and isinstance(data, dict):
        for w in (data.get("webhooks") or []):
            if w.get("url") == callback_url:
                existing_id = w.get("id")
                break
    body = {"url": callback_url, "events": WEBHOOK_EVENTS}
    if existing_id:
        sc2, d2, e2 = await _request("PUT", f"/v3/webhooks/{existing_id}", json=body)
        return {"ok": sc2 in (200, 204), "id": existing_id, "status": sc2, "error": e2, "created": False}
    body2 = {"type": "transactional", "description": "CRMEvent Funnel Demo", **body}
    sc2, d2, e2 = await _request("POST", "/v3/webhooks", json=body2)
    nid = (d2 or {}).get("id") if isinstance(d2, dict) else None
    return {"ok": sc2 in (200, 201) and bool(nid), "id": nid, "status": sc2, "error": e2, "created": True}

