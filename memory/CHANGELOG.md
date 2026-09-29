# CRMEvent — Changelog

## 2026-06 — Flusso inviti utente: mittente, occhio password, stato account
- **(1) Mittente email invito**: sender Resend centralizzato in `email_utils.py` → default `EMAIL_FROM_ADDRESS=hello@crmevent.it` (nome "CRMEvent"). Nessun hardcoding nel frontend. Le email Staff/Volontari (Brevo) NON toccate. In produzione il secret `EMAIL_FROM_ADDRESS` va impostato a `hello@crmevent.it` (o rimosso per usare il default); il dominio crmevent.it è verificato in Resend → qualsiasi mailbox @crmevent.it può inviare.
- **(2) Mostra/nascondi password su /invito** (Invite.jsx): nuovo `PwField` con icona occhio (Eye/EyeOff) su entrambi i campi password (creazione account e accesso). Toggle focus-safe (`onMouseDown preventDefault`, `tabIndex=-1`) → nessuna perdita focus/reset. Requisiti password invariati.
- **(3) Stato account dopo accettazione invito**: `_accept_invite` (flusso Org invite) e `/auth/activate` (flusso person invite) ora impostano sulla Persona `invite_status=account_attivato` + `invite_accepted_at`, membership `active=true`, user `last_login_at`. Il profilo mostra "Account attivo" + "Invito: Accettato · data". Lo `stato` commerciale/operativo (es. "Da contattare") resta un concetto DISTINTO e non rappresenta l'account; lo storico commerciale del Lead non viene mai toccato. Verificato E2E: register org-invite→200, invite_status=account_attivato, invite_accepted_at set, membership attiva.
- ⚠️ Task 4 (separazione Persone in "Referenti aziende" / "Staff & Volontari") NON ancora implementato: richiede analisi non distruttiva delle anagrafiche esistenti → pianificato come intervento dedicato successivo.


## 2026-06 — Normalizzazione cellulare E.164 + telefono non bloccante (Brevo)
- **Normalizzazione E.164** (`_norm_phone`, server.py): gestisce spazi/trattini/parentesi/`00`/`+` già presente; se manca il `+` assume il prefisso di default (Italia +39). Verificato: `3331234567`→`+393331234567`, `333 123 4567`→`+393331234567`, `+39 333 1234567`→`+393331234567`, internazionale `+447911123456` ok, input non validi→None.
- **Salvataggio**: il cellulare è normalizzato in E.164 al submit del form pubblico (`pub_avail_submit`) e usato per dedup persona; a Brevo si invia SOLO il numero normalizzato (attributo `SMS`).
- **Telefono non bloccante + fallback**: `_brevo_avail` non solleva mai; se Brevo rifiuta il telefono (HTTP 400) ritenta l'upsert del contatto **senza SMS**, così il contatto entra comunque in lista e riceve le email; l'errore/warning è loggato in `brevo_sync_log` (`phone_rejected`). Disponibilità/persona/CF non vengono mai persi.
- **Form pubblico** (Partecipa.jsx): campo cellulare ora con **selettore prefisso internazionale** (default 🇮🇹 +39, modificabile) + numero; il numero è combinato col prefisso solo se non inizia già con `+`/`00`.
- Verificato E2E in preview: submit 200 e persone salvate con telefono E.164 (la sync reale Brevo + fallback si testano in produzione con chiave). `BREVO_AVAILABILITY_ENABLED` resta OFF.


## 2026-06 — Fix orari mobile compatti + attivazione template Brevo via API
- **Campi orario mobile** (Partecipa.jsx): input `type="time"` ora con `style={{width:150, maxWidth:"100%"}}` (inline → sovrascrive il `w-full` di shadcn), impilati (Dalle sopra, Alle sotto). Larghezza compatta ~150px, mai oltre la card a 375/390px. Nessuna modifica alla logica disponibilità.
- **Attivazione template Brevo (Bozza→Attivo)**: nuovo `POST /api/brevo/availability-templates/activate` (superadmin) → `PUT /smtp/templates/{id} {isActive:true}` via API Brevo (attivazione REALE su Brevo, nessuna forzatura del DB CRMEvent). `brevo_client.activate_template()`. Nel pannello, accanto allo stato "Bozza" compare il pulsante **"Attiva in Brevo"** per ciascun template; dopo l'attivazione "Aggiorna stato" rileva automaticamente Attivo (il pannello legge lo stato reale via `get_templates().isActive`).
- Flag `BREVO_AVAILABILITY_ENABLED` mantenuto **OFF** (preview e produzione). Nessun invio automatico attivato.
- ⚠️ Le due correzioni sono in preview: serve un nuovo deploy per averle in produzione (compresi input compatti e pulsante "Attiva in Brevo").


## 2026-06 — Form pubblico responsive (Dalle/Alle) + due blocchi Brevo distinti + verifica go-live
- **Responsive form pubblico** (Partecipa.jsx): campi orario Dalle/Alle passati da flex a `grid grid-cols-1 min-[420px]:grid-cols-2` con input `w-full min-w-0` → sotto 420px impilati (Dalle sopra, Alle sotto), zero overflow/sovrapposizioni a 320/360/375/390/430px, compatibili col selettore orario nativo iOS/Android. Nessuna modifica a logica/dati.
- **Due blocchi distinti** ripristinati sulla stessa pagina (Dashboard piattaforma): "Automazioni email · Funnel Demo CRMEvent" (invariato) e "Automazioni email · Staff & Volontari". Rimosso il route/menu separato `/marketing/disponibilita` (consolidato). Pulsanti separati: "Crea/Verifica lista Brevo" (nuovo endpoint `POST /api/brevo/availability-list/ensure`) e "Crea/Verifica template"; badge "Invii automatici Staff & Volontari: ATTIVI/DISATTIVATI"; trigger mostrati per ogni template.
- **Causa scomparsa sezione**: nell'iterazione precedente il pannello era stato spostato dalla pagina del Funnel Demo a un route separato e rimosso dalla pagina Funnel → non più visibile lì (più deploy non ancora propagato). Risolto consolidando entrambi i blocchi sulla stessa pagina.
- **Verifica trigger go-live** (da codice): 1ª email "Disponibilità ricevuta" alla compilazione del form; 2ª email "Partecipazione confermata" solo al passaggio a Confermata (una sola volta); invii transazionali diretti da CRMEvent (nessuna automazione Brevo); invio solo se template `isActive`; mai CF/data nascita/rimborsi a Brevo.
- **Baseline produzione (deployer)**: BREVO_API_KEY presente; BREVO_AVAILABILITY_ENABLED assente (OFF). Preview: flag impostato a `on` (inerte senza chiave). Go-live: aggiungere il secret in produzione + Re-publish.


## 2026-06 — Evento · Descrizione delle singole giornate + Menu Marketing (Email disponibilità)
- **Descrizione singole giornate evento** (verificato backend e2e): campo `giorni_descrizioni` (dict ISO-date → testo breve) sul modello Event. In creazione/modifica Evento (Events.jsx) nuovo tipo campo `daydesc`: genera automaticamente una riga per ogni giorno tra Data inizio e Data fine evento (anche evento di 1 solo giorno), campo breve e facoltativo "Descrizione giornata". Le descrizioni sono legate alla data specifica.
- Pruning automatico (model_validator): al salvataggio mantiene solo le date comprese nell'intervallo evento e non vuote → se cambi le date, le descrizioni delle date che restano nel range sono preservate, quelle fuori range vengono scartate, le nuove partono vuote. Verificato: create scarta date fuori range; update con restringimento a 1 giorno preserva solo la data in range.
- `_avail_days` espone `descrizione` solo per i giorni fase "evento"; allestimento/disallestimento restano con le rispettive etichette. Il modulo pubblico (Partecipa.jsx) mostra la descrizione della giornata sopra il badge EVENTO. Sorgente unica = configurazione Evento (riutilizzabile in futuro in Team/Turni → Briefing).
- **Menu**: la sezione "Email disponibilità eventi" è stata spostata sotto **Marketing CRMEvent — Piattaforma → "Email disponibilità"** (route `/marketing/disponibilita`, `MarketingBrevo.jsx`, solo Super Admin) invece che nella Dashboard piattaforma. Pulsante rinominato "Crea/Configura in Brevo" (idempotente), due pulsanti test etichettati, colonna Test rimossa.
- ⚠️ Entrambe le modifiche sono in preview e richiedono un nuovo deploy per apparire in produzione. BREVO_AVAILABILITY_ENABLED resta OFF.


