"""Testi dei 4 promemoria Accessi e utilizzo (bozze Brevo, modificabili poi direttamente in Brevo)."""
from brevo_funnel import _shell, _p, _cta, _greeting, _closing

LABELS = {"inactive_1": "Inattivo · 1° promemoria", "inactive_2": "Inattivo · 2° promemoria",
          "never_1": "Mai entrato · 1° promemoria", "never_2": "Mai entrato · 2° promemoria"}

TEMPLATES = {
    "inactive_1": {"name": "CRMEvent · Accessi · Inattivo 1", "subject": "I tuoi eventi ti aspettano su CRMEvent",
                   "preview": "Riprendi da dove avevi lasciato."},
    "inactive_2": {"name": "CRMEvent · Accessi · Inattivo 2", "subject": "Ti aiutiamo a ripartire con CRMEvent?",
                   "preview": "Una demo o un supporto per tornare operativo in pochi minuti."},
    "never_1": {"name": "CRMEvent · Accessi · Mai entrato 1", "subject": "Il tuo spazio CRMEvent è pronto",
                "preview": "Accedi e inizia a organizzare il tuo primo evento."},
    "never_2": {"name": "CRMEvent · Accessi · Mai entrato 2", "subject": "Configuriamo insieme il tuo primo evento?",
                "preview": "Assistenza, demo e i primi passi su CRMEvent."},
}


def _body(step: str) -> str:
    if step == "inactive_1":
        return (_greeting() + _p("è da qualche giorno che non accedi a CRMEvent.")
                + _p("I tuoi eventi, le persone, lo staff e i volontari sono dove li hai lasciati: puoi continuare a "
                     "organizzare tutto da un'unica piattaforma, in qualsiasi momento.")
                + _cta("Torna su CRMEvent", "LOGIN_URL") + _closing())
    if step == "inactive_2":
        return (_greeting() + _p("ti ricordiamo cosa puoi fare con CRMEvent:")
                + _p("• eventi e fasi operative<br>• staff, volontari e team<br>• sponsor, aziende e pipeline<br>"
                     "• ospitalità, pasti e briefing")
                + _p("Se vuoi ripartire più velocemente possiamo mostrarti la piattaforma in una breve demo "
                     "oppure aiutarti con il supporto.")
                + _cta("Accedi a CRMEvent", "LOGIN_URL") + _cta("Prenota una demo", "DEMO_URL", primary=False) + _closing())
    if step == "never_1":
        return (_greeting() + _p("il tuo account CRMEvent è attivo ma non hai ancora effettuato il primo accesso.")
                + _p("Entra ora e inizia a organizzare il tuo primo evento: persone, staff, volontari e attività in un unico posto.")
                + _cta("Accedi a CRMEvent", "LOGIN_URL") + _closing())
    if step == "never_2":
        return (_greeting() + _p("non sei ancora entrato in CRMEvent: possiamo aiutarti a iniziare.")
                + _p("Per configurare il primo evento bastano pochi passi: crea l'evento, aggiungi staff e volontari, "
                     "organizza i team.")
                + _p("Se preferisci, ti mostriamo tutto in una breve demo oppure ti assistiamo nella configurazione.")
                + _cta("Inizia ora", "LOGIN_URL") + _cta("Richiedi una demo o assistenza", "DEMO_URL", primary=False) + _closing())
    raise ValueError(step)


def build_html(step: str, kind: str) -> str:
    return _shell(preview_text=TEMPLATES[step]["preview"], body_html=_body(step), unsub=True)
