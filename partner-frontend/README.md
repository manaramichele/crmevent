# CRMEvent Partner (partner.crmevent.it)

Frontend React indipendente; backend condiviso (`/api/partner/*` su api.crmevent.it).

- Sviluppo/anteprima Emergent: `yarn build:preview` → servito da `/api/partner-preview/` (solo se `PARTNER_PREVIEW_DIR` è impostato nel backend).
- Produzione: `REACT_APP_BACKEND_URL=https://api.crmevent.it yarn build` → `/opt/crmevent/partner/current/build`.
- Workflow GitHub: vedi `deploy/partner-deploy.yml.example`.

Nginx (SPA): `root /opt/crmevent/partner/current/build; location / { try_files $uri /index.html; }`

Backend produzione: aggiungere `https://partner.crmevent.it` a `CORS_ORIGINS`, impostare `PARTNER_URL=https://partner.crmevent.it`,
non impostare `PARTNER_PREVIEW_DIR`. Stripe: abilitare l'evento webhook `charge.refunded`.
