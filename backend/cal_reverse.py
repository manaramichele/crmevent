"""Calendario Eventi Italia — Ricerca inversa: dai contatti Brevo agli eventi (Brave Search + lettura pagine pubbliche + estrazione IA verificata)."""
import asyncio
import json
import os
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import cal_feeds
from brevo_client import BrevoClient, BrevoError, BrevoNotConfigured

GENERIC = {"gmail.com", "googlemail.com", "outlook.com", "outlook.it", "hotmail.com", "hotmail.it", "live.com", "live.it", "msn.com", "yahoo.com",
           "yahoo.it", "icloud.com", "me.com", "libero.it", "virgilio.it", "tiscali.it", "alice.it", "tin.it", "fastwebnet.it", "email.it", "inwind.it",
           "aruba.it", "pec.it", "legalmail.it", "tim.it", "katamail.com", "proton.me", "protonmail.com", "gmx.com", "gmx.it", "teletu.it"}
ATTR_MAP = {"nome": ["NOME", "FIRSTNAME", "FIRST_NAME", "PRENOME"], "cognome": ["COGNOME", "LASTNAME", "LAST_NAME", "SURNAME"],
            "societa": ["ORGANIZZAZIONE", "SOCIETA", "SOCIETA_SPORTIVA", "COMPANY", "AZIENDA", "ORGANIZZATORE", "ASD", "ENTE", "RAGIONE_SOCIALE", "NOME_SOCIETA"],
            "sito": ["SITO", "SITO_WEB", "WEBSITE", "WEB", "URL"], "telefono": ["SMS", "TELEFONO", "PHONE", "CELLULARE", "TEL", "WHATSAPP"]}
