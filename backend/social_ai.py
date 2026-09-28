"""Isolated AI service for the CRMEvent Social Media Manager.

Kept completely separate from the support assistant (support_service.py).
Only this file talks to the LLM for Social content. It never touches the database.
Provider/model configurable via env; defaults to the same Emergent LLM key.
"""
import os
import json
import logging
import uuid

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger("crmevent.social")

LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
PROVIDER = os.environ.get("SOCIAL_AI_PROVIDER", "openai")
MODEL = os.environ.get("SOCIAL_AI_MODEL", "gpt-5.4-mini")

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
    "REGOLE FONDAMENTALI:\n"
    "1. Parla di problemi REALI dell'organizzazione di un evento (staff, volontari, turni, sponsor, "
    "partner, ospitalità, briefing, documenti, logistica) e mostra come CRMEvent li risolve.\n"
    "2. NON inventare dati sensibili, numeri, nomi di persone, email o telefoni. Usa solo le "
    "informazioni pubblicabili fornite nel CONTESTO.\n"
    "3. Le caption Instagram devono essere coinvolgenti, con eventuali emoji con misura, e una CTA chiara.\n"
    "4. Gli hashtag devono essere pertinenti al mondo eventi/sport italiano.\n"
    "5. Rispetta le indicazioni 'cosa evitare' e le istruzioni personalizzate del brand.\n"
    "6. Restituisci SOLO un oggetto JSON valido, senza testo aggiuntivo."
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
    chat = LlmChat(api_key=LLM_KEY, session_id=uuid.uuid4().hex, system_message=SYSTEM).with_model(PROVIDER, MODEL)
    return await chat.send_message(UserMessage(text=prompt))


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
        "category": category or "funzionalita_crmevent",
        "format": "1:1",
        "suggested_time": "10:00",
    }


async def generate_post(settings: dict, event_ctx: dict = None, topic: str = None,
                        category: str = None, platform: str = "instagram",
                        extra: str = None) -> dict:
    """Generate a single social post. Returns a structured dict (never raises)."""
    if not LLM_KEY:
        logger.warning("EMERGENT_LLM_KEY mancante: Social AI in fallback")
        return _fallback_post(topic, category)
    prompt = (
        _brand_block(settings) + "\n" + _event_block(event_ctx)
        + f"\nCANALE: {platform}\n"
        + (f"ARGOMENTO RICHIESTO: {topic}\n" if topic else "")
        + (f"CATEGORIA RICHIESTA: {category}\n" if category else f"Scegli una categoria tra {CATEGORIES}.\n")
        + (f"ISTRUZIONI AGGIUNTIVE: {extra}\n" if extra else "")
        + "\nGenera UN post social completo. Restituisci SOLO JSON con questa struttura esatta:\n"
        + '{"topic": "argomento sintetico", "title": "titolo per la creativita", '
        + '"body": "testo breve da inserire nella grafica", '
        + '"caption": "caption Instagram completa e coinvolgente", '
        + '"cta": "call to action", "hashtags": ["#..."], '
        + '"image_suggestion": "descrizione del tipo di immagine consigliata", '
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
        return data
    except Exception as e:  # noqa: BLE001
        logger.exception("Errore generate_post: %s", e)
        return _fallback_post(topic, category)


async def generate_plan(settings: dict, event_ctx: dict = None, goal: str = None,
                        count: int = 6, platform: str = "instagram") -> list:
    """Generate `count` varied post ideas for an editorial plan. Returns a list of dicts."""
    count = max(1, min(int(count or 6), 40))
    if not LLM_KEY:
        return [_fallback_post(None, CATEGORIES[i % len(CATEGORIES)]) for i in range(count)]
    prompt = (
        _brand_block(settings) + "\n" + _event_block(event_ctx)
        + f"\nCANALE: {platform}\n"
        + (f"OBIETTIVO DELLA CAMPAGNA: {goal}\n" if goal else "")
        + f"\nGenera un piano editoriale di ESATTAMENTE {count} post DIVERSI tra loro, "
        + f"variando le categorie tra {CATEGORIES} ed evitando contenuti troppo simili.\n"
        + "Restituisci SOLO JSON con questa struttura esatta:\n"
        + '{"posts": [{"topic": "...", "title": "...", "body": "...", "caption": "...", '
        + '"cta": "...", "hashtags": ["#..."], "image_suggestion": "...", '
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
            out.append(p)
        while len(out) < count:
            out.append(_fallback_post(None, CATEGORIES[len(out) % len(CATEGORIES)]))
        return out
    except Exception as e:  # noqa: BLE001
        logger.exception("Errore generate_plan: %s", e)
        return [_fallback_post(None, CATEGORIES[i % len(CATEGORIES)]) for i in range(count)]
