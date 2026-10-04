"""Seed dei Modelli Pipeline (FASE 3).

Dati SOLO per il primo popolamento idempotente dei modelli gestibili dal Super Admin.
A runtime i modelli e le relative attività sono letti/scritti dal DB: modificando un
modello dal pannello Super Admin, questo file NON viene più usato per quel modello.

Ogni attività del modello:
  - titolo, descrizione, categoria (nome fra le 12 categorie standard)
  - giorni_offset: giorni relativi alla data evento (negativo = prima, 0 = giorno evento, positivo = dopo)
  - priorita: normale | importante | critica
  - crm_section (opzionale): collegamento futuro a una sezione CRMEvent (FASE 4)
"""

# Categorie standard della Pipeline (riferimento). Le attività dei modelli vengono
# distribuite in queste categorie; se mancano nell'evento vengono create.
STANDARD_CATEGORIES = [
    "Autorizzazioni", "Percorso", "Allestimenti", "Staff e volontari", "Sicurezza",
    "Iscrizioni", "Materiali", "Comunicazione", "Sponsor e partner", "Merchandising",
    "Logistica", "Post evento",
]


def _t(titolo, categoria, giorni_offset, priorita="normale", descrizione="", crm_section=None):
    return {"titolo": titolo, "categoria": categoria, "giorni_offset": giorni_offset,
            "priorita": priorita, "descrizione": descrizione, "crm_section": crm_section}


