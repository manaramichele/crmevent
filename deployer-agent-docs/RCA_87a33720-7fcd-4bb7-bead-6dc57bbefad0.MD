# RCA — CRMEvent (manage-events-12): invite emails still sent from noreply@crmevent.it

## Problem statement
Invite/transactional emails in PRODUCTION still arrive FROM `noreply@crmevent.it`.
Expected FROM is `hello@crmevent.it`. Preview `backend/.env` was corrected
(`EMAIL_FROM_ADDRESS` = `hello@crmevent.it`), but production behavior is unchanged.

## Investigation (read-only)
- Active/serving run: `87a33720-7fcd-4bb7-bead-6dc57bbefad0` (redeploy, success).
- `list_secrets` (active run) with expected comparison for `EMAIL_FROM_ADDRESS`:
  - `EMAIL_FROM_ADDRESS` → present, non-empty, **matches_expected = false** (does NOT equal `hello@crmevent.it`)
  - `RESEND_API_KEY` → present, non-empty
  - `EMERGENT_EMAIL_KEY` → present, non-empty
  - `EMAIL_FROM_NAME` → present, non-empty
- Secret VALUES are never revealed; conclusions are from metadata only.

## Root cause
The app builds the sender as `CRMEvent <${EMAIL_FROM_ADDRESS}>` and uses that custom
sender only when BOTH `RESEND_API_KEY` and `EMAIL_FROM_ADDRESS` are set. Both ARE set in
production, so the custom path is active — but production `EMAIL_FROM_ADDRESS` still holds
the OLD value (proven by matches_expected=false), so emails go out from
`noreply@crmevent.it`.

The preview `.env` correction does not reach production: `EMAIL_FROM_ADDRESS` is a USER
(custom) secret that was already customized in prod, so it is carried forward from the
previous production run and is NOT overwritten by the preview `.env` on deploy. A redeploy
alone will therefore NOT change it.

## Fix (user action — before next deploy)
1. Deployment Panel → Secrets → set `EMAIL_FROM_ADDRESS` = `hello@crmevent.it`.
2. Redeploy so the new value is written into the run environment.
3. (Optional) Verify the Resend sending domain/identity for `crmevent.it` allows
   `hello@` as a verified sender in the Resend dashboard.

## Notes
- `RESEND_API_KEY`, `EMERGENT_EMAIL_KEY`, `EMAIL_FROM_NAME` are all present/non-empty — no
  action needed on those.
- This was a read-only diagnosis; no deploy/redeploy or manifest change was performed.
