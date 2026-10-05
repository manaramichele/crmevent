# Secrets/Env Inventory — Read-only Audit (CRMEvent / manage-events-12)

**Request type:** Read-only inventory of production secret/env KEY NAMES. No deploy, restart, rotation, or modification performed.

**Scope:** Active (published) production run `fe9581cf-21ee-4d82-abdf-c830dd1bb27b` — URL https://manage-events-12.emergent.host, domains crmevent.it / www.crmevent.it. Source: list_secrets (metadata_available=true) + mongo_query (db_name).

## Requested variables — presence
All 37 requested keys are PRESENT and non-empty (is_empty=false):
JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD, FRONTEND_URL, CORS_ORIGINS, EMAIL_PROVIDER, EMAIL_FROM_ADDRESS, EMAIL_FROM_NAME, BREVO_API_KEY, BREVO_WEBHOOK_TOKEN, WEBHOOK_CRON_SECRET, STRIPE_MODE, STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_ACCOUNT_ID, CRMEVENT_STRIPE_MODE, CRMEVENT_STRIPE_SECRET_KEY_LIVE, CRMEVENT_STRIPE_PUBLISHABLE_KEY_LIVE, CRMEVENT_STRIPE_WEBHOOK_SECRET_LIVE, CRMEVENT_STRIPE_TAX_RATE_ID_LIVE, FIC_MODE, FIC_CLIENT_ID, FIC_CLIENT_SECRET, FIC_COMPANY_ID, FIC_REDIRECT_URI, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, META_APP_ID, META_APP_SECRET, MONGO_URL, DB_NAME, APP_URL, BACKEND_PUBLIC_URL, EMERGENT_LLM_KEY, EMERGENT_EMAIL_KEY.

**None ABSENT.**

## Values for non-sensitive variables
Tooling does NOT return secret values (encrypted at rest) — not even for non-sensitive vars. Therefore values for FRONTEND_URL, CORS_ORIGINS, EMAIL_PROVIDER, EMAIL_FROM_ADDRESS, EMAIL_FROM_NAME, STRIPE_MODE, CRMEVENT_STRIPE_MODE, FIC_MODE, FIC_REDIRECT_URI, APP_URL, BACKEND_PUBLIC_URL cannot be provided here. Read them in Deployment Panel → Secrets.

Only exception (identifier, not a secret):
- DB_NAME = manage-events-12-test_database

## Other production keys NOT in the requested list (names only)
- BREVO_AVAILABILITY_ENABLED
- CRMEVENT_STRIPE_ACCOUNT_ID_LIVE
- ENABLE_HEALTH_CHECK
- INTEGRATION_PROXY_URL (platform system key)
- REACT_APP_BACKEND_URL (platform system key)
- RESEND_API_KEY
- WDS_SOCKET_PORT

## Observations (non-blocking)
- Both generic STRIPE_* and CRMEVENT_STRIPE_*_LIVE key families are configured.
- Both BREVO_API_KEY and RESEND_API_KEY email-provider keys are present; verify which EMAIL_PROVIDER is actually selected.
