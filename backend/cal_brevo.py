"""Calendario Eventi Italia — Fase 3: lista Brevo organizzatori, template, anteprima destinatari e invio manuale confermato."""
import asyncio
import hashlib
import html as _html
import re
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field

from brevo_client import BrevoClient, BrevoError, BrevoNotConfigured, is_configured

LIST_NAME = "CRMEvent \u2014 Organizzatori Eventi Italia"
FOLDER_NAME = "CRMEvent \u2014 Calendario Italia"
ATTRS = ["CAL_ORGANIZZATORE", "CAL_TIPOLOGIA", "CAL_REGIONE", "CAL_ULTIMO_EVENTO", "CAL_DATA_ULTIMO_EVENTO"]
PARAMS = ["ORGANIZZATORE", "EVENTO", "DATA_EVENTO", "COMUNE", "DEMO_URL", "UNSUB_URL"]
SKIP_COMM = ("escluso", "cliente_acquisito")
ADVANCE = ("da_qualificare", "contatto_da_verificare", "pronto_campagna", "invio_programmato")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _wrap(body: str) -> str:
    return ('<div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.6;color:#0f172a;max-width:600px;margin:0 auto;padding:24px">'
            f'{body}<hr style="border:none;border-top:1px solid #e2e8f0;margin:28px 0 12px"><p style="font-size:12px;color:#64748b">'
            'Ricevi questa email perch\u00e9 il tuo contatto \u00e8 pubblicato come riferimento organizzativo della manifestazione. '
            '<a href="{{ params.UNSUB_URL }}" style="color:#64748b">Non desidero ricevere altre comunicazioni</a></p></div>')


DEFAULT_TEMPLATES = {
    "post_evento": {"nome": "Post-evento", "oggetto": "{{ params.EVENTO }}: com'\u00e8 andata?", "html": _wrap(
        "<p>Gentile {{ params.ORGANIZZATORE }},</p><p>complimenti per <b>{{ params.EVENTO }}</b> del {{ params.DATA_EVENTO }} a {{ params.COMUNE }}.</p>"
        "<p>Mentre preparate la prossima edizione, CRMEvent pu\u00f2 aiutarvi a gestire in un unico posto iscritti, volontari, staff, sponsor e comunicazioni.</p>"
        '<p><a href="{{ params.DEMO_URL }}" style="background:#0ABAB5;color:#0f172a;padding:10px 18px;border-radius:999px;text-decoration:none;font-weight:bold">Prenota una demo</a></p>'
        "<p>Un saluto,<br>Il team CRMEvent</p>")},
    "richiamo": {"nome": "Richiamo", "oggetto": "Prossima edizione di {{ params.EVENTO }}", "html": _wrap(
        "<p>Gentile {{ params.ORGANIZZATORE }},</p><p>vi avevamo scritto dopo <b>{{ params.EVENTO }}</b>. Se state gi\u00e0 pensando alla prossima edizione, "
        "possiamo mostrarvi in pochi minuti come CRMEvent semplifica l'organizzazione.</p>"
        '<p><a href="{{ params.DEMO_URL }}">Prenota una demo</a></p><p>Un saluto,<br>Il team CRMEvent</p>')},
}


