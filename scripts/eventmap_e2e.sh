#!/bin/bash
# E2E Event Map: org TEST_ Silver, attivazione, omaggio 5 video, upload GPX reale, generazione 15s/30s/60s, download.
API=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)/api
J=/tmp/em_e2e; rm -rf $J; mkdir -p $J; SA=$J/sa; ORG=$J/org
curl -s -c $SA -X POST $API/auth/login -H "Content-Type: application/json" -d '{"email":"manara.michele.pro@gmail.com","password":"CrmEvent2026!"}' >/dev/null
EM="test_em_$(date +%s)@example.com"
curl -s -c $ORG -X POST $API/auth/register-organization -H "Content-Type: application/json" -d "{\"nome\":\"TEST\",\"cognome\":\"EventMap\",\"email\":\"$EM\",\"password\":\"TestEventMap2026!\",\"org_name\":\"TEST_EventMap Org\",\"telefono\":\"+393471234567\",\"accept_terms\":true}" >/dev/null
OID=$(curl -s -b $ORG $API/auth/me | python3 -c "import sys,json;print(json.load(sys.stdin)['org_id'])")
curl -s -b $SA -X PUT $API/platform/saas/orgs/$OID/admin -H "Content-Type: application/json" -d '{"plan":"silver","status":"active"}' >/dev/null
E=$(curl -s -b $ORG -X POST $API/events -H "Content-Type: application/json" -d '{"nome":"TEST_Pisa Run","data_inizio":"2026-12-13"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "org $OID event $E"
echo "-- video before activation (expect 403)"; curl -s -b $ORG -X POST $API/eventmap/events/$E/videos -H "Content-Type: application/json" -d '{"track_id":"x"}' | head -c 150; echo
curl -s -b $ORG -X POST $API/addons/eventmap/events/$E/activate; echo
echo "-- bad gpx (expect 400)"; echo "<gpx></gpx>" > $J/bad.gpx; curl -s -b $ORG -F "file=@$J/bad.gpx" $API/eventmap/events/$E/tracks; echo
T=$(curl -s -b $ORG -F "file=@/app/backend/tests/fixtures/pisa_run.gpx" $API/eventmap/events/$E/tracks | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['id'], d['distance_m'], d['points'], file=sys.stderr);print(d['id'])")
echo "-- 0 videos included (expect 403 addon_videos)"; curl -s -b $ORG -X POST $API/eventmap/events/$E/videos -H "Content-Type: application/json" -d "{\"track_id\":\"$T\",\"duration\":15}" | head -c 160; echo
curl -s -b $SA -X POST $API/platform/addons/orgs/$OID/grants -H "Content-Type: application/json" -d '{"product":"eventmap","source":"superadmin","events_total":1,"videos_total":3}'; echo
curl -s -b $ORG -X POST $API/eventmap/tracks/$T/preview -H "Content-Type: application/json" -d '{"style":"streets","format":"1:1"}' -o $J/preview.jpg -w "preview %{http_code}\n"
V1=$(curl -s -b $ORG -X POST $API/eventmap/events/$E/videos -H "Content-Type: application/json" -d "{\"track_id\":\"$T\",\"duration\":15,\"format\":\"9:16\",\"music\":\"sportiva\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
V2=$(curl -s -b $ORG -X POST $API/eventmap/events/$E/videos -H "Content-Type: application/json" -d "{\"track_id\":\"$T\",\"duration\":30,\"format\":\"1:1\",\"style\":\"streets\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
V3=$(curl -s -b $ORG -X POST $API/eventmap/events/$E/videos -H "Content-Type: application/json" -d "{\"track_id\":\"$T\",\"duration\":60,\"format\":\"16:9\",\"music\":\"cinematografica\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "-- 4th over limit (expect 403)"; curl -s -b $ORG -X POST $API/eventmap/events/$E/videos -H "Content-Type: application/json" -d "{\"track_id\":\"$T\",\"duration\":15}" | head -c 160; echo
START=$(date +%s)
for V in $V1 $V2 $V3; do
  while true; do S=$(curl -s -b $ORG $API/eventmap/videos/$V | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'], d.get('progress'), d.get('error') or '')"); case "$S" in completed*|error*) break;; esac; sleep 5; done
  echo "$V $S after $(( $(date +%s)-START ))s"
  curl -s -b $ORG "$API/eventmap/videos/$V/file?download=1" -o $J/$V.mp4 -w "download %{http_code} %{size_download}\n"
done
curl -s -b $ORG $API/eventmap/events/$E | python3 -c "import sys,json;d=json.load(sys.stdin);print('rights',d['rights'])"
echo "$OID $E $V1 $V2 $V3" > $J/ids
