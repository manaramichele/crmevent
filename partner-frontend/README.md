# CRMEvent Partner (partner.crmevent.it)

App React indipendente. Backend condiviso: `/api/partner/*` e `/api/platform/partner*` su api.crmevent.it (stesso database, collezioni `partner_*`).

## Build
- Anteprima Emergent: `CI=false yarn build:preview` → servita da `/api/partner-preview/` (solo se il backend ha `PARTNER_PREVIEW_DIR`).
- Produzione: `REACT_APP_BACKEND_URL=https://api.crmevent.it yarn build` → `build/`.

## Deploy automatico (GitHub Actions)
1. Su GitHub: Add file → Create new file → `.github/workflows/partner-deploy.yml`, incollando `deploy/partner-deploy.yml.example`.
2. Usa gli stessi secrets di `deploy-production.yml` (ARUBA_HOST, ARUBA_USER, ARUBA_SSH_KEY).
3. Il workflow parte solo per modifiche in `partner-frontend/**`; crea `/opt/crmevent/partner/releases/<data>-<sha>/build` e sposta il link `current` in modo atomico (conserva le ultime 7 release).
4. Rollback: Actions → Deploy CRMEvent Partner → Run workflow → `rollback_to` = nome release.

Nota: `deploy-production.yml` parte a ogni push su main (nessun filtro percorsi) e continuerà a eseguire `/opt/crmevent/deploy-from-github.sh` anche per modifiche al solo portale.

## Nginx (partner.crmevent.it)
`root /opt/crmevent/partner/current/build;` e `location / { try_files $uri /index.html; }`. Al primo deploy, se `current` è una cartella reale viene spostata in `releases/initial` e sostituita da un link simbolico.

## Backend produzione (.env, aggiungere senza sovrascrivere)
- `CORS_ORIGINS`: aggiungere `https://partner.crmevent.it`
- `PARTNER_URL=https://partner.crmevent.it`
- NON impostare `PARTNER_PREVIEW_DIR`
- Login Google partner: usa lo stesso client e redirect URI di `GOOGLE_LOGIN_*` (intent=partner).
- Stripe: abilitare l'evento webhook `charge.refunded` sull'endpoint esistente.

## Frontend principale (build su Aruba)
- `REACT_APP_PARTNER_URL=https://partner.crmevent.it` (link "Diventa Partner" nel footer).