## 2026-06 — Super Admin · Email disponibilità eventi (scheda Marketing/Brevo) — verificato frontend 100%
- Riepilogo "Contatti in lista" nel pannello: List ID, **Contatti totali letti direttamente da Brevo** (`GET /contacts/lists/{id}` → totalSubscribers/uniqueSubscribers, mai calcolati dal DB CRMEvent), Ultima sincronizzazione (ultimo `brevo_sync_log` disponibilità con esito sent/synced) e Stato/Errore sincronizzazione (ultimo error se più recente dell'ultimo successo). Nessun grafico/statistica avanzata.
- Lista unica Brevo **«CRMEvent · Disponibilità eventi»** confermata: ogni compilazione del modulo pubblico crea/aggiorna il contatto Brevo e lo associa a questa unica lista (mai una lista per Evento). Il List ID viene creato via API se assente e **persistito** in `brevo_config` (key=availability) per gli invii successivi; helper `_ensure_avail_list`/`_avail_list_id`.
- Dedup persona: contatto già presente → `update_contact` (PUT listIds+attributi, MAI emailBlacklisted → nessun resubscribe, nessun duplicato); nuovo → `create_contact`. Storico partecipazioni per-Evento resta in CRMEvent (collection `availabilities`, una riga per Evento) e non si perde al partecipare a un nuovo Evento.
- Mai inviati a Brevo: Codice Fiscale, Data di nascita, dati rimborsi (attributi limitati a NOME/COGNOME/SMS/EVENTO/DATA_EVENTO/ORGANIZZAZIONE/RUOLO_EVENTO/STATO_DISPONIBILITA).
- GET `/api/brevo/availability-templates` ora restituisce anche `list{id,name}`; POST `/api/brevo/create-availability-templates` garantisce/persiste la lista. UI panel mostra "Lista Brevo unica" + List ID.
- Nuova sezione "Email disponibilità eventi" in /piattaforma (`AvailabilityEmailPanel.jsx`), **riservata al Super Admin** (org-admin/utenti NON la vedono; architettura multi-tenant ready per CRMEvent Pro futuro, senza esporre nulla in UI pubblica).
- Mostra i 2 template master universali (`CRMEvent · Disponibilità ricevuta`, `CRMEvent · Partecipazione confermata`) con: nome, tipo (Disponibilità/Conferma), Template ID Brevo, stato Attivo/Bozza/Non creato, ultimo aggiornamento (modifiedAt Brevo). Badge stato generale "Invii automatici: ATTIVI/DISATTIVATI" da `BREVO_AVAILABILITY_ENABLED` (resta **off** → DISATTIVATI).
- Pulsanti: **Aggiorna stato** (reload), **Crea template in Brevo** (solo se mancanti; anti-duplicato: se i 2 master esistono già riusa i Template ID), **Invia email di test** per ciascun template (scelta Evento di Organizzazione tipo Test + email destinatario; usa i dati reali dell'Evento incluso il logo via HTML master inline, indipendente dallo stato attivo/bozza; l'invio manuale NON attiva gli automatismi e NON dipende dal flag).
- Endpoint tutti blindati a `require_superadmin`: `GET /api/brevo/availability-templates` (esteso: type_label + updated_at), `GET /api/brevo/availability-test-events` (eventi di org type=test), `POST /api/brevo/availability-test-email` (invio reale transazionale, no-op informativo se BREVO_API_KEY assente), `POST /api/brevo/create-availability-templates`.
- In preview (BREVO_API_KEY vuota): configured=false → avviso "Brevo non configurato…"; pulsante test resta visibile e mostra messaggio informativo senza errori. Codice Fiscale MAI inviato a Brevo; chiave API mai esposta.


## 2026-06 — Marketing · Social — SEPARAZIONE SCOPE Platform vs Organization
- Introdotto scope esplicito senza duplicare la logica: `require_admin`/`require_org_admin` onorano `?scope=platform` → solo Super Admin → org_id sentinella `__platform__` (bypassa X-Org-Id/org attiva). Tutti gli endpoint social + pubblicazione IG funzionano in platform scope indipendentemente dall'org attiva.
- Frontend: nuovo client `lib/platformApi.js` (forza `scope=platform`). Le pagine Social/SocialCalendar/SocialSettings usano platformApi. Menu spostato nel gruppo Super Admin "Marketing CRMEvent — Piattaforma"; rimosso per Admin Org/Utenti (CRMEvent Pro futuro, codice mantenuto). Badge "Marketing CRMEvent — Piattaforma" nell'header.
- Migrazione dati (preview) org CRMEvent (brand=CRMEvent, era 976fd… "Org Social Test") → `__platform__`: social_settings 1, social_posts 34 (incl. piano ottobre), social_media 6 + 6 files referenziati, social_ai_generations 20, social_publish_logs 33, social_calendar 2. social_accounts: 0 (nessun account IG salvato in preview). Script: backend/migrate_social_platform.py.
- FASE E pubblicazione IG invariata e ora platform-scope-ready (require_org_admin+scope=platform → __platform__, no X-Org-Id). Nessuna pubblicazione reale effettuata.
- IMPORTANTE: in preview NON esiste "Trio Events" né alcun token @crmevent → OAuth @crmevent e Trio Events sono in PRODUZIONE. La migrazione dell'account IG allo scope platform va rifatta in produzione (stesso meccanismo scope). Verificato: platform scope brand=CRMEvent/34 post; non-superadmin scope=platform→403; org scope social_test→0 post.


## 2026-06 — Marketing · Social — FASE E: pubblicazione Instagram (immagine singola feed, preview)
- Pubblicazione ufficiale via Instagram API (graph.instagram.com): container a 2 passi — `create_media` (image_url+caption) → `publish_media` (creation_id). Solo immagine singola feed + caption (caroselli/Stories/Reels NON attivati).
- Endpoint `POST /api/social/posts/{id}/publish` {confirm}: Pilota automatico resta OFF; richiede **conferma esplicita** (428 se confirm assente). Flusso Bozza → Approva → (Programma | Pubblica ora) → Instagram.
- Controlli pre-pubblicazione: account IG collegato + token non scaduto, post approvato/programmato, creatività presente, formato feed (1:1 o 4:5), caption presente. Se manca qualcosa → 400 con elenco puntuale.
- Immagine per Meta: `/api/files/{id}` è autenticato (Meta non può scaricarlo) → nuovo endpoint PUBBLICO `GET /api/social/public/creative/{token}` che serve una copia **JPEG** (Instagram feed richiede JPEG) generata con `social_creative.to_jpeg`; URL assoluto HTTPS da BACKEND_PUBLIC_URL. Collezione `ig_public_media` (token) + indice.
- Anti-duplicati: lock atomico (status→"publishing" solo se approved/scheduled e published_media_id vuoto) + blocco se già published/published_media_id → 409.
- Log in `social_publish_logs`: publish_requested / publish_success (con instagram media_id) / publish_failed (con errore API). **Nessun access_token** loggato.
- Frontend: pulsante "Pubblica ora" (rosa Instagram) nell'editor per post approvati/programmati, con conferma `window.confirm`.
- Verificato in preview SENZA pubblicare nulla: validazione completa (bozza vuota → 5 problemi), post approvato senza account IG → 400 "account… token valido", endpoint pubblico raggiungibile senza auth (404 su token ignoto). Il primo post reale su @crmevent sarà pubblicato manualmente dall'utente.


## 2026-06 — Marketing · Social — FASE D: Instagram/Meta OAuth (preview, publishing OFF)
- Modulo `instagram_utils.py` (Instagram API with Instagram Login, host graph.instagram.com): authorize_url, exchange_code (short-lived), long_lived_token (~60gg), refresh_token, me(), parse_signed_request (HMAC-SHA256 con META_APP_SECRET). Segreti SOLO da env (META_APP_ID/META_APP_SECRET), mai hard-coded. Username/password IG mai ricevuti/salvati: solo token.
- Endpoint (server.py): GET /api/oauth/instagram/start (require_org_admin, 400 se non configurato), GET /api/oauth/instagram/callback (state JWT + ig_oauth_states single-use, scambio code→long-lived, salva su social_accounts org-scoped, redirect a /marketing/impostazioni?instagram=connected|error), POST /api/social/accounts/{id}/refresh-token, POST /api/oauth/instagram/deauthorize (signed_request → revoca token/stato deauthorized), POST /api/oauth/instagram/data-deletion (signed_request → cancella dati account + confirmation_code + status url), GET /api/oauth/instagram/data-deletion/status.
- Multi-tenant: un social_account instagram per org; deauthorize/data-deletion individuano l'org dal ig_user_id. access_token mai esposto in API (sanitizer _san_account). Indici: ig_oauth_states TTL, social_accounts (platform,ig_user_id), ig_data_deletions.
- Redirect URI produzione: https://crmevent.it/api/oauth/instagram/callback ; preview: https://manage-events-12.preview.emergentagent.com/api/oauth/instagram/callback. Deauthorize/data-deletion URL registrati su Meta come concordato.
- Frontend: SocialSettings — "Collega Instagram" (avvia OAuth), stato Collegato/username, "Aggiorna token", "Scollega", toast su ?instagram=connected|error.
- Pubblicazione automatica DISATTIVATA (nessun endpoint media_publish). Verificato in preview: start 400 senza creds, signed_request valido/invalido, status 404, no token leak. Roundtrip OAuth completo richiede META_APP_ID/SECRET (da inserire dall'utente) + login IG reale.


## 2026-06 — Marketing · Social — FASE C: Creatività immagini (verificato E2E)
- Renderer server-side `social_creative.py` (Pillow): compone creatività on-brand nei formati Instagram 4:5 (1080×1350), 1:1 (1080×1080), 9:16 (1080×1920). Brand kit automatico (logo ufficiale CRMEvent dal file pubblico, colore Tiffany, nome brand, colori da impostazioni). Il logo NON viene mai generato dall'AI.
- Sistema di 6 template riutilizzabili: educational, problema_soluzione, funzionalita, foto_evento, quote, commerciale. Il Social AI sceglie il template dalla categoria del post (CATEGORY_TEMPLATE); l'utente può cambiarlo.
- 3 modalità di sfondo: (A) Foto dalla Libreria Media con auto-suggest della più pertinente; (B) Screenshot/Mockup CRMEvent da Libreria (template funzionalita, layout a pannello con card); (C) Immagine AI generata con Gemini Nano Banana (gemini-3.1-flash-image-preview via Emergent LLM key) quando manca materiale o su scelta utente — prompt che vieta testo/logo nell'immagine. Fallback a sfondo brand se l'AI non è disponibile.
- Overlay: hook (title) grande + sottotitolo (body) breve + tag categoria + CTA pill (adattamento automatico/troncamento se lunga) + logo chip + brand name. Scrim/gradienti per leggibilità.
- Endpoint `POST /api/social/posts/{id}/creative` {mode,template,format,media_id,show_cta,ai_prompt}: renderizza PNG, lo carica su Object Storage, lo salva in Libreria Media (category='creative', post_id) e collega `creative_media_id`/`creative_meta` al social_post. `/social/meta` espone `creative_templates`.
- Frontend: pannello "Creatività immagine" nell'editor del post (`Social.jsx`): Genera/Rigenera, anteprima, cambia modalità/template/formato/foto, mostra/nascondi CTA, Scarica. Flusso: Post → Genera creatività → Anteprima → Modifica/Rigenera → Approva.
- Testato: 3 modalità (photo/screenshot/ai) HTTP 200, PNG dimensioni corrette per tutti i formati, template funzionalita e commerciale-AI verificati visivamente, creatività salvate in libreria e collegate al post.


## 2026-06 — Marketing · Social (Social Media Manager AI) — FASE A + B (testato E2E, iter18 100% PASS)
- Nuovo modulo multi-tenant "Marketing → Social" (Social / Calendario editoriale / Impostazioni Social). Tutte le collezioni org-scoped via `oq(user)`.
- Collezioni: `social_settings`, `social_accounts`, `social_posts`, `social_calendar`, `social_media`, `social_ai_generations`, `social_publish_logs` (+ indici `org_id`).
- Backend `server.py` sezione "MARKETING · SOCIAL AI": settings GET/PUT, dashboard, meta, posts CRUD + approve/schedule, generate (AI), regenerate, plan/generate, calendar, media (upload storage Emergent + /api/files), accounts (scaffold Instagram, status pending_connection), logs. Permessi: `require_org_admin` (settings/accounts/approve/schedule), `require_admin` (generate/list/edit/delete/media/dashboard).
- LLM isolato in `social_ai.py` (gpt-5.4-mini via Emergent LLM key) — separato dalla chat assistente (`support_service.py`). `generate_post` e `generate_plan` con 12 categorie editoriali e anti-ripetizione. Contenuti specifici sul mondo eventi/sport (staff, volontari, turni, sponsor, briefing) — mai generici.
- Uso dati CRMEvent: `_event_public_context` invia all'AI SOLO dati pubblicabili evento (nome, date, località, percorsi, sponsor confermati, giorni all'evento). MAI email/telefoni/dati personali.
- Pilota automatico: presente nel DB, forzato SEMPRE su OFF in questa fase. Nessuna pubblicazione automatica: tutto richiede approvazione manuale.
- Frontend: `Social.jsx` (dashboard, post grid, "Crea con AI", "Genera piano editoriale", editor con Rigenera/Modifica/Approva/Programma/Elimina, tab Libreria Media), `SocialSettings.jsx` (brand, tone, CTA, frequenza, giorni/orari, logo, colori, hashtag, cose da evitare, istruzioni AI, connessione Instagram, Autopilot OFF), `SocialCalendar.jsx` (contenuti per giorno con stati). Menu "MARKETING" in `Layout.jsx`, route in `App.js`.
- Instagram/Meta (Fase D) NON implementato: solo scaffold che salva l'handle. Generazione creatività immagini (Fase C) predisposta ma non ancora attiva.


## 2026-06-26 — Google Analytics 4 + Consent Mode v2 (verificato E2E, TEST A/C/D/E PASS)
- GA4 `G-PZK7J854DS` via gtag.js. Stub + Consent Mode v2 default (tutti `denied`, wait_for_update:500) in public/index.html PRIMA di GA; `gtag('config', ..., {send_page_view:false, anonymize_ip:true})`. Script di raccolta caricato SOLO su host `crmevent.it` (preview/dev/test non contaminano la proprietà).
- `src/lib/analytics.js`: applyConsent/saveConsent (localStorage `crmevent_cookie_consent`), trackPageView (SPA, solo se analytics granted), trackEvent. Nessun dato personale nei parametri.
- `src/components/CookieConsent.jsx`: primo banner cookie (Accetta tutti / Solo necessari / Gestisci preferenze), rifiuto facile quanto accetta, riapribile da footer "Preferenze cookie" (evento `open-cookie-preferences`). Aggiorna Consent Mode via `consent update`.
- SPA page_view: `RouteTracker` in App.js su cambio route (send_page_view:false → nessun duplicato).
- Eventi: pricing_view, demo_request_click, demo_request_submit, contact_submit, sign_up_start, sign_up, login. Conversioni consigliate: sign_up, demo_request_submit, contact_submit (solo su invio riuscito).
- File: public/index.html, src/lib/analytics.js, src/components/CookieConsent.jsx, src/App.js, src/components/Footer.jsx, src/pages/{Register,Login,Pricing,LandingPage}.jsx.


## 2026-06-26 — Fase 2 Ospitalità & Pasti: Anagrafica Strutture + Maps/QR nel Briefing (verificato: backend curl end-to-end, frontend PHASE2_UI_OK)
- Nuova collection `structures` (org-scoped, CRUD via crud_routes): Nome, Tipologia, Indirizzo, CAP, Città, Provincia, Telefono, Email, Sito, Referente, Tel referente, Note, **Link Google Maps**. Tipologie con "+ Aggiungi" (SettingSelect `tipologie_struttura`).
- `Lodging`/`Meal` ora hanno `struttura_id`; helper `_attach_structures` arricchisce lodgings/meals (in `event_hospitality` e `_build_briefing`) con i dati della struttura letti UNA volta dall'anagrafica — nessuna duplicazione del link nelle assegnazioni.
- Frontend: componente riutilizzabile `StructureSelect` (dropdown strutture + "+ Nuova struttura" al volo) nei form Alloggio/Pasto (quindi anche in assegnazione multipla); manager "Strutture" (lista/crea/modifica/elimina) accessibile da Ospitalità & Pasti.
- Assegnazione multipla già esistente ora passa `struttura_id` scelta dall'anagrafica.
- `MapsLink` (link "📍 Apri in Google Maps" + QR code visibile solo in stampa/PDF via `print:` con lib `qrcode`) mostrato nelle righe alloggio/pasto e nel Briefing (sezione Ospitalità & pasti), recuperato automaticamente dalla struttura.
- Verificato: creazione struttura → assegnazione (bulk) con struttura → `event_hospitality` e `briefing-live` restituiscono `struttura` con `google_maps_url`; UI manager + selettore funzionanti. Multi-tenant e Stripe/FIC invariati. Dati QA rimossi.


## 2026-06-26 — Fase 1 UX: dropdown "+ Aggiungi nuovo" + chat compatta (verificato E2E, PHASE1_PASS)
- Nuovo componente riutilizzabile `SettingSelect` (frontend/src/components/SettingSelect.jsx): dropdown su liste settings dell'Organizzazione con azione inline "+ Aggiungi nuovo" → crea la voce (PUT /settings), la seleziona subito, mantiene il form aperto e i dati compilati. Anti-duplicati case/spazi. Il valore corrente è sempre reso come opzione (nessun "vuoto" dopo l'aggiunta). Esclusi i valori di sistema (ruoli/stati/tipi org).
- Applicato a CompanyDialog (campo Settore, `settingKey="settori"`) e reso disponibile a livello generico in `crm.jsx` Field via `field.settingKey` per gli altri menu configurabili.
- Chat assistenza: bottone rotondo compatto 52px desktop / 48px mobile (icona), non copre più i contenuti; pannello invariato all'apertura.
- Verificato: creazione nuovo Settore durante creazione Azienda → form resta aperto, nome preservato, nuovo settore selezionato e persistito org-scoped; FAB 52×52.
- File: SettingSelect.jsx (nuovo), CompanyDialog.jsx, crm.jsx, SupportChat.jsx. Nessuna modifica a Stripe/FIC/OAuth/multi-tenant.


