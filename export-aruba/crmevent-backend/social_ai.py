"""Isolated AI service for the CRMEvent Social Media Manager.

Kept completely separate from the support assistant (support_service.py).
Only this file talks to the LLM for Social content. It never touches the database.
Versione portabile: collegamento diretto alle API OpenAI (SDK ufficiale).
"""
import os
import json
import logging

from openai import AsyncOpenAI

logger = logging.getLogger("crmevent.social")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Editorial categories used across posts and plans.
CATEGORIES = [
    "problema_soluzione", "funzionalita_crmevent", "consigli_organizzatori",
    "gestione_staff_volontari", "sponsor", "organizzazione_evento", "briefing",
    "dietro_le_quinte", "novita_prodotto", "cta_demo_prova", "educational", "countdown",
]

FORMATS = ["1:1", "4:5", "9:16"]

SYSTEM = (
    "Sei il Social Media Manager AI di CRMEvent, un CRM SaaS italiano per organizzatori di eventi "
    "(sportivi e non: running, trail, triathlon, nuoto, ciclismo, tennis, fiere, congressi, festival).\n"
    "Scrivi SEMPRE in italiano, con tono coerente al brand indicato. Crei contenuti per Instagram e "
    "altri social, concreti e specifici, MAI generici da 'software gestionale'.\n"
    "LINEE EDITORIALI PERMANENTI (applicale sempre):\n"
    "1. NON inventare dati sensibili, numeri, nomi di persone, email o telefoni. Usa solo le "
    "informazioni pubblicabili fornite nel CONTESTO.\n"
    "2. TESTO CREATIVITÀ: il campo 'title' è un HOOK di massimo 5-10 parole. Il campo 'body' è un "
    "SOTTOTITOLO OPZIONALE di UNA sola breve frase (può essere vuoto). NON scrivere paragrafi lunghi "
    "dentro l'immagine: tutto il resto va nella caption.\n"
    "3. CTA: varia le CTA tra i post, NON usare sempre la stessa. Alterna CTA commerciali e CTA di "
    "engagement in base al contenuto. Le CTA commerciali devono essere MINORITARIE rispetto ai "
    "contenuti educational/informativi. Quando non serve, lascia 'cta' vuota (\"\"). "
    "Esempi commerciali: 'Scopri CRMEvent su crmevent.it', 'Prova CRMEvent gratis per 14 giorni'. "
    "Esempi engagement: 'Salva questo post', 'Ti è mai successo?', 'Scrivicelo nei commenti', "
    "'Condividilo con il tuo team', 'Qual è la parte più difficile da gestire nel tuo evento?', "
    "'Come gestisci questa attività nel tuo evento?'.\n"
    "4. CAPTION naturali: scritte da chi conosce davvero l'organizzazione di eventi sportivi. Parti "
    "spesso da situazioni concrete (es. 'Chi ha l'elenco aggiornato dei volontari?', 'Il responsabile "
    "del ristoro ha ricevuto l'ultimo briefing?', 'Dove avevamo segnato l'hotel dello speaker?', "
    "'Lo sponsor aveva confermato il materiale?'). Evita linguaggio pubblicitario o tipico dei testi AI. "
    "Presenta CRMEvent come soluzione naturale al problema, senza trasformare ogni post in pubblicità.\n"
    "5. VARIETÀ: non usare sempre lo schema problema→CRMEvent→CTA. Alterna problemi reali, consigli "
    "pratici, checklist, domande alla community, errori frequenti, dietro le quinte, curiosità, mini "
    "tutorial, funzionalità CRMEvent, esempi di organizzazione, contenuti commerciali, aggiornamenti.\n"
    "6. VISUAL concreto: preferisci screenshot reali CRMEvent, mockup dell'interfaccia, foto di eventi, "
    "staff al lavoro, briefing, volontari, village/expo, materiali sponsor, mappe e percorsi. Evita "
    "immagini stock generiche.\n"
    "7. HASHTAG pertinenti allo specifico argomento, VARIATI tra i post; mantieni #CRMEvent quando "
    "opportuno, senza eccedere nel numero (5-8).\n"
    "8. Usa esempi reali di running, trail, triathlon, nuoto, ciclismo, tennis e altri eventi sportivi.\n"
    "Rispetta le indicazioni 'cosa evitare' e le istruzioni personalizzate del brand.\n"
    "Restituisci SOLO un oggetto JSON valido, senza testo aggiuntivo."
)


def _parse_json(text: str) -> dict:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if "```" in t[3:] else t.strip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    t = t.strip()
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1:
        t = t[start:end + 1]
    return json.loads(t)


