# Proposta cron/job — Rinnovo periodico eventi attivi (FASE E.2)

⚠️ NON ANCORA ATTIVATO. Richiede la tua autorizzazione prima di introdurlo in produzione.

## Modalità proposta
- Scheduler gestito dalla piattaforma Emergent (`.emergent/crons.yml`), che invoca un endpoint interno.
- Endpoint già pronto e idempotente: `POST /api/platform/events/run-renewals` → esegue `run_event_renewals()`.
- Logica: trova gli eventi `credit_state="attivo"` con `next_renewal_at <= adesso`; per ciascuno:
  - se la data evento è trascorsa → `concluso` (nessun addebito);
  - altrimenti addebita 20 crediti (dal catalogo) → nuovo `next_renewal_at = adesso + 30 giorni`;
  - se saldo insufficiente → `sospeso` (nessun addebito parziale).

## Frequenza proposta
- **Giornaliera** (una volta al giorno, es. 03:00 Europe/Rome). Il rinnovo scatta il giorno in cui `next_renewal_at` è scaduto; una granularità giornaliera è sufficiente (periodi di 30 giorni).

## Idempotenza
- Ogni addebito usa `idempotency_key = event_active:{event_id}:{numero_periodo}` sul ledger (indice unico).
- Rieseguire il job più volte nello stesso giorno NON produce doppi addebiti: il periodo già addebitato ha la chiave occupata; e dopo il rinnovo `next_renewal_at` è spostato +30 giorni, quindi l'evento non rientra più nella query fino alla scadenza successiva.

## Gestione retry / errori
- Il job è sicuro da ritentare: idempotente e per-evento (un errore su un evento non blocca gli altri, il loop prosegue).
- Errori non-402 (es. DB momentaneo) → l'evento non viene modificato e verrà ripreso alla prossima esecuzione.
- 402 (saldo insufficiente) NON è un errore: è un esito previsto → stato `sospeso`.
- Multi-tenant safe: ogni update filtra per `id + org_id`. Saldo mai negativo (guardia atomica `$gte`).

## Bozza `.emergent/crons.yml` (da attivare solo su tua conferma)
```yaml
crons:
  - name: event-renewals
    schedule: "0 3 * * *"        # ogni giorno 03:00
    timezone: "Europe/Rome"
    method: POST
    path: /api/platform/events/run-renewals
    auth: superadmin
```

## Test manuale già disponibile
- `POST /api/platform/events/run-renewals` (Super Admin) esegue il motore on-demand: usato nei test automatici (`test_credits_faseE2.py`).