## 2026-06-26 — /invito: logo ufficiale + nome demo Nova Events (verificato E2E)
- `/invito` ora usa il PNG ufficiale `/logo-crmevent.png` (fondo bianco) al posto dell'icona generica. Verificato che Login/Registrazione/Reset/Attiva già usavano il PNG corretto (dark su fondo nero, light su fondo bianco).
- Nome demo/test standard: **Nova Events** (placeholder "+ Nuova organizzazione" aggiornato). Rimosso ogni riferimento a "TriO" dal codice; l'org di test creata dall'agente è stata rinominata TriO Events → Nova Events (e l'evento di test rinominato). Nessuna org reale toccata.
- Re-test E2E su /invito (Nova Events): logo ufficiale presente, digitazione "Laura Verdi" + password 15 caratteri con focus mantenuto (FOCUS_PASS), nessun riferimento a TriO.


## 2026-06-26 — Bugfix /invito focus loss (verificato con test di digitazione E2E)
- Causa: nel componente `Invite.jsx` il wrapper `Card` era definito DENTRO il componente. A ogni carattere digitato lo state cambiava → re-render → nuova identità di `Card` → React smontava/rimontava l'intero sottoalbero (inclusi gli input) → perdita del focus.
- Fix: `Card` spostato a livello di modulo (una sola definizione). Nessun re-render distruttivo, la validazione del token resta one-shot (useEffect con guard `done`, deps [token,setUser]).
- Test reale: digitazione carattere-per-carattere su Nome ("Mario Rossi") e Password (14 caratteri) → focus mantenuto in entrambi i campi, valori completi. Nessuna modifica a token/membership/isolamento multi-tenant.


## 2026-06-26 — Organizations & Users management (multi-tenant) — verified: backend Scenari A–E via curl + frontend e2e 17/17 PASS
- New `memberships` collection (user↔org many-to-many, roles admin_org|user, active, permissions{} future). Migration idempotente per utenti operativi esistenti (staff/volontari esclusi).
- Org typing: `type` cliente|interna|test + `status` active|disabled. Interna/Test: nessun trial/Stripe/fatturazione, accesso operativo pieno (`_sub_summary`). Cliente: trial 14gg + Stripe come prima.
- Active-org scoping generalizzato: `_resolve_active_org` valida `X-Org-Id` contro le membership (superadmin=qualsiasi org); `oq()` invariato → isolamento multi-tenant garantito, nessun bypass. Selettore "Org attiva" esteso agli utenti multi-org.
- Super Admin: crea/modifica org (`+ Nuova organizzazione`), scheda org con tab Dati/Utenti e accessi/Eventi/Audit Log. Gestione membri (aggiungi esistente, cambia ruolo, disabilita/riattiva, rimuovi — dati conservati) + guardia "ultimo Admin Organizzazione" per org Cliente.
- Inviti: token sicuro monouso a scadenza via Resend → `/invito` (registrazione password o Google con verifica email; mismatch bloccato 403). Reinvio (invalida token) e revoca. Nessun nuovo trial/abbonamento/org all'accettazione.
- Lead: distinti da Utente/Org; scheda Lead con "Account CRMEvent trovato", Collega account, Assegna a organizzazione, Invita in CRMEvent (con auto-link lead all'accettazione).
- Audit Log esteso: org_created/updated, member_added/removed/role_changed/enabled/disabled, invite_sent/resent/revoked/accepted, lead_linked, org_access/switch. Colonne Interessato + Dettaglio (old→new). Sola lettura, solo Super Admin.
- Super Admin usa CRMEvent operativamente in un'org Interna (es. TriO Events) senza secondo account.
- File: server.py; frontend pages Platform.jsx, OrgDetail.jsx (nuovo), Invite.jsx (nuovo), Leads.jsx, AuditLog.jsx; Layout.jsx, AuthContext.js, App.js, lib/api.js.


## 2026-06-26 — Audit Log Super Admin + indicatore "org attiva" (verificato: backend curl create/list + 403 organizer; frontend screenshot)
- Aggiunta collection append-only `audit_logs` (schema estensibile: actor, action, action_label, org_id/org_name, meta) — nessun dato sensibile (no password/token/secret/pagamenti).
- `record_audit()` helper + `AUDIT_ACTION_LABELS` (predisposto per subscription_change / account_intervention futuri).
- `POST /api/platform/audit/org-access` (registra accesso/cambio org, superadmin-only) chiamato da `setActingOrg` in AuthContext ad ogni selezione/cambio "Org attiva".
- `GET /api/platform/audit` con filtri org_id / actor_user_id / date_from / date_to / action (superadmin-only). NESSUN endpoint di update/delete → non modificabile via UI.
- Nuova pagina `AuditLog.jsx` (rotta `/audit`, SuperAdminOnly) nel gruppo "Amministrazione piattaforma": tabella Data/Ora | Super Admin | Organizzazione | Azione + filtri org/superadmin/periodo.
- Banner giallo evidente "Stai operando come Super Admin in: [Org]" sulle pagine operative; selettore "Org attiva" sempre visibile.
- Scoping multi-tenant invariato. File: server.py, frontend/src/{pages/AuditLog.jsx, context/AuthContext.js, components/Layout.jsx, App.js}.


## 2026-06-26 — Super Admin operational navigation restored + active-org scoping (backend 13/13 pytest PASS; frontend e2e 100%)
- Fixed: Super Admin had lost the operational CRMEvent menu after the Stripe/FIC work.
- Super Admin now sees the full operational menu (Dashboard, Eventi, Aziende, Persone, Ospitalità & Pasti, Sponsor & Partner, Attività, Follow-up, Impostazioni) PLUS a separate "Amministrazione piattaforma" group (Dashboard piattaforma, Lead, Supporto).
- Added an "Org attiva" switcher in the header: frontend sends `X-Org-Id`; `require_admin` validates it for superadmin only (428 no header, 404 invalid org) and returns an ephemeral principal with `org_id` set so `oq()` keeps every query org-scoped — no cross-tenant bypass.
- App.js: `AdminOnly` now allows superadmin (blocks only volunteers); `HomeRoute` sends superadmin to the operational Dashboard; `SuperAdminOnly` still guards /piattaforma, /lead, /supporto.
- Verified: organizer sees only operational menu, no platform group/switcher, and is blocked (redirect + 403) from all superadmin routes/APIs.
- No Stripe/FIC config changed. Files: server.py, frontend/src/{lib/api.js, context/AuthContext.js, components/Layout.jsx, App.js}.
- Test org seeded for verification: organizer.test@crmevent.it / "Eventi Milano SRL".


## 2026-06 — Multi-tenant SaaS + Pricing + Trial (backend 22/22 pytest PASS; frontend e2e verified)

### Multi-tenant data isolation (release gate — VERIFIED)
- Retrofitted the whole app to multi-tenant. Every operational document carries `org_id`.
- `oq(user, **extra)` helper pins the caller's `org_id`; applied in the `crud_routes` factory AND every manual endpoint (dashboard, search, notifications, persons-enriched, persons-match, person/company detail, company-contacts, invite, set-access, hospitality, briefing `_build_briefing(event_id, org_id)` + versions, me/*, settings per-org, upload/download).
- Anti-IDOR: GET/PUT/DELETE by id scoped `{"id": item_id, "org_id": ...}` → cross-tenant → 404, no mutation.

### Roles
- `superadmin`: platform owner CRMEvent (ADMIN_EMAIL, org_id=null). Sees `/piattaforma`. No org CRM access.
- `admin`: organization owner. `require_admin` = role admin AND org_id.
- `staff`/`volunteer`: org members, personal area only.

### Registration & Trial
- `POST /api/auth/register-organization`, `POST /api/auth/complete-organization` (Google). 14-day trial, no card. Trial end = limited access, data preserved (no deletion).
- `/prezzi`, `/registrati`, `/completa-organizzazione`, `/account`, `/piattaforma` + role-based nav + trial banner.

## 2026-06 — Stripe subscription billing (TEST MODE — verified end-to-end)

### Stripe (Flow A claimable sandbox, test mode)
- Sandbox provisioned; env: STRIPE_SECRET_KEY/PUBLISHABLE_KEY/ACCOUNT_ID/WEBHOOK_SECRET/MODE (backend-only).
- `setup_stripe.py`: single Product "CRMEvent" + two recurring EUR prices — `crmevent_monthly` (19,90 €) and `crmevent_yearly` (199 €), auto-renew.
- Endpoints: `GET/PUT /api/account/billing` (org-level Italian billing details), `POST /api/account/checkout` (subscription Checkout, requires billing), `POST /api/account/portal` (Stripe Customer Portal), `POST /api/stripe/webhook` (signature-verified), `POST /api/account/sync-subscription` (fallback sync), `GET /api/account/invoices`, `GET /api/platform/subscriptions` (superadmin).
- Webhook handles: customer.subscription.created/updated/deleted, checkout.session.completed, invoice.paid/payment_succeeded, invoice.payment_failed → syncs `organizations.subscription` status (active/past_due/canceled/expired) + records invoices.
- Status map: trialing/active→active, past_due/incomplete→past_due, canceled→canceled, unpaid→suspended, incomplete_expired→expired.
- Billing details per Organization (edited by org admin) with Italian fields (ragione sociale/nome-cognome, indirizzo, CAP, città, provincia, paese, CF, P.IVA, SDI, PEC); handles no-VAT and foreign customers (Italian-only fields hidden for non-IT / privato).
- Frontend: Account page (billing form + plan toggle monthly/yearly + Attiva/Gestisci abbonamento), Platform "Abbonamenti" table (org, stato, ciclo, importo, rinnovo, Stripe Customer/Subscription id, stato fatturazione).

### E-invoicing (Fatture in Cloud) — SCAFFOLD ONLY (per user)
- `invoices` collection with fields: org_id, stripe_invoice_id, numero_stripe, data, imponibile, iva, totale, valuta, hosted_invoice_url, stripe_pdf, payment_status + FIC placeholders (fic_document_id, fic_numero, fic_data, fic_stato_documento="da_emettere", fic_stato_sdi="non_inviato", fic_pdf_url).
- Hook: `_record_invoice()` creates/updates an invoice row on every paid/failed Stripe invoice, ready for FIC issuance. NO real FIC/SDI calls yet — awaiting FIC OAuth credentials + go-ahead.

### Verified (Stripe test mode)
- Monthly → active; Yearly → active; Failed payment (pm_card_chargeCustomerFail, incomplete) → past_due; Cancel → canceled.
- Signed webhooks delivering in preview (invoices recorded). Multi-tenant isolation on invoices/subscriptions (org A cannot see B; org-admin blocked from /platform → 403). All test data purged (Stripe customers deleted + Mongo cleaned).

### Security
- All Stripe keys backend-only (.env). Webhook signature verified via STRIPE_WEBHOOK_SECRET. Multi-tenant isolation preserved on all Stripe/billing data.

### NOT done (awaiting user)
- LIVE mode: not activated (still test). Fatture in Cloud integration: scaffold only.
- Tax handling: Stripe "DIY" (no Stripe tax) — VAT/e-invoicing handled by CRMEvent via FIC. Prices shown "+ IVA".

## 2026-09-26 — GA4 Stripe subscription funnel tracking
- Added GA4 e-commerce events: `begin_checkout` (fired in Account.jsx before Stripe redirect) and `purchase` (fired only after Stripe confirms payment_status=paid).
- New backend endpoint `GET /api/account/checkout-confirmation?session_id=` verifies the checkout session is really paid and returns ONLY non-personal data (transaction_id, value, currency, billing_cycle).
- purchase deduplicated by Stripe transaction_id stored in localStorage (survives refresh/revisit/re-open).
- All events go through existing trackEvent -> respect Consent Mode v2 + cookie prefs. No PII sent to GA4.
- Did NOT modify: GA4 impl, Measurement ID G-PZK7J854DS, Consent Mode v2, cookie banner, auth, Stripe logic, FIC billing.

## 2026-09-26 — Fase A: Dataset Demo + Demobot sui dati reali
- Creato org "Demo" (type=test) nel preview (id=b7f40862230441b9a0bedabefe8dab49). Seed idempotente in /app/backend/seed_demo.py (id deterministici prefisso demo_, upsert → nessun duplicato in re-run).
- Dataset (tutto org-scoped su org Demo): 3 eventi (Bologna City Run 2026 attivo/completo, Sunset Triathlon 2027 pianificato, Green Trail 2026 concluso), 34 persone (Staff/Volontari, email @example.com), 7 team, 14 turni (2 scoperti volutamente), 17 aziende, 12 deal pipeline (pipeline 42.500 > confermato 22.500), 22 attività (4 scadute), 11 follow-up (3 scaduti), 4 strutture, 8 pernottamenti, 12 pasti (17-18 ott, costi org/persona), 3 mappe.
- Demobot esteso: /support/chat ora inietta un contesto dati operativi LIVE (build_org_data_context in server.py) STRETTAMENTE filtrato per org_id, solo per manager (admin org / superadmin con X-Org-Id). support_service.answer_question usa SYSTEM_DATA quando ci sono dati org: how-to→KB, dati→DB org. Isolamento verificato: agendo su altra org non trapela nulla di Demo.
- Prod: il seed va eseguito SOLO dopo conferma utente; trova la Demo esistente (per nome+type) senza creare duplicati.

## 2026-09-26 — Fase B: gestione SuperAdmin Account/Org + dataset Demo
- Nuovi endpoint superadmin (server.py): GET /platform/users (elenco account: nome, email, org, ruolo, stato, creazione, ultimo accesso, memberships); PATCH /platform/users/{id} (disable/enable); DELETE /platform/users/{id} (guardie: superadmin non eliminabile, no self-delete, blocco se unico admin_org di org cliente; preserva Persona e dati org, scollega owner/persona, elimina sessioni/token); DELETE /platform/organizations/{id} (richiede confirm_name == nome esatto; cascade solo org-scoped + settings by id + account staff/volontari; detach altri account); POST /platform/organizations/{id}/seed-demo (SOLO type=test, idempotente).
- Audit: nuove azioni account_disabled/enabled/deleted, org_disabled/enabled/deleted, demo_seeded.
- Frontend: Platform.jsx tabella Account utenti con disable/elimina (dialog con testo esatto richiesto) + loadAll con Promise.allSettled (resiliente); OrgDetail.jsx zona pericolosa nel tab Dati: Popola/Ripristina dati Demo (solo type=test, con checkbox wipe e conferma) + Elimina organizzazione (input nome esatto).
- FIX critico seed_demo.upsert: ora scoped by (id, org_id) → seedare una seconda org test non ruba piu i record della prima. Regressione verificata: seed A, seed B, counts(A) invariati; cleanup B non tocca A.
- Testato: iteration_14.json backend 8/8, frontend ~90
## Fase B — gestione SuperAdmin Account/Org + dataset Demo
- Nuovi endpoint superadmin (server.py): GET /platform/users (elenco account: nome, email, org, ruolo, stato, creazione, ultimo accesso, memberships); PATCH /platform/users/{id} (disable/enable); DELETE /platform/users/{id} (guardie: superadmin non eliminabile, no self-delete, blocco se unico admin_org di org cliente; preserva Persona e dati org, scollega owner/persona, elimina sessioni/token); DELETE /platform/organizations/{id} (richiede confirm_name == nome esatto; cascade solo org-scoped + settings by id + account staff/volontari; detach altri account); POST /platform/organizations/{id}/seed-demo (SOLO type=test, idempotente).
- Audit: nuove azioni account_disabled/enabled/deleted, org_disabled/enabled/deleted, demo_seeded.
- Frontend: Platform.jsx tabella Account utenti con disable/elimina (dialog testo esatto) + loadAll con Promise.allSettled; OrgDetail.jsx zona pericolosa nel tab Dati: Popola/Ripristina dati Demo (solo type=test, checkbox wipe + conferma) + Elimina organizzazione (input nome esatto).
- FIX critico seed_demo.upsert: scoped by (id, org_id) -> seedare una seconda org test non ruba piu i record della prima. Regressione verificata: seed A, seed B, counts(A) invariati.
- Testato: iteration_14.json backend 8/8, frontend ~90%; Demobot su Demo OK.
- NON eseguito in produzione: seed prod e org Demo reale attendono conferma esplicita.

## Integrazione iubenda (gestore consenso) — preview
- Aggiunto Unified Embedding Code iubenda come PRIMO elemento in <head> (public/index.html): script https://embeds.iubenda.com/widgets/a411033f-bef4-4836-94d4-8a0d2697f51f.js, caricato prima di GA/PostHog.
- iubenda ora gestisce banner, blocco preventivo e Google Consent Mode v2 (default denied + update su scelta).
- Rimosso il secondo sistema di consenso di CRMEvent: eliminato gtag('consent','default',...) da index.html; rimosse readConsent/applyConsent/saveConsent/CONSENT_KEY e il banner custom CookieConsent (ora no-op, non montato in App.js).
- GA4 invariato: Measurement ID G-PZK7J854DS, gtag('config', send_page_view:false, anonymize_ip:true), libreria GA caricata solo su hostname crmevent.it. trackPageView/trackEvent ora pushano sempre su gtag (Consent Mode governa i cookie). Eventi begin_checkout e purchase + dedup (localStorage crmevent_ga4_purchased) invariati.
- Footer "Preferenze cookie" riapre le preferenze iubenda via window._iub.cs.api.openPreferences() (fallback all'evento legacy).
- Nessun dato personale/Stripe verso GA. Testato in preview: iubenda core-it.js 1.107.0 caricato, banner (Rifiuta/Accetta/Scopri di più e personalizza) attivo, build senza errori. NON deployato in produzione (in attesa di conferma).

## Scheda organizzazione: Utenti vs Inviti + pulizia inviti — preview
- OrgDetail.jsx: tab separati "Utenti" (account registrati con accesso) e "Inviti".
- Tab Utenti: colonne Nome, Email, Ruolo, Stato account, Accesso org, Metodo (Google/Email e password), Registrazione, Ultimo accesso. Azioni SuperAdmin: modifica ruolo, disabilita/riattiva accesso (membership), elimina utente (dialog conferma → DELETE /platform/users/{id} Fase B: conserva Persona/eventi/attività/turni; guardie: no SuperAdmin, no auto-eliminazione, no unico admin_org di org cliente). Ruolo SuperAdmin mostrato come badge readonly.
- Backend _member_view arricchito: account_active, created_at, auth_provider, is_superadmin.
- Tab Inviti: "Pulisci duplicati" (POST /platform/organizations/{id}/invites/cleanup) + elimina invito hard (DELETE /platform/invites/{id}?hard=true) senza toccare account.
- Fix duplicato inviti: _accept_invite ora elimina gli altri inviti stesso email+org (niente doppie righe accettate come demo.crmevent@gmail.com Utente+Admin); invite_lead ora blocca se membership attiva.
- Nuova azione audit: invites_cleaned. Testato iteration_15.json: frontend 100% check, backend dedup/cleanup verificato (2 rimossi, account+membership intatti). NON deployato (in attesa conferma).

## Funnel demo Demosmith (/demo) + lead tracking — preview
- Nuova pagina pubblica /demo (DemoPage.jsx): fuori da menu/footer, noindex/nofollow (meta inj. + robots.txt Disallow /demo), branding CRMEvent, titolo/intro richiesti, CTA "Prova CRMEvent gratis" (/registrati) + "Accedi" (/login) + CTA flottante mobile.
- Demosmith: embeddabile via iframe pubblico (public.demosmith.ai/<shortid>/embed.html). L'URL app fornito è X-Frame bloccato → finché non si imposta DEMO_EMBED_URL pubblico, /demo mostra un launcher ("Avvia la demo") che apre in nuova scheda. Costante DEMO_EMBED_URL + flag EMBED_IS_PUBLIC in DemoPage.jsx.
- Form "Richiedi demo": salva lead con source, funnel_status=demo_requested, requested_at + timestamp; GA4 generate_lead; salva lead in localStorage; redirect a /demo.
- Backend: Lead esteso (source, funnel_status, requested_at, funnel_ts_*). POST /leads/{id}/funnel (pubblico, stati validati). Email di conferma AL lead con link /demo (usa email_utils esistente; nessun nuovo servizio). register-organization collega lead per email + funnel_status=trial_started (continuità, niente doppioni).
- GA4: generate_lead, demo_started (onLoad/launcher, dedup trackOnce), sign_up + trial_started (register), begin_checkout/purchase invariati. demo_completed NON emesso (non rilevabile in modo affidabile). Nessun PII inviato. iubenda/Consent Mode/GA4 config invariati.
- Verificato preview: funnel status+timestamp, stato invalido→400, continuità lead→trial_started, pagina /demo render+CTA+noindex, build ok. NON deployato (attende conferma). Non toccati Stripe/FIC/Demo org/Demobot.

## Integrazione Brevo — predisposizione connessione (solo verifica) — preview
- Aggiunto secret BREVO_API_KEY (vuoto in preview) in backend/.env. Chiave letta SOLO da os.environ, mai in codice/DB/frontend/log.
- Nuovo endpoint backend GET /api/integrations/brevo/check (solo Super Admin): valida la chiave via GET https://api.brevo.com/v3/account (header api-key). Ritorna solo {configured, valid, status, message}; nessun invio email/campagna; con chiave vuota short-circuita prima di contattare Brevo. Sistema email esistente (Resend/managed) invariato.
- Testato iteration_16.json (backend 100%): 401 senza auth, configured:false con chiave vuota, nessuna fuga di chiave/payload, /v3/smtp/email mai chiamato, login regressione ok.
- IN ATTESA che l'utente inserisca BREVO_API_KEY nei Secrets di produzione; nessuna automazione/sequenza email creata (come richiesto).

### 2026-06 (Brevo · Mittenti + Email di test — verificato in preview: auth + code path)
- [x] Backend superadmin-only: GET /api/integrations/brevo/senders (elenca mittenti Brevo via GET /v3/senders → nome, email, dominio, active/verificato; chiave mai esposta).
- [x] Backend superadmin-only: POST /api/integrations/brevo/send-test (invio singola transazionale via POST /v3/smtp/email; oggetto "CRMEvent · Test collegamento Brevo"; ritorna success/status/messageId/timestamp/messaggio errore chiaro). Nessun invio automatico.
- [x] Frontend Platform.jsx: pulsante "Carica mittenti" + tabella mittenti; sezione "Invia email di test" (solo se esiste mittente verificato) con select mittente, campo destinatario, log esito (esito/HTTP/messageId/timestamp).
- Vincoli rispettati: nessuna automazione/campagna/template/sequenza; secret invariati (BREVO_API_KEY persistente). Chiave presente solo in produzione → mittenti reali visibili solo in prod.

### 2026-06 (Funnel Demo CRMEvent — automazione email Brevo — BOZZA, verificato in preview)
- Architettura: CRMEvent è la fonte di verità dello stato lead/funnel; Brevo gestisce contatti, invio, statistiche. Nuovo modulo backend `brevo_funnel.py` + endpoint in `server.py`.
- Ingresso funnel: alla richiesta demo (`demo_requested`) il contatto viene upsertato su Brevo (updateEnabled, no duplicati) con attributi NOME/COGNOME/ORGANIZZAZIONE/TIPOLOGIA_EVENTI/SOURCE/FUNNEL_STATUS. L'iscrizione al funnel avviene SOLO se il funnel è ATTIVO; altrimenti resta la vecchia email singola (nessuna doppia email).
- 4 email (template Brevo brandizzati, mittente CRMEvent hello@crmevent.it): E1 immediata, E2 +1g, E3 +3g, E4 +6g. E2-E4 solo se il lead NON ha trial_started e NON è cliente.
- Scheduling: platform cron `.emergent/crons.yml` (`*/15`) → `POST /api/cron/brevo-funnel-tick` (bearer WEBHOOK_CRON_SECRET), ri-controlla le condizioni di stop PRIMA di ogni invio.
- Condizioni di stop: trial_started, cliente, disiscrizione, hard bounce, spam → interrompe subito le email residue.
- Webhook `POST /api/brevo/webhook/{token}` (token segreto, idempotente): delivered/opened/clicked/hard_bounce/unsubscribe/spam → aggiorna lead + interrompe enrollment.
- Disiscrizione: `GET /api/brevo/unsubscribe?token=` pubblico → marketing_opt_out + blocklist Brevo + stop enrollment; link nel footer + params UNSUB_URL.
- SuperAdmin UI: Piattaforma → "Automazioni email · Funnel Demo" (badge Bozza/Attivo/In pausa, Sincronizza template, cambio stato con guardie, "Invia test funnel", dashboard 12 metriche, sequenza email, condizioni di stop). Lead detail → stato funnel per-lead con storico step.
- Sicurezza: al primo deploy il funnel è BOZZA (non parte su lead reali). BREVO_API_KEY mai esposta. Nuovi secret backend: BREVO_WEBHOOK_TOKEN, WEBHOOK_CRON_SECRET.
- Preview: BREVO_API_KEY vuota → sync/test/invii reali non eseguibili in preview (ritornano errore gestito). Logica funnel/guardie/webhook/unsub/cron/UI verificata via curl+screenshot.

### 2026-06 (Brevo · Lista lead + sync contatti + protezione template HTML)
- Lista Brevo "CRMEvent · Lead": nuovo `ensure_list()` (trova o crea la lista, cartella "CRMEvent"); id cachato in `db.settings`. Endpoint SuperAdmin `POST /api/platform/funnels/demo/ensure-list` + pulsante "Verifica/crea lista Brevo".
- Nuovo lead (Richiedi demo): upsert contatto Brevo per email (no duplicati) + inserimento nella lista + attributi NOME/COGNOME/ORGANIZZAZIONE/TIPOLOGIA_EVENTI/SOURCE/FUNNEL_STATUS.
- Cambio stato lead: `POST /leads/{id}/funnel` e continuità trial in register-organization aggiornano FUNNEL_STATUS su Brevo (CRMEvent resta fonte di verità).
- PROTEZIONE TEMPLATE: `create_or_update_template` ora è NON distruttivo di default — collega i template esistenti per nome SENZA sovrascrivere l'HTML modificato manualmente in Brevo. Sovrascrittura solo con `?force=true` (non usato dalla UI). Pulsante rinominato "Collega template".
- Nessuna importazione automatica di lead storici.

### 2026-06 (Email interne/transazionali — nuovo layout base condiviso)
- Ridisegnato `email_utils.link_email` (base comune usata da TUTTE le email interne): header bianco con logo ufficiale CRMEvent centrato, testo scuro, pulsanti/link Tiffany (#81D8D0/#59C1B7), footer essenziale, pulsante "bulletproof" table-based per Outlook. Nuovo helper `_shell()`.
- Logo: da icona/artifact → logo ufficiale del sito, servito via URL pubblico `{APP_URL}/logo-crmevent.png` (niente asset locali). Verificata raggiungibilità (200 image/png) e resa nei preview.
- Coperte: invito utente, reset password, conferma/registrazione, notifica nuova richiesta demo (admin), email demo legacy. Contenuti, link, token, scadenze e logica di invio invariati.
- NESSUNA modifica ai template Brevo / Funnel Demo / lista / contatti (come richiesto). Anteprime verificate in preview per invito, reset, conferma; safety check email superato.

### 2026-06 (Google Calendar OAuth — fix PKCE, invalid_grant "Missing code verifier.")
- Diagnosi prod (via deployer, log reali): fallimento a stage=code_to_token, HTTP 400 invalid_grant "Missing code verifier." → google-auth-oauthlib 1.4.1 autogenera code_challenge all'authorize ma il code_verifier veniva scartato e non inviato al token endpoint.
- Fix PKCE (solo codice, nessun cambio a Client ID/Secret/redirect URI/scope/Google Cloud):
  - gcal_utils.authorization_url→(url, code_verifier); exchange_code(code, code_verifier) invia il verifier.
  - _cal_state→(state, jti) con jti univoco nello state (protezione state mantenuta).
  - /calendar/connect: genera e salva il verifier in Mongo `calendar_oauth_pkce` {jti,uid}, TTL 10 min (multi-pod safe, mai esposto/loggato).
  - /oauth/calendar/callback: recupero monouso (find_one_and_delete), rifiuto se mancante/riusato/scaduto, poi invio al token exchange. Logging diagnostico sicuro mantenuto.
  - Indice TTL su expires_at (expireAfterSeconds=0) + indice {jti,uid}.
- Test preview (6/6 PASS): authorize genera challenge+verifier; callback recupera il verifier corretto; mancante/errato→rifiutato; riusato→non riutilizzabile; scaduto→non utilizzabile; nessun verifier/token/secret nei log. Test file: /app/backend/tests/test_gcal_pkce.py

### 2026-06 (Fatture in Cloud — modalità SIMULAZIONE TEST, separata dal LIVE)
- Nuovo endpoint org-scoped POST /api/fic/simulate/{invoice_id}: costruisce internamente il payload FIC e i valori (cliente, intestazione, numero/data SIMULATI, imponibile/IVA/totale, piano, rif. Stripe, stato, payload preview) SENZA chiamare POST /issued_documents e SENZA alcun invio SDI. Marca la fattura come fic_stato_documento="simulato_test"/fic_stato_sdi="simulato_test".
- Il flusso reale /fic/issue (dry_run, superadmin) resta invariato per il futuro LIVE → separazione netta simulazione vs emissione.
- UI Account (org admin): sezione "Fatture" con pulsante "Simula fattura (TEST)" e dettaglio + payload FIC sicuro (nessun secret/token).
- Nessun documento reale FIC, nessuna numerazione fiscale, nessun SDI durante il test.

### 2026-06 (Funnel Demo — fix STOP immediato al trial + riconciliazione)
- RCA prod: lead convertito aveva user_id ma funnel_status regredito a demo_started (DemoPage rimonta → POST /leads/{id}/funnel demo_started DOPO la registrazione) e la registrazione non chiudeva l'enrollment → cron avrebbe inviato Email 2 (demo_started non è stop reason).
- Fix doppia protezione:
  - register-organization: dopo trial_started chiude subito l'enrollment demo (_stop_active_demo_enrollment) → step 2/3/4 canceled, stop_reason=trial_started, stopped_at salvato.
  - POST /leads/{id}/funnel: se il nuovo stato è una condizione di stop → chiusura immediata enrollment.
  - _stop_reason ora considera anche lead.user_id (lead convertito → stop) come difesa aggiuntiva; il cron continua a rileggere lo stato prima di ogni invio.
  - _cancel_enrollment idempotente + stopped_at.
- Nuovo endpoint SuperAdmin POST /platform/funnels/demo/reconcile (nessuna email): chiude enrollment attivi il cui lead soddisfa una condizione di stop, normalizza funnel_status del lead convertito. Pulsante UI "Riconcilia enrollment".
- UI Leads già mostra: Funnel interrotto — prova gratuita avviata; Email 1 Inviata; Email 2/3/4 Annullata.
- Test preview 4/4 PASS (tests/test_funnel_stop.py). Funnel Demo resta BOZZA. Template/tempi Brevo invariati.

## 2026-09-28 — Pulizia bozze test + verifica OAuth platform scope
- Eliminate 9 bozze residue (tutte draft, plan_id unico, zero relazioni a media/log/calendar) da org test "Org Social a" (4a20906d). Nessun altro tenant toccato.
- Verificato: social_posts __platform__ = 34 (intatti); tenant 7d94739b=1, 7edbced1=1 (intatti).
- Verificato chain OAuth Instagram platform-scope: SocialSettings.jsx usa platformApi (forza ?scope=platform) -> /oauth/instagram/start (require_org_admin: scope=platform+superadmin => org_id=__platform__) -> state JWT porta org_id=__platform__ -> callback salva social_accounts con org_id=__platform__, indipendente da X-Org-Id/Org attiva.
- @crmevent NON ancora collegato (social_accounts=0). Nessun token presente. Pilota automatico OFF. Nessuna pubblicazione eseguita.

## 2026-09-28 — Fix data/ora Social + Creatività manuale (no auto-generazione)
Task 1 — Date/time picker:
- Nuovo helper src/lib/datetime.js (Europe/Rome). Modale Social: campi Data (calendario) + Ora 24h separati, blocco date/orari passati, display GG/MM/AAAA - HH:mm.
- Storage resta UTC ISO (backend invariato). Elenco, modale e Calendario editoriale ora usano lo stesso fuso Europe/Rome -> nessuno sfasamento 1-2h. Verificato estate(+2)/inverno(+1).
Task 2 — Creatività manuale:
- AI genera anche image_brief (Brief grafico) per ogni post (social_ai.py generate_post/plan; salvato in social_posts).
- Disattivata generazione automatica immagini/template: vecchio POST /social/posts/{id}/creative rimosso (ora 405).
- Nuovi endpoint: POST /social/posts/{id}/creative/upload (upload manuale, valida 1:1 o 4:5, converte JPEG check), DELETE /social/posts/{id}/creative (rimuove img e riporta a draft se era approved/scheduled).
- Gating: approve e publish bloccati senza creativita (backend + UI disabilitano i pulsanti). Post puo restare draft/scheduled senza immagine.
- UI modale: sezione Creativita con Brief grafico + Carica/Sostituisci/Anteprima/Elimina immagine. Anteprima Instagram invariata.
- Collegamento Instagram (OAuth platform scope) NON toccato. Nessuna pubblicazione reale eseguita.
- NOTA: Task 1 e 2 sono in PREVIEW, non ancora deployati in produzione.

## 2026-09-28 — Account social auto-assegnato (Marketing CRMEvent Piattaforma)
- Root cause errore "account social selezionato": approve richiedeva post.account_id ma il frontend non permetteva alcuna selezione; publish invece sceglieva gia l unico account (incoerenza).
- Backend: helper _connected_ig_accounts/_default_account_id/_resolve_post_account. Auto-assegnazione del solo account IG connesso a nuovi post (generate/plan) e ai post esistenti al momento di approve. Se >1 account -> richiede selezione. approve/publish falliscono solo se manca davvero un account connesso. Account e post entrambi scope __platform__ via oq().
- Sicurezza: /social/dashboard ora sanifica gli account (niente access_token esposto al frontend).
- Frontend Social.jsx: sezione "Account di pubblicazione" (singolo = @username statico, multipli = selettore), readiness e pulsanti Approva/Pubblica bloccati se account mancante/non selezionato.
- Token OAuth NON toccato; nessun nuovo collegamento richiesto se gia connesso.
- Verificato in preview con account IG di test in __platform__: generate auto-assegna, approve OK senza selezione, publish si ferma a 428 (nessuna pubblicazione reale), multi-account richiede selezione, dashboard non espone token. Nessun 5xx nelle operazioni sui post (il NameError Header nei log era storico, Header e importato). Dati di test rimossi.
- In PREVIEW: da deployare in produzione.

## 2026-09-28 — Fix 502 Cloudflare modulo Social (event-loop blocking)
- Causa: chiamate storage sincrone (requests, timeout fino a 120s) dentro endpoint async su uvicorn a 1 worker -> event loop bloccato quando il proxy objstore e lento -> worker non risponde -> Cloudflare 502 "origin returned invalid or incomplete response" su qualsiasi richiesta Social in coda.
- Endpoint coinvolti: POST /api/social/posts/{id}/creative/upload, POST /api/social/media (upload immagine), GET /api/files/{id} (anteprima), /api/social/public/creative/{token}, e _ensure_public_jpeg.
- Fix: tutte le storage_utils.put_object/get_object nei path async ora via await asyncio.to_thread(...) (8 call site). Nessuna modifica a UI, logica editoriale, OAuth o altre funzioni. Comportamento immagini invariato.
- Verifica preview: open 200, save(PUT) 200, accounts 200, upload OK, preview img 200, approve 200. Nessun 5xx. Nessuna pubblicazione IG. Dati di test rimossi.
- Da deployare in produzione per applicare il fix.

## 2026-09-28 — 502 pubblicazione Instagram riclassificato (RCA produzione)
- RCA deployer (prod, read-only): fix asyncio.to_thread GIA live in prod (8 call site, 0 sincrone). Endpoint apertura post (/api/files/{id}, /api/social/media, /api/social/public/creative/{token}) rispondono 200 -> il 502 "aprendo il post" era cache Cloudflare/bundle JS stantii, non un bug.
- Unico 502 reale: POST /api/social/posts/{id}/publish. Log: Graph /media 200 ma /media_publish 400 Bad Request (post 49630fb1...); il blocco except rimappava il 400 upstream in HTTPException(502).
- Fix (solo classificazione errori, publishing invariato): instagram_utils._check ora solleva GraphAPIError con status_code; publish except restituisce 422 (con dettaglio Meta) per errori client 4xx, 502 solo per gateway/5xx/network. Nessuna modifica a UI/OAuth/dati/post/logica editoriale.
- Test tecnico (no pubblicazione): 400->422, 500->502, 200+error->502, generic->502. In PREVIEW: serve redeploy per applicare in produzione.

## 2026-09-28 — Fix scroll touch drawer mobile (Layout.jsx)
- Drawer mobile ora: h/max-h 100dvh, nav flex-1 min-h-0 overflow-y-auto overscroll-contain + -webkit-overflow-scrolling:touch, padding safe-area inferiore (env(safe-area-inset-bottom)+24px).
- Body-lock iOS-safe via useEffect su mobileOpen: position:fixed/top:-scrollY/overflow:hidden mentre aperto; ripristino stile e window.scrollTo alla chiusura (mantiene posizione).
- Verificato su viewport 390x844: drawer scrollabile fino ultima voce (Impostazioni Social), pagina bloccata (scrollY=0), nessuno scroll chaining, posizione ripristinata alla chiusura.
- Nessuna modifica a menu desktop, voci, permessi, routing o layout generale. VolunteerLayout (bottom-nav) non toccato.
- In PREVIEW: mostrato prima del deploy come richiesto.

## 2026-09-29 — Lead Finder / Organizzatori (Super Admin) + test 20 eventi ENDU
- Nuova sezione Marketing -> Organizzatori (platform scope) con 5 sotto-schede: Dashboard, Organizzatori, Eventi trovati, Lead Finder, Da verificare.
- Modello: lf_organizers (anagrafica, contatti, social URL completi, fonti per-dato, stati, socials_status) + lf_events (organizer_id -> N eventi). Dedup email/dominio/nome_key/instagram (409 su duplicato) + Unisci duplicati. Stato non_contattare sticky (non sovrascrivibile da automatismi).
- Endpoint /api/leadfinder/* (dashboard, organizers CRUD+merge, events CRUD, brevo-export=501 disabilitato).
- Frontend LeadFinder.jsx: tabella+filtri (regione/sport/stato/email/IG/LinkedIn)+ricerca, scheda organizzatore (link cliccabili), dashboard metriche+distribuzioni.
- Seed reale 20 eventi ENDU -> 15 organizzatori (grouping serie: Adriatic 3, Giro Handbike 2, Porto Cervo 3). Dati evento (nome/sport/citta/prov->regione/data/URL) da ENDU; email+social=Da verificare (NON inventati).
- Nessun servizio a pagamento, nessun invio Brevo, nessuna scansione massiva. In PREVIEW.

## 2026-06 — Correzione dominio pubblico template Brevo (crmevent.it)
- `PUBLIC_SITE_URL` ora env-driven (default https://crmevent.it). Il template Prospect Email 1 (`POST /api/brevo/create-email-template`) usa `PUBLIC_SITE_URL` invece di APP_URL: CTA `https://crmevent.it/demo?utm_source=brevo&utm_medium=email&utm_campaign=prospect&utm_content=email1`, logo `https://crmevent.it/logo-crmevent.png`, footer `https://crmevent.it`. Asset statico prospect-email-1.html allineato. Funnel Demo invariato. Deploy in produzione rilanciato.

## 2026-06 — Raccolta pubblica disponibilità Staff/Volontari (per evento)
- Evento: nuovo campo facoltativo `data_inizio_allestimento` con validazioni (allestimento <= data_inizio; data_fine >= data_inizio). Riepilogo lista Eventi "Allestimento dal GG/MM · Evento GG/MM".
- Collection `avail_links` (token sicuro `secrets.token_urlsafe`, un solo link attivo per evento; rigenera invalida il precedente; disattiva blocca invii). URL pubblico `crmevent.it/partecipa/{code}`.
- Collection `availabilities` (adesioni): persona_id+evento_id, giorni {date,fase allestimento/evento,dalle,alle}, preferenza_attivita/altro, ruolo_evento (default `da_definire`), stato (default `nuova`), mismatch dati, privacy (ip/user-agent/timestamp), `submitted` per apply anagrafica.
- Persona: nuovo campo `codice_fiscale`. Form pubblico usa Codice Fiscale (normalizza upper, valida checksum IT, ricava e salva data_nascita) con opzione "Non ho un Codice Fiscale italiano" -> Data di nascita. Età calcolata dinamicamente (frontend `calcAge`, backend `_compute_age`). CF visibile solo in scheda Persona (non nelle tabelle riepilogative).
- Endpoint pubblici (no login, rate-limit 6/60s per IP, anti-enumerazione): `GET/POST /api/public/availability/{code}`, `GET .../logo` (logo evento scoped). Endpoint admin org-scoped: `POST/GET /api/events/{id}/availability/link`, `.../link/deactivate`, `GET /api/events/{id}/availabilities`, `PUT /api/availabilities/{id}` (ruolo/stato/preferenza/apply_person).
- Dedup Persona: email -> cellulare -> codice_fiscale; fill-if-empty, mai overwrite silenzioso (mismatch segnalato, apply manuale). Nessun duplicato Persona/adesione (upsert per persona+evento). Nessuna creazione automatica di Staff/Team/Turni: solo predisposizione dato (flusso Adesione -> Persona -> Ruolo evento -> assegnazione futura -> Briefing).
- Frontend: pagina pubblica mobile-first `Partecipa.jsx` (route `/partecipa/:code`); dialog admin `AvailabilityDialog.jsx` (azione-riga Eventi) con tab Link + Disponibilità ricevute (colonne Nome/Cellulare/Email/Età/Disponibilità/Preferenza/Ruolo evento/Stato, click -> scheda Persona).
- Test: org Test "Nova Events" + evento "Nova Run Festival" (allestimento 18/12, evento 20/12/2026). Backend E2E script `tests/test_availability_flow.py` (27 assert PASS) + curl admin/isolamento. Frontend testing agent 100% (iteration_19). Privacy checkbox obbligatoria, nessun account/trial creato.

## 2026-06 — Disallestimento + dropdown alfabetici + logo pubblico
- Evento: nuovo campo facoltativo `data_fine_disallestimento`. Validazione a catena non-decrescente: inizio allestimento ≤ inizio evento ≤ fine evento ≤ fine disallestimento (validator `_check_dates`). Riepilogo lista Eventi e dialog admin: "Allestimento dal GG/MM · Evento GG/MM–GG/MM · Disallestimento fino al GG/MM".
- Raccolta disponibilità: intervallo giornate ora allestimento→disallestimento (fallback inizio/fine evento). Terza fase `disallestimento` (viola) oltre allestimento (ambra) ed evento (azzurro), classificata automaticamente in `_avail_days`. Intro pubblica aggiornata ("giorni precedenti e successivi ... allestimento e disallestimento").
- Dropdown ordinati alfabeticamente A–Z (locale IT, case-insensitive) come regola generale: helper `sortOptions` applicato in `crm.jsx` (Field select) e `SettingSelect`; opzioni speciali fuori ordinamento ("Nessuna preferenza"/vuoto/"tutti" in testa, "Altro"/"+ Aggiungi" in coda). Nuove voci create con +Aggiungi si riposizionano da sole. Esclusi gli elenchi con ordine logico via `keepOrder:true` (stati, priorità, fasi pipeline, tipi, livelli sponsorship). Anche la preferenza attività del form pubblico è ordinata.
- Pagina pubblica: logo Evento (o logo scuro ufficiale CRMEvent per sfondo bianco) centrato e più grande (150px mobile / 200px desktop, object-contain), con Nome Evento e Data · Località centrati sotto.

## 2026-06 — Impostazioni: Tipi di azienda + aggiunta rapida inline
- Nuova lista settings org-scoped `tipi_azienda` (default: Azienda, Espositore, Istituzione, Partner, Sponsor). Backfill automatico in `GET /api/settings` per le organizzazioni esistenti (merge chiavi mancanti dai default, non distruttivo). `USAGE_MAP` aggiornato (`tipi_azienda` -> companies.tipo) per il controllo utilizzo in eliminazione.
- Impostazioni: nuova sezione "Tipi di azienda" (aggiungi/modifica/elimina come le altre liste).
- Anagrafica Azienda: campo Tipo ora usa `SettingSelect` con "+ Aggiungi nuova tipologia" (crea, seleziona e mantiene aperta la scheda senza perdere i dati; dedup case/spazi-insensitive). Ordinamento alfabetico A–Z. Tipo e Settore restano campi separati. Company.tipo resta stringa libera (valori legacy slug ancora mostrati via label/colore fallback anche lowercase).

## 2026-06 — Unificazione "Tipo azienda" + creazione rapida inline (regola generale)
- Tutti i menu "Tipo azienda" leggono ora dall'unica lista centralizzata `tipi_azienda` (Impostazioni). Default esteso: Azienda, Espositore, Fornitore, Istituzione, Partner, Prospect, Sponsor (alfabetico). Rimossa la lista propria di Sponsor & Partner (sponsor/partner/fornitore/prospect): il campo Tipo della trattativa usa `settingKey: "tipi_azienda"` con "+ Aggiungi nuova tipologia" inline. Una sola fonte dati per organizzazione; le tipologie disattivate non vengono più riproposte ma restano sui record storici.
- Meccanismo generico di creazione rapida da dropdown (riusabile): `Field` supporta `field.addEntity` + `onAddEntity`; `EntityDialog` accetta `entityCreators` e apre il form originale sopra, poi seleziona automaticamente il nuovo elemento senza perdere i dati.
- Sponsor & Partner → Nuova trattativa → Azienda: "+ Aggiungi nuova azienda" apre il CompanyDialog completo sopra la trattativa; al salvataggio l'azienda viene aggiunta all'elenco, auto-selezionata e i dati della trattativa restano intatti; annullando si torna alla trattativa senza perdite. Dedup per nome (conferma) prima della creazione.
- Nota migrazione: `get_settings` fa backfill solo delle chiavi mancanti (non dei valori, per non riproporre voci rimosse). Le org di produzione, prive di `tipi_azienda`, ricevono i 7 default al primo accesso. Patch una-tantum applicata all'org di test Nova per allineare i 7 valori.

## 2026-06 — Brevo disponibilità (gated) + Conferma da tabella (Task 7-8)
- Availability submit: dopo il salvataggio (che ha SEMPRE priorità), sync Brevo best-effort verso lista dedicata "CRMEvent · Disponibilità eventi" con attributi (NOME, COGNOME, SMS, EVENTO, DATA_EVENTO, ORGANIZZAZIONE, RUOLO_EVENTO, STATO_DISPONIBILITA) — MAI il Codice Fiscale. Gated da env `BREVO_AVAILABILITY_ENABLED` (default off): in assenza registra `brevo_sync_log` con stato "pending" senza invii reali; se Brevo irraggiungibile, l'adesione resta salvata e l'errore è loggato per retry.
- Consenso marketing separato e facoltativo nel form pubblico (checkbox non preselezionata, distinta dalla Privacy obbligatoria): salva marketing_consent + ts + source; non blocca invio né email di conferma.
- Template email bozza (isActive=false) via `POST /api/brevo/create-availability-templates`: "CRMEvent · Conferma disponibilità evento" (1ª email ringraziamento) e "CRMEvent · Conferma partecipazione evento" (2ª email conferma), con {{params.nome/nome_evento/data_evento}}. Nessun invio reale finché non approvato.
- Conferma dalla tabella "Disponibilità ricevute" (per evento): colonna Confermato (checkbox = stato Confermata), colonna Ruolo evento inline (Da definire/Staff/Volontario), filtri rapidi Ruolo e Stato, selezione multipla + "Conferma selezionati (N)" con dialog di conferma. La conferma salva confirmed_at/confirmed_by e avvia (gated) la 2ª email UNA sola volta (idempotente: confirmation_email_sent_at). Se l'invio fallisce la persona resta Confermata (errore loggato, reinvio possibile). Endpoint: `POST /api/events/{id}/availabilities/confirm-bulk`.
- Attributi Brevo aggiornati (gated) al cambio Ruolo/Stato. La 1ª email (disponibilità) resta invariata.

## 2026-06 — Dashboard KPI disponibilità + Brevo 2 template master dinamici
- Dashboard sintetica (in cima a "Disponibilità ricevute"): card cliccabili Ricevute/Nuovi/Confermati/Staff/Volontari/Da definire (applicano filtro, combinabili con i filtri Ruolo/Stato) + indicatore Email (Inviate/Da inviare/Errore). Scoping per Evento+Organizzazione.
- Brevo: due SOLI template master di piattaforma "CRMEvent · Disponibilità ricevuta" e "CRMEvent · Partecipazione confermata" (niente copie per evento). Dati dinamici via {{params.*}} (NOME, COGNOME, NOME_EVENTO, DATA_EVENTO, LOCALITA_EVENTO, LOGO_EVENTO_URL, NOME_ORGANIZZAZIONE, DATA_INIZIO_ALLESTIMENTO, DATA_FINE_DISALLESTIMENTO), recuperati a ogni invio da Organizzazione→Evento→Disponibilità. Layout responsive con logo grande centrato + footer "Comunicazione gestita tramite CRMEvent" (no Emergent).
- Logo per-evento pubblico: GET /api/public/event-logo/{event_id} (solo immagine, fallback logo CRMEvent). LOGO_EVENTO_URL non salvato nel template.
- Idempotenza: availability_email_sent_at (1ª) e confirmation_email_sent_at (2ª); nessun doppio invio su refresh/doppio click. Errori Brevo non perdono il dato (loggati, reinvio possibile). Mai inviati a Brevo CF/data nascita/note/rimborsi.
- Endpoint: GET /api/brevo/availability-templates (elenco master + Template ID + is_active), GET /api/brevo/availability-template-preview?event_id&kind (anteprima HTML reale con dati evento). Restano invariati BREVO_AVAILABILITY_ENABLED=off e template in BOZZA.
