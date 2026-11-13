# --- CRMEvent: readiness backend dopo il riavvio (sostituisce "sleep 3 ... fi" in /opt/crmevent/backend/deploy-backend.sh) ---
# Tentativi ogni 5s fino a 120s. 502/503/000 durante l'avvio sono temporanei. Se non diventa operativo: "false" -> rollback come prima.
READY_URL="${READY_URL:-https://api.crmevent.it/api/health}"
FALLBACK_URL="${FALLBACK_URL:-https://api.crmevent.it/docs}"
READY_TIMEOUT="${READY_TIMEOUT:-120}"
READY_INTERVAL="${READY_INTERVAL:-5}"
READY_OK=0
ATTEMPT=0
START_TS=$(date +%s)
echo "Readiness backend: endpoint $READY_URL (riserva $FALLBACK_URL), ogni ${READY_INTERVAL}s, massimo ${READY_TIMEOUT}s"
while :; do
  ATTEMPT=$((ATTEMPT + 1))
  ELAPSED=$(( $(date +%s) - START_TS ))
  SVC_STATE=$(systemctl is-active crmevent-backend 2>/dev/null || true)
  CHECKED="$READY_URL"
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$READY_URL" 2>/dev/null || true)
  if [ "$HTTP_CODE" = "404" ]; then
    CHECKED="$FALLBACK_URL"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$FALLBACK_URL" 2>/dev/null || true)
  fi
  [ -z "$HTTP_CODE" ] && HTTP_CODE="000"
  echo "Tentativo $ATTEMPT (${ELAPSED}s): servizio=$SVC_STATE endpoint=$CHECKED HTTP=$HTTP_CODE"
  if [ "$SVC_STATE" = "active" ] && [ "$HTTP_CODE" = "200" ]; then READY_OK=1; break; fi
  if [ "$ELAPSED" -ge "$READY_TIMEOUT" ]; then break; fi
  sleep "$READY_INTERVAL"
done
if [ "$READY_OK" = "1" ]; then
  echo "Backend operativo: $ATTEMPT tentativi, ${ELAPSED}s, HTTP 200 su $CHECKED"
else
  echo "ERRORE: backend non operativo entro ${READY_TIMEOUT}s: $ATTEMPT tentativi, ultimo HTTP $HTTP_CODE su $CHECKED, servizio=$SVC_STATE"
  journalctl -u crmevent-backend -n 40 --no-pager 2>/dev/null || true
  false
fi
# --- fine readiness backend ---
