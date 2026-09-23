# CRMEvent — PRD

## Problem Statement
CRMEvent (crmevent.it) — piattaforma operativa multi-evento per organizzatori, staff e volontari. Single-organization. Centralizza eventi, aziende, persone, sponsor/partner/fornitori/prospect, pipeline commerciale, staff, volontari, team, turni, presenze, mappe/percorsi, attività, follow-up. Accessi differenziati (admin CRM vs area personale staff/volontario). UI italiana, SaaS B2B, bianco + accento Tiffany RAL 6027 (#81D8D0).

## Architecture
- Backend: FastAPI + MongoDB. Route sotto /api. Auth unificata JWT email/password + Emergent Google login. RBAC: admin/member → CRM; staff/volunteer → solo /me/*. `require_admin` gate su tutte le CRUD admin, dashboard, search, settings. Object-check per area volontario.
- Integrazioni: Resend gestito (email invito/reset), Object storage Emergent (upload mappe), Google Calendar OAuth (per-utente, richiede secrets).
- Frontend: React + Tailwind + shadcn + recharts + sonner. Routing role-based (VolunteerLayout mobile-first per staff/volunteer). EntityManager generico con filtri + rowActions.
- Collections: users, user_sessions, password_reset_tokens, events, companies, persons, deals, staff(presence), teams, shifts, event_maps, activities, followups, files, calendar_connections, calendar_event_links, settings.

## User Personas
- Admin/Organizzatore (manara.michele.pro@gmail.com): gestione completa.
- Commerciale: aziende, pipeline sponsor/partner con importi e livelli.
- Staff/Volontario: area personale (i miei eventi, presenza, ruolo, team, turni, mappe, Google Calendar). Nessun accesso a dati commerciali/anagrafiche complete.

## Implemented
### 2026-06 (MVP)
- Auth JWT + Google, Dashboard KPI+grafici, CRUD Eventi/Aziende/Persone, Pipeline Kanban Sponsor&Partner, Staff, Attività, Follow-up, Impostazioni, ricerca globale, notifiche, demo data.
### 2026-06 (Update grande — verificato 51/51 backend + frontend)
- [x] FIX Tipologia dinamica da Impostazioni (e settori/ruoli/aree/livelli) — no liste hardcoded; usage-check prima dell'eliminazione; rename.
- [x] Eventi: date ufficiali + ora inizio/fine + descrizione; sync Google Calendar per evento.
- [x] Presenza Persona↔Evento con arrivo/partenza, area, ruolo, team, responsabile, punto ritrovo, luogo, stato (7 stati).
- [x] Team (con Team Leader) e Turni (turni scoperti = persona vuota).
- [x] Mappe & Percorsi per evento con upload immagine/PDF/file + Google Maps URL.
- [x] Area personale Staff/Volontario mobile-first: I miei eventi, scheda evento (presenza/ruolo/team/turni/colleghi/mappe), profilo, Google Calendar; isolamento dati (403/404).
- [x] Cambio password, password dimenticata/reset (email Resend), invito Persona → account collegato (stati invito), abilita/disabilita accesso.
- [x] Google Calendar OAuth (connect/select/disconnect, sync eventi e turni senza duplicati via calendar_event_links) — richiede secrets.
- [x] Reset database operativo (endpoint + pulsante Impostazioni) con disabilitazione seed demo — NON ancora eseguito (su richiesta dopo validazione).

### 2026-06 (Unificazione anagrafiche + Rebranding CRMEvent — verificato 61/61 backend + frontend E2E)
- [x] REBRANDING ufficiale a **CRMEvent** (CRM maiuscolo, Event con E maiuscola) in tutte le parti visibili: landing, login, sidebar, email (Resend), prefisso eventi Google Calendar ("CRMEvent · ..."), SEO title/description/OG, manifest/PWA, alt logo. Domini/URL/email restano minuscoli (crmevent.emergent.host). Naming tecnico invariato.
- [x] Loghi: landing/sidebar/header = logo completo (bianco), login = logo completo fondo nero (logo-crmevent-dark.png), favicon/sidebar chiusa = solo icona.
- [x] UNIFICAZIONE Persone: rimossa voce sidebar "Staff & Volontari". Sezione unica **Persone** con viste a tab (Tutte, Referenti, Staff, Volontari, Team, Turni) come filtri/relazioni della stessa anagrafica (GET /api/persons-enriched con flag is_referente/is_staff/is_volontario, aziende_nomi, eventi_count).
- [x] Scheda Persona (PersonDetailDialog) con tab Anagrafica/Aziende/Eventi/Ruoli/Team/Turni/Attività/Accesso; associazione Persona↔Evento (staff/volontario/collaboratore) dal tab Eventi. Ruolo dipende dalla relazione, non dall'anagrafica.
- [x] Anagrafica Persona estesa: email secondaria, cellulare, data nascita, indirizzo/CAP/provincia/regione/nazione, LinkedIn, tag, foto.
- [x] Relazione molti-a-molti Persona↔Azienda (collection person_companies: qualifica, ruolo, referente_principale). Migrazione idempotente da person.azienda_id all'avvio.
- [x] UNIFICAZIONE Aziende: anagrafica unica; tipo (sponsor/partner/media/fornitore/prospect/istituzione/azienda) come caratteristica. Scheda Azienda (CompanyDetailDialog) con tab Anagrafica/Referenti/Eventi/Trattative/Sponsorship/Attività/Follow-up.
- [x] Referenti inline: creazione Azienda + N referenti in un'unica schermata (CompanyDialog); controllo duplicati via /api/persons-match (email/cellulare/nome+cognome) con "Collega persona esistente". Sponsor&Partner/Media leggono da Aziende + relazioni, nessuna anagrafica duplicata.
- Endpoints nuovi: GET /persons-enriched, POST /persons-match, GET /persons/{id}/detail, GET /companies/{id}/detail, GET/POST /companies/{id}/contacts, PUT/DELETE /company-contacts/{id}.

## Backlog (P1/P2)
- P1: Drag&drop reale nel Kanban; scheda dettaglio evento con tab dedicata.
- P2: Export CSV/PDF; calendario turni visuale; foto persona upload in anagrafica; notifiche email automatiche follow-up.

## Configurazioni esterne richieste dall'utente
- Google Cloud (Calendar API): GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET nei Secrets; redirect URI `<BACKEND_URL>/api/oauth/calendar/callback`.

## Next Tasks
- Eseguire il reset finale dopo validazione utente (azzera tutti i dati operativi, mantiene admin/config).
