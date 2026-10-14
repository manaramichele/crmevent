"""Marketplace · Comunicati stampa: AI, rubrica stampa per org, lista Brevo per org, invio transazionale per destinatario,
disiscrizione per organizzazione, automazione post-evento con approvazione obbligatoria, statistiche Brevo."""
import asyncio
import csv
import io
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import brevo_funnel

logger = logging.getLogger("press")
SERVICE_KEY = "comunicati-stampa"
LLM_MODEL = ("openai", "gpt-5.6-terra")
ROME = ZoneInfo("Europe/Rome")
STATUSES = ("bozza", "da_approvare", "programmato", "in_invio", "inviato", "errore", "annullato")
TIPI = {"presentazione": "Presentazione evento", "pre_evento": "Pre-evento", "post_evento": "Post-evento"}
MEDIA = ["Quotidiano", "Quotidiano online", "Rivista", "Radio", "Televisione", "Blog", "Agenzia stampa", "Altro"]
BASI = {"legittimo_interesse": "Legittimo interesse (rapporti con i media)", "consenso": "Consenso espresso",
        "richiesta": "Richiesta del giornalista", "altro": "Altra base giuridica documentata"}
EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SYSTEM = (
    "Sei un addetto stampa professionista italiano. Scrivi comunicati stampa in stile giornalistico (piramide rovesciata, "
    "terza persona, frasi chiare, niente toni pubblicitari o superlativi). REGOLE ASSOLUTE: usa SOLO i dati forniti; "
    "non inventare numeri, risultati, vincitori, nomi, citazioni o dichiarazioni; se un dato importante per la tipologia "
    "manca, non scriverlo e indicalo in 'dati_mancanti'. Inserisci citazioni solo se fornite testualmente. Non includere "
    "dati personali di staff, volontari o partecipanti. Rispondi SOLO con JSON: "
    '{"titolo": str, "sottotitolo": str, "testo": str (paragrafi separati da una riga vuota), "dati_mancanti": [str]}'
)
FOCUS = {
    "presentazione": "Annuncio della manifestazione, date e luogo, organizzatore, programma, iscrizioni, sponsor principali.",
    "pre_evento": "Edizione imminente, programma aggiornato, numeri iscrizioni se forniti, logistica, dichiarazioni se fornite.",
    "post_evento": "Resoconto, partecipanti effettivi, risultati sportivi e vincitori se forniti, dichiarazioni se fornite, "
                   "sponsor e partner, ringraziamenti, prossima edizione se indicata.",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(e: Optional[str]) -> str:
    return (e or "").strip().lower()


class GenerateIn(BaseModel):
    event_id: str
    tipo: str
    extra: Optional[str] = ""
    tono: Optional[str] = "istituzionale"


class ReleaseIn(BaseModel):
    titolo: Optional[str] = ""
    sottotitolo: Optional[str] = ""
    testo: Optional[str] = ""
    citazioni: Optional[List[dict]] = []
    foto: Optional[List[dict]] = []
    contatto_stampa: Optional[str] = ""
    oggetto_email: Optional[str] = ""


class ContactIn(BaseModel):
    nome: Optional[str] = ""
    cognome: Optional[str] = ""
    email: str
    testata: Optional[str] = ""
    tipologia_media: Optional[str] = "Altro"
    citta: Optional[str] = ""
    provincia: Optional[str] = ""
    regione: Optional[str] = ""
    note: Optional[str] = ""
    stato: Optional[str] = "attivo"
    provenienza: Optional[str] = "manuale"
    base_giuridica: Optional[str] = "legittimo_interesse"


class SettingsIn(BaseModel):
    sender_name: Optional[str] = ""
    sender_email: Optional[str] = ""
    reply_to: Optional[str] = ""
    referente: Optional[str] = ""
    telefono: Optional[str] = ""
    org_info: Optional[str] = ""


class AutomationIn(BaseModel):
    enabled: bool = False
    delay_days: int = 1
    send_time: str = "10:00"
    media: Optional[List[str]] = []
    regioni: Optional[List[str]] = []


class SendIn(BaseModel):
    mode: str = "now"
    send_at: Optional[str] = None
    oggetto_email: Optional[str] = None
    media: Optional[List[str]] = []
    regioni: Optional[List[str]] = []
    province: Optional[List[str]] = []


class TestIn(BaseModel):
    email: str


class ActivateIn(BaseModel):
    active: bool


def build_router(db, require_org_member, require_superadmin, record_audit, app_url: str, cron_secret: str):
    r = APIRouter(prefix="/api")

    # ---------------- accesso ----------------
    async def _active(org_id: str) -> bool:
        return bool(await db.org_services.find_one({"org_id": org_id, "service": SERVICE_KEY, "active": True}, {"_id": 1}))

    async def member(user: dict = Depends(require_org_member)) -> dict:
        if not await _active(user["org_id"]):
            raise HTTPException(status_code=403, detail="Servizio Comunicati stampa non attivo per questa organizzazione")
        return user

    async def editor(user: dict = Depends(member)) -> dict:
        if user.get("org_role") not in ("admin_org", "superadmin"):
            raise HTTPException(status_code=403, detail="Operazione riservata agli amministratori dell'organizzazione")
        return user

    async def _release(rid: str, org_id: str) -> dict:
        d = await db.press_releases.find_one({"id": rid, "org_id": org_id}, {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="Comunicato non trovato")
        return d

    async def _event(eid: str, org_id: str) -> dict:
        e = await db.events.find_one({"id": eid, "org_id": org_id}, {"_id": 0})
        if not e:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        return e

    # ---------------- Brevo: lista per organizzazione ----------------
    list_locks: dict = {}

    async def _ensure_list(org_id: str) -> Optional[dict]:
        lock = list_locks.setdefault(org_id, asyncio.Lock())
        async with lock:
            return await _ensure_list_locked(org_id)

    async def _ensure_list_locked(org_id: str) -> Optional[dict]:
        rec = await db.press_brevo_lists.find_one({"org_id": org_id}, {"_id": 0})
        if rec and rec.get("list_id"):
            return rec
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "nome": 1}) or {}
        slug = re.sub(r"[^A-Za-z0-9]+", "_", org.get("nome") or "Org").strip("_")[:40]
        name = f"CRMEvent_STAMPA_{slug}_{org_id[-8:]}"
        base = {"org_id": org_id, "list_name": name, "created_at": (rec or {}).get("created_at") or _now()}
        if not brevo_funnel.is_configured():
            await db.press_brevo_lists.update_one({"org_id": org_id}, {"$set": {**base, "sync_status": "brevo_non_configurato"}}, upsert=True)
            return None
        try:
            sc, data, err = await brevo_funnel._request("GET", "/v3/contacts/folders", params={"limit": 50, "offset": 0})
            folder = next((f["id"] for f in (data or {}).get("folders", []) if f.get("name") == "CRMEvent Stampa"), None)
            if not folder:
                sc, data, err = await brevo_funnel._request("POST", "/v3/contacts/folders", json={"name": "CRMEvent Stampa"})
                folder = (data or {}).get("id")
            existing = None
            off = 0
            while existing is None and off < 2000:
                sc, data, err = await brevo_funnel._request("GET", f"/v3/contacts/folders/{folder}/lists", params={"limit": 50, "offset": off})
                lists = (data or {}).get("lists", [])
                existing = next((l["id"] for l in lists if l.get("name") == name), None)
                if len(lists) < 50:
                    break
                off += 50
            list_id = existing
            if not list_id:
                sc, data, err = await brevo_funnel._request("POST", "/v3/contacts/lists", json={"name": name, "folderId": folder})
                if sc not in (200, 201):
                    raise RuntimeError(err or f"HTTP {sc}")
                list_id = data["id"]
            await db.press_brevo_lists.update_one({"org_id": org_id}, {"$set": {**base, "list_id": list_id, "folder_id": folder,
                                                                              "sync_status": "ok", "last_sync": _now(), "error": None}}, upsert=True)
            return await db.press_brevo_lists.find_one({"org_id": org_id}, {"_id": 0})
        except Exception as e:  # noqa: BLE001
            await db.press_brevo_lists.update_one({"org_id": org_id}, {"$set": {**base, "sync_status": "errore", "error": str(e)[:200]}}, upsert=True)
            return None

    async def _sync_contact(c: dict, remove: bool = False) -> None:
        lst = await _ensure_list(c["org_id"])
        if not lst:
            await db.press_contacts.update_one({"id": c["id"]}, {"$set": {"brevo_status": "in_attesa"}})
            return
        try:
            if remove or c.get("stato") != "attivo":
                sc, _, err = await brevo_funnel._request("POST", f"/v3/contacts/lists/{lst['list_id']}/contacts/remove", json={"emails": [c["email"]]})
                ok = sc in (200, 201, 204) or sc == 400  # 400: contatto non presente nella lista
            else:
                attrs = {k: v for k, v in {"NOME": c.get("nome"), "COGNOME": c.get("cognome")}.items() if v}
                sc, _, err = await brevo_funnel._request("POST", "/v3/contacts", json={"email": c["email"], "attributes": attrs,
                                                                                      "listIds": [lst["list_id"]], "updateEnabled": True})
                ok = sc in (200, 201, 204)
            if not remove:
                await db.press_contacts.update_one({"id": c["id"]}, {"$set": {"brevo_status": "sincronizzato" if ok else ("rate_limit" if sc == 429 else "errore"),
                                                                             "brevo_error": None if ok else (err or f"HTTP {sc}")[:200], "brevo_synced_at": _now()}})
            await db.press_brevo_lists.update_one({"org_id": c["org_id"]}, {"$set": {"last_sync": _now(), "sync_status": "ok" if ok else "errore"}})
        except Exception as e:  # noqa: BLE001
            logger.warning("press contact sync failed: %s", e)
            if not remove:
                await db.press_contacts.update_one({"id": c["id"]}, {"$set": {"brevo_status": "errore", "brevo_error": str(e)[:200]}})

    # ---------------- dati evento + AI ----------------
    async def _event_data(e: dict) -> dict:
        deals = await db.deals.find({"org_id": e["org_id"], "evento_id": e["id"], "fase": "confermato"}, {"_id": 0, "azienda_id": 1, "tipo": 1}).to_list(200)
        names = {}
        for d in deals:
            c = await db.companies.find_one({"id": d.get("azienda_id"), "org_id": e["org_id"]}, {"_id": 0, "nome": 1})
            if c:
                names.setdefault(d.get("tipo") or "sponsor", []).append(c["nome"])
        org = await db.organizations.find_one({"id": e["org_id"]}, {"_id": 0, "nome": 1}) or {}
        data = {"nome_evento": e.get("nome"), "edizione": e.get("edizione"), "tipologia": e.get("tipologia"),
                "data_inizio": e.get("data_inizio"), "data_fine": e.get("data_fine"), "ora_inizio": e.get("ora_inizio"),
                "localita": e.get("localita"), "indirizzo": e.get("indirizzo"), "citta": e.get("citta"), "provincia": e.get("provincia"),
                "regione": e.get("regione"), "organizzazione": org.get("nome"), "organizzatore": e.get("organizzatore"),
                "descrizione": e.get("descrizione"), "programma_giornate": e.get("giorni_descrizioni") or None,
                "sito_web": e.get("sito_web"), "partecipanti_previsti": e.get("partecipanti_previsti"),
                "sponsor_e_partner": names or None}
        return {k: v for k, v in data.items() if v not in (None, "", [], {})}

    def _missing(tipo: str, data: dict) -> list:
        need = {"nome_evento": "Nome evento", "data_inizio": "Data evento", "citta": "Luogo / città", "descrizione": "Descrizione"}
        out = [lbl for k, lbl in need.items() if k not in data and not (k == "citta" and data.get("localita"))]
        if tipo == "post_evento":
            out += ["Partecipanti effettivi", "Risultati / vincitori", "Dichiarazioni degli organizzatori"]
        return out

    async def _ai(tipo: str, data: dict, extra: str, tono: str) -> dict:
        key = os.environ.get("EMERGENT_LLM_KEY")
        if not key:
            raise HTTPException(status_code=503, detail="Generazione AI non configurata")
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=key, session_id=uuid.uuid4().hex, system_message=SYSTEM).with_model(*LLM_MODEL)
        msg = (f"Tipologia: {TIPI[tipo]}. Contenuti attesi: {FOCUS[tipo]}\nTono: {tono or 'istituzionale'}\n"
               f"DATI EVENTO (JSON, unica fonte):\n{json.dumps(data, ensure_ascii=False)}\n"
               f"INFORMAZIONI AGGIUNTIVE DELL'ORGANIZZATORE (fonte verificata):\n{extra or '(nessuna)'}")
        raw = await chat.send_message(UserMessage(text=msg))
        m = re.search(r"\{.*\}", raw or "", re.S)
        try:
            res = json.loads(m.group(0)) if m else {}
        except ValueError:
            res = {}
        if not res.get("testo"):
            raise HTTPException(status_code=502, detail="La generazione AI non ha prodotto un testo valido: riprova")
        return {"titolo": str(res.get("titolo") or "")[:300], "sottotitolo": str(res.get("sottotitolo") or "")[:500],
                "testo": str(res["testo"]), "dati_mancanti": [str(x) for x in (res.get("dati_mancanti") or [])][:20]}

    async def _version(rel: dict, user: dict, origin: str) -> None:
        await db.press_versions.insert_one({"id": uuid.uuid4().hex, "release_id": rel["id"], "org_id": rel["org_id"], "origin": origin,
                                            "titolo": rel.get("titolo"), "sottotitolo": rel.get("sottotitolo"), "testo": rel.get("testo"),
                                            "by": {"user_id": user.get("user_id"), "name": user.get("name")}, "created_at": _now()})

    # ---------------- email ----------------
    def _esc(s) -> str:
        return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    def _html(rel: dict, st: dict, event: dict, unsub_url: str) -> str:
        paras = "".join(f'<p style="margin:0 0 14px;line-height:1.6">{_esc(p).replace(chr(10), "<br>")}</p>' for p in (rel.get("testo") or "").split("\n\n") if p.strip())
        quotes = "".join(f'<blockquote style="margin:16px 0;padding:8px 14px;border-left:3px solid #0ABAB5;color:#334155">«{_esc(q.get("testo"))}»<br><span style="font-size:13px;color:#64748b">— {_esc(q.get("autore"))}</span></blockquote>' for q in (rel.get("citazioni") or []) if q.get("testo"))
        foto = "".join(f'<img src="{_esc(f.get("url"))}" alt="{_esc(f.get("didascalia"))}" style="width:100%;max-width:560px;border-radius:8px;display:block;margin:12px 0 4px"><div style="font-size:12px;color:#64748b;margin-bottom:12px">{_esc(f.get("didascalia"))}</div>' for f in (rel.get("foto") or []) if str(f.get("url", "")).startswith("https://"))
        logo = event.get("logo_url") if str(event.get("logo_url") or "").startswith("https://") else None
        site = event.get("sito_web")
        contact = rel.get("contatto_stampa") or " · ".join(x for x in (st.get("referente"), st.get("sender_email"), st.get("telefono")) if x)
        return (
            '<!doctype html><html><body style="margin:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#0f172a">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">'
            '<table role="presentation" width="100%" style="max-width:600px;background:#fff;border-radius:12px;overflow:hidden" cellpadding="0" cellspacing="0">'
            '<tr><td style="height:4px;background:#0ABAB5"></td></tr><tr><td style="padding:28px 28px 8px">'
            + (f'<img src="{_esc(logo)}" alt="" style="max-height:56px;margin-bottom:16px">' if logo else "")
            + '<div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#088F8A;font-weight:bold">Comunicato stampa</div>'
            f'<h1 style="font-size:24px;line-height:1.25;margin:8px 0">{_esc(rel.get("titolo"))}</h1>'
            + (f'<p style="font-size:16px;color:#475569;margin:0 0 18px">{_esc(rel.get("sottotitolo"))}</p>' if rel.get("sottotitolo") else "")
            + f'</td></tr><tr><td style="padding:0 28px 8px;font-size:15px">{paras}{quotes}{foto}</td></tr>'
            '<tr><td style="padding:16px 28px;background:#f8fafc;font-size:13px;color:#475569">'
            + (f'<div style="margin-bottom:6px">{_esc(st.get("org_info"))}</div>' if st.get("org_info") else "")
            + (f'<div><b>Contatto stampa:</b> {_esc(contact)}</div>' if contact else "")
            + (f'<div><a href="{_esc(site)}" style="color:#088F8A">{_esc(site)}</a></div>' if site else "")
            + f'</td></tr><tr><td style="padding:14px 28px;font-size:11px;color:#94a3b8">Ricevi questa comunicazione in quanto contatto media di {_esc(st.get("sender_name"))}. '
            f'<a href="{_esc(unsub_url)}" style="color:#64748b">Non desidero ricevere altri comunicati da questa organizzazione</a>.</td></tr>'
            '</table></td></tr></table></body></html>')

    async def _send_one(to: str, subject: str, html: str, st: dict, tag: str) -> tuple:
        payload = {"sender": {"name": st["sender_name"], "email": st["sender_email"]}, "to": [{"email": to}],
                   "subject": subject, "htmlContent": html, "tags": [tag]}
        if st.get("reply_to"):
            payload["replyTo"] = {"email": st["reply_to"]}
        sc, data, err = await brevo_funnel._request("POST", "/v3/smtp/email", json=payload)
        return sc, (data or {}).get("messageId"), err

    def _recipients_q(org_id: str, f: dict) -> dict:
        q = {"org_id": org_id, "stato": "attivo", "base_giuridica": {"$in": list(BASI)}}
        if f.get("media"):
            q["tipologia_media"] = {"$in": f["media"]}
        if f.get("regioni"):
            q["regione"] = {"$in": f["regioni"]}
        if f.get("province"):
            q["provincia"] = {"$in": f["province"]}
        return q

    async def _settings(org_id: str) -> dict:
        return await db.press_settings.find_one({"org_id": org_id}, {"_id": 0}) or {"org_id": org_id}

    def _sender_ok(st: dict) -> Optional[str]:
        if not (st.get("sender_name") and st.get("sender_email")):
            return "Configura nome ed email del mittente nelle Impostazioni"
        if not st.get("sender_verified"):
            return "Il mittente non risulta verificato su Brevo: completa la verifica nelle Impostazioni"
        return None

    async def _deliver(rid: str) -> None:
        """Invio idempotente: un record press_sends unico per (release, email); riprende dopo riavvii."""
        rel = await db.press_releases.find_one({"id": rid}, {"_id": 0})
        if not rel or rel["status"] != "in_invio":
            return
        st = await _settings(rel["org_id"])
        event = await db.events.find_one({"id": rel.get("event_id"), "org_id": rel["org_id"]}, {"_id": 0}) or {}
        subject = rel.get("oggetto_email") or rel.get("titolo") or "Comunicato stampa"
        contacts = await db.press_contacts.find(_recipients_q(rel["org_id"], rel.get("filters") or {}), {"_id": 0}).to_list(10000)
        if not brevo_funnel.is_configured():
            await db.press_releases.update_one({"id": rid}, {"$set": {"status": "errore", "error": "Brevo non configurato"}})
            return
        for c in contacts:
            try:
                await db.press_sends.insert_one({"id": uuid.uuid4().hex, "release_id": rid, "org_id": rel["org_id"], "email": c["email"],
                                                 "contact_id": c["id"], "status": "in_corso", "created_at": _now()})
            except DuplicateKeyError:
                prev = await db.press_sends.find_one({"release_id": rid, "email": c["email"]}, {"_id": 0, "status": 1})
                if prev and prev["status"] in ("inviato", "in_corso"):
                    continue
            unsub = f"{app_url.rstrip('/')}/api/public/press/unsubscribe/{c['unsub_token']}"
            sc, mid, err = await _send_one(c["email"], subject, _html(rel, st, event, unsub), st, f"press-{rid}")
            stt = "inviato" if sc in (200, 201) else ("rate_limit" if sc == 429 else "errore")
            await db.press_sends.update_one({"release_id": rid, "email": c["email"]}, {"$set": {"status": stt, "message_id": mid, "error": None if stt == "inviato" else (err or f"HTTP {sc}")[:200], "sent_at": _now()}})
            if sc == 429:
                await db.press_releases.update_one({"id": rid}, {"$set": {"error": "Limite Brevo raggiunto: invio ripreso automaticamente"}})
                return
            await asyncio.sleep(0.15)
        agg = {s["_id"]: s["n"] for s in await db.press_sends.aggregate([{"$match": {"release_id": rid}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]).to_list(10)}
        ok = agg.get("inviato", 0)
        await db.press_releases.update_one({"id": rid, "status": "in_invio"}, {"$set": {
            "status": "inviato" if ok else "errore", "sent_at": _now(), "recipients_count": sum(agg.values()), "sent_count": ok,
            "error_count": agg.get("errore", 0), "error": None if ok else "Nessuna email inviata"}})

    async def _refresh_stats(rel: dict) -> dict:
        if not brevo_funnel.is_configured() or not rel.get("sent_at"):
            return rel.get("stats") or {}
        start = rel["sent_at"][:10]
        end = datetime.now(timezone.utc).date().isoformat()
        sc, data, err = await brevo_funnel._request("GET", "/v3/smtp/statistics/aggregatedReport", params={"tag": f"press-{rel['id']}", "startDate": start, "endDate": end})
        if sc == 200 and data:
            stats = {k: data.get(k, 0) for k in ("requests", "delivered", "hardBounces", "softBounces", "blocked", "invalid", "uniqueOpens", "uniqueClicks", "unsubscribed")}
            await db.press_releases.update_one({"id": rel["id"]}, {"$set": {"stats": stats, "stats_at": _now()}})
            return stats
        return rel.get("stats") or {}

    # ---------------- stato / dashboard ----------------
    @r.get("/press/status")
    async def status(user: dict = Depends(require_org_member)):
        return {"active": await _active(user["org_id"]), "can_edit": user.get("org_role") in ("admin_org", "superadmin"),
                "tipi": TIPI, "media": MEDIA, "basi": BASI, "statuses": STATUSES}

    @r.get("/press/dashboard")
    async def dashboard(user: dict = Depends(member)):
        org = user["org_id"]
        counts = {s: 0 for s in STATUSES}
        for c in await db.press_releases.aggregate([{"$match": {"org_id": org}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]).to_list(20):
            counts[c["_id"]] = c["n"]
        last = await db.press_releases.find_one({"org_id": org, "status": "inviato"}, {"_id": 0, "sent_at": 1}, sort=[("sent_at", -1)])
        rows = await db.press_releases.find({"org_id": org}, {"_id": 0, "testo": 0}).sort("updated_at", -1).to_list(500)
        names = {e["id"]: e["nome"] for e in await db.events.find({"org_id": org}, {"_id": 0, "id": 1, "nome": 1}).to_list(2000)}
        for x in rows:
            x["event_name"] = names.get(x.get("event_id"))
        return {"counts": counts, "total": sum(counts.values()), "contacts": await db.press_contacts.count_documents({"org_id": org}),
                "last_sent_at": (last or {}).get("sent_at"), "releases": rows,
                "list": await db.press_brevo_lists.find_one({"org_id": org}, {"_id": 0})}

    # ---------------- comunicati ----------------
    @r.get("/press/events")
    async def events(user: dict = Depends(member)):
        return await db.events.find({"org_id": user["org_id"]}, {"_id": 0, "id": 1, "nome": 1, "data_inizio": 1, "data_fine": 1}).sort("data_inizio", -1).to_list(1000)

    @r.get("/press/events/{eid}/data")
    async def event_data(eid: str, tipo: str = "presentazione", user: dict = Depends(member)):
        d = await _event_data(await _event(eid, user["org_id"]))
        return {"data": d, "missing": _missing(tipo, d)}

    @r.post("/press/generate")
    async def generate(body: GenerateIn, rid: Optional[str] = None, user: dict = Depends(editor)):
        if body.tipo not in TIPI:
            raise HTTPException(status_code=400, detail="Tipologia non valida")
        ev = await _event(body.event_id, user["org_id"])
        res = await _ai(body.tipo, await _event_data(ev), body.extra or "", body.tono or "istituzionale")
        now = _now()
        if rid:
            rel = await _release(rid, user["org_id"])
            if rel["status"] in ("in_invio", "inviato"):
                raise HTTPException(status_code=400, detail="Comunicato già inviato")
            upd = {**{k: res[k] for k in ("titolo", "sottotitolo", "testo", "dati_mancanti")}, "extra": body.extra, "tono": body.tono,
                   "updated_at": now, "approved_at": None, "approved_by": None,
                   "status": "da_approvare" if rel.get("automation") else "bozza"}
            await db.press_releases.update_one({"id": rid}, {"$set": upd})
            rel.update(upd)
        else:
            rel = {"id": uuid.uuid4().hex, "org_id": user["org_id"], "event_id": ev["id"], "tipo": body.tipo, **res, "extra": body.extra,
                   "tono": body.tono, "citazioni": [], "foto": [], "contatto_stampa": "", "oggetto_email": "", "status": "bozza",
                   "created_by": {"user_id": user["user_id"], "name": user.get("name")}, "created_at": now, "updated_at": now}
            await db.press_releases.insert_one(dict(rel))
        await _version(rel, user, "ai")
        return {k: v for k, v in rel.items() if k != "_id"}

    @r.get("/press/releases/{rid}")
    async def get_release(rid: str, user: dict = Depends(member)):
        rel = await _release(rid, user["org_id"])
        rel["versions"] = await db.press_versions.find({"release_id": rid, "org_id": user["org_id"]}, {"_id": 0, "testo": 0}).sort("created_at", -1).to_list(50)
        return rel

    @r.put("/press/releases/{rid}")
    async def save_release(rid: str, body: ReleaseIn, user: dict = Depends(editor)):
        rel = await _release(rid, user["org_id"])
        if rel["status"] in ("in_invio", "inviato"):
            raise HTTPException(status_code=400, detail="Comunicato già inviato: non modificabile")
        upd = {**body.model_dump(), "updated_at": _now(), "error": None}
        if rel["status"] in ("programmato", "errore") or rel.get("approved_at"):
            upd.update({"status": "da_approvare" if rel.get("automation") else "bozza", "approved_at": None, "approved_by": None})
        await db.press_releases.update_one({"id": rid}, {"$set": upd})
        rel.update(upd)
        await _version(rel, user, "modifica")
        return rel

    @r.delete("/press/releases/{rid}")
    async def delete_release(rid: str, user: dict = Depends(editor)):
        rel = await _release(rid, user["org_id"])
        if rel["status"] in ("in_invio", "inviato"):
            raise HTTPException(status_code=400, detail="Un comunicato inviato non può essere eliminato")
        await db.press_releases.update_one({"id": rid}, {"$set": {"status": "annullato", "updated_at": _now()}})
        return {"ok": True}

    @r.get("/press/releases/{rid}/preview", response_class=HTMLResponse)
    async def preview(rid: str, user: dict = Depends(member)):
        rel = await _release(rid, user["org_id"])
        ev = await db.events.find_one({"id": rel.get("event_id"), "org_id": user["org_id"]}, {"_id": 0}) or {}
        return HTMLResponse(_html(rel, await _settings(user["org_id"]), ev, "#"), headers={"Content-Security-Policy": "script-src 'none'"})

    @r.post("/press/releases/{rid}/test")
    async def test_send(rid: str, body: TestIn, user: dict = Depends(editor)):
        rel = await _release(rid, user["org_id"])
        st = await _settings(user["org_id"])
        if (e := _sender_ok(st)):
            raise HTTPException(status_code=400, detail=e)
        if not EMAIL_RX.match(_norm(body.email)):
            raise HTTPException(status_code=400, detail="Email di prova non valida")
        ev = await db.events.find_one({"id": rel.get("event_id"), "org_id": user["org_id"]}, {"_id": 0}) or {}
        sc, mid, err = await _send_one(_norm(body.email), "[PROVA] " + (rel.get("oggetto_email") or rel.get("titolo") or ""), _html(rel, st, ev, "#"), st, f"press-test-{rid}")
        if sc not in (200, 201):
            raise HTTPException(status_code=400, detail=f"Invio di prova non riuscito: {err or sc}")
        return {"ok": True}

    @r.post("/press/releases/{rid}/recipients")
    async def recipients(rid: str, body: SendIn, user: dict = Depends(member)):
        await _release(rid, user["org_id"])
        q = _recipients_q(user["org_id"], body.model_dump())
        return {"count": await db.press_contacts.count_documents(q),
                "excluded": await db.press_contacts.count_documents({"org_id": user["org_id"]}) - await db.press_contacts.count_documents(_recipients_q(user["org_id"], {}))}

    @r.post("/press/releases/{rid}/approve")
    async def approve(rid: str, user: dict = Depends(editor)):
        rel = await _release(rid, user["org_id"])
        if rel["status"] not in ("bozza", "da_approvare", "errore"):
            raise HTTPException(status_code=400, detail="Questo comunicato non può essere approvato")
        if not (rel.get("titolo") and rel.get("testo")):
            raise HTTPException(status_code=400, detail="Titolo e testo sono obbligatori")
        upd = {"approved_at": _now(), "approved_by": {"user_id": user["user_id"], "name": user.get("name")}, "approval_expired": False}
        if rel.get("automation") and rel.get("send_at") and rel["send_at"] > _now() and not _sender_ok(await _settings(user["org_id"])):
            upd["status"] = "programmato"
        await db.press_releases.update_one({"id": rid}, {"$set": upd})
        await record_audit(user, "press_release_approved", org_id=user["org_id"], detail=f"Comunicato «{rel.get('titolo')}» approvato")
        return {**rel, **upd}

    @r.post("/press/releases/{rid}/send")
    async def schedule(rid: str, body: SendIn, user: dict = Depends(editor)):
        rel = await _release(rid, user["org_id"])
        if not rel.get("approved_at"):
            raise HTTPException(status_code=400, detail="Approva il comunicato prima di programmare l'invio")
        if rel["status"] not in ("bozza", "da_approvare", "programmato", "errore"):
            raise HTTPException(status_code=400, detail="Comunicato non programmabile")
        if (e := _sender_ok(await _settings(user["org_id"]))):
            raise HTTPException(status_code=400, detail=e)
        filters = {"media": body.media or [], "regioni": body.regioni or [], "province": body.province or []}
        n = await db.press_contacts.count_documents(_recipients_q(user["org_id"], filters))
        if not n:
            raise HTTPException(status_code=400, detail="Nessun destinatario idoneo (attivo e con base giuridica)")
        send_at = _now()
        if body.mode == "scheduled":
            try:
                send_at = datetime.fromisoformat(body.send_at).astimezone(timezone.utc).isoformat()
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Data e ora di invio non valide")
            if send_at <= _now():
                raise HTTPException(status_code=400, detail="La data di invio deve essere futura")
        upd = {"status": "programmato", "send_at": send_at, "filters": filters, "recipients_count": n, "error": None, "scheduled_by": {"user_id": user["user_id"], "name": user.get("name")},
               "oggetto_email": body.oggetto_email or rel.get("oggetto_email") or rel.get("titolo"), "updated_at": _now()}
        await db.press_releases.update_one({"id": rid}, {"$set": upd})
        await record_audit(user, "press_release_scheduled", org_id=user["org_id"], detail=f"«{rel.get('titolo')}» · {n} destinatari · {send_at}")
        if body.mode != "scheduled":
            asyncio.create_task(tick())
        return {**rel, **upd}

    @r.post("/press/releases/{rid}/cancel")
    async def cancel(rid: str, user: dict = Depends(editor)):
        res = await db.press_releases.update_one({"id": rid, "org_id": user["org_id"], "status": "programmato"}, {"$set": {"status": "bozza", "approved_at": None, "approved_by": None, "updated_at": _now()}})
        if not res.modified_count:
            raise HTTPException(status_code=400, detail="Solo un invio programmato può essere annullato")
        return {"ok": True}

    @r.get("/press/releases/{rid}/report")
    async def report(rid: str, user: dict = Depends(member)):
        rel = await _release(rid, user["org_id"])
        stats = await _refresh_stats(rel)
        sends = await db.press_sends.find({"release_id": rid, "org_id": user["org_id"]}, {"_id": 0, "email": 1, "status": 1, "sent_at": 1, "error": 1}).to_list(10000)
        return {"release": {k: rel.get(k) for k in ("id", "titolo", "sent_at", "status", "recipients_count", "sent_count", "error_count")}, "stats": stats,
                "sends": sends, "note": "Le aperture possono risultare imprecise per effetto dei sistemi di protezione della privacy delle caselle email."}

    # ---------------- contatti ----------------
    async def _contact_doc(body: ContactIn, org_id: str, existing: Optional[dict] = None) -> dict:
        email = _norm(body.email)
        if not EMAIL_RX.match(email):
            raise HTTPException(status_code=400, detail=f"Email non valida: {body.email}")
        d = body.model_dump()
        d.update({"email": email, "tipologia_media": d["tipologia_media"] if d["tipologia_media"] in MEDIA else "Altro",
                  "base_giuridica": d["base_giuridica"] if d["base_giuridica"] in BASI else None,
                  "stato": d["stato"] if d["stato"] in ("attivo", "sospeso") else "attivo"})
        if existing and existing.get("stato") == "opposto":
            d["stato"] = "opposto"  # opposizione/disiscrizione non riattivabile
        return d

    @r.get("/press/contacts")
    async def contacts(q: Optional[str] = None, media: Optional[str] = None, regione: Optional[str] = None, provincia: Optional[str] = None,
                       user: dict = Depends(member)):
        f = {"org_id": user["org_id"]}
        if media:
            f["tipologia_media"] = media
        if regione:
            f["regione"] = regione
        if provincia:
            f["provincia"] = provincia
        if q and q.strip():
            rx = {"$regex": re.escape(q.strip()), "$options": "i"}
            f["$or"] = [{"nome": rx}, {"cognome": rx}, {"email": rx}, {"testata": rx}, {"citta": rx}]
        return await db.press_contacts.find(f, {"_id": 0, "unsub_token": 0}).sort([("cognome", 1), ("nome", 1)]).to_list(10000)

    @r.post("/press/contacts")
    async def add_contact(body: ContactIn, user: dict = Depends(editor)):
        d = await _contact_doc(body, user["org_id"])
        if await db.press_contacts.find_one({"org_id": user["org_id"], "email": d["email"]}, {"_id": 1}):
            raise HTTPException(status_code=400, detail="Contatto già presente in rubrica con questa email")
        c = {**d, "id": uuid.uuid4().hex, "org_id": user["org_id"], "unsub_token": secrets.token_urlsafe(24), "created_at": _now(), "brevo_status": "in_attesa"}
        await db.press_contacts.insert_one(dict(c))
        asyncio.create_task(_sync_contact(c))
        c.pop("unsub_token")
        return c

    @r.put("/press/contacts/{cid}")
    async def edit_contact(cid: str, body: ContactIn, user: dict = Depends(editor)):
        old = await db.press_contacts.find_one({"id": cid, "org_id": user["org_id"]}, {"_id": 0})
        if not old:
            raise HTTPException(status_code=404, detail="Contatto non trovato")
        d = await _contact_doc(body, user["org_id"], old)
        if d["email"] != old["email"] and await db.press_contacts.find_one({"org_id": user["org_id"], "email": d["email"]}, {"_id": 1}):
            raise HTTPException(status_code=400, detail="Esiste già un contatto con questa email")
        await db.press_contacts.update_one({"id": cid}, {"$set": {**d, "updated_at": _now()}})
        if d["email"] != old["email"]:
            asyncio.create_task(_sync_contact(old, remove=True))
        asyncio.create_task(_sync_contact({**old, **d}))
        return {**{k: v for k, v in old.items() if k != "unsub_token"}, **d}

    @r.delete("/press/contacts/{cid}")
    async def del_contact(cid: str, user: dict = Depends(editor)):
        old = await db.press_contacts.find_one({"id": cid, "org_id": user["org_id"]}, {"_id": 0})
        if not old:
            raise HTTPException(status_code=404, detail="Contatto non trovato")
        await db.press_contacts.delete_one({"id": cid})
        asyncio.create_task(_sync_contact(old, remove=True))  # rimosso solo dalla lista dell'org, mai eliminato globalmente
        return {"ok": True}

    class ImportIn(BaseModel):
        csv_text: str
        base_giuridica: str = "legittimo_interesse"

    @r.post("/press/contacts/import")
    async def import_csv(body: ImportIn, user: dict = Depends(editor)):
        if body.base_giuridica not in BASI:
            raise HTTPException(status_code=400, detail="Indica la base giuridica dei contatti importati")
        text = body.csv_text.lstrip("\ufeff")
        delim = ";" if text.split("\n", 1)[0].count(";") >= text.split("\n", 1)[0].count(",") else ","
        rows = list(csv.DictReader(io.StringIO(text), delimiter=delim))
        if len(rows) > 5000:
            raise HTTPException(status_code=400, detail="Massimo 5000 righe per importazione")
        alias = {"nome": "nome", "cognome": "cognome", "email": "email", "e-mail": "email", "testata": "testata", "testata giornalistica": "testata",
                 "tipologia": "tipologia_media", "tipologia media": "tipologia_media", "città": "citta", "citta": "citta", "provincia": "provincia",
                 "regione": "regione", "note": "note"}
        added = dup = invalid = 0
        seen = set()
        for row in rows:
            m = {alias[k.strip().lower()]: (v or "").strip() for k, v in row.items() if k and k.strip().lower() in alias}
            email = _norm(m.get("email"))
            if not EMAIL_RX.match(email):
                invalid += 1
                continue
            if email in seen or await db.press_contacts.find_one({"org_id": user["org_id"], "email": email}, {"_id": 1}):
                dup += 1
                continue
            seen.add(email)
            d = await _contact_doc(ContactIn(**{**m, "email": email, "provenienza": "import_csv", "base_giuridica": body.base_giuridica}), user["org_id"])
            c = {**d, "id": uuid.uuid4().hex, "org_id": user["org_id"], "unsub_token": secrets.token_urlsafe(24), "created_at": _now(), "brevo_status": "in_attesa"}
            await db.press_contacts.insert_one(c)
            added += 1
        asyncio.create_task(_sync_pending(user["org_id"]))
        return {"added": added, "duplicates": dup, "invalid": invalid}

    async def _sync_pending(org_id: str) -> None:
        for c in await db.press_contacts.find({"org_id": org_id, "brevo_status": {"$in": ["in_attesa", "errore", "rate_limit"]}}, {"_id": 0}).to_list(5000):
            await _sync_contact(c)
            await asyncio.sleep(0.12)

    @r.get("/press/contacts/export")
    async def export_csv(user: dict = Depends(member)):
        rows = await db.press_contacts.find({"org_id": user["org_id"]}, {"_id": 0}).to_list(10000)
        cols = ["nome", "cognome", "email", "testata", "tipologia_media", "citta", "provincia", "regione", "note", "stato", "base_giuridica", "provenienza", "created_at"]
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(cols)
        for c in rows:
            w.writerow([c.get(k) or "" for k in cols])
        return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="contatti-stampa.csv"'})

    # ---------------- impostazioni / automazioni ----------------
    @r.get("/press/settings")
    async def get_settings(user: dict = Depends(member)):
        return {"settings": await _settings(user["org_id"]), "list": await db.press_brevo_lists.find_one({"org_id": user["org_id"]}, {"_id": 0}),
                "automations": await db.press_automations.find({"org_id": user["org_id"]}, {"_id": 0}).to_list(1000)}

    @r.put("/press/settings")
    async def put_settings(body: SettingsIn, user: dict = Depends(editor)):
        d = body.model_dump()
        for k in ("sender_email", "reply_to"):
            d[k] = _norm(d[k])
            if d[k] and not EMAIL_RX.match(d[k]):
                raise HTTPException(status_code=400, detail="Indirizzo email non valido")
        if d["sender_email"].endswith("@crmevent.it"):
            raise HTTPException(status_code=400, detail="Usa un indirizzo della tua organizzazione come mittente")
        old = await _settings(user["org_id"])
        if d["sender_email"] != old.get("sender_email"):
            d["sender_verified"] = False
        await db.press_settings.update_one({"org_id": user["org_id"]}, {"$set": {**d, "org_id": user["org_id"], "updated_at": _now()}}, upsert=True)
        return await _settings(user["org_id"])

    @r.post("/press/settings/verify-sender")
    async def verify_sender(user: dict = Depends(editor)):
        st = await _settings(user["org_id"])
        if not (st.get("sender_email") and st.get("sender_name")):
            raise HTTPException(status_code=400, detail="Salva prima nome ed email del mittente")
        if not brevo_funnel.is_configured():
            raise HTTPException(status_code=400, detail="Brevo non configurato sulla piattaforma")
        sc, data, err = await brevo_funnel._request("GET", "/v3/senders")
        found = next((s for s in (data or {}).get("senders", []) if _norm(s.get("email")) == st["sender_email"]), None)
        if not found:
            sc, data, err = await brevo_funnel._request("POST", "/v3/senders", json={"name": st["sender_name"], "email": st["sender_email"]})
            if sc not in (200, 201):
                raise HTTPException(status_code=400, detail=f"Brevo: {err or sc}")
            msg = "Brevo ha inviato un'email di verifica al mittente: conferma e poi premi di nuovo Verifica"
            verified = False
        else:
            verified = bool(found.get("active"))
            msg = "Mittente verificato" if verified else "Verifica in attesa: conferma l'email ricevuta da Brevo"
        await db.press_settings.update_one({"org_id": user["org_id"]}, {"$set": {"sender_verified": verified, "sender_checked_at": _now()}})
        return {"verified": verified, "message": msg}

    @r.put("/press/automations/{eid}")
    async def put_automation(eid: str, body: AutomationIn, user: dict = Depends(editor)):
        await _event(eid, user["org_id"])
        if not re.match(r"^\d{2}:\d{2}$", body.send_time) or not 0 <= body.delay_days <= 30:
            raise HTTPException(status_code=400, detail="Ritardo (0-30 giorni) o orario non validi")
        d = {**body.model_dump(), "org_id": user["org_id"], "event_id": eid, "require_approval": True, "updated_at": _now()}
        await db.press_automations.update_one({"org_id": user["org_id"], "event_id": eid}, {"$set": d}, upsert=True)
        return d

    # ---------------- disiscrizione pubblica (per organizzazione) ----------------
    @r.get("/public/press/unsubscribe/{token}", response_class=HTMLResponse)
    async def unsubscribe(token: str):
        c = await db.press_contacts.find_one({"unsub_token": token}, {"_id": 0})
        if c and c.get("stato") != "opposto":
            await db.press_contacts.update_one({"id": c["id"]}, {"$set": {"stato": "opposto", "opposed_at": _now(), "updated_at": _now()}})
            asyncio.create_task(_sync_contact({**c, "stato": "opposto"}))
        body = "Non riceverai più comunicati stampa da questa organizzazione." if c else "Link non valido o già utilizzato."
        return HTMLResponse(f'<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><body style="font-family:Arial;padding:40px;text-align:center;color:#0f172a"><h2 style="color:#088F8A">CRMEvent</h2><p>{body}</p></body>')

    # ---------------- job programmati (idempotenti) ----------------
    async def _automation_tick() -> None:
        today = datetime.now(ROME).date()
        for a in await db.press_automations.find({"enabled": True}, {"_id": 0}).to_list(2000):
            if not await _active(a["org_id"]):
                continue
            ev = await db.events.find_one({"id": a["event_id"], "org_id": a["org_id"]}, {"_id": 0})
            end = (ev or {}).get("data_fine") or (ev or {}).get("data_inizio")
            if not end or end[:10] >= today.isoformat():
                continue
            key = f"{a['org_id']}:{a['event_id']}:post"
            try:
                await db.press_releases.insert_one({"id": uuid.uuid4().hex, "automation_key": key, "org_id": a["org_id"], "event_id": ev["id"], "tipo": "post_evento",
                                                    "status": "generazione", "automation": True, "created_at": _now(), "updated_at": _now()})
            except DuplicateKeyError:
                continue
            hh, mm = map(int, a.get("send_time", "10:00").split(":"))
            local = datetime.fromisoformat(end[:10]).replace(tzinfo=ROME) + timedelta(days=a.get("delay_days", 1), hours=hh, minutes=mm)
            data = await _event_data(ev)
            try:
                res = await _ai("post_evento", data, "", "istituzionale")
            except Exception as e:  # noqa: BLE001
                res = {"titolo": f"{ev.get('nome')}: resoconto", "sottotitolo": "", "testo": "", "dati_mancanti": _missing("post_evento", data)}
                logger.warning("press automation AI failed: %s", e)
            await db.press_releases.update_one({"automation_key": key}, {"$set": {
                **res, "status": "da_approvare", "send_at": local.astimezone(timezone.utc).isoformat(), "citazioni": [], "foto": [],
                "filters": {"media": a.get("media") or [], "regioni": a.get("regioni") or [], "province": []},
                "created_by": {"user_id": None, "name": "Automazione post-evento"}, "updated_at": _now()}})
            await db.press_notifications.insert_one({"id": uuid.uuid4().hex, "org_id": a["org_id"], "kind": "post_event_draft", "event_id": ev["id"],
                                                     "text": f"Bozza del comunicato post-evento «{ev.get('nome')}» pronta: controllala e approvala.", "created_at": _now(), "read": False})

    async def tick() -> dict:
        await _automation_tick()
        now = _now()
        # automazioni non approvate in tempo: sospese, serve nuova conferma
        await db.press_releases.update_many({"status": "da_approvare", "automation": True, "approved_at": None, "send_at": {"$lte": now}, "approval_expired": {"$ne": True}},
                                            {"$set": {"approval_expired": True, "send_at": None}})
        n = 0
        while True:
            rel = await db.press_releases.find_one_and_update({"status": "programmato", "send_at": {"$lte": now}, "approved_at": {"$ne": None}},
                                                              {"$set": {"status": "in_invio", "sending_started_at": now}}, return_document=ReturnDocument.AFTER)
            if not rel:
                break
            n += 1
            await _deliver(rel["id"])
        for rel in await db.press_releases.find({"status": "in_invio"}, {"_id": 0, "id": 1}).to_list(50):  # ripresa dopo riavvio / rate limit
            await _deliver(rel["id"])
        await _sync_lists_retry()
        return {"started": n}

    async def _sync_lists_retry() -> None:
        active = [s["org_id"] for s in await db.org_services.find({"service": SERVICE_KEY, "active": True}, {"_id": 0, "org_id": 1}).to_list(5000)]
        for c in await db.press_contacts.find({"org_id": {"$in": active}, "brevo_status": {"$in": ["in_attesa", "rate_limit"]}}, {"_id": 0}).limit(200).to_list(200):
            await _sync_contact(c)

    @r.get("/press/notifications")
    async def notifications(user: dict = Depends(member)):
        return await db.press_notifications.find({"org_id": user["org_id"], "read": False}, {"_id": 0}).sort("created_at", -1).to_list(50)

    @r.post("/press/notifications/read")
    async def notifications_read(user: dict = Depends(member)):
        await db.press_notifications.update_many({"org_id": user["org_id"]}, {"$set": {"read": True}})
        return {"ok": True}

    # ---------------- Super Admin ----------------
    @r.get("/platform/press/orgs")
    async def sa_orgs(admin: dict = Depends(require_superadmin)):
        orgs = await db.organizations.find({}, {"_id": 0, "id": 1, "nome": 1}).sort("nome", 1).to_list(5000)
        act = {s["org_id"]: s for s in await db.org_services.find({"service": SERVICE_KEY}, {"_id": 0}).to_list(5000)}
        lists = {x["org_id"]: x for x in await db.press_brevo_lists.find({}, {"_id": 0}).to_list(5000)}
        agg = {}
        for c in await db.press_releases.aggregate([{"$group": {"_id": {"o": "$org_id", "s": "$status"}, "n": {"$sum": 1}}}]).to_list(10000):
            agg.setdefault(c["_id"]["o"], {})[c["_id"]["s"]] = c["n"]
        out = []
        for o in orgs:
            a = act.get(o["id"]) or {}
            st = agg.get(o["id"], {})
            out.append({"org_id": o["id"], "nome": o.get("nome"), "active": bool(a.get("active")), "activated_at": a.get("activated_at"),
                        "releases": sum(st.values()), "sent": st.get("inviato", 0), "errors": st.get("errore", 0),
                        "contacts": await db.press_contacts.count_documents({"org_id": o["id"]}) if a else 0,
                        "contact_errors": await db.press_contacts.count_documents({"org_id": o["id"], "brevo_status": "errore"}) if a else 0,
                        "list": lists.get(o["id"])})
        return out

    @r.post("/platform/press/orgs/{org_id}/activate")
    async def sa_activate(org_id: str, body: ActivateIn, admin: dict = Depends(require_superadmin)):
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "nome": 1})
        if not org:
            raise HTTPException(status_code=404, detail="Organizzazione non trovata")
        await db.org_services.update_one({"org_id": org_id, "service": SERVICE_KEY}, {"$set": {
            "active": body.active, "updated_at": _now(), "billing": "gratuito_in_attesa_listino",
            **({"activated_at": _now(), "activated_by": admin.get("email")} if body.active else {"deactivated_at": _now()})}}, upsert=True)
        if body.active:
            asyncio.create_task(_ensure_list(org_id))
        await record_audit(admin, "press_service_" + ("activated" if body.active else "deactivated"), org_id=org_id, org_name=org.get("nome"))
        return {"ok": True, "active": body.active}

    async def ensure_indexes():
        await db.press_releases.create_index("id", unique=True)
        await db.press_releases.create_index("automation_key", unique=True, partialFilterExpression={"automation_key": {"$type": "string"}})
        await db.press_contacts.create_index([("org_id", 1), ("email", 1)], unique=True)
        await db.press_contacts.create_index("unsub_token")
        await db.press_sends.create_index([("release_id", 1), ("email", 1)], unique=True)
        await db.org_services.create_index([("org_id", 1), ("service", 1)], unique=True)

    return {"router": r, "ensure_indexes": ensure_indexes, "tick": tick, "is_active": _active}