MODEL = ("anthropic", "claude-opus-5-5")
UA = "Mozilla/5.0 (compatible; CRMEvent-Calendario/1.0; verifica eventi pubblici)"
STATI_RICERCA = ["da_analizzare", "in_corso", "eventi_trovati", "nessun_evento", "dati_insufficienti", "errore"]
SYSTEM = """Sei un analista che estrae manifestazioni sportive italiane SOLO dai testi forniti. Regole tassative:
- Considera solo running su strada (10 km, mezza maratona 21 km, maratona 42 km), trail e triathlon, in Italia, edizioni dal 2026 in poi.
- Non inventare nulla: ogni evento deve comparire esplicitamente in una pagina fornita. Se la data non è scritta, lascia data_inizio null.
- fonte_url deve essere esattamente uno degli URL [P..] forniti. estratto deve essere una frase COPIATA ALLA LETTERA (max 200 caratteri) da quella pagina che contiene nome e data.
- Il dominio email non prova l'identità dell'organizzatore: conferma l'organizzatore solo se una pagina lo indica chiaramente.
- Rispondi solo con JSON valido, senza testo prima o dopo."""
SCHEMA = """{"organizzatore_confermato": bool, "nome_organizzatore": str|null, "sito_ufficiale": str|null, "motivo": str,
"eventi": [{"nome": str, "disciplina": "running"|"trail"|"triathlon", "distanza": str|null, "data_inizio": "YYYY-MM-DD"|null, "data_fine": "YYYY-MM-DD"|null,
"comune": str|null, "provincia": str|null, "regione": str|null, "anno": int|null, "sito_ufficiale": str|null, "fonte_url": str, "estratto": str,
"stato_evento": "confermata"|"rinviata"|"annullata", "attendibilita": int (0-100)}]}"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _domain(email: str) -> Optional[str]:
    d = (email or "").split("@")[-1].strip().lower()
    return None if not d or d in GENERIC else d


def _text(html: str) -> str:
    t = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", html)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h\d|tr)>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    import html as _h
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", _h.unescape(t))).strip()


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


class ImportIn(BaseModel):
    list_ids: list[int] = Field(min_length=1)


class SearchIn(BaseModel):
    scope: str = "test"
    size: int = Field(50, ge=1, le=5000)
    contact_ids: Optional[list[str]] = None


class ReviewIn(BaseModel):
    action: str
    nome: Optional[str] = None
    data_inizio: Optional[str] = None
    data_fine: Optional[str] = None
    comune: Optional[str] = None
    distanza: Optional[str] = None
    disciplina: Optional[str] = None


class RvSettingsIn(BaseModel):
    aggiornamento_notturno: bool = True
    intervallo_giorni: int = Field(7, ge=1, le=90)
    max_per_notte: int = Field(50, ge=1, le=2000)
    cache_giorni: int = Field(3, ge=1, le=30)


def build(db, deps: dict):
    r = APIRouter()
    sa, audit, upsert_event, clean_event, org_by_name, history = (deps[k] for k in ("sa", "audit", "upsert_event", "clean_event", "org_by_name", "history"))
    state = {"task": None, "last_brave": 0.0}
    robots: dict = {}

    async def rv_settings() -> dict:
        s = (await db.cal_settings.find_one({"id": "main"}, {"_id": 0, "rv": 1}) or {}).get("rv") or {}
        return {**RvSettingsIn().model_dump(), **s}

    # ---------- importazione contatti (sola lettura su Brevo) ----------
    @r.get("/reverse/brevo/lists")
    async def brevo_lists(admin: dict = Depends(sa)):
        try:
            async with BrevoClient() as b:
                out, off = [], 0
                while True:
                    page = await b._req("GET", "/contacts/lists", params={"limit": 50, "offset": off})
                    out += page.get("lists") or []
                    off += 50
                    if off >= (page.get("count") or 0):
                        break
        except BrevoNotConfigured as e:
            raise HTTPException(status_code=400, detail="Brevo non configurato (BREVO_API_KEY mancante)") from e
        except BrevoError as e:
            raise HTTPException(status_code=502, detail=f"Brevo ha risposto {e.status}") from e
        return {"lists": [{"id": x["id"], "name": x.get("name"), "contatti": x.get("totalSubscribers") or x.get("uniqueSubscribers") or 0} for x in out]}

    def attr(a: dict, k: str) -> Optional[str]:
        up = {str(x).upper(): v for x, v in (a or {}).items()}
        return next((str(up[n]).strip() for n in ATTR_MAP[k] if up.get(n) not in (None, "")), None)

    @r.post("/reverse/import")
    async def import_contacts(body: ImportIn, admin: dict = Depends(sa)):
        res = {"letti": 0, "nuovi": 0, "aggiornati": 0}
        try:
            async with BrevoClient() as b:
                names = {x["id"]: x.get("name") for x in await b.lists()}
                for lid in body.list_ids:
                    off = 0
                    while True:
                        page = await b._req("GET", f"/contacts/lists/{lid}/contacts", params={"limit": 500, "offset": off})
                        rows = page.get("contacts") or []
                        for c in rows:
                            await save_contact(c, admin.get("email"), res)
                        off += 500
                        if not rows or off >= (page.get("count") or 0):
                            break
        except BrevoNotConfigured as e:
            raise HTTPException(status_code=400, detail="Brevo non configurato (BREVO_API_KEY mancante)") from e
        except BrevoError as e:
            raise HTTPException(status_code=502, detail=f"Brevo ha risposto {e.status}") from e
        sel = [{"id": i, "name": names.get(i)} for i in body.list_ids]
        await db.cal_settings.update_one({"id": "main"}, {"$set": {"rv_lists": sel, "rv_last_import": {"at": _now(), **res}}}, upsert=True)
        await audit(admin, "cal_rv_import", detail=f"liste {body.list_ids} · {res}")
        return {**res, "liste": sel}

    async def save_contact(c: dict, by: str, res: dict):
        email = (c.get("email") or "").strip().lower()
        if not email:
            return
        res["letti"] += 1
        a = c.get("attributes") or {}
        known = {v for vs in ATTR_MAP.values() for v in vs}
        extra = {k: v for k, v in a.items() if str(k).upper() not in known and v not in (None, "") and not isinstance(v, (dict, list))}
        doc = {"brevo_id": c.get("id"), "email": email, "nome": attr(a, "nome"), "cognome": attr(a, "cognome"), "societa": attr(a, "societa"),
               "sito": attr(a, "sito"), "telefono": attr(a, "telefono"), "attributi": dict(list(extra.items())[:30]), "list_ids": c.get("listIds") or [],
               "brevo_blacklisted": bool(c.get("emailBlacklisted")), "dominio": _domain(email), "updated_at": _now()}
        cur = await db.cal_rv_contacts.find_one({"$or": [{"brevo_id": c.get("id")}, {"email": email}]}, {"_id": 0, "id": 1})
        if cur:
            await db.cal_rv_contacts.update_one({"id": cur["id"]}, {"$set": doc})
            res["aggiornati"] += 1
        else:
            await db.cal_rv_contacts.insert_one({**doc, "id": uuid.uuid4().hex, "stato_ricerca": "da_analizzare", "eventi": [], "fonti": [],
                                                 "imported_at": _now(), "imported_by": by})
            res["nuovi"] += 1

    # ---------- ricerca web (Brave) e lettura pagine pubbliche, con cache ----------
    async def cached(kind: str, key: str, days: int, fn):
        hit = await db.cal_rv_cache.find_one({"kind": kind, "key": key, "expires_at": {"$gt": _now()}}, {"_id": 0})
        if hit:
            return hit["payload"]
        payload = await fn()
        await db.cal_rv_cache.update_one({"kind": kind, "key": key}, {"$set": {"payload": payload, "expires_at": (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()}}, upsert=True)
        return payload

    async def brave(q: str, days: int) -> list:
        key = os.environ.get("BRAVE_API_KEY")
        if not key:
            raise RuntimeError("Chiave Brave Search mancante (BRAVE_API_KEY)")

        async def call():
            async with httpx.AsyncClient(timeout=15) as c:
                for attempt in range(4):
                    wait = 1.1 - (time.monotonic() - state["last_brave"])
                    if wait > 0:
                        await asyncio.sleep(wait)
                    state["last_brave"] = time.monotonic()
                    res = await c.get("https://api.search.brave.com/res/v1/web/search", headers={"X-Subscription-Token": key, "Accept": "application/json"},
                                      params={"q": q, "country": "IT", "search_lang": "it", "count": 10, "result_filter": "web", "safesearch": "moderate"})
                    if res.status_code == 200:
                        return [{"url": x.get("url"), "titolo": x.get("title"), "descrizione": re.sub(r"<[^>]+>", "", x.get("description") or "")}
                                for x in (res.json().get("web") or {}).get("results") or []]
                    if res.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                        await asyncio.sleep(2 ** attempt + 1)
                        continue
                    raise RuntimeError(f"Brave Search ha risposto HTTP {res.status_code}")
            return []
        return await cached("brave", q, days, call)

    async def allowed(url: str) -> bool:
        u = urlparse(url)
        base = f"{u.scheme}://{u.netloc}"
        if base not in robots:
            rp = RobotFileParser()
            try:
                async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers={"User-Agent": UA}) as c:
                    res = await c.get(f"{base}/robots.txt")
                rp.parse(res.text.splitlines() if res.status_code == 200 else [])
            except Exception:  # noqa: BLE001
                rp.parse([])
            robots[base] = rp
        return robots[base].can_fetch("*", url)

    async def page(url: str, days: int) -> dict:
        async def call():
            if not await allowed(url):
                return {"esito": "bloccata da robots.txt", "testo": ""}
            nxt = url
            async with httpx.AsyncClient(timeout=15, follow_redirects=False, headers={"User-Agent": UA}) as c:
                for _ in range(5):
                    res = await c.get(cal_feeds.check_url(nxt))
                    if res.status_code not in (301, 302, 303, 307, 308):
                        break
                    nxt = str(res.next_request.url) if res.next_request else ""
            if res.status_code >= 400:
                return {"esito": f"HTTP {res.status_code}", "testo": ""}
            if "html" not in res.headers.get("content-type", "html"):
                return {"esito": "non è una pagina web", "testo": ""}
            return {"esito": "letta", "testo": _text(res.text[:1_500_000])[:20000]}
        try:
            return await cached("page", url, days, call)
        except Exception as e:  # noqa: BLE001
            return {"esito": f"non raggiungibile ({str(e)[:80]})", "testo": ""}

    async def extract(c: dict, snippets: list, pages: list) -> dict:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        blocks = "\n\n".join(f"[P{i + 1}] {p['url']}\n{p['testo'][:6000]}" for i, p in enumerate(pages))
        snip = "\n".join(f"- {s['titolo']} | {s['url']} | {s['descrizione'][:200]}" for s in snippets[:15])
        prompt = (f"Contatto: email={c['email']} · società={c.get('societa') or '-'} · sito={c.get('sito') or '-'} · nome={c.get('nome') or ''} {c.get('cognome') or ''}\n"
                  f"Oggi è {date.today().isoformat()}.\n\nRisultati di ricerca (solo orientamento, NON valgono come fonte):\n{snip}\n\nPagine lette:\n{blocks}\n\n"
                  f"Restituisci JSON con questo schema:\n{SCHEMA}")
        chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"cal-rv-{c['id']}-{uuid.uuid4().hex[:6]}", system_message=SYSTEM).with_model(*MODEL)
        out = await chat.send_message(UserMessage(text=prompt))
        m = re.search(r"\{.*\}", out if isinstance(out, str) else str(out), re.S)
        return json.loads(m.group(0)) if m else {"eventi": [], "organizzatore_confermato": False, "motivo": "Risposta non leggibile"}

    def verify(ev: dict, pages: dict, org_ok: bool) -> tuple:
        """Controlla la risposta IA contro i testi realmente letti. Ritorna (stato, attendibilita, note)."""
        txt = pages.get(ev.get("fonte_url") or "")
        if txt is None:
            return "da_verificare", 0, "La fonte indicata non è tra le pagine lette"
        found = _flat(ev.get("estratto"))[:120] in _flat(txt) if ev.get("estratto") else False
        try:
            di = date.fromisoformat(ev["data_inizio"]) if ev.get("data_inizio") else None
        except ValueError:
            di = None
        att = max(0, min(100, int(ev.get("attendibilita") or 0)))
        if not found:
            return "da_verificare", min(att, 40), "Estratto non trovato nel testo della fonte"
        if not di:
            return "data_da_confermare", att, "Data non indicata nella fonte"
        if di.year < 2026:
            return "da_verificare", min(att, 40), "Edizione precedente al 2026"
        if not org_ok:
            return "da_verificare", min(att, 60), "Organizzatore non confermato dalla fonte"
        return ("verificato" if att >= 70 else "da_verificare"), att, ""

    async def search_contact(cid: str, by: str):
        c = await db.cal_rv_contacts.find_one({"id": cid}, {"_id": 0})
        s = await rv_settings()
        name, dom = (c.get("societa") or "").strip(), c.get("dominio") or _domain("@" + (urlparse(c.get("sito") or "").netloc or ""))
        if c.get("sito") and not urlparse(c["sito"]).scheme:
            c["sito"] = "https://" + c["sito"]
        if not name and not dom and not c.get("sito"):
            await db.cal_rv_contacts.update_one({"id": cid}, {"$set": {"stato_ricerca": "dati_insufficienti", "last_search_at": _now(), "errore": None,
                                                                         "nota": "Email generica e nessun nome società: impossibile identificare l'organizzatore",
                                                                         "next_check_at": (datetime.now(timezone.utc) + timedelta(days=s["intervallo_giorni"] * 4)).isoformat()}})
            return
        await db.cal_rv_contacts.update_one({"id": cid}, {"$set": {"stato_ricerca": "in_corso"}})
        yr = date.today().year
        queries = []
        if dom:
            queries.append(f"site:{dom} gara {yr} OR {yr + 1}")
        if name:
            queries += [f"\"{name}\" gara corsa trail triathlon {yr}", f"\"{name}\" {yr + 1} manifestazione"]
        if not name and dom:
            queries.append(f"{dom} gara podistica")
        fonti, snippets = [], []
        for q in queries[:3]:
            rs = await brave(q, s["cache_giorni"])
            snippets += rs
            fonti.append({"tipo": "ricerca", "query": q, "risultati": len(rs)})
        urls = []
        for u in ([c["sito"]] if c.get("sito") else []) + ([f"https://{dom}"] if dom else []):
            urls.append(u)
        toks = [t for t in re.findall(r"\w{4,}", name.lower())][:4]
        for x in snippets:
            u = x.get("url") or ""
            hay = _flat(f"{x.get('titolo')} {x.get('descrizione')} {u}")
            if u and u not in urls and ((dom and dom in u) or (toks and sum(t in hay for t in toks) >= max(1, len(toks) // 2))):
                urls.append(u)
        pages = []
        for u in urls[:6]:
            p = await page(u, s["cache_giorni"])
            fonti.append({"tipo": "pagina", "url": u, "esito": p["esito"]})
            if p["testo"]:
                pages.append({"url": u, "testo": p["testo"]})
        if not pages:
            await db.cal_rv_contacts.update_one({"id": cid}, {"$set": {"stato_ricerca": "nessun_evento", "fonti": fonti, "last_search_at": _now(), "errore": None,
                                                                         "nota": "Nessuna pagina pubblica leggibile trovata",
                                                                         "next_check_at": (datetime.now(timezone.utc) + timedelta(days=s["intervallo_giorni"])).isoformat()}})
            return
        res = await extract(c, snippets, pages)
        texts = {p["url"]: p["testo"] for p in pages}
        org_ok = bool(res.get("organizzatore_confermato") and res.get("nome_organizzatore"))
        org_id = None
        if org_ok:
            org_id = await org_by_name(res["nome_organizzatore"], {"sito_web": res.get("sito_ufficiale"), "email": c["email"], "_source": "ricerca_brevo"}, by)
            await db.cal_organizers.update_one({"id": org_id}, {"$set": {"brevo_contact_id": c.get("brevo_id")}, "$addToSet": {"email_brevo": c["email"]}})
            if c.get("brevo_blacklisted"):
                await db.cal_organizers.update_one({"id": org_id, "privacy.status": {"$nin": ["disiscritto", "opposizione"]}},
                                                   {"$set": {"privacy.status": "disiscritto", "privacy.note": "Contatto disiscritto su Brevo"}})
        found = []
        for ev in (res.get("eventi") or [])[:20]:
            if not ev.get("nome") or ev.get("disciplina") not in ("running", "trail", "triathlon"):
                continue
            st, att, nota = verify(ev, texts, org_ok)
            found.append(await save_finding(c, org_id, res, ev, st, att, nota, by))
        await db.cal_rv_contacts.update_one({"id": cid}, {"$set": {
            "stato_ricerca": "eventi_trovati" if found else "nessun_evento", "fonti": fonti, "eventi": found, "organizer_id": org_id,
            "organizzatore_identificato": res.get("nome_organizzatore") if org_ok else None, "sito_ufficiale": res.get("sito_ufficiale"),
            "nota": res.get("motivo"), "last_search_at": _now(), "errore": None,
            "next_check_at": (datetime.now(timezone.utc) + timedelta(days=s["intervallo_giorni"])).isoformat()}})

    async def save_finding(c: dict, org_id: Optional[str], res: dict, ev: dict, st: str, att: int, nota: str, by: str) -> str:
        di = ev.get("data_inizio")
        anno = ev.get("anno") or (int(di[:4]) if di else None)
        key = f"{c['id']}:{_flat(ev['nome'])[:80]}:{anno}"
        cur = await db.cal_rv_findings.find_one({"key": key}, {"_id": 0})
        doc = {"key": key, "contact_id": c["id"], "email": c["email"], "organizer_id": org_id, "organizzatore": res.get("nome_organizzatore") or c.get("societa"),
               "nome": ev["nome"][:200], "disciplina": ev["disciplina"], "distanza": ev.get("distanza"), "data_inizio": di, "data_fine": ev.get("data_fine") or di,
               "comune": ev.get("comune"), "provincia": ev.get("provincia"), "regione": ev.get("regione"), "anno": anno,
               "sito_ufficiale": ev.get("sito_ufficiale") or res.get("sito_ufficiale"), "fonte_url": ev.get("fonte_url"), "estratto": (ev.get("estratto") or "")[:300],
               "stato_evento": ev.get("stato_evento") if ev.get("stato_evento") in ("confermata", "rinviata", "annullata") else "confermata",
               "attendibilita": att, "nota": nota, "verificato_il": _now()}
        if cur and cur.get("stato") in ("approvato", "scartato"):
            doc["stato"] = cur["stato"]  # decisione manuale: non sovrascrivere
        elif cur and cur.get("event_id") and st == "verificato" and (cur.get("data_inizio") != di):
            doc["stato"], doc["nota"] = "da_verificare", f"Data cambiata ({cur.get('data_inizio')} → {di}): verifica manuale"
        else:
            doc["stato"] = st
        fid = cur["id"] if cur else uuid.uuid4().hex
        await db.cal_rv_findings.update_one({"key": key}, {"$set": doc, "$setOnInsert": {"id": fid, "created_at": _now()}}, upsert=True)
        if doc["stato"] in ("verificato", "approvato"):
            await to_calendar(fid, by)
        elif cur and cur.get("event_id") and doc["stato"] == "da_verificare":
            await db.cal_events.update_one({"id": cur["event_id"]}, {"$set": {"data_da_verificare": True}})
        return fid

    async def to_calendar(fid: str, by: str) -> Optional[str]:
        f = await db.cal_rv_findings.find_one({"id": fid}, {"_id": 0})
        past = (f.get("data_fine") or f.get("data_inizio") or "9999") < date.today().isoformat()
        stato = f["stato_evento"] if f["stato_evento"] != "confermata" else ("conclusa" if past else "confermata")
        d = clean_event({"nome": f["nome"], "disciplina": f["disciplina"], "distanza": f.get("distanza"), "anno": f.get("anno"), "data_inizio": f.get("data_inizio"),
                         "data_fine": f.get("data_fine"), "comune": f.get("comune"), "provincia": f.get("provincia"), "regione": f.get("regione"),
                         "sito_web": f.get("sito_ufficiale"), "stato": stato, "organizer_id": f.get("organizer_id"),
                         "organizzatore": None if f.get("organizer_id") else f.get("organizzatore")})
        res = await upsert_event(d, "ricerca_brevo", f.get("fonte_url"), f"rv:{f['key']}", by)
        ev = await db.cal_events.find_one({"id": res["id"]}, {"_id": 0})
        if ev and ev.get("stato") != stato and stato in ("rinviata", "annullata") and "stato" not in (ev.get("manual_fields") or []):
            await db.cal_events.update_one({"id": ev["id"]}, {"$set": {"stato": stato, "updated_at": _now()}})
            await history(ev["id"], "stato", ev.get("stato"), stato, "ricerca_brevo", "automatica", by)
        if ev and f.get("organizer_id") and not ev.get("organizer_id"):
            o = await db.cal_organizers.find_one({"id": f["organizer_id"]}, {"_id": 0, "nome": 1})
            await db.cal_events.update_one({"id": ev["id"]}, {"$set": {"organizer_id": f["organizer_id"], "organizzatore_nome": (o or {}).get("nome")}})
        await db.cal_rv_findings.update_one({"id": fid}, {"$set": {"event_id": res["id"]}})
        return res["id"]

    # ---------- elaborazione progressiva (job sospendibili) ----------
    async def run_job(jid: str):
        while True:
            j = await db.cal_rv_jobs.find_one({"id": jid}, {"_id": 0})
            if not j or j["status"] != "running":
                return
            if j["pos"] >= len(j["queue"]):
                await db.cal_rv_jobs.update_one({"id": jid}, {"$set": {"status": "completato", "finished_at": _now()}})
                return
            cid = j["queue"][j["pos"]]
            err = None
            try:
                await search_contact(cid, j["created_by"])
            except Exception as e:  # noqa: BLE001
                err = str(e)[:300]
                await db.cal_rv_contacts.update_one({"id": cid}, {"$set": {"stato_ricerca": "errore", "errore": err, "last_search_at": _now()}})
            await db.cal_rv_jobs.update_one({"id": jid}, {"$inc": {"pos": 1, "errori": 1 if err else 0}, "$set": {"updated_at": _now(), **({"ultimo_errore": err} if err else {})}})
            if err and "BRAVE_API_KEY" in err:
                await db.cal_rv_jobs.update_one({"id": jid}, {"$set": {"status": "sospeso", "motivo": err}})
                return

    def start(jid: str):
        state["task"] = asyncio.create_task(run_job(jid))

    async def active_job():
        return await db.cal_rv_jobs.find_one({"status": "running"}, {"_id": 0, "queue": 0})

    async def new_job(kind: str, ids: list, by: str) -> dict:
        if await active_job():
            raise HTTPException(status_code=409, detail="C'è già un'elaborazione in corso: sospendila o attendi la fine")
        if not ids:
            raise HTTPException(status_code=400, detail="Nessun contatto da elaborare")
        jid = uuid.uuid4().hex
        await db.cal_rv_jobs.insert_one({"id": jid, "kind": kind, "queue": ids, "pos": 0, "total": len(ids), "errori": 0, "status": "running",
                                         "created_by": by, "created_at": _now()})
        start(jid)
        return {"job_id": jid, "contatti": len(ids)}

    def informative(c: dict) -> int:
        return (2 if c.get("societa") else 0) + (1 if c.get("dominio") or c.get("sito") else 0)

    @r.post("/reverse/search")
    async def search(body: SearchIn, admin: dict = Depends(sa)):
        if body.scope not in ("test", "gruppo", "tutti", "selezione"):
            raise HTTPException(status_code=400, detail="Ambito non valido")
        test_done = await db.cal_rv_jobs.find_one({"kind": "test", "status": "completato"})
        if body.scope in ("gruppo", "tutti") and not test_done:
            raise HTTPException(status_code=400, detail="Esegui e controlla prima il test su 20 contatti")
        if body.scope == "selezione":
            ids = body.contact_ids or []
        else:
            pend = await db.cal_rv_contacts.find({"stato_ricerca": "da_analizzare"}, {"_id": 0, "id": 1, "societa": 1, "dominio": 1, "sito": 1}).to_list(200000)
            if body.scope == "test":
                pend = sorted(pend, key=lambda c: -informative(c))[:20]
            elif body.scope == "gruppo":
                pend = pend[:body.size]
            ids = [c["id"] for c in pend]
        out = await new_job(body.scope if body.scope != "selezione" else "gruppo", ids, admin.get("email"))
        await audit(admin, "cal_rv_search", detail=f"{body.scope} · {len(ids)} contatti")
        return out

    @r.post("/reverse/update")
    async def update_dates(admin: dict = Depends(sa)):
        ids = [c["id"] for c in await db.cal_rv_contacts.find({"stato_ricerca": "eventi_trovati"}, {"_id": 0, "id": 1}).to_list(200000)]
        out = await new_job("aggiornamento", ids, admin.get("email"))
        await audit(admin, "cal_rv_update", detail=f"{len(ids)} contatti")
        return out

    @r.post("/reverse/jobs/{jid}/{action}")
    async def job_action(jid: str, action: str, admin: dict = Depends(sa)):
        j = await db.cal_rv_jobs.find_one({"id": jid}, {"_id": 0, "queue": 0})
        if not j or action not in ("pausa", "riprendi", "annulla"):
            raise HTTPException(status_code=400, detail="Operazione non valida")
        if action == "riprendi":
            if j["status"] != "sospeso":
                raise HTTPException(status_code=400, detail="L'elaborazione non è sospesa")
            if await active_job():
                raise HTTPException(status_code=409, detail="C'è già un'elaborazione in corso")
            await db.cal_rv_jobs.update_one({"id": jid}, {"$set": {"status": "running", "motivo": None}})
            start(jid)
        else:
            await db.cal_rv_jobs.update_one({"id": jid, "status": {"$in": ["running", "sospeso"]}},
                                            {"$set": {"status": "sospeso" if action == "pausa" else "annullato"}})
        return {"ok": True}

    async def nightly() -> dict:
        s = await rv_settings()
        if not s["aggiornamento_notturno"] or await active_job():
            return {"skipped": True}
        due = await db.cal_rv_contacts.find({"stato_ricerca": {"$in": ["eventi_trovati", "nessun_evento"]}, "next_check_at": {"$lte": _now()}},
                                            {"_id": 0, "id": 1}).sort("next_check_at", 1).limit(s["max_per_notte"]).to_list(s["max_per_notte"])
        if not due:
            return {"contatti": 0}
        return await new_job("notturno", [c["id"] for c in due], "aggiornamento notturno")

    # ---------- stato, tabelle, verifica risultati ----------
    @r.get("/reverse/status")
    async def status(admin: dict = Depends(sa)):
        cfg = await db.cal_settings.find_one({"id": "main"}, {"_id": 0, "rv_lists": 1, "rv_last_import": 1}) or {}
        by = {x["_id"]: x["n"] for x in await db.cal_rv_contacts.aggregate([{"$group": {"_id": "$stato_ricerca", "n": {"$sum": 1}}}]).to_list(20)}
        fs = {x["_id"]: x["n"] for x in await db.cal_rv_findings.aggregate([{"$group": {"_id": "$stato", "n": {"$sum": 1}}}]).to_list(20)}
        jobs = await db.cal_rv_jobs.find({}, {"_id": 0, "queue": 0}).sort("created_at", -1).to_list(10)
        return {"liste": cfg.get("rv_lists") or [], "ultima_importazione": cfg.get("rv_last_import"), "settings": await rv_settings(),
                "brave_configurato": bool(os.environ.get("BRAVE_API_KEY")),
                "test_completato": bool(await db.cal_rv_jobs.find_one({"kind": "test", "status": "completato"})),
                "kpi": {"totale_contatti": sum(by.values()), "analizzati": sum(v for k, v in by.items() if k not in ("da_analizzare", "in_corso")),
                        "organizzatori_identificati": await db.cal_rv_contacts.count_documents({"organizzatore_identificato": {"$nin": [None, ""]}}),
                        "eventi_trovati": sum(fs.values()), "eventi_verificati": fs.get("verificato", 0) + fs.get("approvato", 0),
                        "eventi_da_verificare": fs.get("da_verificare", 0) + fs.get("data_da_confermare", 0),
                        "senza_eventi": by.get("nessun_evento", 0) + by.get("dati_insufficienti", 0), "errori": by.get("errore", 0)},
                "per_stato": by, "jobs": jobs}

    @r.get("/reverse/contacts")
    async def contacts(admin: dict = Depends(sa), stato: str = "", q: str = "", page: int = 1, limit: int = 50):
        qq = {**({"stato_ricerca": stato} if stato else {})}
        if q:
            qq["$or"] = [{k: {"$regex": re.escape(q), "$options": "i"}} for k in ("email", "societa", "organizzatore_identificato")]
        limit = max(1, min(limit, 200))
        tot = await db.cal_rv_contacts.count_documents(qq)
        rows = await db.cal_rv_contacts.find(qq, {"_id": 0, "attributi": 0}).sort([("last_search_at", -1), ("email", 1)]).skip((max(page, 1) - 1) * limit).limit(limit).to_list(limit)
        fids = [f for c in rows for f in c.get("eventi") or []]
        fx = {f["id"]: f for f in await db.cal_rv_findings.find({"id": {"$in": fids}}, {"_id": 0, "id": 1, "nome": 1, "data_inizio": 1, "stato": 1, "event_id": 1}).to_list(5000)}
        return {"total": tot, "rows": [{**c, "eventi": [fx[f] for f in c.get("eventi") or [] if f in fx]} for c in rows]}

    @r.get("/reverse/findings")
    async def findings(admin: dict = Depends(sa), stato: str = "", contact_id: str = ""):
        qq = {**({"stato": {"$in": stato.split(",")}} if stato else {}), **({"contact_id": contact_id} if contact_id else {})}
        return {"rows": await db.cal_rv_findings.find(qq, {"_id": 0}).sort([("data_inizio", 1)]).to_list(2000)}

    @r.post("/reverse/findings/{fid}/review")
    async def review(fid: str, body: ReviewIn, admin: dict = Depends(sa)):
        f = await db.cal_rv_findings.find_one({"id": fid}, {"_id": 0})
        if not f or body.action not in ("approva", "scarta"):
            raise HTTPException(status_code=400, detail="Operazione non valida")
        if body.action == "scarta":
            await db.cal_rv_findings.update_one({"id": fid}, {"$set": {"stato": "scartato", "revisionato_da": admin.get("email"), "revisionato_il": _now()}})
            return {"ok": True}
        fix = {k: v for k, v in body.model_dump(exclude={"action"}).items() if v not in (None, "")}
        if not (fix.get("data_inizio") or f.get("data_inizio")):
            raise HTTPException(status_code=400, detail="Per approvare serve la data di inizio")
        if fix.get("data_inizio"):
            fix["anno"] = int(fix["data_inizio"][:4])
        if not f.get("organizer_id") and f.get("organizzatore"):
            fix["organizer_id"] = await org_by_name(f["organizzatore"], {"email": f["email"], "_source": "ricerca_brevo"}, admin.get("email"))
        await db.cal_rv_findings.update_one({"id": fid}, {"$set": {**fix, "stato": "approvato", "revisionato_da": admin.get("email"), "revisionato_il": _now()}})
        eid = await to_calendar(fid, admin.get("email"))
        if eid and ({"data_inizio", "data_fine"} & set(fix)):
            await db.cal_events.update_one({"id": eid}, {"$set": {k: fix[k] for k in ("data_inizio", "data_fine") if k in fix} | {"data_da_verificare": False, "data_confermata_manuale": True}})
        await audit(admin, "cal_rv_review", detail=f"{f['nome']} → approvato")
        return {"ok": True, "event_id": eid}

    @r.put("/reverse/settings")
    async def put_settings(body: RvSettingsIn, admin: dict = Depends(sa)):
        await db.cal_settings.update_one({"id": "main"}, {"$set": {"rv": body.model_dump()}}, upsert=True)
        await audit(admin, "cal_rv_settings", detail=str(body.model_dump()))
        return await rv_settings()

    async def ensure():
        await db.cal_rv_contacts.create_index("id", unique=True)
        await db.cal_rv_contacts.create_index("email")
        await db.cal_rv_contacts.create_index("brevo_id")
        await db.cal_rv_findings.create_index("key", unique=True)
        await db.cal_rv_cache.create_index([("kind", 1), ("key", 1)], unique=True)
        await db.cal_rv_jobs.update_many({"status": "running"}, {"$set": {"status": "sospeso", "motivo": "Riavvio del server: riprendi quando vuoi"}})
        await db.cal_rv_contacts.update_many({"stato_ricerca": "in_corso"}, {"$set": {"stato_ricerca": "da_analizzare"}})

    return {"router": r, "nightly": nightly, "ensure": ensure}
