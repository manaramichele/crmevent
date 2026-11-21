"""Esportazione PDF degli elenchi Staff, Volontari e Team per l'evento selezionato."""
import io
import re
import unicodedata
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

ROME = ZoneInfo("Europe/Rome")
OPTIONAL = {"telefono": "Telefono", "team": "Team", "taglia": "Taglia", "disp_dal": "Disponibilità dal", "disp_al": "Disponibilità al"}
SECTIONS = {"staff": ("Elenco Staff", "Staff", ("staff", "collaboratore")), "volontari": ("Elenco Volontari", "Volontari", ("volontario",)),
            "team": ("Elenco Team", "Team", None)}
CAT_LABEL = {"staff": "Staff", "collaboratore": "Staff", "volontario": "Volontario", "da_classificare": "Da classificare"}
TIFFANY = "#0ABAB5"


class ExportIn(BaseModel):
    section: str
    evento_id: str
    person_ids: Optional[List[str]] = None
    team_ids: Optional[List[str]] = None
    columns: List[str] = []


class GroupsPdfIn(BaseModel):
    evento_id: Optional[str] = None
    gruppo: Optional[str] = None


def _d(s):
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return ""


def _fold(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _span(days):
    ok = sorted((d for d in days or [] if d.get("disponibile", True) and d.get("date")), key=lambda d: d["date"])
    if not ok:
        return "", ""
    a, b = ok[0], ok[-1]
    return (f"{_d(a['date'])} {a.get('dalle') or ''}".strip(), f"{_d(b['date'])} {b.get('alle') or ''}".strip())


def build(db, deps: dict):
    r = APIRouter(prefix="/api")

    async def _logo(ev, org_id):
        if ev.get("logo_url"):
            try:
                rec = await deps["resolve_attachment"](ev["logo_url"], org_id)
                if rec:
                    return (await deps["read_file_rec"](rec))[0]
            except Exception:
                pass
        try:
            with open(deps["fallback_logo"], "rb") as f:
                return f.read()
        except Exception:
            return None

    @r.post("/staff/export-pdf")
    async def export_pdf(body: ExportIn, user: dict = Depends(deps["require_admin"])):
        if body.section not in SECTIONS:
            raise HTTPException(status_code=400, detail="Sezione non valida")
        org = user["org_id"]
        ev = await db.events.find_one({"org_id": org, "id": body.evento_id}, {"_id": 0})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento non trovato")
        cols = [c for c in OPTIONAL if c in body.columns]
        title, slug, cats = SECTIONS[body.section]
        teams = {t["id"]: t for t in await db.teams.find({"org_id": org, "evento_id": ev["id"]}, {"_id": 0}).to_list(2000)}
        q = {"org_id": org, "evento_id": ev["id"]}
        if cats:
            q["categoria"] = {"$in": list(cats)}
        else:
            q["team_id"] = {"$in": [t for t in teams if not body.team_ids or t in body.team_ids]}
        if body.person_ids is not None:
            q["persona_id"] = {"$in": body.person_ids}
        links = await db.staff.find(q, {"_id": 0}).to_list(20000)
        pids = list({x["persona_id"] for x in links})
        persons = {p["id"]: p for p in await db.persons.find({"org_id": org, "id": {"$in": pids}, "archiviato": {"$ne": True}}, {"_id": 0}).to_list(20000)}
        avs = {a["persona_id"]: a for a in await db.availabilities.find({"org_id": org, "evento_id": ev["id"], "persona_id": {"$in": pids}}, {"_id": 0, "persona_id": 1, "days": 1}).to_list(20000)}

        def row(p, ls):
            mans = ", ".join(sorted({x.get("ruolo") for x in ls if x.get("ruolo")}))
            ruolo = mans or ", ".join(sorted({CAT_LABEL.get(x.get("categoria"), x.get("categoria") or "") for x in ls}))
            if any(teams.get(x.get("team_id"), {}).get("responsabile_id") == p["id"] for x in ls):
                ruolo = f"{ruolo} (Team Leader)" if ruolo else "Team Leader"
            dal, al = _span((avs.get(p["id"]) or {}).get("days"))
            extra = {"telefono": p.get("cellulare") or p.get("telefono") or "", "taglia": p.get("taglia") or "", "disp_dal": dal, "disp_al": al,
                     "team": ", ".join(sorted({teams[x["team_id"]]["nome"] for x in ls if x.get("team_id") in teams}))}
            return [p.get("cognome") or "", p.get("nome") or "", ruolo] + [extra[c] for c in cols]

        by_p = {}
        for x in links:
            if x["persona_id"] in persons:
                by_p.setdefault(x["persona_id"], []).append(x)
        key = lambda pid: (_fold(persons[pid].get("cognome")), _fold(persons[pid].get("nome")))  # noqa: E731
        groups = []
        if cats:
            groups.append((None, [row(persons[pid], by_p[pid]) for pid in sorted(by_p, key=key)]))
        else:
            for tid in sorted({x["team_id"] for x in links}, key=lambda t: _fold(teams[t].get("nome"))):
                members = [pid for pid in by_p if any(x.get("team_id") == tid for x in by_p[pid])]
                groups.append((teams[tid].get("nome") or "Team", [row(persons[pid], [x for x in by_p[pid] if x.get("team_id") == tid]) for pid in sorted(members, key=key)]))
        total = len(by_p)
        pdf = _render(title, ev, await _logo(ev, org), ["Cognome", "Nome", "Ruolo"] + [OPTIONAL[c] for c in cols], groups, total)
        name = re.sub(r"[^A-Za-z0-9]+", "", (ev.get("nome") or "Evento").title())[:40] or "Evento"
        fname = f"CRMEvent_{slug}_{name}_{datetime.now(ROME).strftime('%Y-%m-%d')}.pdf"
        return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{fname}"', "X-Export-Count": str(total)})

    @r.post("/staff/groups-pdf")
    async def groups_pdf(body: GroupsPdfIn, user: dict = Depends(deps["require_admin"])):
        """PDF dei Gruppi di appartenenza (uno o tutti), opzionalmente filtrato per evento. Niente telefono/email."""
        org = user["org_id"]
        ev = None
        if body.evento_id:
            ev = await db.events.find_one({"org_id": org, "id": body.evento_id}, {"_id": 0})
            if not ev:
                raise HTTPException(status_code=404, detail="Evento non trovato")
        pq = {"org_id": org, "archiviato": {"$ne": True}, "gruppo_appartenenza": body.gruppo or {"$nin": [None, ""]}}
        persons = {p["id"]: p for p in await db.persons.find(pq, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "taglia": 1, "gruppo_appartenenza": 1}).to_list(20000)}
        lq = {"org_id": org, "persona_id": {"$in": list(persons)}}
        if ev:
            lq["evento_id"] = ev["id"]
        links = await db.staff.find(lq, {"_id": 0, "persona_id": 1, "ruolo": 1, "preferenza": 1}).to_list(50000)
        avs = await db.availabilities.find(lq, {"_id": 0, "persona_id": 1, "preferenza_attivita": 1}).to_list(50000)
        if ev:
            keep = {x["persona_id"] for x in links} | {a["persona_id"] for a in avs}
            persons = {k: v for k, v in persons.items() if k in keep}
        mans, prefs = {}, {}
        for x in links:
            if x.get("ruolo"):
                mans.setdefault(x["persona_id"], set()).add(x["ruolo"])
            if x.get("preferenza"):
                prefs.setdefault(x["persona_id"], set()).add(x["preferenza"])
        for a in avs:
            if a.get("preferenza_attivita"):
                prefs.setdefault(a["persona_id"], set()).add(a["preferenza_attivita"])
        st = await db.settings.find_one({"id": org}, {"_id": 0, "taglie": 1}) or {}
        order = list(st.get("taglie") or [])
        groups = {}
        for p in persons.values():
            groups.setdefault(p["gruppo_appartenenza"], []).append(p)
        sections = []
        for g in sorted(groups, key=_fold):
            rows, sizes = [], {}
            for p in sorted(groups[g], key=lambda x: (_fold(x.get("cognome")), _fold(x.get("nome")))):
                m = ", ".join(sorted(mans.get(p["id"], [])))
                job = (m, False) if m else (("Preferenza: " + ", ".join(sorted(prefs[p["id"]])), True) if prefs.get(p["id"]) else ("", False))
                rows.append([p.get("cognome") or "", p.get("nome") or "", job, p.get("taglia") or ""])
                k = p.get("taglia") or "Non indicata"
                sizes[k] = sizes.get(k, 0) + 1
            sz = sorted(sizes.items(), key=lambda kv: (kv[0] == "Non indicata", order.index(kv[0]) if kv[0] in order else 999, kv[0]))
            sections.append((g, rows, sz))
        o = await db.organizations.find_one({"id": org}, {"_id": 0, "nome": 1}) or {}
        logo = await _logo(ev, org) if ev else await _logo({}, org)
        total = sum(len(s[1]) for s in sections)
        pdf = _render_groups(body.gruppo, ev, o.get("nome") or "", logo, sections, total)
        name = re.sub(r"[^A-Za-z0-9]+", "", body.gruppo or "TuttiIGruppi")[:40] or "Gruppo"
        fname = f"CRMEvent_Gruppo_{name}_{datetime.now(ROME).strftime('%Y-%m-%d')}.pdf"
        return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{fname}"', "X-Export-Count": str(total)})

    return {"router": r}


