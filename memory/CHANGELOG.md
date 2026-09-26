# CRMEvent — Changelog

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
