# CRMEvent Backend — Versione PORTABILE per server Linux (Aruba)

Export del **solo backend**, reso indipendente dai servizi Emergent. Il frontend resta su Emergent e NON è incluso.

## Differenze rispetto alla versione Emergent
- **Object storage**: S3-compatibile via `boto3` (`storage_utils.py`) — non più Emergent Object Storage.
- **LLM**: API OpenAI dirette via SDK ufficiale (`social_ai.py`, `support_service.py`, `social_creative.py`).
- **Dipendenze**: rimosse `emergentintegrations` e la wheel privata `litellm`.
- Dettagli completi in `MIGRATION_REPORT.md`.

## Requisiti
- Python 3.11.x · MongoDB 7.0.x · Nginx (reverse proxy + SSL) consigliato davanti a Uvicorn

## Installazione
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env   # compilare i valori (S3_*, OPENAI_*, Mongo, ecc.)
chmod +x start.sh && ./start.sh
```
Non è più necessario alcun indice pip privato Emergent.

## Routing
Tutte le API sono sotto il prefisso `/api`. Configurare Nginx:
`api.crmevent.it/api/*  ->  http://127.0.0.1:8001`

## Variabili chiave aggiunte
- Object storage: `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`, `S3_REGION`
- LLM: `OPENAI_API_KEY`, `OPENAI_MODEL` (default codice `gpt-4o-mini`)
- Immagini social (opz.): `SOCIAL_IMAGE_PROVIDER=openai`, `SOCIAL_IMAGE_MODEL=gpt-image-1`
- Email: `EMAIL_PROVIDER=brevo` (nessuna dipendenza Emergent)

## Cron
Replicare con crontab/systemd-timer la chiamata ogni 15 min a
`POST /api/cron/brevo-funnel-tick` (protetta da `WEBHOOK_CRON_SECRET`).
