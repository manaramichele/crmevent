# CRMEvent — PRD

## Problem Statement
CRMEvent (crmevent.it) — piattaforma operativa multi-evento per organizzatori, staff e volontari. Single-organization. Centralizza eventi, aziende, persone, sponsor/partner/fornitori/prospect, pipeline commerciale, staff, volontari, team, turni, presenze, mappe/percorsi, attività, follow-up. Accessi differenziati (admin CRM vs area personale staff/volontario). UI italiana, SaaS B2B, bianco + accento Tiffany RAL 6027 (#81D8D0).

> **Stato 2026-06 (ultima sessione)**: Completati e testati in preview — (1) Dashboard membro non mostra più `da contattare` (solo stati operativi), (2) mittente invito `hello@crmevent.it` (fix override in backend/.env), (3) occhio password su `/invito` e `/attiva`, (4) Persone con tab "Referenti aziende" / "Staff & Volontari" (+sotto-filtri) / "Da classificare" (classificazione non distruttiva via flag `is_evento`). ⚠️ PRODUZIONE: il secret `EMAIL_FROM_ADDRESS` è ancora ≠ hello@crmevent.it (confermato dal deployer) → l'utente deve aggiornarlo nel pannello Secrets PRIMA/insieme al redeploy, altrimenti resta noreply.


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

### 2026-06 (Assistente Virtuale AI + Supporto — verificato 13/13 backend + frontend E2E)
- [x] Assistente chat "Chiedi a CRMEvent": pulsante flottante + pannello responsive (`SupportChat.jsx`, montato nel Layout CRM). Contesto pagina passato automaticamente all'AI. Feedback 👍/👎 sotto ogni risposta.
- [x] Servizio AI ISOLATO (`support_service.py`) provider-agnostic (env `SUPPORT_AI_PROVIDER`/`SUPPORT_AI_MODEL`), modello OpenAI **gpt-5.4-mini** via Emergent LLM key. Risponde SOLO dalla Knowledge Base (no allucinazioni); se non sa → `answered=false` + bottone "Invia richiesta al supporto" che genera ticket automatico con cronologia.
- [x] Rilevamento richieste di nuove funzionalità (`is_feature_request`) → raggruppamento per similarità parole chiave in `support_feature_requests` (stati Nuova→Completata/Scartata).
- [x] Area SuperAdmin (ruolo `admin`) → **Supporto** (`Support.jsx`, nav filtrata, `require_superadmin`): Conversazioni (filtri periodo/categoria/feedback/risolto + ricerca testo + dettaglio + risolvi), Knowledge Base (CRUD, stati Bozza/Pubblicato/Archiviato; solo Pubblicato usato dall'assistente), FAQ (+ "Genera FAQ" AI da approvare, mai pubblicata automaticamente), Richieste funzionalità, Insights (KPI, % utili/non utili, senza risposta, ticket, categorie, trend, domande frequenti; domande senza risposta e 👎 convertibili in KB/FAQ con un click).
- [x] Isolamento dati per utente: organizzatore `member` vede solo le proprie conversazioni (`/support/my-conversations`); aggregati e insights riservati al SuperAdmin. Campo `org_id` presente su tutte le strutture (predisposizione multi-tenant). Architettura predisposta a vector embeddings futuri (campo `embedding` su KB).
- Collezioni: support_conversations, support_messages, support_feedback, support_categories, support_knowledge_base, support_faq, support_tickets, support_feature_requests, support_feature_request_matches.
- Endpoint: POST /support/chat|feedback|ticket|faq/generate, GET /support/my-conversations|conversations|conversations/{id}|insights, PUT /support/conversations/{id}/resolve, CRUD /support-kb|support-faq|support-categories|support-feature-requests|support-tickets.

### 2026-06 (Assistente role-aware + KB area personale staff/volontari — verificato 9/10 backend + frontend, nuance admin poi corretta)
- [x] KB ampliata a ~37 voci pubblicate; nuove procedure per l'AREA PERSONALE (staff/volontario): i miei eventi, i miei turni (data/ora/luogo), team + Team Leader, briefing/info operative, mappe/percorsi/documenti, disponibilità/presenza (sola lettura), modifiche/comunicazioni turno (sola lettura), uso da smartphone, accesso/recupero password, sync Google Calendar.
- [x] Campo `ruoli` su ogni voce KB (es. "staff,volontario", "tutti"); voci senza `ruoli` = solo admin.
- [x] Assistente ROLE-AWARE: `_support_role` + `_kb_visible` filtrano la KB per ruolo; `answer_question(role)` adatta la risposta ai permessi. Volontario che chiede "come modifico il mio turno" riceve risposta di sola lettura ("gestito dall'organizzatore"), NON la procedura admin; "come creo un evento" → answered=false. Admin riceve le procedure complete.
- [x] Funzioni area personale non ancora esistenti NON inventate: create 4 richieste funzionalità (stato da_valutare): conferma disponibilità, check-in presenze, modifica turno, comunicazioni/messaggi con Team Leader.
- [x] Assistente montato anche nel portale volontari (`VolunteerLayout`, pulsante sopra la bottom-nav). Isolamento confermato: volontario 403 su conversations/insights, 200 solo su my-conversations.
- [x] Account volontario di test creato (`/app/scripts/seed_test_volunteer.py`) → vedi test_credentials.md.

### 2026-06 (Rifiniture UI + fix navigazione/Sponsor — verificato 6/6 backend + frontend)
- [x] Homepage: logo CRMEvent ingrandito (h-14 mobile / h-16 desktop); rimossa scritta "Software SaaS per la gestione eventi"; hero → "Organizza il tuo evento. Tutto in un'unica piattaforma."
- [x] Nome "CRMEvent" mostrato in grassetto nelle copy della landing (e già bold in titoli/loghi).
- [x] Loghi PNG ufficiali aggiornati: "Logo per fondo bianco" → logo-crmevent.png (aree chiare), "Logo per fondo nero" → logo-crmevent-dark.png (login/aree scure). Nessuna ricreazione via testo/SVG/CSS.
- [x] Navigazione: sidebar "Dashboard" → /app (dashboard app); click sul logo in alto a sinistra → homepage pubblica (/). Verificato da più sezioni.
- [x] Persone: ruolo per relazione Persona↔Evento con opzioni Referente/Staff/Collaboratore/Volontario/Team; stessa persona con ruoli diversi in eventi diversi senza duplicare l'anagrafica (una sola Persona in /persons).
- [x] FIX Sponsor: modale "Modifica trattativa" non più coperta dalla sidebar/colonne (Dialog z-[100]); tutti i campi accessibili su desktop/tablet/mobile.

## Next Tasks

### 2026-06 (Briefing Evento — verificato: backend 8/8 pytest 100%, frontend e2e ~100% dopo fix)
- [x] **Briefing Evento**: documento operativo aggregato per evento, accessibile da Eventi (icona `briefing-{id}`) alla rotta `/eventi/:id/briefing` (admin-only).
- [x] **BOZZA LIVE** (`GET /api/events/{id}/briefing-live`): aggregazione in SOLA LETTURA da collection esistenti (staff, teams, shifts, event_maps, lodgings, meals, deals) — NESSUNA duplicazione dati. Sezioni: Team&responsabili, Staff&volontari, Turni (scoperti evidenziati), Mappe, Ospitalità (costi redatti se non SuperAdmin), Sponsor&Partner, Timeline. Stats card (staff/volontari/team/turni/scoperti/mappe/sponsor/pernottamenti/pasti).
- [x] **Completezza Briefing %** con 8 check (date, località, staff, team con responsabile, turni coperti, mappe, volontari con referente, ospitalità) → warning con dettaglio per dati mancanti.
- [x] **Versioning & Snapshot** (collection `briefing_versions`): `POST /api/events/{id}/briefing-versions` congela snapshot JSON con versione incrementale + content_hash + published_by; `GET` lista (senza content), `GET /api/briefing-versions/{id}` snapshot completo, `DELETE` rimozione. UI Storico versioni + visualizzazione read-only snapshot con banner "torna alla bozza live".
- [x] **Rilevamento dati obsoleti**: `is_stale` true quando i dati live differiscono dall'ultima versione pubblicata → banner ambra "Pubblica una nuova versione".
- [x] **Presentation Mode** fullscreen (slide deck cover→panoramica→sezioni, nav prev/next/ESC).
- [x] **Export PDF lato client** via `window.print()` + print CSS A4 (nasconde chrome, mantiene logo/mappe/tabelle).
- [x] Fix z-index: `AlertDialog` overlay/content portati a z-[110] (sopra `Dialog` z-[100]) — la conferma eliminazione versione dentro il dialog Storico era bloccata dall'overlay.
- Note: `briefing_versions` aggiunta a OPERATIONAL (reset). Briefing non ancora esposto in area personale staff/volontari (scelta rimandata).

### 2026-06-26 (Super Admin navigation + active-org scoping — verificato: backend 13/13 pytest 100%, frontend e2e 100%)
- [x] Super Admin vede il menu operativo CRMEvent completo + gruppo separato "Amministrazione piattaforma" (Dashboard piattaforma, Lead, Supporto).
- [x] Selettore "Org attiva" in header: frontend invia header `X-Org-Id`; `require_admin` lo valida SOLO per superadmin (428 senza header, 404 org inesistente) e restituisce principal effimero con `org_id` → `oq()` mantiene lo scoping per organizzazione (nessun bypass multi-tenant).
- [x] `AdminOnly` consente superadmin (blocca solo volontari); `HomeRoute` porta il superadmin alla Dashboard operativa; `SuperAdminOnly` continua a proteggere /piattaforma, /lead, /supporto.
- [x] Organizzatore: vede solo il menu operativo, nessun gruppo piattaforma/selettore, bloccato (redirect + 403) da rotte/API superadmin.
- [x] Nessuna modifica a Stripe/FIC. File: server.py, frontend/src/{lib/api.js, context/AuthContext.js, components/Layout.jsx, App.js}.


## Backlog (P1/P2)
- IN ATTESA UTENTE: URL reali iubenda per Cookie/Privacy (l'utente fornirà i link definitivi).
- SOSPESO su richiesta utente: refactoring `server.py` (rimandato fino a stabilizzazione funzionalità pre-lancio).
- Audit Log estendibile: predisposto per registrare azioni future (modifica stato abbonamento, interventi su account cliente) tramite `AUDIT_ACTION_LABELS` + `record_audit()`.
- P1: Drag&drop reale nel Kanban; scheda dettaglio evento con tab dedicata; Briefing in area personale staff/volontari (vista read-only per ruolo).
- P1: Cascade delete `briefing_versions` (+ staff/shifts/maps/lodgings/meals) all'eliminazione di un evento.
- P2: Export CSV/PDF altri moduli; calendario turni visuale; foto persona upload in anagrafica; notifiche email automatiche follow-up; pagina Prezzi/Piani SaaS; banner Cookie/CMP funzionante; completare dati legali `[DA COMPLETARE]` in Privacy Policy.
- P2: refactoring `server.py` (>2200 righe) in router per risorsa.

### 2026-06 (Pulizia database demo — PREVIEW eseguita + backup)
- [x] Backup completo preview: `mongodump` in `/app/backups/preview_20260925_112942` (persistente).
- [x] Reset PREVIEW via `/api/admin/reset-data`: azzerate le collection operative (events, companies, persons, deals, staff, teams, shifts, event_maps, activities, followups, files, calendar links, person_companies, lodgings, meals) + account demo staff/volontari; impostato `settings.demo_disabled=true` (seed_demo NON ripopola più). Preservati: admin, settings, Knowledge Base/categorie/procedure supporto, conversazioni. Config email/Resend/dominio = env (intatte).
- [x] Validato flusso da zero (event→company→person→staff→team→shift→deal→map) e login admin OK.
- [ ] **PRODUZIONE**: NON eseguita da qui (DB separato, nessun accesso/backup dal mio ambiente). L'utente deve lanciarla su crmevent.it: Impostazioni → "Azzera database operativo" (`reset-data-button`) → conferma. Nessun backup di produzione garantito dal mio lato.
- Ambiente demo: preview e produzione sono già DB separati; demo_disabled=true impedisce la generazione di dati demo.

- Team upgrade (parti 4-9): Responsabile Team (persona Staff dell'evento), componenti multipli (Staff/Volontari) senza cambiare il loro Ruolo evento, scheda Team con conteggi (Staff/Volontari/totale) e collegamento Turni. Predisporre per Briefing (Team→Responsabile→Staff→Volontari→Qualifiche→Turni).
- Eseguire il reset finale dopo validazione utente.

### 2026-06 (Ruolo evento semplificato a Staff/Volontario — verificato curl + UI)
- [x] Ruolo evento ora SOLO **Staff / Volontario / Nessun ruolo** (rimuove l'associazione), sia nella colonna "Ruolo eventi" (dialog `EventRolesDialog`) sia nella scheda Persona (tab Eventi). Salvato in Persona↔Evento (collection `staff`), non in anagrafica.
- [x] Rimossi come Ruolo evento: Referente, Collaboratore, Team, e il vecchio select "ruolo operativo" (la Qualifica resta in anagrafica Person.ruolo).
- [x] **Referente** resta gestito nelle Aziende (Persona↔Azienda); backend persons-enriched `is_referente` di nuovo solo company-based.
- [x] Team resta funzionalità separata (gruppo operativo per evento), non è un Ruolo evento; associazione Team ancora possibile dal dialog/scheda (opzionale) senza cambiare il ruolo.
- [x] Flusso obbligatorio testato: persona senza ruolo → Staff → Volontario → Nessun ruolo; le viste Staff/Volontari si aggiornano. Associazioni/Referenti/Team esistenti non toccati.

### 2026-06 (Ruolo evento gestibile in Persone — verificato frontend 100%, backend curl)
- [x] Distinzione **Qualifica** (Person.ruolo, anagrafica) vs **Ruolo evento** (link persona↔evento, collection `staff`, campo `categoria`: referente/staff/collaboratore/volontario/team + `ruolo` operativo + `team_id`). Una persona = una sola anagrafica, ruoli diversi in eventi diversi.
- [x] Colonna "Ruolo eventi" resa **interattiva** (`role-cell-<id>`): apre `EventRolesDialog` che elenca gli eventi collegati con select modificabili (categoria/ruolo/team), rimozione, e "Collega a nuovo evento" (anche più ruoli nello stesso evento).
- [x] Scheda Persona → tab Eventi: ogni associazione ora **modificabile inline** (categoria/ruolo/team salvano su PUT /staff/{id}); add/delete invariati.
- [x] I ruoli alimentano automaticamente le viste: backend persons-enriched → `is_referente` ora vero anche per event-role "referente", `is_staff` (staff/collaboratore), `is_volontario`, nuovo `is_team`. Cambiando Staff→Volontario la persona si sposta tra i tab.
- [x] Fix z-index: `SelectContent` z-[200] (Dialog usa z-[100]) — le Select dentro i Dialog erano bloccate dall'overlay.

### 2026-06 (Logo evento — verificato backend curl + UI)
- [x] Campo **Logo evento** nell'anagrafica Evento (crea/modifica): upload PNG/JPG, anteprima (object-contain, proporzioni mantenute), sostituzione ed eliminazione. Nuovo tipo campo `image` in `crm.jsx` (componente `ImageUpload`) usato da `EntityDialog`.
- [x] Backend `Event.logo_url` (Optional). Salvato in modo permanente come elemento dell'evento → riutilizzabile in futuro per documenti/PDF/accrediti/pass (parte 6).
- [ ] Integrazione nel **Briefing** (copertina con logo/nome/data/località + toggle "Mostra logo evento", parti 3-5): NON implementata perché la funzione **Briefing non esiste ancora** in CRMEvent. Il logo è già pronto e verrà usato automaticamente quando si costruirà il Briefing.

### 2026-06 (Mappe & Percorsi — view/edit + GPX + mappa — verificato frontend 100%)
- [x] Dialog "Mappe & Percorsi" (Events.jsx) riorganizzato: sezione "PERCORSI ESISTENTI" (righe con Nome, Tipologia, distanza, stato GPX + azioni Visualizza/Modifica/Elimina) e sezione "NUOVO/MODIFICA PERCORSO".
- [x] Modifica carica il record nel form; pulsante commuta tra "Aggiungi percorso" e "Salva modifiche"; "+ Nuovo percorso" svuota il form. La modifica NON crea duplicati (dopo POST resta in edit sul nuovo id).
- [x] Campo dedicato "File GPX (.gpx)": valida, calcola distanza (haversine), auto-compila Distanza se vuota, anteprima mappa interattiva Leaflet (traccia + partenza + arrivo, zoom/pan), download/sostituisci/elimina GPX.
- [x] Backend EventMap: aggiunti `gpx_url`, `distanza` (retrocompatibile, dati esistenti intatti). CRUD /maps invariato. Dipendenza frontend: leaflet 1.9.4.
- [x] Regression OK: Immagine/PDF/File/Google Maps/URL esterno continuano a funzionare.

### 2026-06 (Auth persistence + Email branding Resend + rimozione riferimenti Emergent — verificato in PRODUZIONE dall'utente)
- [x] **Bug password risolto**: `seed_admin()` reso idempotente — non sovrascrive più la password di un admin esistente ad ogni restart/deploy (causa reale del "devo rifare password dimenticata"). Testato: cambio password → restart → la nuova password persiste; logout/sessione non invalidano la password.
- [x] **Email mittente**: passaggio a Resend (account utente, dominio crmevent.it verificato SPF/DKIM/DMARC). Mittente reale **"CRMEvent <noreply@crmevent.it>"**. `email_utils.send_email` usa Resend quando `RESEND_API_KEY`+`EMAIL_FROM_ADDRESS` presenti, con fallback gestito non-bloccante. Nessun Reply-To. Nuovi env: `EMAIL_FROM_ADDRESS`, `RESEND_API_KEY`. Verificato in produzione dall'utente (email ricevuta, mittente/dominio/link/reset/login OK).
- [x] **Rimozione riferimenti Emergent visibili**: login page text, canonical/OpenGraph, sitemap.xml, robots.txt → `crmevent.it`. Riferimenti residui solo tecnici/invisibili (auth Google, script piattaforma, endpoint interni).
- [x] Secret produzione: APP_URL/FRONTEND_URL/REACT_APP_BACKEND_URL = https://crmevent.it; BACKEND_PUBLIC_URL corretto su URL backend; EMAIL_FROM_NAME=CRMEvent.

### 2026-06 (Ospitalità & Pasti — verificato: backend 13/13 pytest, frontend 95%)
- [x] Nuova sezione **Ospitalità & Pasti** (`/ospitalita`, voce menu con selettore evento), integrata con anagrafica Persone esistente (nessun duplicato). Dati legati alla relazione Persona↔Evento (collection `staff`).
- [x] Nuove collection `lodgings` (pernottamenti) e `meals` (colazione/pranzo/cena), aggiunte a OPERATIONAL. Modelli `Lodging`/`Meal` in server.py.
- [x] `Person` e `Presence` estesi con `esigenze_alimentari` + `esigenze_note` (default in anagrafica, override per evento).
- [x] Endpoint: crud `/lodgings` `/meals`; `POST /lodgings/bulk` e `/meals/bulk` (assegnazione multipla per persona_ids/categorie/ruoli/team); `DELETE /hospitality/group/{gruppo_id}?tipo=`; `GET /events/{id}/hospitality` (aggregato persons+lodgings+meals+summary, redazione campi costo se ruolo≠admin).
- [x] 3 viste: Per persona (tabella + dialog piano completo con CRUD pernottamenti/pasti + editor esigenze), Per giorno (colonne pernott./colazione/pranzo/cena con conteggi), Per struttura/servizio (raggruppamento + breakdown esigenze). Dashboard riepilogo (7 card), filtri (ricerca/ruolo/stato/esigenze/giorno), mobile-first.
- [x] Permessi: view/edit admin+member; costi/pagamenti/note amministrative solo SuperAdmin (`can_view_costs`).
- [x] Assegnazione multipla con selezione manuale / per categoria / per team / tutti; la modifica individuale prevale.
- Predisposizione futura (non implementata ora, come da scelta utente): briefing personale, export Excel/PDF, rooming list, voucher, budget.

### 2026-06 (Riferimenti legali + Footer — verificato via screenshot)
- [x] Footer condiviso (`components/Footer.jsx`) usato su landing + pagine legali; logo fondo nero, link Privacy Policy/Cookie Policy/Termini; riga legale "© 2026 CRMEvent – P. IVA 02671780340" (nome titolare NON mostrato).
- [x] Nuova rotta `/privacy-policy` (Privacy Policy completa per SaaS CRM eventi); `/privacy` reindirizza a `/privacy-policy`.
- [x] `Legal.jsx` riscritta: Privacy Policy (13 sezioni GDPR), Cookie Policy (tecnici + analitici + marketing, con banner/CMP), Termini. Titolare nel testo: MANARA MICHELE – P.IVA 02671780340. Dati non configurati (indirizzo, email privacy, data center, durate conservazione, fornitori analytics/marketing, CMP) marcati [DA COMPLETARE], nessuna info legale inventata.

## Funnel Demo CRMEvent (Brevo email automation) — stato: BOZZA (2026-06)
- Implementato e verificato in preview (testing iter 17: backend 100%, frontend 100%). Vedi CHANGELOG per dettaglio.
- IN ATTESA: test reale delle 4 email (richiede BREVO_API_KEY, vuota in preview) + attivazione esplicita dell'utente.
- Deploy: aggiungere in produzione i secret BREVO_WEBHOOK_TOKEN e WEBHOOK_CRON_SECRET; configurare webhook Brevo su /api/brevo/webhook/{BREVO_WEBHOOK_TOKEN}. Il funnel resta BOZZA dopo il deploy.
- Nuovi file: backend/brevo_funnel.py, frontend/src/components/FunnelPanel.jsx. Cron: .emergent/crons.yml (brevo-funnel-tick */15).

## Google Calendar OAuth — PKCE fix (2026-06)
- RCA prod: invalid_grant "Missing code verifier." → verifier non inviato (google-auth-oauthlib autogenera challenge). Risolto con PKCE server-side (verifier in Mongo calendar_oauth_pkce, monouso, TTL 10min). Solo codice; nessun cambio Google Cloud/secret.
- In attesa: verifica utente in produzione con "Collega Google Calendar" dopo il redeploy.

## E2E test cliente (2026-06) — predisposizione
- FIC: modalità SIMULAZIONE TEST implementata (POST /api/fic/simulate/{id}, org-scoped) — nessun documento FIC reale, nessun SDI. Flusso reale /fic/issue invariato.
- UI Account: sezione Fatture + pulsante "Simula fattura (TEST)".
- Stripe resta TEST (STRIPE_MODE=test verificato in prod).
- Funnel Demo: autorizzata attivazione TEMPORANEA per il test (B1), poi ripristino BOZZA (azioni SuperAdmin lato utente in prod).
- Pre-step SuperAdmin in prod (l'agente non ha auth SuperAdmin Google in prod): 1) Verifica/crea lista Brevo, 2) Collega template, 3) Attiva Funnel, poi test, poi Funnel→BOZZA.

## Marketing · Social (Social Media Manager AI) — roadmap- FASE A (fatto): DB + UI Marketing/Social + impostazioni + libreria media + calendario editoriale.
- FASE B (fatto): generazione AI contenuti (post singolo + piano editoriale) con dati evento sanitizzati; trigger intelligenti come SUGGERIMENTI (architettura predisposta).
- FASE C (fatto): generazione/suggerimento creatività immagini (Nano Banana / Pillow) — 6 template, 3 modalità (foto libreria / screenshot / AI), brand kit automatico, formati IG 1:1 / 4:5 / 9:16, creatività collegata al post e salvata in Libreria Media.
- FASE D (fatto in preview, publishing OFF): OAuth ufficiale Instagram Business Login (start/callback/deauthorize/data-deletion/status), token long-lived + refresh, collegamento multi-tenant su social_accounts, compliance callbacks. Richiede META_APP_ID/META_APP_SECRET in env. Non ancora deployato in produzione.
- FASE E (fatto in preview — immagine singola feed): pubblicazione Instagram (container media → media_publish), "Pubblica ora" con conferma esplicita, controlli pre-publish, JPEG pubblico per Meta, anti-duplicati, logging completo. Pilota automatico resta OFF. Da fare in seguito: caroselli, Stories, Reels; pubblicazione automatica degli scheduled via cron; Pilota Automatico ON con regole. Limiti Meta: 100 post/24h.
- Trigger intelligenti (P1): 90/60/30/7/1 giorni all'evento, nuovo sponsor/percorso → generano SOLO suggerimenti (nessuna pubblicazione automatica).

## Lead Finder — Scansione ENDU → Sito ufficiale → Organizzatore (2026-06)
- Nuova catena di scraping (`leadfinder_scraper.py`, requests + BeautifulSoup, NESSUN servizio a pagamento):
  ENDU (scoperta evento + "Link utili": sito ufficiale + pagina social) → visita sito ufficiale (home + pagine rilevanti auto-individuate: contatti/chi siamo/organizzazione/staff/associazione/team/privacy/footer) → estrae ragione sociale ASD/SSD/APS, email pubbliche (ranking per dominio del sito + role-inbox), telefono, Instagram/Facebook/LinkedIn.
- LinkedIn/social MAI inventati: associati solo se presenti esplicitamente su ENDU o sui siti ufficiali. Social dell'evento (da ENDU, alta affidabilità) distinti dai social dell'organizzatore (dal sito). Se il sito evento rimanda a un sito ASD su altro dominio, lo segue una volta.
- Tracciabilità granulare: per ogni dato (email/IG/FB/LinkedIn/telefono/ragione sociale) salva l'URL della pagina sorgente + label fonte ("ENDU"/"sito ufficiale"). Distinti URL ENDU, sito evento, sito organizzatore. `last_verified_at` aggiornato senza sovrascrivere dati confermati manualmente (fill-if-empty).
- Dedup organizzatore (email → dominio → nome → social): non fa merge automatico se incerto → segna `possibile_duplicato` con l'organizzatore candidato (visibile nel dettaglio). Relazione 1 organizzatore → N eventi mantenuta.
- Endpoint: `POST /leadfinder/scan-endu` (job async in background), `GET /leadfinder/scan/{id}` (progress+report+stats), `GET /leadfinder/scans`. Collection `lf_scans`. Tutti i risultati salvati in stato "Da verificare".
- UI (`LeadFinder.jsx`, tab "Lead Finder"): pulsante "Scansiona ENDU + Arricchisci" con polling progress, griglia metriche, tabella 20 eventi (evento/organizzatore/sito evento/sito org./email/IG/FB/LinkedIn/stato Completo|Parziale|Da verificare/note). Ultimo scan ricaricato al mount.
- Test controllato 20 eventi ENDU (2026-06): 13 con sito ufficiale su ENDU, 10 con social su ENDU, 9 siti visitati, 7 con email, 13 IG, 9 FB, 2 LinkedIn, 2 ragioni sociali identificate (SSD Neapolis Marathon, ASD Leaning Tower Runners), 1 possibile duplicato, 0 errori. Nessun Brevo, nessun servizio a pagamento.
- FIX diagnosi "0/0" (2026-06): il "Completata 0/0" in produzione era dovuto alla collection `lf_events` vuota (seed solo in preview). Ora: (1) estrazione ENDU di nome/data/città via JSON-LD SportsEvent; (2) auto-seed idempotente dei 20 eventi se il DB platform è vuoto (fix produzione, verificato: seeded=20 → 20/20); (3) stato onesto `empty` = "Nessun evento acquisito — scansione da verificare" con motivo quando 0 eventi o ENDU irraggiungibile (non più "Completata"); (4) endpoint `GET /leadfinder/diagnose?url=` + pulsante UI "Diagnostica su 1 evento" (HTTP status → nome/data/città → sito ufficiale → social → raggiungibilità → errore). ENDU verificato non-JS/non-anti-bot (HTTP 200, dati nell'HTML).
- Arricchimento potenziato (2026-06): `scrape_official_site` ora visita fino a 8 pagine interne + secondo livello se manca l'email; keyword estese (contatti/chi siamo/organizzazione/staff/associazione/società/privacy/cookie/note legali/about/impress); deoffuscamento email ("[at]/[dot]"); ragione sociale anche da copyright/footer; follow del sito organizzatore su dominio diverso. Diagnostica arricchita: organizzatore, email (main+lista con fonti), telefono, Instagram evento (ENDU) vs Instagram organizzatore (sito), Facebook, LinkedIn, elenco URL pagine analizzate, motivi dei dati non trovati. Verificato: Pisa → ASD Leaning Tower Runners + email; Monza → MG SPORT + IG/FB/LinkedIn su 7 pagine (email assente perché form di contatto).
- Inserimento manuale / Importazione email organizzatori (2026-06, solo Super Admin): pulsanti "Aggiungi organizzatore" e "Importa email" nel tab Organizzatori. Single-add: email obbligatoria + nome/sito/note facoltativi → record in stato `da_completare` (verify `non_verificato`, origine "Inserimento manuale"), dedup per email (se esiste mostra il record, nessun duplicato), nessun dato inventato. Import .xlsx/.xls/.csv (colonna `email`): endpoint preview restituisce total/valide/nuove/già presenti/duplicate nel file/non valide (+elenco non valide) senza scrivere; confirm crea solo le nuove (normalizzazione minuscolo+trim, validazione formato, dedup in-file e vs DB, no overwrite), origine "Importazione manuale". Nessun invio/sync Brevo. Selezione record + pulsante "Arricchisci selezionati" predisposto (azione automatica NON ancora attiva). Endpoint: `POST /leadfinder/organizers/manual`, `/import/preview` (multipart), `/import/confirm`.

## Brevo — sincronizzazione controllata Prospect (2026-06, solo Super Admin)
- Distinzione netta Prospect (trovati/importati da CRMEvent) vs Demo (richiesta reale). Funnel Demo esistente (`brevo_funnel`, lista "CRMEvent · Lead") NON toccato. Lista Prospect separata: **"CRMEvent – Prospect"**.
- Client backend `brevo_client.py` (httpx async, header `api-key`, base https://api.brevo.com/v3): account, lists, attributes, senders, folders, get_contact (404→None), create_contact (updateEnabled=false), add_existing_to_list (solo listIds → mai resubscribe), create_list. Chiave da env `BREVO_API_KEY` (mai restituita/loggata/salvata in DB). Nota: `BREVO_API_KEY` è VUOTA in preview, valorizzata nei Secrets di produzione (usata dal Demo funnel).
- Endpoint: `GET /brevo/status`, `POST /brevo/test` (account+liste+attributi+mittenti, individua lista Prospect, salva listId in `brevo_config`), `POST /brevo/create-list` (solo su conferma), `POST /leadfinder/organizers/approve-brevo`, `POST /leadfinder/organizers/sync-brevo` (solo record approvati, conferma lato UI). Audit in `brevo_sync_log` (email, contactId, listId, risultato, errore, utente, timestamp).
- Stati Brevo separati dallo stato commerciale, su `lf_organizers.brevo_status`: non_approvato / approvato / in_corso / sincronizzato / gia_presente / disiscritto_bloccato / errore. Campi: brevo_contact_id, brevo_list_id, brevo_synced_at, brevo_error.
- Regole rispettate: approvazione manuale obbligatoria (nessun auto-sync da Lead Finder/import/manuale); prima della sync legge stato contatto → se emailBlacklisted o unsubscribed dalla lista NON sincronizza e segna "Disiscritto/bloccato" (priorità assoluta anche su re-import); se già in lista → "gia_presente" (no re-trigger); attributi personalizzati inviati solo se già esistenti in Brevo (mostra i mancanti, non li crea). Email è l'unico dato minimo.
- UI: nuovo tab **Brevo** (stato connessione, lista+listId, ultimo test, Test connessione, attributi disponibili/mancanti, mittenti, crea lista con conferma); colonna Brevo + azioni "Approva per Brevo" e "Sincronizza con Brevo" (conferma "Stai per sincronizzare N prospect nella lista …") su singolo e selezione multipla; sezione Brevo nel dettaglio organizzatore. Webhook Demo esistente `/brevo/webhook/{token}` riusabile per unsubscribe/bounce (gestione lf_organizers da collegare in fase futura).
- Email 1 Prospect: template HTML pronto in `/app/frontend/public/email-templates/prospect-email-1.html` (branding Tiffany #147D74, sfondo bianco, logo, CTA "GUARDA LA DEMO" → `/demo?utm_source=brevo&utm_medium=email&utm_campaign=prospect&utm_content=email1`, footer con `{{ unsubscribe }}`). Route demo pubblica confermata: `/demo`. Da caricare in Brevo (UI); automazione/mittente da configurare manualmente (API Brevo non crea automazioni). Click demo ≠ Demo richiesta.
- Creazione template Brevo via API (2026-06): verificato che Brevo consente la creazione di template email via `POST /v3/smtp/templates`. Implementato `brevo_client.create_email_template`/`get_templates` + endpoint `POST /brevo/create-email-template` (Super Admin): crea il template **"CRMEvent · Funnel Prospect · Email 1"** come BOZZA (isActive=false, nessun invio), dedup per nome (non duplica), usa un mittente Brevo già verificato (preferendo CRMEvent; se nessun mittente verificato si ferma e NON ne crea). HTML generato dal builder backend `_prospect_email_html(domain)` con dominio pubblico da APP_URL (nessun placeholder nel template finale) e tag Brevo `{{ unsubscribe }}`/`{{ contact.EMAIL }}`. Il Test connessione ora rileva anche presenza/ID del template. UI: pulsante "Crea template in Brevo" nel tab Brevo. Le AUTOMAZIONI Brevo NON sono creabili via API → configurazione manuale in UI. Nota: esecuzione reale bloccata finché la chiave non è raggiungibile (preview vuota) e il deploy in produzione non è ripubblicato (deploy fallito per limite AWS ECR lato piattaforma, escalato a Platform; produzione resta sulla versione precedente).


## Raccolta pubblica disponibilità Staff/Volontari (2026-06)
- Obiettivo: link pubblico per evento (crmevent.it/partecipa/{code}) dove potenziali collaboratori indicano la disponibilità per giorno senza login; i dati confluiscono in anagrafica Persone + adesione all'Evento. Classificazione Staff/Volontario decisa dopo dall'organizzatore (default Ruolo evento "Da definire", Stato "Nuova").
- Codice Fiscale obbligatorio nel form pubblico (deriva data nascita, calcola età, resta su Persona per futura gestione rimborsi Staff); opzione stranieri -> Data di nascita. CF visibile solo in scheda Persona.
- Modelli: Event.data_inizio_allestimento; Person.codice_fiscale; collections `avail_links`, `availabilities`. Endpoint pubblici `/api/public/availability/{code}` (+logo) rate-limited; admin `/api/events/{id}/availability/link*`, `/api/events/{id}/availabilities`, `/api/availabilities/{id}`. File: `Partecipa.jsx`, `AvailabilityDialog.jsx`, `PersonDetailDialog.jsx` (Età+CF), `crm.jsx` (calcAge).
- Predisposto (non implementato ora): QR/WhatsApp/email link, reminder, richiesta a Persone esistenti, modifica disponibilità, conferma, assegnazione Turno, check-in; consultazione disponibilità durante creazione Team/Turni; segnale Disponibile/fuori-fascia; alimentazione Briefing tramite assegnazione reale.

### Backlog aggiornato
- P1: mappatura disponibilità in creazione Team/Turni (mostra chi è disponibile per giorno/fascia); webhook Brevo -> lf_organizers (unsubscribe/bounce).
- P1 (in attesa deploy): test E2E reale creazione template Brevo in produzione (Template ID + mittente).
- P2: QR/condivisione WhatsApp del link disponibilità; punteggio qualità lead; spostamento Prospect<->Demo; pubblicazione Instagram caroselli/Stories/Reel; Stripe/Fatture in Cloud LIVE.

## Brevo disponibilità + Conferma da tabella (2026-06)
- Pipeline: Raccolta disponibilità pubblica -> Persona (dedup email/cellulare/CF) -> adesione (ruolo Da definire, stato Nuova) -> sync Brevo lista "CRMEvent · Disponibilità eventi" (attributi dedicati, MAI il CF) -> 1ª email "Conferma disponibilità" -> Conferma organizzatore (tabella per evento: checkbox Confermato, ruolo inline, filtri, bulk) -> stato Confermata + confirmed_at/by -> 2ª email "Conferma partecipazione" (una sola volta) -> futura assegnazione Team/Turno/Briefing.
- Brevo GATED da env BREVO_AVAILABILITY_ENABLED (default off): in preview e finché non approvato, nessun invio reale; le intenzioni sono loggate in brevo_sync_log (pending) per retry. Template creati come BOZZA via POST /api/brevo/create-availability-templates. Consenso marketing separato e facoltativo (non blocca).
- Endpoint nuovi: POST /api/events/{id}/availabilities/confirm-bulk, POST /api/brevo/create-availability-templates. availability doc: confirmed_at/by, confirmation_email_sent_at/status/error, brevo_status, marketing_consent(+ts/source).

### 2026-06-30 (Nuova pagina /prezzi — FASE 1 frontend COMPLETATA)
- 3 piani FREE/PLUS/PREMIUM con selettore eventi (Fino a 3 / Più di 3) e prezzi dinamici. Solo frontend, Stripe intatto.
- FASE 2 da fare per rendere Plus/Premium acquistabili: vedi ROADMAP.



### MODELLO COMMERCIALE DEFINITIVO (2026-06-30) — SUPERSEDES tutte le regole FREE
- ❌ PIANO FREE ELIMINATO. Rimosse tutte le regole precedenti su FREE (1 evento gratuito/anno, gating FREE, downgrade a FREE). Non vanno implementate.
- ✅ 3 piani A PAGAMENTO per evento (prezzo per anno solare):
  - STARTER 49/99 · PROFESSIONAL 79/149 · PREMIUM 99/199 (€ + IVA, fino a 3 / oltre 3 eventi/anno).
- ✅ TRIAL 14 giorni con accesso PREMIUM sostituisce FREE. Alla scadenza senza acquisto → account in SOLA LETTURA (eventi non modificabili), nessun dato cancellato, CTA per acquistare un piano.
- ✅ Gating rivisto: STARTER=gestione staff · PROFESSIONAL=+gestione evento · PREMIUM=+organizzazione avanzata+marketing/social. Org-level sul miglior piano attivo (Professional/Premium) con evento attivo nell'anno.
- 🆕 FASE 2 — "Piani e prezzi" (Super Admin): listino prezzi gestibile da DB (NO hardcoding), 6 prezzi (3 piani × 2 fasce), sync Stripe con NUOVO Price ad ogni variazione (vecchi Price archiviati per riconciliazione), storico variazioni prezzo, snapshot immutabile del prezzo su ogni acquisto evento. Solo ruolo Super Admin. Gestione sicura errori di sync (DB e Stripe mai divergenti).

### MAPPA DI GATING DEFINITIVA (APPROVATA 2026-06-30) — FASE 2
STARTER — Gestisci il tuo team (49€ / 99€ +IVA per evento):
  Persone/anagrafiche (staff), Staff e volontari, Team, Turni, Disponibilità e conferme, Informazioni allo staff.
PROFESSIONAL — Gestisci tutto il tuo evento (79€ / 149€) [EVIDENZIATO]:
  Tutto Starter + Aziende, Contatti aziendali, Sponsor e partner, Attività, Follow-up, SCADENZE, Assegnazione RESPONSABILI, STATO attività, Ospitalità, Pernottamenti, Pasti, Briefing, Documenti, Mappe e percorsi.
PREMIUM — Organizza e promuovi (99€ / 199€):
  Tutto Professional + Checklist completa evento, Pipeline organizzativa pre-evento, Controllo avanzamento complessivo, Modelli/checklist per tipologia evento, automazioni future, Marketing, Piano editoriale, Calendario social, Libreria media, Creazione contenuti, Gestione+Pubblicazione social.
NOTE:
- Anagrafiche/Persone: gating PER SEZIONE (staff=Starter; aziende/contatti/sponsor=Professional). Mai bloccare l'intera pagina.
- Org-level: Aziende+Strutture da Professional; Libreria media+Impostazioni Social+strumenti marketing da Premium. Gating sul MIGLIOR piano con evento ATTIVO nell'anno, senza modificare il piano dei singoli eventi.
- Attività "normali" (incl. scadenze/responsabili/stato) in PROFESSIONAL; solo l'evoluto (checklist/pipeline/controllo avanzamento/modelli) in PREMIUM.
- Trial 14gg = tutte le funzionalità PREMIUM. Nessun FREE.

### FASE 2 — GESTIONE DINAMICA PREZZI (APPROVATA 2026-06-30)
Struttura a 3 livelli (APPROVATA):
1. `pricing_plans` → LISTINO ATTUALE = fonte di verità (6 doc: 3 piani × 2 fasce). Campi: plan, fascia, net, vat_rate(22), gross, currency, stripe_product_id, stripe_price_id(attivo), status, version, updated_at, updated_by.
2. `pricing_history` → storico append-only: plan, fascia, old_net, new_net, old_stripe_price_id, new_stripe_price_id, changed_at, changed_by.
3. Snapshot IMMUTABILE dell'acquisto su `events.entitlement` (mai toccato da variazioni listino).

/prezzi e Checkout LEGGONO il listino dal DB via API (GET /api/pricing). NESSUN prezzo hardcoded.

FLUSSO AGGIORNAMENTO PREZZO (ordine APPROVATO — archiviazione vecchio Price DOPO il DB):
1. crea NUOVO Price su Stripe;
2. verifica price_id restituito correttamente;
3. aggiorna `pricing_plans` (nuovo prezzo + nuovo stripe_price_id + version++);
4. registra variazione in `pricing_history`;
5. SOLO DOPO i passaggi 1-4 → archivia il vecchio Price Stripe (active:false).
- Se la creazione del nuovo Price fallisce → DB INVARIATO.
- Se errore dopo la creazione ma prima del completamento DB → il nuovo Price NON deve diventare utilizzabile dal Checkout (Checkout usa solo pricing_plans.stripe_price_id attivo); il Price resta ORFANO/non attivo da riconciliare.
- Checkout usa ESCLUSIVAMENTE lo stripe_price_id del record pricing_plans attivo; MAI cercare un Price autonomamente su Stripe.

SNAPSHOT ACQUISTO (immutabile) — campi APPROVATI:
plan, price_tier(fascia), net, vat, gross, currency, year, purchased_at,
event_id, organization_id, pricing_plan_version, quantita (default 1, per uso futuro),
payment_status, upgrade_amount_paid (importo upgrade già pagato),
stripe_price_id, stripe_payment/checkout_ref, invoice_id (FIC).
→ Ricostruibile sempre: cosa ha acquistato il cliente, per quale evento, a quale prezzo e con quale versione di listino.

REGOLA FONDAMENTALE: una modifica del listino interessa SOLO i nuovi acquisti.
Es.: acquisto Professional a 79€+IVA → cambio listino a 89€+IVA → l'anagrafica cliente/evento continua a mostrare 79€+IVA; i nuovi acquisti usano 89€+IVA.

SICUREZZA: solo Super Admin (require_superadmin) modifica il listino; tutte le modifiche tracciate (audit).

PIANI DEFINITIVI: STARTER / PROFESSIONAL / PREMIUM (nessun FREE). Trial Premium 14 giorni senza carta.

### FASE 2 — Logica TRIAL 14 giorni (da implementare, NON ancora fatta)
- Alla registrazione: 14 giorni di prova gratuita con accesso alle funzionalità PREMIUM (prova intera piattaforma).
- Nessuna carta richiesta per iniziare.
- Allo scadere dei 14 giorni senza acquisto: [SUPERSEDED] account resta ATTIVO ma in SOLA LETTURA (nessun piano FREE): l'utente deve scegliere Starter/Professional/Premium per continuare. I dati NON vengono cancellati.
- Per continuare con Plus/Premium l'utente acquista il piano per l'evento (modello per-evento).
- Da implementare in FASE 2 insieme all'adeguamento Stripe + Fatture in Cloud. In FASE 1 aggiornati solo testi/CTA della pagina prezzi.

### FASE 2 — Modello commerciale PER EVENTO (sostituisce mensile/annuale)
- Il nuovo modello NON è più ad abbonamento mensile/annuale ma a **prezzo per evento** su 3 piani FREE/PLUS/PREMIUM (fino a 3 eventi vs più di 3).
- Da adeguare in FASE 2: **Stripe** (nuovi prodotti/prezzi per-evento, checkout per piano+tier) e **Fatture in Cloud** (descrizione riga per piano, importo per-evento). Non ancora toccati.

### Backlog aggiornato (P1)
- Attivazione invii Brevo disponibilità (dopo approvazione utente): BREVO_AVAILABILITY_ENABLED=on in produzione + attivazione template + test invio singolo.
- Consultazione disponibilità in creazione Team/Turni; alimentazione Briefing da assegnazione reale.

### 2026-06-30 (Messaggio 304 — COMPLETATO E VERIFICATO)
- [x] Team Leader dropdown filtrato a Staff & Volontari dell'evento selezionato (esclusi referenti-only), alfabetico, event-aware.
- [x] Pasti con Data inizio | Data fine (retrocompat con `data` singola, no duplicazione, validazione fine≥inizio) — un record copre l'intero periodo.
- [x] Auto-compilazione Luogo/Indirizzo/Referente/Telefono/Google Maps da anagrafica Struttura nei form Pasto e Pernottamento, con nota "Dato non presente".
- [x] Viste aggiornate: Ospitalità Per-giorno (espansione), Per-struttura/Briefing/Area Staff (range leggibile "16–20 ottobre 2026").
- Prossimi P1: passaggio Stripe + Fatture in Cloud in modalità LIVE.

## Super Admin · Scheda "Email disponibilità eventi" (Marketing/Brevo) — 2026-06 (verificato frontend 100%)
- Sezione in /piattaforma (`AvailabilityEmailPanel.jsx`) SOLO Super Admin (org-admin/utenti esclusi; multi-tenant ready per CRMEvent Pro futuro, nessun riferimento Pro in UI pubblica). Mostra i 2 template master (nome, tipo Disponibilità/Conferma, Template ID, stato Attivo/Bozza/Non creato, ultimo aggiornamento) + badge "Invii automatici ATTIVI/DISATTIVATI" (da BREVO_AVAILABILITY_ENABLED, resta off).
- Pulsanti: Aggiorna stato · Crea template in Brevo (anti-duplicato, riusa Template ID esistenti) · Invia email di test per template (Evento di org type=test + email destinatario, dati reali evento+logo via HTML inline; invio manuale indipendente dal flag).
- Endpoint require_superadmin: GET /api/brevo/availability-templates (esteso type_label+updated_at), GET /api/brevo/availability-test-events, POST /api/brevo/availability-test-email (no-op informativo se BREVO_API_KEY assente), POST /api/brevo/create-availability-templates. CF mai a Brevo; chiave mai esposta.
- ORDINE GO-LIVE concordato (produzione): 1) Deploy 2) Crea 2 template master 3) Invio test reale (evento org Test) 4) Verifica utente (mittente/oggetto/logo/nome/data/località/grafica/no Emergent) 5) Attiva template in Brevo 6) Solo dopo conferma utente: BREVO_AVAILABILITY_ENABLED=on. Durante i test in produzione il flag resta off.

## FASE C — Acquisto reale crediti (Stripe TEST) — 2026-06-30 ✅ COMPLETATO e VERIFICATO
- Ricarica crediti dall'Area Account con Checkout Stripe (SOLO TEST): scelta taglio, breakdown IVA 22% esclusa (TaxRate manuale, no automatic_tax), pagamento, ritorno, accredito automatico. Crediti accreditati SOLO dopo conferma server-side (webhook autorevole + fallback confirmation con retrieve su Stripe). Atomico, idempotente (no doppio accredito), org-scoped, registrato nel ledger. Snapshot pacchetto immutabile. Bonus senza valore economico in fattura. Storico acquisti + fattura (simulazione FIC TEST). 6 tagli da credit_packages modificabili dal Super Admin.
- Endpoint: POST /api/credits/checkout, GET /api/credits/checkout-confirmation, GET /api/credits/purchases; webhook kind=credit_purchase.

### Backlog aperto (in attesa autorizzazione utente)
- FASE D — Sostituzione modello commerciale: rimuovere listino per-evento, sostituire /prezzi con acquisto Crediti, ripulire EventPlanManager, aggiornare /demo, migrare le org esistenti (+100 crediti). (P0, NON avviare senza ok utente)
- FASE E — Pagamenti LIVE: Stripe LIVE per i pacchetti crediti + Fatture in Cloud reale per ricariche + auto-ricarica. (P1)
- Attivazione consumi reali (era FASE C nel piano originale, ora rinviata): agganciare reserve→settle ai servizi IA/briefing/automazioni/email/Calendar/WhatsApp. credit_services restano DISATTIVATI finché l'utente non autorizza. (P0)
- Config Stripe account per checkout in EUR puro (opzionale).

## FASE D + Bilingue Partecipa — 2026-06-30 ✅ COMPLETATO e VERIFICATO (100%)
- Modello a crediti reso pubblico: /prezzi=pagina crediti, registrazione con 100 crediti + welcome, Account ripulito, /demo aggiornata, banner trial rimosso. Super Admin: tab Migrazione con dry-run (11 org, 4 idonee +400, 7 escluse) — migrazione NON eseguita (attende autorizzazione).
- Home hero title aggiornato. Pagina pubblica /partecipa bilingue IT/EN (?lang, selettore, logo fondo bianco, metadato compilation_lang, doppio link IT/EN nella maschera evento).

### Backlog aperto (attende autorizzazione utente)
- Eseguire migrazione org esistenti (+100 crediti alle 4 idonee) dopo approvazione del dry-run. (P0)
- Attivazione consumi reali reserve→settle su servizi IA/briefing/automazioni/email/Calendar/WhatsApp (credit_services off). (P0)
- Stripe LIVE + Fatture in Cloud reale + auto-ricarica. (P1)
- Rimozione definitiva vecchio sistema commerciale per-evento (verifica separata). (P2)

## FASE E — Prima attivazione consumi crediti — 2026-06-30 ✅ backend COMPLETATO e VERIFICATO (24/24)
- Catalogo consumi configurato (Super Admin, non hardcoded): Assistente IA=1, Contenuti=2, Briefing IA=3, Analisi evento=5, Checklist/piano IA=5, Immagini=5 (attivi). Google Calendar gratis (consumo off). Newsletter/WhatsApp/SMS/Automazioni NON attivi.
- Motore reserve→settle/release agganciato via `_charge_begin`. Endpoint REALI a consumo: /api/social/generate, /social/posts/{id}/regenerate, /social/plan/generate (ai_content=2). Saldo insufficiente→402 (no esecuzione), idempotenza, isolamento, ledger completo. Storico invariato alle modifiche costo.
- PENDING: (a) transparency UI (costo prima + "Ricarica crediti" su 402) sulle azioni AI; (b) collegamento consumi alle funzioni AI non ancora esistenti come endpoint (briefing IA, analisi evento, checklist/piano IA, generazione immagini, assistente IA) — costi già configurati, si agganceranno alla creazione delle feature.

### Backlog aperto (attende autorizzazione)
- Transparency UI consumi + gestione 402 con apertura ricarica. (P1)
- Collegare consumi alle future funzioni AI (briefing/analisi/checklist/immagini/assistente). (P1)
- Definire costi/contabilizzazione per Newsletter/WhatsApp/SMS/Automazioni prima di attivarli. (P1)
- Migrazione org esistenti (+100), Stripe LIVE + FIC reale. (P0/P1)

## FASE E.1 fix + E.2 Evento attivo a crediti — 2026-06-30 ✅ backend COMPLETATO e VERIFICATO
- E.1: consumo ai_content scollegato dal Social (marketing piattaforma). Catalogo distingue active (disponibilità) vs consumo_active (consumo). Bugfix idempotenza su saldo insufficiente (claim cancellato).
- E.2: evento attivo = 20 crediti/30gg (catalogo event_active_period, configurabile). Stati preparazione/attivo/sospeso/concluso. Attivazione/riattivazione, motore rinnovo idempotente, guardia centralizzata scritture, dry-run, UI EventCreditDialog. Eventi legacy non bloccati/migrati.
- Test: test_credits_faseE2.py 18/18, test_credits_faseE.py 24/24.

### Backlog aperto (attende autorizzazione)
- Attivare cron rinnovi (proposta in EVENT_RENEWAL_CRON_PROPOSAL.md). (P0)
- Migrazione eventi/org esistenti (solo dopo revisione dry-run). (P0)
- Aggiornare copy pubblico Home/prezzi al modello "attivi l'evento con i crediti". (P1)
- Futura funzione "contenuti evento" lato org che usi ai_content. UI trasparenza consumi lato org quando esisterà. (P1)
- Stripe LIVE + FIC reale. (P1)

## FASE prep LIVE (Stripe mode + billing + FIC emissione reale + pannello SA) — 2026-10 ✅ (resta TEST/dry-run)
- Stripe: modalità esplicita `STRIPE_MODE` (test|live) con risoluzione secret per-mode (`*_LIVE`/`*_TEST`, generico solo in test), coerenza all'avvio (nessun fallback LIVE→TEST), `_assert_stripe_ready()` blocca checkout se incoerente. `_get_tax_rate_id` usa `STRIPE_TAX_RATE_ID` se presente.
- Billing: `_billing_missing()` (Privato: nome/cognome/CF IT; Azienda IT: ragione sociale/P.IVA/indirizzo + SDI o PEC). Gate HARD in `/credits/checkout` (400 billing_incomplete) + endpoint `/account/billing/validate`. Form frontend già Privato/Azienda.
- FIC: `FIC_MODE` (test=dry-run|live). `_emit_credit_invoice()` emette automaticamente dopo accredito, NON blocca pagamento/accredito, idempotente anti-duplicato, salva attempts/last_attempt/error/stato/doc_id/numero/importi. Metodo di pagamento aggiunto solo in live (FIC_PAYMENT_ACCOUNT_ID/METHOD, non hardcodato). Retry `/platform/invoices/{id}/retry-emit`.
- Super Admin: `/platform/integrations/status` (no secret) + `/platform/credit-invoices` + tab "Fatture & Integrazioni" (Pagamento/Crediti/Fattura + Riprova emissione).
- Testato: Stripe config_ok test, gate billing 400 con lista campi mancanti, SA list, retry 404, badge stato. Tutto resta TEST/dry-run; nessuna transazione reale.

## FASE 1 — Audit pagamenti LIVE (Stripe + Fatture in Cloud) — 2026-10 (sola lettura)
- Stripe ricariche (`/credits/checkout`): modalità TEST. `STRIPE_MODE` presente in .env ma NON usato nel codice → modalità dipende solo dalla chiave. Flusso completo e robusto: IVA 22% exclusive EUR via TaxRate on-demand, metadata credit_purchase (org_id/purchase_id/importi), success/cancel su origin_url client, webhook firmato `/api/stripe/webhook`, accredito idempotente (`credit_purchase:{session}` + status paid, indice unico), nessun doppio accredito su retry, storico `credit_purchases`.
- Fatture in Cloud: SOLO simulazione/dry-run. Webhook crea solo record fattura (`da_emettere`), non emette. `/fic/issue` forzato dry_run=True; `/fic/simulate` nessuna chiamata FIC/SDI. Manca flusso emissione reale su pagamento + metodo di pagamento nel payload. OAuth predisposto (token in `fic_settings`).
- Dati fatturazione (`BillingDetails` su org.billing): struttura OK ma validazione debole (checkout blocca solo su `paese` mancante). Da rafforzare per azienda/professionista (P.IVA, indirizzo, SDI/PEC) e privato (CF) prima del LIVE.
- Mancano per LIVE: switch LIVE/TEST da secret; secrets Stripe LIVE (SECRET/PUBLISHABLE/WEBHOOK_SECRET); nell'account LIVE webhook + TaxRate 22% + dominio crmevent.it; OAuth FIC produzione + flusso emissione reale.
- NESSUNA modifica effettuata in questa fase. In attesa secrets/decisioni utente prima della FASE 2.

## Fix visibilità "Utenti e accessi" — 2026-10 ✅
- Il gate era solo `org_role === "admin_org"` → nascondeva la sezione al Super Admin (il cui payload non ha org_role/active_org_id; l'org attiva è in `localStorage.acting_org_id`).
- Nuova regola in `Profile.jsx`: `canManageUsers = org_role === "admin_org" || role === "superadmin"`. Per il Super Admin `manageOrgId = localStorage.acting_org_id` (org attiva); fallback messaggio "Seleziona un'organizzazione per gestire utenti e accessi." se nessuna org attiva. Utente normale: non visibile.
- Verificato in preview i 3 casi (Super Admin+org → visibile, Super Admin → org attiva, Utente → nascosto). Richiede redeploy per la produzione.

## Multiutenza Admin Organizzazione — "Utenti e accessi" in Profilo & Account — 2026-10 ✅ VERIFICATO (preview)
- Riuso TOTALE del backend esistente (nessuna nuova tabella/sistema/endpoint): `/platform/organizations/{org_id}/members` (GET/POST/PATCH) e `/invites` (GET/POST, resend, revoke) — già gated da `_require_manage` (Admin Org gestisce solo la propria org; cross-tenant 403).
- Estensione MINIMA e retrocompatibile dell'invito: `InviteCreateIn`/`_create_invite`/`_invite_view`/`get_invite` ora includono nome/cognome/telefono; `_member_view` include telefono. `create_org_invite` richiede nome+cognome+telefono (telefono validato con `_normalize_phone`, stesso sistema della registrazione). Vecchi inviti senza questi campi continuano a funzionare.
- Registrazione via invito: nome (nome+cognome) e telefono precompilati; email dell'invito NON sostituibile. Frontend `Invite.jsx` precompila Nome e Cellulare dai dati invito.
- Nuovo componente `frontend/src/components/OrgUsers.jsx` montato in `Profile.jsx` come scheda "Utenti e accessi", visibile SOLO se `user.org_role === "admin_org"`. Tabella unica membri+inviti: Nome | Email | Cellulare | Ruolo | Stato (Invito inviato/Attivo/Invito scaduto) | Ultimo accesso | Azioni. "+ Invita utente" (Nome, Cognome, Email, Cellulare con PhoneInput intl, Ruolo). Azioni: Reinvia · Cambia ruolo · Disattiva/Riattiva accesso. Scadenza invito 7gg. Nessun consumo crediti; nessuna modifica a Stripe/wallet/ledger/FIC.
- Test (curl+UI): crea invito (nome/cognome/telefono) · 400 senza telefono · prefill GET /invites/{token} · registrazione→membro Attivo (nome "Marco Rossi", telefono) · cambio ruolo 200 · disattiva/riattiva · reinvio 200 · guardia ultimo admin 400 · cross-tenant 403 · bypass utente normale (lista/crea) 403 · UI desktop/mobile. NOTA: in preview `email_sent=false` (Resend non configurato): il token funziona, l'invio email reale dipende dalla config Resend gestita in produzione.

## Super Admin → Servizi e crediti → Organizzazioni — ricerca + gestione crediti — 2026-10 ✅ VERIFICATO
- Sostituita la ricerca per ID con un unico campo "Cerca organizzazione, referente o email...": ricerca live (≥2 caratteri) per nome org / nome-cognome admin / email / telefono / ID (criterio tecnico). Click sul risultato → recupera internamente org_id e apre la scheda crediti.
- Scheda org selezionata: Organizzazione, Admin, Email, Crediti disponibili / Acquistati-accreditati / Utilizzati. Sotto: Storico movimenti con filtri (data da/a, tipo accredito/addebito, servizio).
- Nuova tabella "Tutte le organizzazioni" (Organizzazione | Admin | Email | Crediti | Utilizzati | Gestisci), filtrabile dallo stesso campo, senza bisogno di conoscere ID.
- Dialog "Gestisci crediti": + Aggiungi / − Rimuovi, quantità, motivazione obbligatoria (preset Bonus commerciale/Assistenza cliente/Correzione saldo/Promozione + testo libero), anteprima Saldo attuale → Variazione → Nuovo saldo, "Conferma accredito/rimozione".
- Backend: nuovo endpoint SOLA LETTURA GET /api/platform/orgs-overview (superadmin) con admin + crediti. Rettifica via endpoint ESISTENTE POST /api/platform/orgs/{org_id}/credits/adjust (ledger reason_code=manual_adjustment, note=motivazione, user_id=admin, created_at, balance_after; guardia sotto-zero via _apply_credit_movement → HTTP 402). Nessuna modifica a wallet/ledger/logica crediti, né a Stripe/FIC.
- Solo Super Admin (route SuperAdminOnly + require_superadmin). Verificato: ricerca, dropdown, scheda, dialog con anteprima, creazione movimento ledger (+10 Bonus commerciale / −10 Correzione saldo), guardia sotto-zero (402), mobile.

## Consumo crediti AI centralizzato — 2026-06 ✅ Assistente CRMEvent COMPLETATO e VERIFICATO
- RCA: l'endpoint `POST /api/support/chat` (widget Assistente CRMEvent) non aveva ALCUNA logica crediti → risposte AI gratuite. Inoltre l'infrastruttura reserve/settle (`_charge_begin`/`_credits_reserve`/`_credits_settle`/`_credits_release`) era definita ma NON agganciata a nessun endpoint.
- Fix: helper CENTRALIZZATO `ai_charge(org_id, service_key, ...)` + classe `_AiChargeCtl` (server.py ~8960): legge costo dal catalogo (mai hardcoded) → verifica saldo e PRENOTA prima della chiamata AI (402 se insufficiente, AI non eseguita) → `ctl.settle()` solo su risultato utile, altrimenti release → idempotenza via `idempotency_key`.
- Assistente collegato a servizio `ai_assistant` (1 credito). Addebita SOLO se `answered=true` e NON feature-request (regola 2B). Idempotency key = `ai_assistant:{request_id}` (request_id UUID generato dal widget). Ledger note "Assistente CRMEvent" con org_id/user_id/event_id/timestamp. Org risolta con `_resolve_org_for_support` (il wallet addebitato è quello dell'org reale, non DEFAULT_ORG).
- Frontend `SupportChat.jsx`: invia `request_id`; su 402 mostra "Crediti insufficienti…" + CTA "Ricarica crediti" (RechargeDialog).
- Test: iteration_40 backend 8/8 (addebito utile, no-addebito non-utile=released, idempotenza stesso request_id, 2 addebiti request_id diversi, 402 saldo insufficiente senza chiamata AI, isolamento multi-tenant, saldo aggiornato subito). File: backend/tests/test_iter40_ai_assistant_credits.py.
- SOSPESO (decisione utente): modulo Social (`/social/generate`, `/social/posts/{id}/regenerate`, `/social/plan/generate`) NON consuma ancora crediti — l'utente deciderà nome/costo di un servizio dedicato (per il piano: 2 crediti flat per generazione, non per post).
- SEGNALATO (nessun endpoint AI collegato, nulla da agganciare): `ai_briefing`/`ai_analysis`/`ai_checklist` (_build_briefing è sola aggregazione) e `image_generation` (`social_creative.generate_background` definita ma mai chiamata).
- NESSUN addebito retroattivo su richieste già effettuate (incl. account prod manara.michele+60@gmail.com).

## Modello crediti — regole DEFINITIVE (agg. 2026-06)
- Attivazione evento: 20 crediti UNA TANTUM, copre fino alla data evento. Nessun rinnovo 30gg, nessuno stato 'sospeso'.
- Primo evento di ogni org: attivazione GRATIS (flag org welcome_event_activation_used, una volta per org). 100 crediti benvenuto restano interi.
- Stati evento: In preparazione | Attivo (fino alla data) | Concluso (data trascorsa).
- Saldo minimo: org su modello crediti deve avere saldo>0 per scritture (saldo 0 = sola consultazione; ripristino automatico dopo ricarica, nessuna riattivazione). Creare evento richiede saldo>=1, nessun consumo. Guardie backend: _assert_org_operational, _assert_can_create_event, _assert_event_operational.
- Legacy org/eventi (senza signup_bonus_granted): esentati, non bloccati.
- Servizio catalogo: key event_active_period, nome 'Attivazione evento', 20 crediti (configurabile da superadmin).
- run_event_renewals: solo manuale (superadmin), conclude eventi a data trascorsa. NESSUN cron. Stripe TEST.
- Account test preview Demo: demo.crmevent@gmail.com / DemoCrm#2026pv (org 4cdfbd7aed3d43b882032892885feef3).

## Changelog 2026-06 (fork corrente)
- **Riorganizzazione Anagrafiche / Staff-Volontari** (solo navigazione+filtri, nessuna migrazione dati): sidebar riordinata (Dashboard, Eventi, Staff/Volontari, Aziende, Anagrafiche, …). Nuova rotta `/staff-volontari` e `/persone` usano lo stesso componente `Persons` con prop `mode` ('staff' | 'anagrafiche'). Staff/Volontari: tab Staff & Volontari (solo is_staff||is_volontario, sub-filtro) · Da classificare (!referente&&!staff&&!volontario) · Team · Turni. Anagrafiche: solo referenti aziende (is_referente), sottotitolo "Referenti e contatti delle aziende". Anagrafica unica (persona con più relazioni compare in entrambe, nessuna duplicazione). Team Leader continua a pescare solo staff/volontari. Testato frontend 14/14 (iteration_42).
- **Super Admin · Modifica anagrafica utenti org**: nuovo `PATCH /api/platform/users/{user_id}/profile` (superadmin) per Nome/Cognome/Email/Cellulare; cellulare obbligatorio E.164 (permette backfill utenti legacy), unicità email, aggiorna solo contatto Brevo (sync_registered_user), non tocca crediti/ruoli/org. `_member_view` ora include nome/cognome. Frontend: `OrgUsers.jsx` ha prop `allowProfileEdit` (gate superadmin) con dialog "Modifica anagrafica"; `OrgUsers` renderizzato dentro la scheda Organizzazione (OrgsTab in PlatformCredits.jsx) come "Utenti dell'organizzazione". Testato backend (400 telefono invalido, 200 + E.164 salvato) e frontend (lista + dialog).
- **Cellulare obbligatorio (E.164) su tutti i percorsi**: flag `needs_phone` in user_payload, gate in App.js, pagina /completa-profilo, endpoint /api/auth/complete-profile; routing AuthCallback/Invite. Testato (iteration_41, backend 9/9, frontend 4/4).
- **Stripe LIVE switch**: modalità Stripe risolta via `_resolve_stripe_mode()` con priorità `CRMEVENT_STRIPE_MODE` → `STRIPE_MODE` → default `test` (server.py ~4475). In `live` usa ESCLUSIVAMENTE i secret `CRMEVENT_STRIPE_*_LIVE`, nessun fallback TEST. Motivo: i secret con prefisso `STRIPE_` sono intercettati/bloccati dall'integrazione Stripe nativa di Emergent (read-only), quindi serve una custom key `CRMEVENT_STRIPE_MODE` modificabile dall'utente. Aggiunta `CRMEVENT_STRIPE_MODE="test"` in backend/.env. **PENDING**: l'utente deve impostare `CRMEVENT_STRIPE_MODE=live` dalla UI Secrets + redeploy, poi verifica finale (mode LIVE, diagnostica PRONTA).
- **Diagnostica Stripe LIVE**: endpoint `GET /api/platform/stripe/live-diagnostics` (Super Admin) read-only, legge i `CRMEVENT_STRIPE_*_LIVE` da env anche in STRIPE_MODE=test con client Stripe isolato; chiamate non transazionali (Balance/TaxRate/WebhookEndpoint). UI: pannello "Diagnostica Stripe LIVE" + pulsante in PlatformCredits.jsx tab "Fatture & Integrazioni". Non espone valori.
- **UI colonna Azioni Eventi (Events.jsx)**: desktop = pulsanti icona+testo (Disponibilità, Pipeline, Percorsi, Calendario) + dropdown "Altre" (Crediti, Briefing) + Modifica/Elimina come icone 9x9; mobile = singolo dropdown "Azioni" con tutte le voci icona+testo. Aggiunto prop `fullActions` a EntityManager (crm.jsx) che delega l'intera cella Azioni alla pagina passando helper {openEdit, onDelete}. Route/permessi/comportamento invariati. Tooltip via attributo `title`.