async def _run(prompt: str) -> str:
    resp = await _client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content


def _brand_block(settings: dict) -> str:
    s = settings or {}
    def g(k, label):
        v = s.get(k)
        if isinstance(v, list):
            v = ", ".join([str(x) for x in v if x])
        return f"- {label}: {v}\n" if v else ""
    return (
        "BRAND / IMPOSTAZIONI SOCIAL:\n"
        + g("brand_name", "Brand/Evento")
        + g("description", "Descrizione")
        + g("website", "Sito web")
        + g("target", "Target")
        + g("tone_of_voice", "Tone of voice")
        + g("main_goal", "Obiettivo principale")
        + g("default_cta", "CTA predefinita")
        + g("main_hashtags", "Hashtag principali")
        + g("avoid_info", "COSE DA EVITARE (non usare)")
        + g("ai_instructions", "Istruzioni personalizzate")
    )


def _event_block(event_ctx: dict) -> str:
    if not event_ctx:
        return ""
    lines = ["CONTESTO EVENTO (solo dati pubblicabili — nessun dato personale):"]
    for k, label in [("nome", "Nome"), ("edizione", "Edizione"), ("tipologia", "Tipologia"),
                     ("data_inizio", "Data inizio"), ("data_fine", "Data fine"),
                     ("localita", "Località"), ("citta", "Città"), ("descrizione", "Descrizione"),
                     ("sito_web", "Sito web")]:
        if event_ctx.get(k):
            lines.append(f"- {label}: {event_ctx[k]}")
    if event_ctx.get("percorsi"):
        lines.append("- Percorsi: " + ", ".join(event_ctx["percorsi"]))
    if event_ctx.get("sponsor"):
        lines.append("- Sponsor/Partner: " + ", ".join(event_ctx["sponsor"]))
    if event_ctx.get("giorni_all_evento") is not None:
        lines.append(f"- Giorni all'evento: {event_ctx['giorni_all_evento']}")
    return "\n".join(lines) + "\n"


def _fallback_post(topic, category):
    return {
        "topic": topic or "CRMEvent per organizzatori di eventi",
        "title": "Organizza il tuo evento senza stress",
        "body": "Gestisci staff, volontari, sponsor e logistica in un unico posto con CRMEvent.",
        "caption": "Basta fogli Excel e messaggi persi: con CRMEvent coordini staff, volontari, turni e sponsor del tuo evento in un unico posto. 🎯 Prova la demo gratuita.",
        "cta": "Prova gratis 14 giorni",
        "hashtags": ["#CRMEvent", "#eventi", "#organizzazioneeventi", "#sport"],
        "image_suggestion": "Foto di uno staff evento coordinato dietro le quinte",
        "image_brief": "Grafica stile CRMEvent: sfondo bianco, headline nera con accenti Tiffany, logo CRMEvent in alto, screenshot reale del gestionale o mockup, CTA in basso.",
        "category": category or "funzionalita_crmevent",
        "format": "1:1",
        "suggested_time": "10:00",
    }


async def generate_post(settings: dict, event_ctx: dict = None, topic: str = None,
                        category: str = None, platform: str = "instagram",
                        extra: str = None) -> dict:
    """Generate a single social post. Returns a structured dict (never raises)."""
    if not _client:
        logger.warning("OPENAI_API_KEY mancante: Social AI in fallback")
        return _fallback_post(topic, category)
    prompt = (
        _brand_block(settings) + "\n" + _event_block(event_ctx)
        + f"\nCANALE: {platform}\n"
        + (f"ARGOMENTO RICHIESTO: {topic}\n" if topic else "")
        + (f"CATEGORIA RICHIESTA: {category}\n" if category else f"Scegli una categoria tra {CATEGORIES}.\n")
        + (f"ISTRUZIONI AGGIUNTIVE: {extra}\n" if extra else "")
        + "\nGenera UN post social completo seguendo le LINEE EDITORIALI. Restituisci SOLO JSON con questa struttura esatta:\n"
        + '{"topic": "argomento sintetico", '
        + '"title": "HOOK per la creativita: massimo 5-10 parole", '
        + '"body": "SOTTOTITOLO opzionale: UNA sola breve frase, oppure stringa vuota (NIENTE paragrafi)", '
        + '"caption": "caption Instagram naturale che parte da una situazione concreta", '
        + '"cta": "CTA adatta al contenuto (alterna commerciale/engagement); stringa vuota se non serve", '
        + '"hashtags": ["#..."], '
        + '"image_suggestion": "suggerimento visual CONCRETO (screenshot/mockup CRMEvent, foto evento/staff/volontari/briefing/sponsor/percorsi)", '
        + '"image_brief": "BRIEF GRAFICO in 1-2 frasi: quale immagine creare nello stile ufficiale CRMEvent (sfondo bianco, headline nera con accenti Tiffany, logo CRMEvent in alto, screenshot reale del gestionale oppure mockup laptop/telefono, CTA semplice in basso). Descrivi COSA mostrare, senza generare immagini.", '
        + f'"category": uno tra {CATEGORIES}, '
        + f'"format": uno tra {FORMATS}, '
        + '"suggested_time": "HH:MM"}'
    )
    try:
        data = _parse_json(await _run(prompt))
        if data.get("category") not in CATEGORIES:
            data["category"] = category if category in CATEGORIES else "funzionalita_crmevent"
        if data.get("format") not in FORMATS:
            data["format"] = "1:1"
        hs = data.get("hashtags") or []
        if isinstance(hs, str):
            hs = [h.strip() for h in hs.replace(",", " ").split() if h.strip()]
        data["hashtags"] = [h if h.startswith("#") else f"#{h}" for h in hs][:15]
        data.setdefault("image_brief", data.get("image_suggestion") or "")
        return data
    except Exception as e:  # noqa: BLE001
        logger.exception("Errore generate_post: %s", e)
        return _fallback_post(topic, category)