# ---------------------------------------------------------------------------
# MODELLO RUNNING — gare su strada, maratone, mezze maratone, corse podistiche
# ---------------------------------------------------------------------------
RUNNING_TASKS = [
    # Autorizzazioni
    _t("Richiesta autorizzazione Comune", "Autorizzazioni", -180, "critica"),
    _t("Domanda / autorizzazione Federazione", "Autorizzazioni", -150, "critica"),
    _t("Autorizzazione occupazione suolo pubblico", "Autorizzazioni", -120, "importante"),
    _t("Richiesta chiusura strade", "Autorizzazioni", -120, "critica"),
    _t("Coordinamento Polizia Municipale", "Autorizzazioni", -90, "importante"),
    _t("Eventuali autorizzazioni Questura", "Autorizzazioni", -90, "importante"),
    _t("Assicurazione RC evento", "Autorizzazioni", -120, "critica"),
    _t("Documentazione amministrativa", "Autorizzazioni", -60, "normale"),
    # Percorso
    _t("Definizione percorso", "Percorso", -150, "critica", crm_section="routes"),
    _t("Sopralluogo percorso", "Percorso", -120, "importante", crm_section="routes"),
    _t("Misurazione / certificazione percorso", "Percorso", -90, "importante", crm_section="routes"),
    _t("Tracciato GPX", "Percorso", -75, "normale", crm_section="routes"),
    _t("Piano chiusure strade", "Percorso", -75, "importante"),
    _t("Segnaletica percorso", "Percorso", -45, "importante"),
    _t("Transenne percorso", "Percorso", -30, "importante"),
    _t("Individuazione punti critici e incroci", "Percorso", -45, "critica"),
    _t("Moto e bikers di supporto", "Percorso", -30, "normale"),
    _t("Mezzi apripista / chiusura gara", "Percorso", -30, "importante"),
    # Allestimenti
    _t("Progettazione Village", "Allestimenti", -60, "importante"),
    _t("Allestimento area partenza", "Allestimenti", -30, "critica"),
    _t("Allestimento area arrivo", "Allestimenti", -30, "critica"),
    _t("Portale partenza", "Allestimenti", -14, "importante"),
    _t("Portale arrivo", "Allestimenti", -14, "importante"),
    _t("Palco premiazioni", "Allestimenti", -14, "normale"),
    _t("Gazebo e stand", "Allestimenti", -10, "normale"),
    _t("Bagni chimici", "Allestimenti", -30, "importante"),
    _t("Transenne village", "Allestimenti", -7, "importante"),
    _t("Impianto audio", "Allestimenti", -10, "importante"),
    _t("Energia elettrica e generatore", "Allestimenti", -10, "importante"),
    _t("Segnaletica village", "Allestimenti", -5, "normale"),
    # Staff e volontari
    _t("Definizione responsabili area", "Staff e volontari", -60, "importante"),
    _t("Reclutamento volontari", "Staff e volontari", -45, "critica", crm_section="volunteers"),
    _t("Assegnazione addetti percorso", "Staff e volontari", -14, "importante", crm_section="staff"),
    _t("Assegnazione addetti ristori", "Staff e volontari", -14, "normale", crm_section="staff"),
    _t("Addetti partenza e arrivo", "Staff e volontari", -10, "importante", crm_section="staff"),
    _t("Addetti Expo / Village", "Staff e volontari", -10, "normale", crm_section="staff"),
    _t("Speaker e DJ", "Staff e volontari", -21, "normale"),
    _t("Fotografi e video", "Staff e volontari", -21, "normale"),
    _t("Briefing generale staff", "Staff e volontari", -2, "critica", crm_section="briefing"),
    _t("Pianificazione turni", "Staff e volontari", -7, "importante"),
    # Sicurezza
    _t("Piano sanitario", "Sicurezza", -90, "critica"),
    _t("Ambulanze e mezzi di soccorso", "Sicurezza", -60, "critica"),
    _t("Medico di gara", "Sicurezza", -60, "importante"),
    _t("Defibrillatori (DAE)", "Sicurezza", -30, "importante"),
    _t("Piano di emergenza", "Sicurezza", -45, "critica"),
    _t("Sicurezza area evento", "Sicurezza", -30, "importante"),
    _t("Protezione Civile (se necessaria)", "Sicurezza", -45, "normale"),
    _t("Contatti emergenza", "Sicurezza", -14, "importante"),
    # Iscrizioni
    _t("Definizione quote", "Iscrizioni", -150, "normale"),
    _t("Regolamento gara", "Iscrizioni", -150, "importante"),
    _t("Setup piattaforma iscrizioni", "Iscrizioni", -140, "importante"),
    _t("Apertura iscrizioni", "Iscrizioni", -120, "importante"),
    _t("Chiusura iscrizioni", "Iscrizioni", -7, "importante"),
    _t("Controllo iscritti", "Iscrizioni", -5, "normale"),
    _t("Gestione cambi nominativi", "Iscrizioni", -3, "normale"),
    _t("Liste di partenza", "Iscrizioni", -3, "importante"),
    _t("Assegnazione pettorali", "Iscrizioni", -5, "importante"),
    # Materiali
    _t("Ordine pettorali e chip", "Materiali", -60, "critica"),
    _t("Ordine medaglie", "Materiali", -60, "importante"),
    _t("Pacchi gara", "Materiali", -45, "importante"),
    _t("Maglie e gadget", "Materiali", -45, "normale"),
    _t("Materiale ristori", "Materiali", -21, "importante"),
    _t("Cartellonistica", "Materiali", -21, "normale"),
    _t("Materiale staff", "Materiali", -14, "normale"),
    _t("Spille e nastri", "Materiali", -21, "normale"),
    _t("Sacche gara", "Materiali", -45, "normale"),
    # Comunicazione
    _t("Creazione pagina evento", "Comunicazione", -120, "normale"),
    _t("Aggiornamento sito", "Comunicazione", -90, "normale"),
    _t("Pubblicazione regolamento", "Comunicazione", -90, "normale"),
    _t("Pubblicazione percorso", "Comunicazione", -75, "normale"),
    _t("Piano social", "Comunicazione", -60, "normale"),
    _t("Newsletter partecipanti", "Comunicazione", -30, "normale"),
    _t("Comunicati stampa", "Comunicazione", -30, "normale"),
    _t("Informazioni logistiche partecipanti", "Comunicazione", -14, "importante"),
    _t("Programma evento", "Comunicazione", -14, "normale"),
    _t("Informazioni viabilità residenti", "Comunicazione", -10, "importante"),
    # Sponsor e partner
    _t("Ricerca sponsor", "Sponsor e partner", -150, "importante", crm_section="sponsors"),
    _t("Contratti sponsor", "Sponsor e partner", -90, "importante", crm_section="sponsors"),
    _t("Raccolta loghi sponsor", "Sponsor e partner", -45, "normale", crm_section="sponsors"),
    _t("Materiali sponsor", "Sponsor e partner", -30, "normale"),
    _t("Presenza Expo sponsor", "Sponsor e partner", -14, "normale"),
    _t("Banner e archi / gonfiabili", "Sponsor e partner", -10, "normale"),
    _t("Prodotti pacco gara sponsor", "Sponsor e partner", -30, "normale"),
    _t("Prodotti ristoro sponsor", "Sponsor e partner", -21, "normale"),
    _t("Attività sampling", "Sponsor e partner", -7, "normale"),
    _t("Verifica obblighi sponsor", "Sponsor e partner", -2, "importante", crm_section="sponsors"),
    _t("Report post evento sponsor", "Sponsor e partner", 15, "importante", crm_section="sponsors"),
    # Merchandising
    _t("Definizione prodotti merchandising", "Merchandising", -90, "normale"),
    _t("Definizione quantità merchandising", "Merchandising", -75, "normale"),
    _t("Ordine merchandising", "Merchandising", -60, "importante"),
    _t("Personalizzazione prodotti", "Merchandising", -45, "normale"),
    _t("Consegna merchandising", "Merchandising", -7, "normale"),
    _t("Gestione vendita / distribuzione", "Merchandising", -1, "normale"),
    # Logistica
    _t("Piano parcheggi", "Logistica", -30, "importante"),
    _t("Mezzi e furgoni", "Logistica", -21, "normale"),
    _t("Deposito materiali", "Logistica", -14, "importante"),
    _t("Piano carico / scarico", "Logistica", -7, "importante"),
    _t("Prenotazione hotel staff", "Logistica", -45, "normale"),
    _t("Gestione pasti staff", "Logistica", -14, "normale"),
    _t("Trasferimenti", "Logistica", -7, "normale"),
    _t("Allestimento magazzino", "Logistica", -5, "normale"),
    _t("Consegna materiali alle postazioni", "Logistica", -1, "importante"),
    # Post evento
    _t("Premiazioni", "Post evento", 0, "importante"),
    _t("Pubblicazione classifiche", "Post evento", 1, "critica"),
    _t("Comunicazione risultati", "Post evento", 1, "normale"),
    _t("Pubblicazione foto", "Post evento", 2, "normale"),
    _t("Ringraziamenti volontari", "Post evento", 3, "normale"),
    _t("Ringraziamenti sponsor", "Post evento", 3, "normale"),
    _t("Report sponsor", "Post evento", 15, "importante", crm_section="sponsors"),
    _t("Reso materiali", "Post evento", 5, "importante"),
    _t("Chiusura fornitori", "Post evento", 15, "normale"),
    _t("Controllo fatture", "Post evento", 20, "importante"),
    _t("Rendiconto finale", "Post evento", 30, "importante"),
    _t("Debrief organizzativo", "Post evento", 7, "normale"),
]


