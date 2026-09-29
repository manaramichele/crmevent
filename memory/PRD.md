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

