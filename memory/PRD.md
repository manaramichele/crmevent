# CRMEvent — PRD

## Problem Statement
CRMEvent (crmevent.it) — CRM e gestionale multi-evento per organizzatori di eventi. Centralizza eventi, aziende, contatti, sponsor, partner, fornitori, prospect, staff, collaboratori, volontari, ruoli, attività, follow-up, pipeline commerciale e storico relazioni. Una stessa azienda/persona può collegarsi a più eventi con ruoli e stati diversi. UI italiana, SaaS B2B, bianco + accento Tiffany RAL 6027 (#81D8D0).

## Architecture
- Backend: FastAPI + MongoDB (motor). Tutte le route sotto /api. Auth unificata: JWT email/password (bcrypt, cookie httpOnly access_token) + Emergent Google Auth (session_token). Generic CRUD factory per 7 collezioni. Seed admin + seed demo idempotenti allo startup.
- Frontend: React (CRA/craco) + Tailwind + shadcn/ui + recharts + framer-motion + sonner. AuthContext, ProtectedRoute, Layout con sidebar collassabile + topbar (ricerca globale, notifiche, profilo). EntityManager generico (tabella + dialog CRUD).
- Collezioni: users, user_sessions, events, companies, persons, deals, staff, activities, followups, settings.

## User Personas
- Organizzatore/Event manager: gestisce eventi, staff, follow-up.
- Commerciale/Sponsorship: gestisce aziende, pipeline sponsor/partner, valori.
- Admin: manara.michele.pro@gmail.com (ruolo admin).

## Core Requirements (static)
- Multi-evento senza duplicazioni; relazioni evento-azienda (deals) ed evento-persona (staff).
- Pipeline commerciale con importi e stati (fasi: prospect→contattato→proposta_inviata→in_trattativa→confermato/perso).
- Dashboard con KPI eventi/CRM/commerciale/attività/staff + grafici + filtro per evento.
- Auth email/password + Google.

## Implemented (2026-06)
- [x] Auth JWT email/password + Emergent Google login (unified) — 2026-06
- [x] Dashboard con 21 KPI + grafico pipeline (bar) e relazioni per tipo (pie) + filtro evento
- [x] Eventi: CRUD completo con scheda ricca (edizione, tipologia, date, località, org, budget, stato)
- [x] Aziende: CRUD (settore, tipo azienda/prospect/fornitore)
- [x] Persone: CRUD con collegamento azienda
- [x] Sponsor & Partner: Kanban pipeline con cambio fase, importi, totali
- [x] Staff & Volontari: assegnazioni persona↔evento con categoria/ruolo/stato/turno (turni scoperti)
- [x] Attività: CRUD
- [x] Follow-up: CRUD con scadenza/priorità e coloring scaduti/oggi
- [x] Impostazioni: profilo + liste configurabili (tipologie evento, settori, ruoli staff)
- [x] Ricerca globale + notifiche follow-up
- [x] Dati demo precaricati (3 eventi, 8 aziende, 10 persone, 8 trattative, 5 staff, 3 attività, 4 follow-up)
- Verified: 29/29 backend tests pass; frontend core flows verified (testing agent iteration_1).

## Backlog (prioritized)
- P1: Scheda dettaglio evento con tab (relazioni, staff, pipeline, storico) su pagina dedicata.
- P1: Drag & drop reale nel Kanban pipeline.
- P1: Storico relazioni / timeline per azienda e persona.
- P2: Export CSV/PDF di eventi e pipeline.
- P2: Gestione turni avanzata con calendario e slot scoperti.
- P2: Ruoli/permessi utente (RBAC) e inviti team.
- P2: Reminder email automatici per follow-up in scadenza (Resend).

## Next Tasks
- Costruire pagina dettaglio evento con tabs.
- Aggiungere timeline storico relazioni.
