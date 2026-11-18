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

    return {"router": r}


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
