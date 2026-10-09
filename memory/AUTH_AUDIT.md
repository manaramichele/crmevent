# CRMEvent – Audit autenticazione (2026-10-09) – SOLO ANALISI, nessuna modifica al codice

## 1. Stato attuale
| Componente | Dove | Note |
|---|---|---|
| Login email/password | `POST /api/auth/login` (server.py ~810) | bcrypt (`hash_password`/`verify_password`), JWT HS256 firmato con `JWT_SECRET`, cookie httpOnly `access_token` 7 gg. **Già indipendente da Emergent.** |
| Registrazione | `POST /api/auth/register-organization`, `/auth/complete-organization`, `/auth/complete-profile`, `/invites/{token}/register` | Indipendente da Emergent. |
| Password dimenticata / reset / attivazione | `/auth/forgot-password`, `/auth/reset-password`, `/auth/activate`, `/auth/change-password` | Indipendenti (email via Brevo, `EMAIL_PROVIDER=brevo`). |
| **Login/registrazione con Google** | Frontend: `Login.jsx:41`, `Register.jsx:45`, `Invite.jsx:98` → redirect a `https://auth.emergentagent.com/?redirect=...`; ritorno con `#session_id=` gestito da `App.js:131` → `AuthCallback.jsx`, `Invite.jsx:52`, `AuthContext.js:34`. Backend: `POST /api/auth/session` (server.py ~824) chiama `EMERGENT_SESSION_URL = https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data` (server.py:60) | **Unico punto che dipende da Emergent**: è la causa di dominio auth.emergentagent.com, logo Emergent, "Grant Permission to Crmevent" e testi in inglese. |
| Sessioni | `_get_base_user` legge cookie `session_token` (Google/Emergent, salvato in `user_sessions`, 7 gg) oppure `access_token` (JWT) o header Bearer | Due meccanismi paralleli. |
| Utenti ↔ organizzazioni | `users` (chiave `user_id`, email univoca) + `memberships` (user_id, org_id, ruolo, permessi) | Il collegamento alle organizzazioni NON dipende dal provider di login. |
| Google Calendar | `/api/oauth/calendar/*` con **client OAuth proprio** (`GOOGLE_CLIENT_ID/SECRET`, redirect `${BACKEND_PUBLIC_URL}/api/oauth/calendar/callback`) | Già indipendente: esiste già un progetto Google Cloud di CRMEvent riutilizzabile. |

Altre dipendenze Emergent (non di autenticazione, da valutare separatamente):
- `email_utils.py`: fallback email Resend via `integrations.emergentagent.com` (primario Brevo).
- `storage_utils.py`: lettura file "legacy" dallo storage Emergent (oggi `STORAGE_BACKEND=local`).
- `brevo_funnel.py`: `LOGO_URL` ospitato su CDN Emergent.
- Funzioni IA: `EMERGENT_LLM_KEY` (emergentintegrations).

## 2. Risposte alle domande
- **Dominio personalizzato (auth.crmevent.it) con Emergent Auth?** No: è un servizio gestito, dominio/logo/testi/lingua non sono personalizzabili.
- **Personalizzare logo, nome e consenso?** Sì, ma solo con un proprio client Google OAuth: la schermata Google mostra nome app "CRMEvent", logo, dominio crmevent.it, link a privacy e termini, e la lingua del browser dell'utente (quindi italiano).
- **Serve migrare?** Sì, ma solo il login Google. Password, sessioni JWT, inviti e reset restano invariati.
- **Nuovo provider esterno (Auth0, Firebase, ecc.)?** Non necessario. Consigliato: Google OAuth 2.0 / OpenID Connect gestito direttamente dal backend CRMEvent (nessun costo, nessun terzo intermedio).

