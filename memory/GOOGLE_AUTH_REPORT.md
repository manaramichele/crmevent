# CRMEvent – Report tecnico login Google (2026-10-09) – SOLO ANALISI, nessuna modifica

## 1. Perché compare "Continua su emergentagent.com"
Il login Google NON usa un client OAuth di CRMEvent ma il servizio gestito Emergent Auth:
- Frontend: `Login.jsx:41`, `Register.jsx:47`, `Invite.jsx:99` → redirect a `https://auth.emergentagent.com/?redirect=...`.
- Google mostra quindi il dominio del client OAuth di Emergent (emergentagent.com), non personalizzabile.
- Ritorno con `#session_id=...` intercettato da `App.js:129` (AuthCallback) e `AuthContext.js:34`.
- Backend `POST /api/auth/session` (server.py ~829) scambia il session_id con `EMERGENT_SESSION_URL = https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data` (server.py:62).

| Voce | Valore attuale |
|---|---|
| Provider OAuth effettivo | Emergent Auth (client Google di Emergent) |
| OAuth Client ID | di Emergent (non visibile/controllabile da CRMEvent) |
| Redirect URI | gestito da auth.emergentagent.com → torna a `<frontend>/#session_id=` |
| Callback | `AuthCallback.jsx` → `POST /api/auth/session` |
| Sessione | cookie `session_token` (token Emergent, 7 gg, collezione `user_sessions`) in parallelo al JWT `access_token` del login password |
| Collegamento account | per **email** (`users.email`), poi `memberships` (org, ruolo, permessi) — indipendente dal provider |

Il resto dell'autenticazione (email/password, JWT, inviti, reset, attivazione) è già indipendente da Emergent.
Esiste già un client OAuth CRMEvent (`GOOGLE_CLIENT_ID/SECRET`) usato da Google Calendar (`/api/oauth/calendar/callback`).

## 2. Serve sostituire Emergent Auth?
Sì, è l'unico modo: il dominio mostrato da Google dipende dal client OAuth. Con un client OAuth di proprietà CRMEvent la schermata mostrerà "Continua su crmevent.it" (dominio del redirect/homepage verificati), nome app "CRMEvent" e logo (dopo verifica brand).
Nessun provider terzo necessario: Google OAuth 2.0 / OpenID Connect gestito direttamente dal backend Aruba.

Implementazione proposta (dopo autorizzazione):
- `GET /api/oauth/google/start?next=&invite=` → `state` firmato monouso (10 min) + PKCE + `nonce`, redirect a `accounts.google.com`.
- `GET /api/oauth/google/callback` → scambio code, verifica `id_token` (firma JWKS, `aud`, `iss`, `exp`, `nonce`, `email_verified=true`), abbinamento utente (prima `google_sub`, poi email), emissione del JWT `access_token` già usato dal login password, redirect a `FRONTEND_URL` + `next`.
- Frontend: i 3 pulsanti Google puntano a `${API}/api/oauth/google/start`. Flusso invito: il token invito passa nello `state`.
- Transizione: `/api/auth/session` e cookie `session_token` restano attivi 7 giorni (scadenza naturale), poi rimozione di tutto il codice Emergent Auth.
- Scope: solo `openid email profile` (non sensibili → nessuna revisione di sicurezza; Calendar resta separato con il suo consenso).

## 3. Configurazione Google Cloud (a cura del titolare)
1. Progetto Google Cloud CRMEvent (riutilizzabile quello di Calendar).
2. Schermata consenso OAuth: tipo Esterno, nome "CRMEvent", logo 120×120, email supporto, homepage `https://crmevent.it`, Privacy `https://crmevent.it/privacy`, Termini `https://crmevent.it/termini`, domini autorizzati `crmevent.it`.
3. Verifica proprietà dominio `crmevent.it` in Google Search Console (record TXT DNS su Aruba).
4. Client OAuth "Applicazione web":
   - Redirect URI: `https://api.crmevent.it/api/oauth/google/callback` (+ quello di preview per i test).
   - Origini JavaScript: `https://crmevent.it`, `https://www.crmevent.it` (non strettamente necessarie col flusso server-side).
   - Mantenere anche `https://api.crmevent.it/api/oauth/calendar/callback` per Calendar.
5. Pubblicare l'app ("In produzione") e richiedere la **verifica del brand** (necessaria per mostrare logo/nome; tempi tipici alcuni giorni).
Nota: Google mostra il dominio associato al client/redirect; con redirect su `api.crmevent.it` e dominio autorizzato `crmevent.it` verificato, compare "crmevent.it".

## 4. Variabili da configurare su Aruba (backend)
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (già presenti; eventualmente nuovi valori)
- `GOOGLE_LOGIN_REDIRECT_URI=https://api.crmevent.it/api/oauth/google/callback`
- `FRONTEND_URL=https://crmevent.it`, `BACKEND_PUBLIC_URL=https://api.crmevent.it`
- `JWT_SECRET` robusto (≥ 32 caratteri), `CORS_ORIGINS=https://crmevent.it,https://www.crmevent.it`
Nessun segreto nel frontend (riceve solo l'URL del backend).
Cookie: con frontend e API entrambi sotto crmevent.it si può passare a `SameSite=Lax; Domain=.crmevent.it` (oggi `SameSite=None; Secure`, funziona comunque).

## 5. Continuità degli account
- Abbinamento per email verificata → stesso `user_id`, stesse `memberships`, ruoli e permessi: nessun duplicato, nessuna cancellazione.
- Al primo login col nuovo sistema si salva `google_sub` sull'utente; poi abbinamento prioritario per `google_sub`.
- Super Admin e utenti con password: invariati.
- Collaboratori invitati: l'accettazione invito con Google funziona come oggi (email dell'invito = email Google).
- Nessuna migrazione dati obbligatoria. Prima del rilascio contare in produzione `users.auth_provider="google"` (in anteprima: 0 su 16).
- Utente che usa un account Google con email diversa da quella registrata: non viene collegato automaticamente (accede con password o collegamento manuale).

## 6. Rischi e mitigazioni
| Rischio | Mitigazione |
|---|---|
| `redirect_uri_mismatch` | Registrare esattamente gli URI di produzione e preview |
| Verifica brand non ancora completata | Il login funziona comunque; logo visibile dopo la verifica |
| Sessioni Google esistenti | Doppio supporto 7 giorni |
| App OAuth in stato "Test" | Solo utenti di test possono accedere → pubblicare prima del rilascio |
| Account takeover tramite email non verificata | Accettare solo `email_verified=true`, `state`+PKCE+`nonce` |
| Safari/iOS e cookie cross-site | Flusso server-side con redirect top-level; JWT impostato dal dominio API |

## 7. Test previsti (dopo implementazione, su preview)
Nuova registrazione Google · login Google utente esistente · Super Admin (password) · invito collaboratore con Google · collegamento organizzazione · logout/login · desktop + iPhone Safari + Android Chrome · assenza di riferimenti Emergent.

## 8. Altri riferimenti Emergent (non di login)
Fallback email Resend via integrations.emergentagent.com, storage legacy, logo email su CDN Emergent, chiave IA Emergent: da valutare separatamente.
