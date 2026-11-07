"""Calendario Eventi Italia — Fase 2: esiti verifica fonti, scaricamento e lettura feed autorizzati (CSV/XLSX/JSON/ICS)."""
import asyncio
import ipaddress
import json
import re
import socket
from datetime import date, timedelta
from urllib.parse import urlparse

import httpx

from iscritti import read_rows

VERIFICATA_IL = "2026-11-07"
_NO = "non_consentita"
# Esito della verifica di accesso (API, feed, export, robots.txt, condizioni d'uso) per le fonti richieste.
VERIFICHE = {
    "fidal": {"esito": _NO, "metodo": None, "evidenze": [
        "Nessuna API pubblica né feed/esportazione del calendario gare documentati.",
        "Il calendario è consultabile solo come pagina web (fidal.it/calendario.php); il portale calendario.fidal.it richiede credenziali.",
        "Nessuna licenza o autorizzazione al riutilizzo automatico dei dati pubblicata."],
        "come_sbloccare": "Richiedere a FIDAL un accordo scritto o un'esportazione/feed ufficiale."},
    "raceup": {"esito": _NO, "metodo": None, "evidenze": [
        "raceup.org è protetto da un controllo anti-bot (Cloudflare, HTTP 403): l'accesso automatico è bloccato.",
        "Nessuna API pubblica o feed del calendario documentati.",
        "Attenzione: raceup.it è un altro sito (team universitario di motorsport), non un calendario gare."],
        "come_sbloccare": "Richiedere al gestore un'API/feed ufficiale o un'autorizzazione scritta."},
    "wedosport": {"esito": _NO, "metodo": None, "evidenze": [
        "robots.txt vieta l'accesso alla cartella /restapi/.",
        "Nessuna API pubblica documentata; i termini e condizioni non concedono il riutilizzo automatico dei contenuti."],
        "come_sbloccare": "Richiedere a Wedosport l'accesso API o un accordo di riutilizzo dati."},
    "runningaround": {"esito": _NO, "metodo": None, "evidenze": [
        "robots.txt consente la scansione, ma consentire la scansione non equivale a un'autorizzazione al riutilizzo dei dati.",
        "Nessuna API, feed, esportazione o licenza di riutilizzo pubblicata; il sito espone solo informativa privacy."],
        "come_sbloccare": "Richiedere al gestore un'autorizzazione scritta o un feed dedicato."},
    "fitri": {"esito": _NO, "metodo": None, "evidenze": [
        "robots.txt vieta l'accesso alla cartella /api/.",
        "Nessuna API pubblica o open data del calendario gare; il calendario è consultabile solo via web."],
        "come_sbloccare": "Richiedere a FITRI un accordo scritto o un'esportazione ufficiale del calendario."},
    "myfitri": {"esito": _NO, "metodo": None, "evidenze": [
        "Piattaforma riservata a tesserati e società: accesso con credenziali.",
        "Le integrazioni esistenti (es. cronometristi) sono collegamenti privati, non API pubbliche."],
        "come_sbloccare": "Solo tramite accordo con FITRI."},
    "ironman": {"esito": _NO, "metodo": None, "evidenze": [
        "Le condizioni d'uso non sono accessibili in modo automatico (HTTP 403).",
        "robots.txt dichiara 'use=reference' e blocca diversi agenti automatici; nessuna API pubblica del calendario gare."],
        "come_sbloccare": "Richiedere a IRONMAN un'autorizzazione o un feed partner."},
    "manuale": {"esito": "consentita", "metodo": "Importazione Excel/CSV da parte del Super Admin", "evidenze": [], "come_sbloccare": None},
}
FORMATI = ["csv", "xlsx", "json", "ics"]
MAX_BYTES = 20 * 1024 * 1024
UA = "CRMEvent-CalendarioItalia/1.0 (sincronizzazione fonti autorizzate)"


def check_url(url: str) -> str:
    """Solo http/https verso host pubblici (blocca indirizzi interni)."""
    u = urlparse((url or "").strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("Indirizzo del feed non valido (serve http:// o https://)")
    try:
        addrs = {a[4][0] for a in socket.getaddrinfo(u.hostname, None)}
    except socket.gaierror as e:
        raise ValueError(f"Dominio non raggiungibile: {u.hostname}") from e
    for a in addrs:
        ip = ipaddress.ip_address(a)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("Indirizzi interni non ammessi")
    return url.strip()


async def fetch(url: str, attempts: int = 3) -> bytes:
    """Scarica il feed con nuovi tentativi (attese 5s, 20s)."""
    last = None
    for n in range(attempts):
        try:
            check_url(url)
            async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": UA}) as c:
                res = await c.get(url)
            if res.status_code >= 400:
                raise ValueError(f"La fonte ha risposto HTTP {res.status_code}")
            if len(res.content) > MAX_BYTES:
                raise ValueError("File del feed troppo grande (max 20 MB)")
            return res.content
        except Exception as e:  # noqa: BLE001
            last = e
            if n < attempts - 1:
                await asyncio.sleep(5 if n == 0 else 20)
    raise ValueError(f"Scaricamento non riuscito dopo {attempts} tentativi: {last}")


def _ics_date(v: str):
    m = re.match(r"(\d{4})(\d{2})(\d{2})", v.strip())
    return f"{m[1]}-{m[2]}-{m[3]}" if m else None


def _ics(text: str):
    text = re.sub(r"\r?\n[ \t]", "", text)
    out = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        p = {}
        for line in block.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                p.setdefault(k.split(";")[0].upper(), v.replace("\\,", ",").replace("\\n", " ").strip())
        end = _ics_date(p.get("DTEND", ""))
        if end and len(p.get("DTEND", "")) == 8:  # DTEND di giornata intera è esclusivo
            end = (date.fromisoformat(end) - timedelta(days=1)).isoformat()
        out.append({"nome": p.get("SUMMARY", ""), "data_inizio": _ics_date(p.get("DTSTART", "")), "data_fine": end,
                    "comune": p.get("LOCATION", ""), "sito_web": p.get("URL", ""), "note": p.get("DESCRIPTION", "")[:500], "ext_id": p.get("UID", "")})
    return out


def parse(content: bytes, fmt: str):
    """Ritorna (colonne, righe come liste)."""
    if fmt in ("csv", "xlsx"):
        return read_rows(content, fmt)
    if fmt == "json":
        data = json.loads(content.decode("utf-8-sig"))
        if isinstance(data, dict):
            data = next((v for k in ("events", "eventi", "data", "items", "results") if isinstance(v := data.get(k), list)), [])
        items = [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
    elif fmt == "ics":
        items = _ics(content.decode("utf-8", "ignore"))
    else:
        raise ValueError("Formato non supportato")
    cols = list(dict.fromkeys(k for x in items for k in x))
    return cols, [[("" if x.get(c) is None else str(x.get(c))) for c in cols] for x in items]