## 3. Soluzione consigliata
1. Nel progetto Google Cloud già usato per Calendar: configurare la schermata di consenso OAuth (tipo "Esterno", nome "CRMEvent", logo, email di supporto, domini autorizzati `crmevent.it`, link Privacy e Termini) e richiedere la verifica del brand (necessaria per mostrare il logo; scope base `openid email profile` non richiedono revisione di sicurezza).
2. Creare (o riusare) un client OAuth "Applicazione web" con redirect URI `https://<dominio-backend>/api/oauth/google/callback` (es. `https://app.crmevent.it/api/oauth/google/callback`).
3. Backend: nuovi endpoint `GET /api/oauth/google/start` (genera `state` firmato + PKCE + `nonce`, redirect a Google) e `GET /api/oauth/google/callback` (scambio code, verifica `id_token`: firma, `aud`, `iss`, `exp`, `nonce`, `email_verified=true`), poi stessa logica di oggi: cerca utente per email → se esiste lo collega, se no lo crea; emette il **JWT `access_token`** già usato dal login password. Salvare `google_sub` sull'utente.
4. Frontend: i tre pulsanti Google (Login, Registrati, Invito) puntano a `/api/oauth/google/start?next=...`; rimuovere `AuthCallback` basato su `#session_id`.
5. Periodo di transizione: mantenere `/api/auth/session` e la lettura del cookie `session_token` per 7 giorni (scadenza naturale delle sessioni esistenti), poi rimuovere `EMERGENT_SESSION_URL`.

## 4. Account esistenti e organizzazioni
- Il collegamento avviene per **email** (già oggi): stesso `user_id`, stesse `memberships`, ruoli e permessi → nessuna nuova registrazione.
- Utenti che hanno usato solo Google: continueranno ad accedere con Google (stessa email). Opzionale: proporre "Imposta una password" dal profilo.
- Primo accesso dopo la migrazione: salvare `google_sub`; in seguito abbinare prima per `google_sub` e poi per email (protegge da cambi email Google).
- Nell'anteprima tutti i 17 utenti sono `auth_provider=password`; in produzione va contato quanti hanno `auth_provider=google` prima del rilascio.

## 5. Configurazioni necessarie
- **DNS (Aruba)**: nessun nuovo record obbligatorio. `auth.crmevent.it` non serve (il callback può stare sul dominio backend). Serve la verifica di proprietà del dominio in Google Search Console (record TXT) per i domini autorizzati della schermata di consenso.
- **HTTPS** valido su frontend e backend (redirect URI solo https).
- **Variabili d'ambiente**: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (già presenti), `GOOGLE_LOGIN_REDIRECT_URI`, `FRONTEND_URL`, `JWT_SECRET` robusto (≥32 caratteri), `CORS_ORIGINS` limitato ai domini CRMEvent.
- **Cookie**: se frontend e backend sono sotto `crmevent.it`, valutare `SameSite=Lax` + `Domain=.crmevent.it` (oggi `SameSite=None; Secure`).
- **Sicurezza**: `state` monouso con scadenza breve, PKCE, verifica `nonce` e `email_verified`, nessun token in URL/fragment, rate-limit su callback, log audit dei login Google.

## 6. Rischi
| Rischio | Mitigazione |
|---|---|
| Verifica brand Google richiede alcuni giorni (senza verifica il logo non appare) | Avviare subito la richiesta; il login funziona anche prima, con nome app. |
| Redirect URI errato → errore `redirect_uri_mismatch` | Registrare esattamente gli URI di produzione e di test. |
| Sessioni Google esistenti | Periodo di doppio supporto di 7 giorni. |
| Account Google con email diversa da quella registrata | Restano accessibili con password; eventuale collegamento manuale dal profilo. |
| Google Calendar usa scope sensibile `calendar` | Già oggi soggetto a verifica: la verifica del login non lo peggiora; può essere fatta nello stesso progetto. |

## 7. Passaggi operativi (dopo approvazione)
1. Cliente: configurazione schermata consenso + verifica dominio/brand su Google Cloud; fornire eventuale nuovo client ID/secret.
2. Sviluppo: endpoint backend start/callback + aggiornamento 3 pulsanti frontend (≈ mezza giornata) + test su preview.
3. Test: desktop, iPhone (Safari), Android (Chrome), account esistente password+Google, nuovo utente, invito.
4. Deploy su Aruba con doppio supporto; dopo 7 giorni rimozione codice Emergent Auth.