def _render_groups(single, ev, org_name, logo, sections, total):
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak

    ss = getSampleStyleSheet()
    W = A4[0] - 28 * mm
    cell = ss["BodyText"].clone("gcell", fontSize=9, leading=11)
    ital = cell.clone("gital", fontName="Helvetica-Oblique", textColor=colors.HexColor("#475569"))
    hcell = cell.clone("ghcell", textColor=colors.white, fontName="Helvetica-Bold")
    sub = ss["BodyText"].clone("gsub", fontSize=9, leading=12, textColor=colors.HexColor("#475569"))
    h1 = ss["Title"].clone("gh1", alignment=0, fontSize=17, leading=21, spaceAfter=2)
    gh = ss["Heading2"].clone("ggh", textColor=colors.HexColor("#0F172A"), spaceBefore=4, spaceAfter=4)
    gen = datetime.now(ROME).strftime("%d/%m/%Y %H:%M")
    ev_name = (ev or {}).get("nome") or "Tutti gli eventi"
    title = f"Gruppo: {single}" if single else "Gruppi di appartenenza"

    def footer(c, d):
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#64748B"))
        c.drawString(14 * mm, 8 * mm, f"CRMEvent · {title} · {ev_name} · generato il {gen}")
        c.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Pagina {d.page}")

    def table(rows):
        widths = [W * 0.27, W * 0.25, W * 0.36, W * 0.12]
        data = [[Paragraph(h, hcell) for h in ("Cognome", "Nome", "Mansione", "Taglia")]]
        for cg, nm, (job, is_pref), tg in rows:
            data.append([Paragraph(escape(cg or "—"), cell), Paragraph(escape(nm or "—"), cell),
                         Paragraph(escape(job or "—"), ital if is_pref else cell), Paragraph(escape(tg or "—"), cell)])
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(TIFFANY)), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
                               ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        return t

    def sizes_para(sz, n):
        txt = " · ".join(f"{escape(k)}: <b>{v}</b>" for k, v in sz) or "—"
        return Paragraph(f"<b>Riepilogo taglie</b> ({n} {'persona' if n == 1 else 'persone'}): {txt}", sub)

    info = [Paragraph(escape(title), h1), Paragraph(f"<b>{escape(ev_name)}</b>" + (f" · {escape(org_name)}" if org_name else ""), ss["BodyText"]),
            Paragraph(f"Generato il {gen} · <b>Persone: {total}</b>" + ("" if single else f" · Gruppi: {len(sections)}"), sub),
            Paragraph("<i>In corsivo: attività preferita indicata, quando non è ancora assegnata una mansione.</i>", sub)]
    story = []
    if logo:
        try:
            story.append(Table([[Image(io.BytesIO(logo), width=22 * mm, height=22 * mm, kind="proportional"), info]], colWidths=[26 * mm, W - 26 * mm],
                               style=[("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        except Exception:
            story += info
    else:
        story += info
    story.append(Spacer(1, 8))
    if not sections:
        story.append(Paragraph("Nessuna persona con gruppo di appartenenza per i filtri selezionati.", ss["BodyText"]))
    for i, (g, rows, sz) in enumerate(sections):
        if i and not single:
            story.append(PageBreak())
        if not single:
            story.append(Paragraph(f"{escape(g)} <font size=10 color='#64748B'>· {len(rows)} {'persona' if len(rows) == 1 else 'persone'}</font>", gh))
        story += [table(rows), Spacer(1, 6), sizes_para(sz, len(rows))]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=16 * mm, title=title, author="CRMEvent")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def _render(title, ev, logo, head, groups, total):
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    size = landscape(A4) if len(head) > 5 else A4
    W = size[0] - 28 * mm
    ss = getSampleStyleSheet()
    cell = ss["BodyText"].clone("cell", fontSize=8.5, leading=10.5)
    hcell = cell.clone("hcell", textColor=colors.white, fontName="Helvetica-Bold")
    gen = datetime.now(ROME).strftime("%d/%m/%Y %H:%M")

    class Numbered(rl_canvas.Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            n = len(self._pages)
            for st in self._pages:
                self.__dict__.update(st)
                self.setFont("Helvetica", 8)
                self.setFillColor(colors.HexColor("#64748B"))
                self.drawString(14 * mm, 8 * mm, f"CRMEvent · {title} · {ev.get('nome') or ''} · generato il {gen}")
                self.drawRightString(size[0] - 14 * mm, 8 * mm, f"Pagina {self._pageNumber} di {n}")
                super().showPage()
            super().save()

    weights = {"Cognome": 1.3, "Nome": 1.2, "Ruolo": 1.6, "Telefono": 1.1, "Team": 1.3, "Taglia": 0.6, "Disponibilità dal": 1.2, "Disponibilità al": 1.2}
    tw = sum(weights[h] for h in head)
    widths = [W * weights[h] / tw for h in head]

    def table(rows):
        data = [[Paragraph(escape(h), hcell) for h in head]] + [[Paragraph(escape(str(c or "—")), cell) for c in rw] for rw in rows]
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(TIFFANY)), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
                               ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        return t

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=size, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=16 * mm, title=f"{title} · {ev.get('nome') or ''}", author="CRMEvent")
    h1 = ss["Title"].clone("h1", alignment=0, fontSize=17, leading=21, spaceAfter=2)
    sub = ss["BodyText"].clone("sub", fontSize=9, leading=12, textColor=colors.HexColor("#475569"))
    info = [Paragraph(escape(title), h1), Paragraph(f"<b>{escape(ev.get('nome') or '')}</b>", ss["BodyText"])]
    if ev.get("descrizione"):
        info.append(Paragraph(escape(ev["descrizione"][:600]), sub))
    dates = " – ".join(x for x in (_d(ev.get("data_inizio") or ""), _d(ev.get("data_fine") or "")) if x)
    info.append(Paragraph(f"{'Evento: ' + dates + ' · ' if dates else ''}Generato il {gen} · <b>Persone esportate: {total}</b>", sub))
    story = []
    if logo:
        try:
            story.append(Table([[Image(io.BytesIO(logo), width=24 * mm, height=24 * mm, kind="proportional"), info]], colWidths=[28 * mm, W - 28 * mm],
                               style=[("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        except Exception:
            story += info
    else:
        story += info
    story.append(Spacer(1, 8))
    gh = ss["Heading3"].clone("gh", textColor=colors.HexColor("#0F172A"), spaceBefore=8, spaceAfter=4)
    if not any(rows for _, rows in groups):
        story.append(Paragraph("Nessuna persona corrisponde ai filtri selezionati.", ss["BodyText"]))
    for name, rows in groups:
        if name is None:
            story.append(table(rows))
        else:
            story.append(KeepTogether([Paragraph(f"{escape(name)} <font size=9 color='#64748B'>· {len(rows)} persone</font>", gh), table(rows)]))
    doc.build(story, canvasmaker=Numbered)
    return buf.getvalue()