class TemplateIn(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    oggetto: str = Field(min_length=2, max_length=200)
    html: str = Field(min_length=20, max_length=100000)


class SenderIn(BaseModel):
    sender_id: int


class TestIn(BaseModel):
    to: Optional[EmailStr] = None


class FilterIn(BaseModel):
    template_id: str
    dal: Optional[str] = None
    al: Optional[str] = None
    disciplina: Optional[str] = None
    regione: Optional[str] = None


class SendIn(FilterIn):
    firma: str
    conferma: str
    simulazione: bool = False


def _brevo_err(e: Exception) -> HTTPException:
    if isinstance(e, BrevoNotConfigured):
        return HTTPException(status_code=400, detail="Brevo non configurato (BREVO_API_KEY mancante)")
    if isinstance(e, BrevoError):
        msg = (e.body or {}).get("message") if isinstance(e.body, dict) else str(e.body)
        return HTTPException(status_code=502, detail=f"Brevo ha risposto {e.status}: {str(msg)[:200]}")
    return HTTPException(status_code=502, detail=f"Errore di comunicazione con Brevo: {str(e)[:200]}")


def build(db, deps: dict):
    r = APIRouter()
    pub = APIRouter(prefix="/api/public/cal")
    sa, audit, settings, comm_date, history = deps["sa"], deps["audit"], deps["settings"], deps["comm_date"], deps["history"]
    app_url = (deps.get("app_url") or "").rstrip("/")
    tasks: set = set()

    async def cfg() -> dict:
        return (await db.cal_settings.find_one({"id": "main"}, {"_id": 0}) or {}).get("brevo") or {}

    async def set_cfg(patch: dict):
        await db.cal_settings.update_one({"id": "main"}, {"$set": {f"brevo.{k}": v for k, v in patch.items()}}, upsert=True)

    async def template(tid: str) -> dict:
        t = await db.cal_templates.find_one({"id": tid}, {"_id": 0})
        if t:
            return t
        if tid not in DEFAULT_TEMPLATES:
            raise HTTPException(status_code=404, detail="Template non trovato")
        return {"id": tid, **DEFAULT_TEMPLATES[tid], "brevo_template_id": None}

    async def unsub_token(org: dict) -> str:
        if org.get("unsub_token"):
            return org["unsub_token"]
        tok = secrets.token_urlsafe(24)
        await db.cal_organizers.update_one({"id": org["id"]}, {"$set": {"unsub_token": tok}})
        return tok

    def org_email(o: dict) -> Optional[str]:
        return (o.get("email_organizzativa") or o.get("email_generale") or "").strip() or None

    # ---------- stato, mittenti ----------
    @r.get("/brevo/status")
    async def status(admin: dict = Depends(sa)):
        c = await cfg()
        n = await db.cal_organizers.count_documents({"merged_into": None, "privacy.status": "idoneo", "escluso_campagne": {"$ne": True},
                                                     "$or": [{"email_organizzativa": {"$nin": [None, ""]}}, {"email_generale": {"$nin": [None, ""]}}]})
        tpls = [await template(t) for t in DEFAULT_TEMPLATES]
        return {"configured": is_configured(), "list_id": c.get("list_id"), "list_name": LIST_NAME, "sender": c.get("sender"),
                "last_list_sync": c.get("last_list_sync"), "last_list_result": c.get("last_list_result"), "idonei_con_email": n,
                "templates": [{k: t.get(k) for k in ("id", "nome", "oggetto", "brevo_template_id", "synced_at", "updated_at")} for t in tpls]}

    @r.get("/brevo/senders")
    async def senders(admin: dict = Depends(sa)):
        try:
            async with BrevoClient() as b:
                rows = await b.senders()
        except Exception as e:  # noqa: BLE001
            raise _brevo_err(e) from e
        return {"senders": [{"id": s.get("id"), "name": s.get("name"), "email": s.get("email")} for s in rows if s.get("active")]}

    @r.put("/brevo/sender")
    async def set_sender(body: SenderIn, admin: dict = Depends(sa)):
        s = next((x for x in (await senders(admin))["senders"] if x["id"] == body.sender_id), None)
        if not s:
            raise HTTPException(status_code=400, detail="Mittente non verificato su Brevo")
        await set_cfg({"sender": s})
        await audit(admin, "cal_brevo_sender", detail=s["email"])
        return s

    # ---------- lista organizzatori ----------
    async def ensure_list(b: BrevoClient) -> int:
        c = await cfg()
        if c.get("list_id"):
            try:
                await b.get_list(c["list_id"])
                return c["list_id"]
            except BrevoError as e:
                if e.status != 404:
                    raise
        lst = next((x for x in await b.lists() if x.get("name") == LIST_NAME), None)
        if not lst:
            folder = next((f for f in await b.folders() if f.get("name") == FOLDER_NAME), None) or await b.create_folder(FOLDER_NAME)
            lst = await b.create_list(LIST_NAME, folder["id"])
        await set_cfg({"list_id": lst["id"]})
        have = {a.get("name") for a in await b.attributes()}
        for a in ATTRS:
            if a not in have:
                await b._req("POST", f"/contacts/attributes/normal/{a}", json={"type": "text"})
        return lst["id"]

    @r.post("/brevo/list/sync")
    async def list_sync(admin: dict = Depends(sa)):
        """Allinea la lista: aggiunge/aggiorna solo i contatti 'Idoneo', toglie quelli non pi\u00f9 idonei. Non reiscrive mai contatti disiscritti."""
        res = {"aggiunti": 0, "aggiornati": 0, "rimossi": 0, "disiscritti_brevo": 0, "errori": 0}
        try:
            async with BrevoClient() as b:
                lid = await ensure_list(b)
                orgs = await db.cal_organizers.find({"merged_into": None}, {"_id": 0}).to_list(100000)
                remove = []
                for o in orgs:
                    email = org_email(o)
                    ok = email and (o.get("privacy") or {}).get("status") == "idoneo" and not o.get("escluso_campagne")
                    if not ok:
                        if o.get("brevo_email"):
                            remove.append((o["id"], o["brevo_email"]))
                        continue
                    last = await db.cal_events.find_one({"organizer_id": o["id"], "merged_into": None}, {"_id": 0, "nome": 1, "data_inizio": 1}, sort=[("data_inizio", -1)]) or {}
                    attrs = {"CAL_ORGANIZZATORE": o["nome"], "CAL_TIPOLOGIA": o.get("tipologia"), "CAL_REGIONE": o.get("regione"),
                             "CAL_ULTIMO_EVENTO": last.get("nome"), "CAL_DATA_ULTIMO_EVENTO": last.get("data_inizio")}
                    try:
                        cur = await b.get_contact(email)
                        if cur and cur.get("emailBlacklisted"):
                            res["disiscritti_brevo"] += 1
                            await mark_unsub(o, "Disiscritto su Brevo", "brevo")
                            continue
                        if cur:
                            await b.update_contact(email, list_id=lid, attributes=attrs)
                            res["aggiornati"] += 1
                        else:
                            await b.create_contact(email, lid, {k: v for k, v in attrs.items() if v})
                            res["aggiunti"] += 1
                        await db.cal_organizers.update_one({"id": o["id"]}, {"$set": {"brevo_email": email, "brevo_synced_at": _now()}})
                    except BrevoError:
                        res["errori"] += 1
                for i in range(0, len(remove), 150):
                    chunk = remove[i:i + 150]
                    try:
                        await b._req("POST", f"/contacts/lists/{lid}/contacts/remove", json={"emails": [e for _, e in chunk]})
                    except BrevoError as e:
                        if e.status != 400:  # 400 = contatti già assenti dalla lista
                            res["errori"] += len(chunk)
                            continue
                    await db.cal_organizers.update_many({"id": {"$in": [x for x, _ in chunk]}}, {"$set": {"brevo_email": None}})
                    res["rimossi"] += len(chunk)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise _brevo_err(e) from e
        await set_cfg({"last_list_sync": _now(), "last_list_result": res})
        await audit(admin, "cal_brevo_list_sync", detail=str(res))
        return {"list_id": lid, **res}

    # ---------- template ----------
    @r.get("/templates")
    async def list_templates(admin: dict = Depends(sa)):
        return {"templates": [await template(t) for t in DEFAULT_TEMPLATES], "params": PARAMS}

    @r.put("/templates/{tid}")
    async def save_template(tid: str, body: TemplateIn, admin: dict = Depends(sa)):
        await template(tid)
        if "params.UNSUB_URL" not in body.html:
            raise HTTPException(status_code=400, detail="Il testo deve contenere il link di disiscrizione {{ params.UNSUB_URL }}")
        await db.cal_templates.update_one({"id": tid}, {"$set": {**body.model_dump(), "updated_at": _now(), "updated_by": admin.get("email")}}, upsert=True)
        await audit(admin, "cal_template_save", detail=tid)
        return await template(tid)

    @r.post("/templates/{tid}/brevo")
    async def push_template(tid: str, admin: dict = Depends(sa)):
        t, sender = await template(tid), (await cfg()).get("sender")
        if not sender:
            raise HTTPException(status_code=400, detail="Scegli prima il mittente verificato in Impostazioni")
        payload = {"templateName": f"CRMEvent \u00b7 Calendario Italia \u00b7 {t['nome']}", "subject": t["oggetto"], "htmlContent": t["html"],
                   "sender": {"id": sender["id"]}, "isActive": True, "tag": "calendario-italia"}
        try:
            async with BrevoClient() as b:
                if t.get("brevo_template_id"):
                    try:
                        await b._req("PUT", f"/smtp/templates/{t['brevo_template_id']}", json=payload)
                        bid = t["brevo_template_id"]
                    except BrevoError as e:
                        if e.status != 404:
                            raise
                        bid = (await b._req("POST", "/smtp/templates", json=payload))["id"]
                else:
                    bid = (await b._req("POST", "/smtp/templates", json=payload))["id"]
        except Exception as e:  # noqa: BLE001
            raise _brevo_err(e) from e
        await db.cal_templates.update_one({"id": tid}, {"$set": {**{k: t[k] for k in ("nome", "oggetto", "html")}, "brevo_template_id": bid,
                                                                 "synced_at": _now(), "sender": sender}}, upsert=True)
        await audit(admin, "cal_template_brevo", detail=f"{tid} \u2192 {bid}")
        return await template(tid)

    async def send_one(b: BrevoClient, t: dict, to: str, name: str, params: dict, unsub: Optional[str]) -> str:
        body = {"templateId": int(t["brevo_template_id"]), "to": [{"email": to, "name": name[:70]}], "params": params, "tags": ["calendario-italia"]}
        if unsub:
            body["headers"] = {"List-Unsubscribe": f"<{unsub}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
        return ((await b._req("POST", "/smtp/email", json=body)) or {}).get("messageId")

    def sample_params(unsub: str) -> dict:
        return {"ORGANIZZATORE": "ASD Esempio", "EVENTO": "Mezza Maratona di Esempio", "DATA_EVENTO": "12/04/2026", "COMUNE": "Esempio",
                "DEMO_URL": app_url or "https://crmevent.it", "UNSUB_URL": unsub}

    @r.post("/templates/{tid}/test")
    async def test_template(tid: str, body: TestIn, admin: dict = Depends(sa)):
        t = await template(tid)
        if not t.get("brevo_template_id"):
            raise HTTPException(status_code=400, detail="Salva prima il template su Brevo")
        to = body.to or admin.get("email")
        try:
            async with BrevoClient() as b:
                mid = await send_one(b, {**t, "brevo_template_id": t["brevo_template_id"]}, to, "Prova", sample_params(f"{app_url}/"), None)
        except Exception as e:  # noqa: BLE001
            raise _brevo_err(e) from e
        await audit(admin, "cal_template_test", detail=f"{tid} \u2192 {to}")
        return {"ok": True, "to": to, "message_id": mid}

    # ---------- anteprima destinatari e invio ----------
    async def recipients(f: FilterIn) -> dict:
        s = await settings()
        days, gap = int(s["giorni_post_evento"]), int(s["intervallo_min_giorni"])
        today = date.today().isoformat()
        dal, al = f.dal or (date.today() - timedelta(days=60)).isoformat(), f.al or today
        q = {"merged_into": None, "stato": {"$in": ["confermata", "conclusa"]}, "data_inizio": {"$lte": al}}
        if f.disciplina:
            q["disciplina"] = f.disciplina
        if f.regione:
            q["regione"] = f.regione
        evs = [e for e in await db.cal_events.find(q, {"_id": 0}).sort("data_inizio", 1).to_list(20000)]
        evs = [(e, comm_date(e, days)) for e in evs]
        evs = [(e, cd) for e, cd in evs if cd and dal <= cd <= al]
        orgs = {o["id"]: o for o in await db.cal_organizers.find({"id": {"$in": list({e.get("organizer_id") for e, _ in evs if e.get("organizer_id")})}}, {"_id": 0}).to_list(20000)}
        sent = {c["event_id"] for c in await db.cal_comms.find({"template_id": f.template_id, "status": "inviato"}, {"_id": 0, "event_id": 1}).to_list(100000)}
        limit = (datetime.now(timezone.utc) - timedelta(days=gap)).isoformat()
        inc, exc, seen = [], [], set()
        for e, cd in evs:
            o = orgs.get(e.get("organizer_id"))
            row = {"event_id": e["id"], "evento": e["nome"], "data_evento": e.get("data_fine") or e.get("data_inizio"), "comune": e.get("comune"),
                   "data_comunicazione": cd, "org_id": (o or {}).get("id"), "organizzatore": (o or {}).get("nome") or e.get("organizzatore_nome"),
                   "email": org_email(o) if o else None}
            p = (o or {}).get("privacy") or {}
            why = ("Organizzatore mancante" if not o else
                   "Escluso dalle campagne" if o.get("escluso_campagne") or o.get("stato_commerciale") == "escluso" else
                   "Gi\u00e0 cliente" if o.get("stato_commerciale") == "cliente_acquisito" else
                   f"Contatto non idoneo ({p.get('status') or 'da_verificare'})" if p.get("status") != "idoneo" else
                   "Email mancante" if not row["email"] else
                   "Gi\u00e0 inviato per questo evento" if e["id"] in sent else
                   f"Contattato il {o['ultimo_contatto'][:10]} (intervallo minimo {gap} giorni)" if (o.get("ultimo_contatto") or "") > limit else
                   "Organizzatore gi\u00e0 incluso per un altro evento" if o["id"] in seen else None)
            if why:
                exc.append({**row, "motivo": why})
            else:
                seen.add(o["id"])
                inc.append(row)
        firma = hashlib.sha256("|".join(sorted(f"{x['org_id']}:{x['event_id']}" for x in inc)).encode()).hexdigest()[:16]
        return {"inclusi": inc, "esclusi": exc, "firma": firma, "dal": dal, "al": al, "giorni_post_evento": days, "intervallo_min_giorni": gap}

    @r.post("/campaigns/preview")
    async def preview(body: FilterIn, admin: dict = Depends(sa)):
        t = await template(body.template_id)
        res = await recipients(body)
        return {**res, "template": {"id": t["id"], "nome": t["nome"], "oggetto": t["oggetto"], "su_brevo": bool(t.get("brevo_template_id"))},
                "mittente": (await cfg()).get("sender")}

    @r.post("/campaigns/send")
    async def send(body: SendIn, admin: dict = Depends(sa)):
        if body.conferma.strip().upper() != "INVIA":
            raise HTTPException(status_code=400, detail="Scrivi INVIA per confermare")
        t = await template(body.template_id)
        if not body.simulazione and not (t.get("brevo_template_id") and (await cfg()).get("sender")):
            raise HTTPException(status_code=400, detail="Mittente e template su Brevo sono obbligatori per l'invio reale")
        res = await recipients(body)
        if res["firma"] != body.firma:
            raise HTTPException(status_code=409, detail="I destinatari sono cambiati dall'anteprima: rifai l'anteprima")
        if not res["inclusi"]:
            raise HTTPException(status_code=400, detail="Nessun destinatario idoneo")
        cid = uuid.uuid4().hex
        await db.cal_campaigns.insert_one({"id": cid, "template_id": t["id"], "template_nome": t["nome"], "filtri": body.model_dump(exclude={"firma", "conferma"}),
                                           "destinatari": len(res["inclusi"]), "inviati": 0, "errori": 0, "status": "in_corso", "simulazione": body.simulazione,
                                           "created_by": admin.get("email"), "created_at": _now()})
        task = asyncio.create_task(run_campaign(cid, t, res["inclusi"], body.simulazione, admin.get("email")))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        await audit(admin, "cal_campaign_send", detail=f"{cid} \u00b7 {t['id']} \u00b7 {len(res['inclusi'])} \u00b7 simulazione={body.simulazione}")
        return {"campaign_id": cid, "destinatari": len(res["inclusi"]), "simulazione": body.simulazione}

    async def run_campaign(cid: str, t: dict, rows: list, sim: bool, by: str):
        ok = ko = 0
        b = None if sim else BrevoClient()
        try:
            for x in rows:
                o = await db.cal_organizers.find_one({"id": x["org_id"]}, {"_id": 0})
                if (not o or (o.get("privacy") or {}).get("status") != "idoneo" or o.get("escluso_campagne")
                        or o.get("stato_commerciale") in SKIP_COMM):  # ricontrollo prima di ogni invio
                    continue
                unsub = f"{app_url}/api/public/cal/unsubscribe/{await unsub_token(o)}"
                params = {"ORGANIZZATORE": o["nome"], "EVENTO": x["evento"], "COMUNE": x.get("comune") or "", "DEMO_URL": app_url, "UNSUB_URL": unsub,
                          "DATA_EVENTO": datetime.strptime(x["data_evento"], "%Y-%m-%d").strftime("%d/%m/%Y") if x.get("data_evento") else ""}
                doc = {"id": uuid.uuid4().hex, "campaign_id": cid, "org_id": o["id"], "organizzatore": o["nome"], "event_id": x["event_id"], "evento": x["evento"],
                       "email": x["email"], "template_id": t["id"], "template_nome": t["nome"], "at": _now(), "by": by}
                try:
                    if sim:
                        doc.update(status="simulato", message_id=None)
                    else:
                        cur = await b.get_contact(x["email"])
                        if cur and cur.get("emailBlacklisted"):
                            await mark_unsub(o, "Disiscritto su Brevo", "brevo")
                            doc.update(status="saltato", errore="Contatto disiscritto su Brevo")
                        else:
                            doc.update(status="inviato", message_id=await send_one(b, t, x["email"], o["nome"], params, unsub))
                            await db.cal_organizers.update_one({"id": o["id"]}, {"$set": {"ultimo_contatto": _now(), **({"stato_commerciale": "inviato"} if o.get("stato_commerciale") in ADVANCE else {})}})
                            await db.cal_events.update_one({"id": x["event_id"]}, {"$set": {"stato_commerciale": "inviato"}})
                            await history(o["id"], "comunicazione", None, f"{t['nome']} \u00b7 {x['evento']}", "brevo", "manuale", by)
                    ok += doc["status"] in ("inviato", "simulato")
                except Exception as e:  # noqa: BLE001
                    doc.update(status="errore", errore=str(getattr(e, "body", None) or e)[:300])
                    ko += 1
                await db.cal_comms.insert_one({**doc})
                await db.cal_campaigns.update_one({"id": cid}, {"$set": {"inviati": ok, "errori": ko}})
                if not sim:
                    await asyncio.sleep(0.3)
        finally:
            if b:
                await b.__aexit__()
            await db.cal_campaigns.update_one({"id": cid}, {"$set": {"status": "completata", "inviati": ok, "errori": ko, "finished_at": _now()}})

    @r.get("/campaigns")
    async def campaigns(admin: dict = Depends(sa)):
        return {"campaigns": await db.cal_campaigns.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)}

    @r.get("/comms")
    async def comms(admin: dict = Depends(sa), status: str = "", campaign_id: str = "", q: str = "", limit: int = 200):
        qq = {**({"status": status} if status else {}), **({"campaign_id": campaign_id} if campaign_id else {})}
        if q:
            qq["$or"] = [{k: {"$regex": re.escape(q), "$options": "i"}} for k in ("organizzatore", "evento", "email")]
        return {"rows": await db.cal_comms.find(qq, {"_id": 0}).sort("at", -1).limit(min(limit, 1000)).to_list(1000),
                "totali": {x["_id"]: x["n"] for x in await db.cal_comms.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]).to_list(20)}}

    # ---------- disiscrizione ----------
    async def mark_unsub(o: dict, nota: str, fonte: str):
        p = {**(o.get("privacy") or {}), "status": "disiscritto", "note": nota, "ultima_verifica": _now(), "verificato_da": fonte}
        await db.cal_organizers.update_one({"id": o["id"]}, {"$set": {"privacy": p}})
        await history(o["id"], "privacy", (o.get("privacy") or {}).get("status"), "disiscritto", fonte, "automatica", fonte)

    def page(msg: str, form: str = "") -> HTMLResponse:
        return HTMLResponse(f'<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>CRMEvent</title></head>'
                            f'<body style="font-family:Arial,sans-serif;padding:40px;text-align:center;color:#0f172a"><h2>CRMEvent</h2><p>{_html.escape(msg)}</p>{form}</body></html>')

    async def by_token(token: str) -> Optional[dict]:
        return await db.cal_organizers.find_one({"unsub_token": token}, {"_id": 0}) if len(token) > 20 else None

    @pub.get("/unsubscribe/{token}", response_class=HTMLResponse)
    async def unsubscribe_page(token: str):
        """Solo conferma: un GET (anche da scanner/anteprime) non disiscrive."""
        if not await by_token(token):
            return page("Link non valido o scaduto.")
        return page("Vuoi smettere di ricevere comunicazioni da CRMEvent?",
                    f'<form method="post"><button style="background:#0ABAB5;border:none;padding:10px 20px;border-radius:999px;font-weight:bold;cursor:pointer">Conferma disiscrizione</button></form>')

    @pub.post("/unsubscribe/{token}", response_class=HTMLResponse)
    async def unsubscribe(token: str):
        o = await by_token(token)
        if o and (o.get("privacy") or {}).get("status") != "disiscritto":
            await mark_unsub(o, "Disiscrizione dal link nell'email", "link_email")
            if o.get("brevo_email") and is_configured():
                lid = (await cfg()).get("list_id")
                try:
                    async with BrevoClient() as b:
                        if lid:
                            await b._req("POST", f"/contacts/lists/{lid}/contacts/remove", json={"emails": [o["brevo_email"]]})
                except Exception:  # noqa: BLE001
                    pass
        return page("Disiscrizione registrata: non riceverai altre comunicazioni da CRMEvent." if o else "Link non valido o scaduto.")

    return {"router": r, "public_router": pub}
