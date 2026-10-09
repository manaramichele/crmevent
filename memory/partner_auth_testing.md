Save this section to /app/auth_testing.md (partner auth, see /app/memory/test_credentials.md)
- Partner auth: POST /api/partner/login sets `partner_token` cookie (JWT type "partner"); org cookies (access_token/session_token) never authenticate /api/partner/*, and partner_token never authenticates org APIs.
- Brute force: 5 failed logins per ip:email → 429 for 15 min (collection partner_login_attempts).
- Reset: POST /api/partner/forgot-password → partner_reset_tokens (sha256 hash, 1h TTL); POST /api/partner/reset-password {token,password}.
