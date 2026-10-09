# Aggiornamento 2026-10-09
- Logo consenso Google: `frontend/public/google-oauth-logo-120.png` (120×120 PNG, ricavato senza modifiche dal logo quadrato calendario su Tiffany `favicon-512.png`). URL: https://crmevent.it/google-oauth-logo-120.png
- Lingua: parametro `hl` nella richiesta a Google = `it` di default; se il browser dell'utente preferisce un'altra lingua, viene passata quella.
- Cellulare obbligatorio al primo accesso: popup "Completa la registrazione" (nuovi organizzatori) / "Completa profilo" (invitati). Brevo "Utenti registrati": sync in complete-organization e complete-profile.
- Provider in produzione: NON attivo finché non confermato (GOOGLE_LOGIN_PROVIDER assente/emergent).


# CRMEvent – Login Google proprietario: report implementazione (2026-10-09)
Stato: implementato e testato in anteprima (iteration_113: backend 16/16, frontend 100%). **Non attivo** (GOOGLE_LOGIN_PROVIDER=emergent). Nessun deploy.

## File
- NUOVO `backend/google_login.py` – config, `resolve_identity`, endpoint start/callback/link.
- `backend/server.py` – import + `include_router(google_login.build_router(...))`.
- NUOVO `frontend/src/lib/googleAuth.js` – `startGoogle()` (sceglie flusso CRMEvent o precedente in base a /config) + messaggi errore.
- NUOVO `frontend/src/components/GoogleLinkPrompt.jsx` – conferma password per collegamento.
- `frontend/src/pages/Login.jsx`, `Register.jsx`, `Invite.jsx` – pulsanti Google, errori `?google_error=`, prompt `?google_link=1`, accettazione automatica invito `&google=ok`.
Login email/password, reset, inviti, sessioni, ruoli e Google Calendar: invariati.

## Endpoint
| Metodo | Path | Funzione |
|---|---|---|
| GET | /api/oauth/google/config | `{provider: crmevent|emergent}` (pubblico, nessun segreto) |
| GET | /api/oauth/google/start?intent=login|register|invite&next=&invite= | state (DB, monouso, 10 min) + cookie httpOnly `g_oauth_state` + PKCE S256 + nonce → redirect Google |
| GET | /api/oauth/google/callback | verifica state+cookie, scambio code con code_verifier, verifica id_token (firma JWKS Google, aud, iss, exp, nonce, email_verified) → cookie JWT `access_token` → redirect FRONTEND_URL |
| POST | /api/oauth/google/link {password} | collegamento con password (Super Admin / conflitto), max 5 tentativi, 10 min |
Errori → `FRONTEND_URL/login?google_error=denied|state|exchange|invalid|unverified|no_account|disabled|conflict`. Nessun token nell'URL.

## Regole account
1. Abbinamento per `google_sub`; 2. altrimenti email verificata da Google → collegamento automatico; 3. Super Admin o email già collegata a un altro account Google → richiesta password CRMEvent; 4. nuovo account solo da Registrazione/Invito; dal Login con email sconosciuta → "Registrati". Utenti disattivati bloccati. Nessun duplicato (stesso user_id, memberships, ruoli).

## Variabili Aruba (backend)
```
GOOGLE_LOGIN_PROVIDER=crmevent
GOOGLE_LOGIN_CLIENT_ID=<Client ID "CRMEvent Login">
GOOGLE_LOGIN_CLIENT_SECRET=<Client Secret "CRMEvent Login">
GOOGLE_LOGIN_REDIRECT_URI=https://api.crmevent.it/api/oauth/google/callback
FRONTEND_URL=https://crmevent.it
BACKEND_PUBLIC_URL=https://api.crmevent.it
JWT_SECRET=<già presente, ≥32 caratteri>
```
NON modificare GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET (Google Calendar "CRMEvent Web"). Nessuna variabile nel frontend.
Nota nomi: si usano GOOGLE_LOGIN_CLIENT_ID/SECRET perché GOOGLE_CLIENT_ID/SECRET sono già occupate da Calendar.

## Attivazione su Aruba
1. Contare utenti Google in produzione: `db.users.countDocuments({auth_provider:"google"})` e quelli senza password `({auth_provider:"google", password_hash:{$exists:false}})`.
2. Google Cloud, client "CRMEvent Login": redirect URI esatto sopra; schermata consenso pubblicata ("In produzione"), dominio crmevent.it verificato.
3. Deploy del codice con `GOOGLE_LOGIN_PROVIDER=emergent` (nessun cambiamento visibile).
4. Impostare le variabili sopra e `GOOGLE_LOGIN_PROVIDER=crmevent`, riavviare il backend.
5. Verifica: `GET https://api.crmevent.it/api/oauth/google/config` → `crmevent`; login Google con account esistente, nuovo utente, invito, Super Admin (richiede password la prima volta).
Le sessioni Emergent già aperte restano valide fino a scadenza (7 gg): `/api/auth/session` non è stato rimosso.

## Rollback
Impostare `GOOGLE_LOGIN_PROVIDER=emergent` e riavviare il backend: i pulsanti tornano subito al login precedente. Nessun dato da ripristinare (si aggiunge solo `users.google_sub`). Rimozione definitiva di Emergent Auth solo dopo conferma.

## Esito test (anteprima, client fittizio)
Start/redirect con PKCE+state+nonce, errori callback (annullato, state falso/riusato, code non valido), tutte le regole di abbinamento, collegamento con password (blocco dopo 5 tentativi), pulsanti Login/Registrazione/Invito verso Google e non emergentagent.com, regressioni password/logout/Calendar, mobile 390px: OK.
Non testabile in anteprima: il passaggio reale su Google (serve il client vero) → da provare su Aruba.
Da verificare in produzione: il cookie `g_oauth_state` (SameSite=Lax) torna correttamente dal redirect Google (in anteprima il proxy lo riscrive).
