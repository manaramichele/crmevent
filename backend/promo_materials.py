"""Materiali promozionali ufficiali CRMEvent (video demo, anteprima JPG, newsletter HTML Brevo) con versioni. Gestione solo Super Admin; pagine video pubbliche solo per i materiali pubblicati."""
import html as H
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

FIELDS = ["name", "title", "subtitle", "description", "subject", "preheader", "headline", "body", "benefits", "button_label", "html_override"]

DEFAULTS = [
    {"slug": "event-planner", "order": 1, "status": "pubblicato", "name": "Event Planner", "title": "EVENT PLANNER", "subtitle": "Progetta il tuo evento",
     "description": "Disegna l'area del tuo evento su una mappa reale: strutture, percorsi, ristori, sponsor e postazioni dello staff, tutto in scala e condiviso con il team.",
     "subject": "Event Planner: progetta il tuo evento sulla mappa", "preheader": "Strutture, percorsi e postazioni in scala, condivisi con il team.",
     "headline": "Progetta il tuo evento sulla mappa",
     "body": "Con Event Planner disegni l'area del tuo evento su una mappa reale.\n\nStrutture, percorsi, ristori, spazi sponsor e postazioni dello staff restano in scala e condivisi con il team.\n\nScopri come funziona guardando il nostro video dimostrativo.",
     "benefits": ["Mappa reale con strutture e percorsi in scala", "Postazioni dello staff e dei volontari sulla mappa", "Progetto condiviso con tutto il team"],
     "mp4": "/media/event-planner-demo.mp4", "webm": "/media/event-planner-demo.webm", "poster": "/media/event-planner-demo-poster.jpg", "preview": "/media/brevo/event-planner-anteprima.jpg"},
    {"slug": "event-map", "order": 2, "status": "pubblicato", "name": "Event Map", "title": "EVENT MAP", "subtitle": "Il tuo percorso prende vita",
     "description": "Trasforma la traccia GPX della gara in un video animato con profilo altimetrico, distanza progressiva e logo dell'evento, pronto per i social.",
     "subject": "Event Map: il tuo percorso prende vita", "preheader": "Dalla traccia GPX a un video animato pronto per i social.",
     "headline": "Il tuo percorso prende vita",
     "body": "Con Event Map la traccia GPX della tua gara diventa un video animato.\n\nProfilo altimetrico, distanza progressiva, punti di ristoro e logo dell'evento, pronto da condividere sui social.\n\nScopri come funziona guardando il nostro video dimostrativo.",
     "benefits": ["Video animato dalla traccia GPX della gara", "Profilo altimetrico e distanza progressiva", "Logo dell'evento e formato pronto per i social"],
     "mp4": "/media/event-map-demo-gvt.mp4", "webm": None, "poster": "/media/event-map-demo-gvt-poster.jpg", "preview": "/media/brevo/event-map-anteprima.jpg"},
    {"slug": "eventi", "order": 3, "status": "bozza", "name": "Eventi", "title": "EVENTI", "subtitle": "Gestisci tutti i tuoi eventi",
     "description": "Crea e gestisci tutte le tue manifestazioni in un'unica piattaforma: dati dell'evento, pipeline delle attività con scadenze e briefing operativo sempre aggiornato.",
     "subject": "Organizza tutti i tuoi eventi con CRMEvent", "preheader": "Scopri come gestire le tue manifestazioni da un'unica piattaforma.",
     "headline": "Tutti i tuoi eventi, un'unica piattaforma",
     "body": "Organizzare un evento sportivo richiede tempo, coordinamento e attenzione ai dettagli.\n\nCon CRMEvent puoi raccogliere in un unico ambiente le informazioni e le attività necessarie per gestire le tue manifestazioni.\n\nScopri come funziona guardando il nostro video dimostrativo.",
     "benefits": ["Tutte le manifestazioni in un unico elenco, con date, città e fase", "Pipeline delle attività con scadenze calcolate sulla data dell'evento", "Briefing operativo con team, turni, percorsi e ospitalità"],
     "mp4": "/media/eventi-demo.mp4", "webm": None, "poster": "/media/eventi-demo-poster.jpg", "preview": "/media/brevo/eventi-anteprima.jpg"},
    {"slug": "staff-volontari", "order": 4, "status": "bozza", "name": "Staff e Volontari", "title": "STAFF E VOLONTARI", "subtitle": "Organizza staff e volontari",
     "description": "Raccogli le disponibilità con un modulo pubblico, organizza team, ruoli e mansioni e assegna le persone ai turni e alle postazioni dell'evento.",
     "subject": "Staff e volontari: organizza tutto con CRMEvent", "preheader": "Disponibilità, ruoli e assegnazioni in un'unica piattaforma.",
     "headline": "Le persone giuste, nel posto giusto",
     "body": "Gestire staff e volontari è una delle attività più impegnative nell'organizzazione di un evento sportivo.\n\nCon CRMEvent puoi raccogliere le disponibilità, organizzare i team e coordinare le assegnazioni, mantenendo tutte le informazioni a portata di mano.\n\nGuarda il video e scopri come semplificare il lavoro del tuo team.",
     "benefits": ["Modulo pubblico per raccogliere le disponibilità", "Team con responsabile, ruoli e mansioni", "Turni e postazioni, con i turni scoperti in evidenza"],
     "mp4": "/media/staff-volontari-demo.mp4", "webm": None, "poster": "/media/staff-volontari-demo-poster.jpg", "preview": "/media/brevo/staff-volontari-anteprima.jpg"},
    {"slug": "sponsor-partner", "order": 5, "status": "bozza", "name": "Sponsor e Partner", "title": "SPONSOR E PARTNER", "subtitle": "Gestisci sponsor e partner",
     "description": "Un'anagrafica unica di aziende, sponsor e partner con i loro referenti e una pipeline commerciale per fasi, con ogni trattativa collegata al suo evento.",
     "subject": "Sponsor e partner: gestisci ogni collaborazione con CRMEvent", "preheader": "Contatti, attività e collaborazioni sempre sotto controllo.",
     "headline": "Ogni collaborazione sotto controllo",
     "body": "Gli sponsor e i partner contribuiscono alla crescita di ogni evento sportivo.\n\nCon CRMEvent puoi organizzare i contatti, seguire le attività commerciali e gestire le informazioni relative alle collaborazioni in un unico ambiente.\n\nScopri come funziona guardando il video dimostrativo.",
     "benefits": ["Anagrafica unica di aziende, sponsor e partner con referenti", "Pipeline commerciale per fasi, con valore e importo confermato", "Ogni trattativa collegata al suo evento"],
     "mp4": "/media/sponsor-partner-demo.mp4", "webm": None, "poster": "/media/sponsor-partner-demo-poster.jpg", "preview": "/media/brevo/sponsor-partner-anteprima.jpg"},
]


class PromoIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=1500)
    subject: str = Field(min_length=1, max_length=200)
    preheader: str = Field(default="", max_length=250)
    headline: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=4000)
    benefits: List[str] = Field(default_factory=list, max_length=8)
    button_label: str = Field(default="GUARDA IL VIDEO", max_length=40)
    html_override: Optional[str] = Field(default=None, max_length=200000)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _pub(m):
    keys = ["slug", "order", "status", "name", "title", "subtitle", "description", "mp4", "webm", "poster", "preview"]
    return {k: m.get(k) for k in keys}


def render_html(m, site):
    """Newsletter a tabelle con CSS inline (Outlook/Gmail/Apple Mail), larghezza 600px, link assoluti, nessuno script."""
    if m.get("html_override"):
        return m["html_override"].replace("{{SITE}}", site)
    e = H.escape
    page = f"{site}/video/{m['slug']}"
    paras = "".join(f'<p style="margin:0 0 16px 0;font-size:16px;line-height:24px;color:#334155;">{e(p.strip())}</p>'
                    for p in (m.get("body") or "").split("\n\n") if p.strip())
    bens = "".join(f'<tr><td width="28" valign="top" style="padding:0 0 10px 0;font-size:16px;line-height:24px;color:#0ABAB5;font-weight:bold;">&#10003;</td>'
                   f'<td valign="top" style="padding:0 0 10px 0;font-size:15px;line-height:22px;color:#334155;">{e(b)}</td></tr>' for b in m.get("benefits") or [])
    btn = (lambda href, label, bg, fg: f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center"><tr><td align="center" bgcolor="{bg}" style="border-radius:999px;">'
           f'<!--[if mso]><v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" href="{href}" style="height:48px;v-text-anchor:middle;width:260px;" arcsize="50%" stroke="f" fillcolor="{bg}"><center style="color:{fg};font-family:Arial,sans-serif;font-size:15px;font-weight:bold;">{e(label)}</center></v:roundrect><![endif]-->'
           f'<!--[if !mso]><!--><a href="{href}" target="_blank" style="display:inline-block;padding:14px 34px;font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:bold;color:{fg};text-decoration:none;border-radius:999px;background:{bg};">{e(label)}</a><!--<![endif]--></td></tr></table>')
    return f"""<!DOCTYPE html>
<html lang="it" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="X-UA-Compatible" content="IE=edge">
<title>{e(m['subject'])}</title>
<style>@media only screen and (max-width:620px){{.wrap{{width:100%!important}}.px{{padding-left:20px!important;padding-right:20px!important}}h1{{font-size:26px!important;line-height:32px!important}}}}</style></head>
<body style="margin:0;padding:0;background:#f1f5f9;">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;color:#f1f5f9;">{e(m.get('preheader') or '')}&#8199;&#65279;&#847;&#8199;&#65279;&#847;&#8199;&#65279;&#847;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f1f5f9" style="background:#f1f5f9;"><tr><td align="center" style="padding:24px 10px;">
<table role="presentation" class="wrap" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background:#ffffff;border-radius:16px;font-family:Arial,Helvetica,sans-serif;">
<tr><td align="left" bgcolor="#0f172a" class="px" style="padding:24px 32px;border-radius:16px 16px 0 0;background:#0f172a;"><a href="{site}" target="_blank"><img src="{site}/logo-crmevent-dark.png" width="170" alt="CRMEvent" style="display:block;width:170px;height:auto;border:0;"></a></td></tr>
<tr><td class="px" style="padding:32px 32px 8px 32px;"><p style="margin:0 0 8px 0;font-size:13px;font-weight:bold;letter-spacing:1px;color:#088F8A;text-transform:uppercase;">{e(m['name'])}</p>
<h1 style="margin:0 0 20px 0;font-size:30px;line-height:36px;color:#0f172a;font-weight:bold;">{e(m.get('headline') or m['title'])}</h1>{paras}</td></tr>
<tr><td class="px" style="padding:8px 32px 8px 32px;"><a href="{page}" target="_blank" style="display:block;text-decoration:none;"><img src="{site}{m['preview']}" width="536" alt="{e(m['title'])} – guarda il video dimostrativo" style="display:block;width:100%;max-width:536px;height:auto;border:0;border-radius:12px;"></a></td></tr>
<tr><td class="px" align="center" style="padding:20px 32px 28px 32px;">{btn(page, m.get('button_label') or 'GUARDA IL VIDEO', '#0ABAB5', '#0f172a')}
<p style="margin:12px 0 0 0;font-size:13px;line-height:18px;color:#64748b;">oppure apri il video: <a href="{page}" target="_blank" style="color:#088F8A;">{e(page)}</a></p></td></tr>
<tr><td class="px" style="padding:0 32px 12px 32px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f8fafc;border-radius:12px;"><tr><td style="padding:22px 24px 12px 24px;">
<p style="margin:0 0 14px 0;font-size:16px;font-weight:bold;color:#0f172a;">Cosa puoi fare con CRMEvent</p><table role="presentation" cellpadding="0" cellspacing="0" border="0">{bens}</table></td></tr></table></td></tr>
<tr><td class="px" align="center" style="padding:24px 32px 32px 32px;">{btn(site, 'Scopri CRMEvent', '#0f172a', '#ffffff')}</td></tr>
<tr><td align="center" bgcolor="#0f172a" class="px" style="padding:24px 32px;border-radius:0 0 16px 16px;background:#0f172a;">
<p style="margin:0 0 6px 0;font-size:14px;font-weight:bold;color:#ffffff;">CRMEvent · Il CRM per gli eventi sportivi</p>
<p style="margin:0 0 10px 0;font-size:13px;"><a href="{site}" target="_blank" style="color:#5EEAD4;text-decoration:none;">www.crmevent.it</a></p>
<p style="margin:0;font-size:12px;line-height:18px;color:#94a3b8;">Hai ricevuto questa email perché sei iscritto alle comunicazioni CRMEvent.<br><a href="{{{{ unsubscribe }}}}" style="color:#94a3b8;">Annulla l'iscrizione</a></p></td></tr>
</table></td></tr></table></body></html>"""


