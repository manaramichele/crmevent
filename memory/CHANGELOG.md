# CRMEvent — Changelog

## 2026-06 — Multi-tenant SaaS + Pricing + Trial (backend 22/22 pytest PASS; frontend e2e verified)

### 🔴 Multi-tenant data isolation (release gate — VERIFIED)
- Retrofitted the entire app from single-tenant to true multi-tenant. Every operational document now carries `org_id`.
- `oq(user, **extra)` helper pins the caller's `org_id`; applied in the `crud_routes` factory AND every manual endpoint (dashboard, search, notifications, persons-enriched, persons-match, person/company detail, company-contacts, invite, set-access, hospitality bulk/group/aggregate, briefing `_build_briefing(event_id, org_id)` + versions, me/* personal area, settings per-org, upload/download).
- Anti-IDOR: GET/PUT/DELETE by id are scoped `{"id": item_id, "org_id": ...}` → cross-tenant access returns 404, no mutation. Verified with 22 backend tests (two orgs, tamper GET/PUT/DELETE/briefing/detail).
- Support collections (KB/FAQ/categories/feature-requests/tickets) are platform-level (NOT org-scoped), gated by `require_support_manager`.

### Roles
- `superadmin`: platform owner CRMEvent (existing `ADMIN_EMAIL` account promoted, `org_id=null`). Sees `/piattaforma`. Cannot access org CRM.
- `admin`: organization owner/admin (org_id). Full CRM for own org only.
- `staff`/`volunteer`: org members, personal area only.
- `require_admin` now requires role admin AND org_id; `require_superadmin` = role superadmin.

### Registration & Trial
- `POST /api/auth/register-organization` {nome, cognome, email, password, org_name, telefono, accept_terms} → creates Organization + admin user + 14-day trial (no card).
- `POST /api/auth/complete-organization` for Google users without an org.
- Subscription model on organizations: states trial/active/expired/canceled/past_due/suspended; `_sub_summary` computes days_left + access (full/limited) and auto-expires trial. Trial end does NOT delete data (limited access only).
- `GET /api/account/subscription`; `GET /api/platform/stats` + `/api/platform/organizations` (superadmin): orgs, trial/active/expired counts, MRR/ARR, leads.
- Google new-user role default = admin (needs org); leads endpoints moved to superadmin.

### Frontend
- Public **/prezzi** (single plan, monthly 19,90 € / annual 199 € + IVA, cycle toggle, 2-mesi-inclusi badge, 12-feature list, "Aggiornamenti inclusi" section, 3× CTA "Prova CRMEvent gratis").
- Public **/registrati** (org signup, mandatory un-preselected terms checkbox with legal links) and **/completa-organizzazione** (Google users).
- **/account** (Account e abbonamento): status, trial days, price, "Attiva CRMEvent" (payments coming soon toast).
- **/piattaforma** superadmin console (stats + orgs table).
- Layout: role-based nav (ORG_NAV vs SUPER_NAV) + trial banner. Landing header/footer + Login link to Prezzi/Registrati. `StatusBadge` forwards props (data-testid).
- Guards in App.js: Protected (needs_org redirect), AdminOnly (superadmin→/piattaforma), SuperAdminOnly.

### Stripe
- Data model + subscription states scaffolded. Real payments NOT wired yet (per user: validate multi-tenant first). Integration_expert Stripe playbook obtained (Flow A claimable sandbox) for next step.

### Notes
- `seed_demo()` no longer called on startup (clean production slate). `/admin/reset-data` is now org-scoped.
- Startup creates `org_id` indexes on operational collections.