# ---------------------------------------------------------------------------
# MODELLO EVENTO GENERICO — struttura essenziale personalizzabile
# ---------------------------------------------------------------------------
GENERICO_TASKS = [
    # Autorizzazioni
    _t("Richiesta autorizzazioni", "Autorizzazioni", -90, "critica"),
    _t("Assicurazione evento", "Autorizzazioni", -75, "importante"),
    _t("Permessi occupazione spazi", "Autorizzazioni", -60, "importante"),
    # Luogo (categoria Percorso)
    _t("Selezione location", "Percorso", -120, "critica"),
    _t("Sopralluogo location", "Percorso", -90, "importante"),
    _t("Contratto location", "Percorso", -75, "importante"),
    # Allestimenti
    _t("Piano allestimento", "Allestimenti", -45, "importante"),
    _t("Palco e audio / video", "Allestimenti", -21, "importante"),
    _t("Energia elettrica", "Allestimenti", -14, "importante"),
    _t("Segnaletica", "Allestimenti", -10, "normale"),
    # Staff
    _t("Definizione organigramma staff", "Staff e volontari", -45, "importante", crm_section="staff"),
    _t("Reclutamento staff / volontari", "Staff e volontari", -30, "importante", crm_section="volunteers"),
    _t("Briefing staff", "Staff e volontari", -2, "importante", crm_section="briefing"),
    # Sicurezza
    _t("Piano sicurezza", "Sicurezza", -60, "critica"),
    _t("Piano sanitario / primo soccorso", "Sicurezza", -45, "critica"),
    _t("Piano emergenza", "Sicurezza", -30, "importante"),
    # Partecipanti / Iscrizioni
    _t("Apertura iscrizioni / registrazioni", "Iscrizioni", -60, "importante"),
    _t("Chiusura iscrizioni", "Iscrizioni", -7, "normale"),
    _t("Lista partecipanti", "Iscrizioni", -3, "normale"),
    # Comunicazione
    _t("Pagina / sito evento", "Comunicazione", -75, "normale"),
    _t("Piano comunicazione e social", "Comunicazione", -45, "normale"),
    _t("Programma evento", "Comunicazione", -14, "normale"),
    # Sponsor / Fornitori
    _t("Ricerca sponsor / partner", "Sponsor e partner", -90, "normale", crm_section="sponsors"),
    _t("Selezione fornitori", "Sponsor e partner", -60, "importante", crm_section="companies"),
    _t("Contratti fornitori", "Sponsor e partner", -45, "importante", crm_section="companies"),
    # Materiali
    _t("Ordine materiali", "Materiali", -45, "importante"),
    _t("Gadget / materiale partecipanti", "Materiali", -30, "normale"),
    # Logistica
    _t("Piano logistico", "Logistica", -30, "importante"),
    _t("Parcheggi e trasferimenti", "Logistica", -14, "normale"),
    # Post evento
    _t("Debrief e ringraziamenti", "Post evento", 3, "normale"),
    _t("Report e rendiconto", "Post evento", 15, "importante"),
    _t("Controllo fatture", "Post evento", 20, "normale"),
]


# Modelli iniziali: codice -> metadati + attività.
PIPELINE_TEMPLATES_SEED = [
    {"key": "running", "name": "Running", "order": 0,
     "description": "Pipeline completa per gare su strada, maratone, mezze maratone e corse podistiche.",
     "tasks": RUNNING_TASKS},
    {"key": "generico", "name": "Evento generico", "order": 1,
     "description": "Struttura essenziale personalizzabile per eventi non classificabili come Running.",
     "tasks": GENERICO_TASKS},
]