def build(db, deps):
    sa_dep = deps["require_superadmin"]
    get_user = deps["get_current_user"]
    site_default = deps["site"]
    router = APIRouter(prefix="/api")

    async def ensure():
        await db.promo_materials.create_index("slug", unique=True)
        await db.promo_material_versions.create_index([("slug", 1), ("created_at", -1)])
        for d in DEFAULTS:
            await db.promo_materials.update_one({"slug": d["slug"]}, {"$setOnInsert": {**d, "id": uuid.uuid4().hex, "button_label": "GUARDA IL VIDEO", "html_override": None,
                                                                                   "version": 1, "created_at": _now(), "updated_at": _now()}}, upsert=True)

    async def _get(slug):
        m = await db.promo_materials.find_one({"slug": slug}, {"_id": 0})
        if not m:
            raise HTTPException(status_code=404, detail="Materiale non trovato")
        return m

    def _site(base):
        if base and re.fullmatch(r"https://[a-z0-9.-]+(:\d+)?", base):
            return base
        return site_default

    async def _is_sa(request):
        try:
            return (await get_user(request)).get("role") == "superadmin"
        except HTTPException:
            return False

    @router.get("/public/promo")
    async def public_list():
        rows = await db.promo_materials.find({"status": "pubblicato"}, {"_id": 0}).sort("order", 1).to_list(50)
        return [_pub(m) for m in rows]

    @router.get("/public/promo/{slug}")
    async def public_one(slug: str, request: Request):
        m = await db.promo_materials.find_one({"slug": slug}, {"_id": 0})
        if not m or (m.get("status") != "pubblicato" and not await _is_sa(request)):
            raise HTTPException(status_code=404, detail="Video non trovato")
        return _pub(m)

    @router.get("/promo-materials")
    async def admin_list(_: dict = Depends(sa_dep)):
        return await db.promo_materials.find({}, {"_id": 0}).sort("order", 1).to_list(50)

    @router.get("/promo-materials/{slug}/html")
    async def admin_html(slug: str, base: Optional[str] = Query(None), _: dict = Depends(sa_dep)):
        return {"html": render_html(await _get(slug), _site(base)), "site": _site(base)}

    async def _snapshot(m, user, reason):
        await db.promo_material_versions.insert_one({"id": uuid.uuid4().hex, "slug": m["slug"], "version": m.get("version", 1), "reason": reason,
                                                     "data": {k: m.get(k) for k in FIELDS + ["status"]}, "created_at": _now(),
                                                     "created_by": user.get("email")})

    @router.put("/promo-materials/{slug}")
    async def admin_update(slug: str, body: PromoIn, user: dict = Depends(sa_dep)):
        m = await _get(slug)
        await _snapshot(m, user, "modifica")
        data = body.model_dump()
        data["benefits"] = [b.strip() for b in data["benefits"] if b.strip()]
        data["html_override"] = (data.get("html_override") or "").strip() or None
        await db.promo_materials.update_one({"slug": slug}, {"$set": {**data, "updated_at": _now(), "updated_by": user.get("email")}, "$inc": {"version": 1}})
        return await _get(slug)

    @router.post("/promo-materials/{slug}/status")
    async def admin_status(slug: str, status: str = Query(..., pattern="^(bozza|pubblicato)$"), user: dict = Depends(sa_dep)):
        m = await _get(slug)
        if m.get("status") != status:
            await _snapshot(m, user, "stato")
            await db.promo_materials.update_one({"slug": slug}, {"$set": {"status": status, "updated_at": _now(), "updated_by": user.get("email")}, "$inc": {"version": 1}})
        return await _get(slug)

    @router.get("/promo-materials/{slug}/versions")
    async def admin_versions(slug: str, _: dict = Depends(sa_dep)):
        await _get(slug)
        return await db.promo_material_versions.find({"slug": slug}, {"_id": 0}).sort("created_at", -1).to_list(100)

    @router.post("/promo-materials/{slug}/versions/{vid}/restore")
    async def admin_restore(slug: str, vid: str, user: dict = Depends(sa_dep)):
        m = await _get(slug)
        v = await db.promo_material_versions.find_one({"id": vid, "slug": slug}, {"_id": 0})
        if not v:
            raise HTTPException(status_code=404, detail="Versione non trovata")
        await _snapshot(m, user, "ripristino")
        await db.promo_materials.update_one({"slug": slug}, {"$set": {**{k: v["data"].get(k) for k in FIELDS}, "updated_at": _now(), "updated_by": user.get("email")}, "$inc": {"version": 1}})
        return await _get(slug)

    return {"router": router, "ensure": ensure}
