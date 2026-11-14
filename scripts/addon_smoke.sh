#!/bin/bash
# Smoke test addons: TEST_ org Silver -> attiva 1 evento incluso, secondo evento bloccato.
API=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)/api
J=/tmp/addon_smoke; mkdir -p $J
SA=$J/sa.txt; ORG=$J/org.txt
curl -s -c $SA -X POST $API/auth/login -H "Content-Type: application/json" -d '{"email":"manara.michele.pro@gmail.com","password":"CrmEvent2026!"}' >/dev/null
EM="test_addon_$(date +%s)@example.com"
curl -s -c $ORG -X POST $API/auth/register-organization -H "Content-Type: application/json" \
  -d "{\"nome\":\"TEST\",\"cognome\":\"Addon\",\"email\":\"$EM\",\"password\":\"TestAddon2026!\",\"org_name\":\"TEST_Addon Org\",\"telefono\":\"+393471234567\",\"accept_terms\":true}" > $J/reg.json
head -c 200 $J/reg.json; echo
OID=$(curl -s -b $ORG $API/auth/me | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('org_id') or d.get('user',{}).get('org_id'))")
echo "org $OID"
echo "--- trial status"; curl -s -b $ORG $API/addons/planner | python3 -c "import sys,json;d=json.load(sys.stdin);print({k:d.get(k) for k in ('mode','plan','included','included_free','unrestricted')})"
curl -s -b $SA -X PUT $API/platform/saas/orgs/$OID/admin -H "Content-Type: application/json" -d '{"plan":"silver","status":"active"}' | head -c 150; echo
E1=$(curl -s -b $ORG -X POST $API/events -H "Content-Type: application/json" -d '{"nome":"TEST_Ev1","data_inizio":"2026-12-13"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
E2=$(curl -s -b $ORG -X POST $API/events -H "Content-Type: application/json" -d '{"nome":"TEST_Ev2","data_inizio":"2026-12-20"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "events $E1 $E2"
echo "--- planner before activation (expect 403)"; curl -s -b $ORG $API/planner/events/$E1/projects | head -c 200; echo
echo "--- activate E1"; curl -s -b $ORG -X POST $API/addons/planner/events/$E1/activate; echo
echo "--- activate E1 again (expect 400)"; curl -s -b $ORG -X POST $API/addons/planner/events/$E1/activate; echo
echo "--- planner E1 (expect 200)"; curl -s -b $ORG $API/planner/events/$E1/projects | head -c 120; echo
echo "--- activate E2 (expect 403 addon_required)"; curl -s -b $ORG -X POST $API/addons/planner/events/$E2/activate; echo
echo "--- checkout E2 no price (expect 400)"; curl -s -b $ORG -X POST $API/addons/planner/checkout -H "Content-Type: application/json" -d "{\"origin_url\":\"https://x\",\"event_id\":\"$E2\"}"; echo
echo "--- SA grant E2"; curl -s -b $SA -X POST $API/platform/addons/orgs/$OID/grants -H "Content-Type: application/json" -d "{\"product\":\"planner\",\"source\":\"promo\",\"events_total\":1,\"expires_at\":\"2027-12-31\",\"event_ids\":[\"$E2\"]}"; echo
echo "--- planner E2 (expect 200)"; curl -s -b $ORG -o /dev/null -w "%{http_code}\n" $API/planner/events/$E2/projects
echo "--- downgrade bronze"; curl -s -b $SA -X PUT $API/platform/saas/orgs/$OID/admin -H "Content-Type: application/json" -d '{"plan":"bronze","status":"active"}' -o /dev/null -w "%{http_code}\n"
echo "--- planner E1 after downgrade (expect 403)"; curl -s -b $ORG -o /dev/null -w "%{http_code}\n" $API/planner/events/$E1/projects
echo "--- planner E2 promo still (expect 200)"; curl -s -b $ORG -o /dev/null -w "%{http_code}\n" $API/planner/events/$E2/projects
echo "--- eventmap status"; curl -s -b $ORG $API/addons/eventmap | python3 -c "import sys,json;d=json.load(sys.stdin);print({k:d.get(k) for k in ('plan','included','videos_total','videos_available','packages')})"
echo "--- SA orgs row"; curl -s -b $SA $API/platform/addons/orgs | python3 -c "import sys,json;print([r for r in json.load(sys.stdin) if r['id']=='$OID'])"
echo "$OID" > $J/oid
