"""Isolated AI service for the CRMEvent support assistant.

Provider/model are configurable via env so the AI backend can be swapped
without touching the rest of the support module.
Only this file talks to the LLM. It never touches the database.
"""
import os
import json
import logging
import uuid

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger("crmevent.support")

LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
PROVIDER = os.environ.get("SUPPORT_AI_PROVIDER", "openai")
MODEL = os.environ.get("SUPPORT_AI_MODEL", "gpt-5.4-mini")

CATEGORIES = ["eventi", "persone", "aziende", "sponsor", "partner", "fornitori", "staff",
              "volontari", "team", "turni", "attivita", "documenti", "briefing",
              "impostazioni", "account", "altro"]

SYSTEM = (
    "Sei \"Assistente CRMEvent\", l'assistente di supporto integrato in CRMEvent, "
    "un CRM SaaS B2B per organizzatori di eventi. Rispondi SEMPRE in italiano, in tono "
    "professionale e conciso, con passaggi numerati quando spieghi una procedura.\n"
    "REGOLE FONDAMENTALI:\n"
    "1. Rispondi ESCLUSIVAMENTE usando le informazioni presenti nella KNOWLEDGE BASE fornita.\n"
    "2. NON inventare funzionalità, passaggi o dati non presenti nella knowledge base.\n"
    "3. Se la knowledge base non contiene informazioni sufficienti, imposta \"answered\": false e "
    "spiega che non hai trovato una risposta sufficientemente precisa nella documentazione di CRMEvent.\n"
    "4. Rileva se l'utente sta chiedendo una funzionalità che potrebbe non esistere "
    "(es. 'posso duplicare un evento?', 'si può inviare un WhatsApp?'): in tal caso imposta "
    "\"is_feature_request\": true e sintetizza la funzionalità richiesta in \"feature_request_summary\".\n"
    "5. Il prodotto si chiama sempre 'CRMEvent'.\n"
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


async def _run(system: str, prompt: str) -> str:
    chat = LlmChat(api_key=LLM_KEY, session_id=uuid.uuid4().hex, system_message=system).with_model(PROVIDER, MODEL)
    return await chat.send_message(UserMessage(text=prompt))


async def answer_question(question: str, kb_context: str, page_context: str = None, history=None, role: str = "admin") -> dict:
    """Return {answer, answered, category, confidence, is_feature_request, feature_request_summary}."""
    role_labels = {"admin": "Organizzatore/Amministratore", "staff": "Staff", "volontario": "Volontario"}
    role_label = role_labels.get(role, "Organizzatore/Amministratore")
    admin_note = (
        "Poiché il ruolo è amministrativo, se nella KNOWLEDGE BASE è presente una procedura pertinente, "
        "considerala valida anche quando la domanda usa 'mio/miei/il mio' e imposta \"answered\": true.\n\n"
    ) if role == "admin" else ""
    fallback = {
        "answer": "Non ho trovato una risposta sufficientemente precisa nella documentazione di CRMEvent.",
        "answered": False, "category": "altro", "confidence": 0.0,
        "is_feature_request": False, "feature_request_summary": None,
    }
    if not LLM_KEY:
        logger.warning("EMERGENT_LLM_KEY mancante: assistente in fallback")
        return fallback
    hist_txt = ""
    if history:
        hist_txt = "\n".join([f"{h['role']}: {h['content']}" for h in history[-6:]])
    prompt = (
        f"RUOLO UTENTE AUTENTICATO: {role_label}.\n"
        + "Adatta la risposta ai permessi di questo ruolo. Se il ruolo è Staff o Volontario, NON descrivere "
        + "procedure amministrative (creare/modificare eventi, gestire anagrafiche persone/aziende, pipeline sponsor, "
        + "impostazioni, inviti): spiega invece cosa può fare dalla propria area personale. Se l'azione richiesta è "
        + "riservata all'organizzatore, indicalo gentilmente e suggerisci di contattare l'organizzatore o il Team Leader.\n\n"
        + admin_note
        + (f"CONTESTO PAGINA (sezione da cui l'utente scrive): {page_context}\n\n" if page_context else "")
        + (f"CRONOLOGIA CONVERSAZIONE:\n{hist_txt}\n\n" if hist_txt else "")
        + "KNOWLEDGE BASE (unica fonte consentita):\n"
        + (kb_context if kb_context else "(nessun contenuto pertinente trovato nella knowledge base)")
        + f"\n\nDOMANDA UTENTE:\n{question}\n\n"
        + "Rispondi con un JSON con questa struttura esatta:\n"
        + '{"answer": "testo della risposta in italiano", "answered": true/false, '
        + f'"category": uno tra {CATEGORIES}, '
        + '"confidence": numero tra 0 e 1, "is_feature_request": true/false, '
        + '"feature_request_summary": "sintesi breve della funzionalità richiesta oppure null"}'
    )
    try:
        raw = await _run(SYSTEM, prompt)
        data = _parse_json(raw)
        cat = data.get("category")
        if cat not in CATEGORIES:
            cat = "altro"
        try:
            conf = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        return {
            "answer": (data.get("answer") or fallback["answer"]).strip(),
            "answered": bool(data.get("answered", False)),
            "category": cat,
            "confidence": max(0.0, min(1.0, conf)),
            "is_feature_request": bool(data.get("is_feature_request", False)),
            "feature_request_summary": data.get("feature_request_summary") or None,
        }
    except Exception as e:  # noqa: BLE001
        logger.exception("Errore assistente AI: %s", e)
        return fallback


async def draft_faq(question: str, kb_context: str) -> dict:
    """Draft a FAQ (domanda/risposta/categoria/parole_chiave) for SuperAdmin approval."""
    result = {"domanda": question, "risposta": "", "categoria": "altro", "parole_chiave": []}
    if not LLM_KEY:
        return result
    prompt = (
        "Sulla base della knowledge base seguente, prepara una FAQ chiara per gli organizzatori di CRMEvent.\n\n"
        + "KNOWLEDGE BASE:\n" + (kb_context or "(vuota)")
        + f"\n\nDOMANDA RICORRENTE DEGLI UTENTI:\n{question}\n\n"
        + "Restituisci SOLO JSON con questa struttura:\n"
        + f'{{"domanda": "...", "risposta": "...", "categoria": uno tra {CATEGORIES}, "parole_chiave": ["...", "..."]}}'
    )
    try:
        data = _parse_json(await _run("Sei un redattore di documentazione per CRMEvent. Rispondi solo in JSON valido, in italiano.", prompt))
        cat = data.get("categoria")
        if cat not in CATEGORIES:
            cat = "altro"
        kw = data.get("parole_chiave") or []
        if isinstance(kw, str):
            kw = [k.strip() for k in kw.split(",") if k.strip()]
        return {"domanda": data.get("domanda") or question, "risposta": data.get("risposta") or "",
                "categoria": cat, "parole_chiave": kw}
    except Exception as e:  # noqa: BLE001
        logger.exception("Errore draft FAQ: %s", e)
        return result
