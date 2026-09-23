# CRMEvent Auth Testing

## Credentials (admin, email/password)
- Email: manara.michele.pro@gmail.com
- Password: CrmEvent2026!
- Role: admin

## Auth endpoints
- POST /api/auth/register {email,password,name}
- POST /api/auth/login {email,password}  -> sets httpOnly access_token cookie
- POST /api/auth/session (Google, header X-Session-ID) -> sets session_token cookie
- GET /api/auth/me
- POST /api/auth/logout

## Notes
- Unified auth: get_current_user accepts either JWT access_token cookie or Google session_token cookie, or Authorization: Bearer.
- Same-origin app (frontend + backend share preview domain). Cookies: secure, samesite=none.

## Quick API test
curl -c cookies.txt -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" -d '{"email":"manara.michele.pro@gmail.com","password":"CrmEvent2026!"}'
curl -b cookies.txt http://localhost:8001/api/auth/me
curl -b cookies.txt http://localhost:8001/api/dashboard