async def generate_plan(settings: dict, event_ctx: dict = None, goal: str = None,
                        count: int = 6, platform: str = "instagram") -> list:
    """Generate `count` varied post ideas for an editorial plan. Returns a list of dicts."""
    count = max(1, min(int(count or 6), 40))
    if not _client:
        return [_fallback_post(None, CATEGORIES[i % len(CATEGORIES)]) for i in range(count)]
    prompt = (
        _brand_block(settings) + "\n" + _event_block(event_ctx)
        + f"\nCANALE: {platform}\n"
        + (f"OBIETTIVO DELLA CAMPAGNA: {goal}\n" if goal else "")
        + f"\nGenera un piano editoriale di ESATTAMENTE {count} post DIVERSI tra loro, "
        + f"variando le categorie tra {CATEGORIES} ed evitando contenuti troppo simili.\n"
        + "LINEA EDITORIALE (non rigida): la maggioranza dei post deve essere educational/engagement/"
        + "problemi reali, alcuni dedicati alle funzionalità CRMEvent, e MASSIMO 2-3 direttamente "
        + "commerciali. Varia CTA (spesso engagement o nessuna), hashtag e schema narrativo tra i post.\n"
        + "Restituisci SOLO JSON con questa struttura esatta:\n"
        + '{"posts": [{"topic": "...", '
        + '"title": "HOOK max 5-10 parole", '
        + '"body": "SOTTOTITOLO opzionale di UNA frase o stringa vuota (NIENTE paragrafi)", '
        + '"caption": "caption naturale che parte da una situazione concreta", '
        + '"cta": "CTA variata; vuota se non serve", '
        + '"hashtags": ["#..."], '
        + '"image_suggestion": "visual concreto (screenshot/mockup CRMEvent, foto evento/staff/volontari/briefing/sponsor/percorsi)", '
        + '"image_brief": "BRIEF GRAFICO in 1-2 frasi: quale immagine creare nello stile ufficiale CRMEvent (sfondo bianco, headline nera con accenti Tiffany, logo in alto, screenshot reale o mockup, CTA in basso), senza generare immagini", '
        + f'"category": uno tra {CATEGORIES}, "format": uno tra {FORMATS}, "suggested_time": "HH:MM"}}]}}'
    )
    try:
        data = _parse_json(await _run(prompt))
        posts = data.get("posts") or []
        out = []
        for p in posts[:count]:
            if p.get("category") not in CATEGORIES:
                p["category"] = "funzionalita_crmevent"
            if p.get("format") not in FORMATS:
                p["format"] = "1:1"
            hs = p.get("hashtags") or []
            if isinstance(hs, str):
                hs = [h.strip() for h in hs.replace(",", " ").split() if h.strip()]
            p["hashtags"] = [h if h.startswith("#") else f"#{h}" for h in hs][:15]
            p.setdefault("image_brief", p.get("image_suggestion") or "")
            out.append(p)
        while len(out) < count:
            out.append(_fallback_post(None, CATEGORIES[len(out) % len(CATEGORIES)]))
        return out
    except Exception as e:  # noqa: BLE001
        logger.exception("Errore generate_plan: %s", e)
        return [_fallback_post(None, CATEGORIES[i % len(CATEGORIES)]) for i in range(count)]
