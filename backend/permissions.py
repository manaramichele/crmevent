"""Ruoli e permessi per organizzazione (membership). Logica pura, senza accesso al DB."""
from typing import Optional

SECTIONS = [
    ("dashboard", "Dashboard"), ("eventi", "Eventi"), ("staff", "Staff / Volontari"),
    ("aziende", "Aziende"), ("anagrafiche", "Anagrafiche"), ("ospitalita", "Ospitalità & Pasti"),
    ("sponsor", "Sponsor & Partner"), ("attivita", "Attività"), ("followup", "Follow-up"),
    ("briefing", "Briefing"), ("mappe", "Mappe / GPX"), ("pipeline", "Pipeline Evento"),
]
SECTION_KEYS = [k for k, _ in SECTIONS]
ACTIONS = ["view", "create", "edit", "delete"]
ACTION_LABELS = {"view": "Visualizza", "create": "Crea", "edit": "Modifica", "delete": "Elimina"}
ROLES = {"admin_org": "Admin Organizzatore", "user": "Utente", "collaboratore": "Collaboratore"}
COLLAB_HIDDEN = {"sponsor", "pipeline"}

METHOD_ACTION = {"GET": "view", "HEAD": "view", "POST": "create", "PUT": "edit", "PATCH": "edit", "DELETE": "delete"}

# (prefisso del path template senza /api, sezioni "a|b" | "*" (qualsiasi membro) | None (solo Admin), azione forzata)
# Il primo prefisso che corrisponde vince. Path non mappati => solo Admin Organizzatore (fail-closed).
ROUTE_RULES = [
    ("/events/{event_id}/activate", None, None),
    ("/events/{event_id}/checkout", None, None),
    ("/events/{event_id}/upgrade", None, None),
    ("/events/{event_id}/calendar-sync", "eventi", "edit"),
    ("/events/{event_id}/pipeline/activate", None, None),
    ("/events/{event_id}/pipeline/recalculate-deadlines", "pipeline", "edit"),
    ("/events/{event_id}/pipeline/keep-deadlines", "pipeline", "edit"),
    ("/events/{event_id}/pipeline", "pipeline", None),
    ("/pipeline/tasks/{task_id}/duplicate", "pipeline", "create"),
    ("/pipeline/", "pipeline", None),
    ("/events/{event_id}/briefing", "briefing", None),
    ("/briefing-versions", "briefing", None),
    ("/events/{event_id}/hospitality", "ospitalita", None),
    ("/hospitality", "ospitalita", None),
    ("/lodgings", "ospitalita", None),
    ("/meals", "ospitalita", None),
    ("/structures", "ospitalita", None),
    ("/events/{event_id}/availabilities/confirm-bulk", "staff", "edit"),
    ("/events/{event_id}/availability/link/deactivate", "staff", "edit"),
    ("/events/{event_id}/availabilit", "staff", None),
    ("/availabilities", "staff", None),
    ("/staff", "staff", None),
    ("/teams", "staff", None),
    ("/shifts", "staff", None),
    ("/brevo/availability-template-preview", "staff", "view"),
    ("/maps", "mappe", None),
    ("/events", "eventi", None),
    ("/companies", "aziende", None),
    ("/company-contacts", "aziende", None),
    ("/persons-match", "anagrafiche|staff", "view"),
    ("/persons/{person_id}/invite", "anagrafiche|staff", "edit"),
    ("/persons/{person_id}/access", "anagrafiche|staff", "edit"),
    ("/persons", "anagrafiche|staff", None),
    ("/deals", "sponsor", None),
    ("/activities/{rec_id}/calendar", "attivita", "edit"),
    ("/activities", "attivita", None),
    ("/followups/{rec_id}/calendar", "followup", "edit"),
    ("/followups", "followup", None),
    ("/dashboard", "dashboard", None),
    ("/search", "*", None),
    ("/notifications", "*", None),
    ("/my/", "*", None),
    ("/upload", "*", None),
    ("/calendar/feature", "*", None),
]
# Letture comuni a tutti i membri (liste di opzioni, saldo per i messaggi di creazione evento)
READ_ANY_EXACT = {"/settings", "/credits/balance", "/credits/services", "/events"}


def default_permissions(role: str) -> dict:
    if role == "collaboratore":
        return {"sections": {k: ([] if k in COLLAB_HIDDEN else ["view"]) for k in SECTION_KEYS}, "events": "all"}
    return {"sections": {k: list(ACTIONS) for k in SECTION_KEYS}, "events": "all"}


def normalize_permissions(raw: Optional[dict], role: str) -> dict:
    """Permessi salvati -> forma canonica. Vuoti/assenti => predefiniti del ruolo (compatibilità)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("sections"), dict):
        return default_permissions(role)
    secs = {}
    for k in SECTION_KEYS:
        acts = [a for a in ACTIONS if a in (raw["sections"].get(k) or [])]
        if acts and "view" not in acts:
            acts = ["view"] + acts
        secs[k] = acts
    ev = raw.get("events", "all")
    if ev != "all":
        ev = sorted({str(x) for x in (ev or []) if x})
    return {"sections": secs, "events": ev}


def effective(membership: dict) -> dict:
    role = (membership or {}).get("role") or "user"
    if role == "admin_org":
        return {"admin": True, "role": role}
    p = normalize_permissions((membership or {}).get("permissions"), role)
    return {"admin": False, "role": role, **p}


def route_rule(path: str, method: str):
    """-> (sezioni, azione). sezioni: tuple | "*" | None (solo Admin)."""
    action = METHOD_ACTION.get(method.upper(), "edit")
    if path in READ_ANY_EXACT and action == "view":
        return "*", action
    for prefix, secs, forced in ROUTE_RULES:
        if path == prefix or path.startswith(prefix if prefix.endswith("/") else prefix):
            if secs is None or secs == "*":
                return secs, forced or action
            return tuple(secs.split("|")), forced or action
    return None, action


def allows(perm: dict, sections, action: str) -> bool:
    if perm.get("admin"):
        return True
    if sections == "*":
        return True
    if not sections:
        return False
    return any(action in (perm.get("sections") or {}).get(s, []) for s in sections)
