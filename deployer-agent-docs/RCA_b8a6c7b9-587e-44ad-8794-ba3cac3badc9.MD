# Production Secret Audit — CRMEvent (manage-events-12)

**Active run:** b8a6c7b9-587e-44ad-8794-ba3cac3badc9 (redeploy, status success)
**Live URL:** https://manage-events-12.emergent.host
**Custom domains:** crmevent.it, www.crmevent.it (both verified)
**Request:** Report presence + value-match (yes/no, no values revealed) for APP_URL, FRONTEND_URL, BACKEND_PUBLIC_URL. No deploy / no secret change requested.

## Findings (via list_secrets with `equals`, active run only)

| Key | Present | Empty | matches_expected (vs https://crmevent.it) |
|---|---|---|---|
| APP_URL | Yes | No | YES — equals https://crmevent.it ✅ correct |
| FRONTEND_URL | Yes | No | YES — equals https://crmevent.it ✅ correct |
| BACKEND_PUBLIC_URL | Yes | No | YES — equals https://crmevent.it ⚠️ WRONG (should be backend's own public URL) |

## Assessment
- APP_URL and FRONTEND_URL already point to the live custom domain https://crmevent.it. System emails (password reset, account activation) and calendar links built from APP_URL will therefore use the production public domain as intended. No action needed on these two.
- BACKEND_PUBLIC_URL is set to https://crmevent.it, i.e. the frontend domain. Per the requester this key must remain the backend's OWN public URL (e.g. https://manage-events-12.emergent.host). If backend self-referencing absolute links / callbacks depend on this, the current value is misconfigured.

## Also noted
- GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are present but EMPTY (only relevant if Google OAuth is expected).

## Suggested fix (owner: User)
- In Deployment Panel → Secrets, change BACKEND_PUBLIC_URL back to the backend's own public URL, then redeploy so the new value takes effect. Leave APP_URL and FRONTEND_URL as-is.

## Scope / caveats
- Values were never revealed; only presence, empty-state, and equality-to-expected were checked. `matches_expected=true` for BACKEND_PUBLIC_URL means its stored value equals https://crmevent.it.
- list_secrets reflects the ACTIVE run only. No deploy or secret change was performed.
