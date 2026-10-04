# CRMEvent Backend — Pacchetto di export per server Linux (Aruba)

Export del **solo backend** nello stato attuale. Il frontend resta su Emergent e NON è incluso.

## Contenuto
- `server.py` — applicazione FastAPI (monolite)
- Moduli Python: `brevo_client.py`, `brevo_funnel.py`, `email_utils.py`, `gcal_utils.py`,
  `instagram_utils.py`, `leadfinder_scraper.py`, `storage_utils.py`, `social_ai.py`,
  `social_creative.py`, `social_readonly_check.py`, `support_service.py`, `pipeline_seed.py`
- Script di seed/setup: `seed_*.py`, `setup_stripe.py`, `migrate_social_platform.py`
- Test: cartella `tests/`, `test_credits_*.py`, `pytest.ini`
- `requirements.txt` — dipendenze complete e verificate
- `.env.example` — elenco variabili d'ambiente (senza valori reali)
- `start.sh` — script di avvio produzione

## Requisiti
- Python 3.11.x
- MongoDB 7.0.x
- Nginx (reverse proxy + SSL) consigliato davanti a Uvicorn

## Installazione
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# emergentintegrations NON e' su PyPI pubblico: vedi NOTA sotto
cp .env.example .env   # compilare i valori
chmod +x start.sh && ./start.sh
```

## Routing
Tutte le API sono esposte sotto il prefisso `/api`. Configurare Nginx:
`api.crmevent.it/api/*  ->  http://127.0.0.1:8001`

## ⚠️ NOTE / Blocker da risolvere fuori da Emergent
1. **emergentintegrations** (in requirements.txt) NON è su PyPI pubblico. Si installa solo da:
   `pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/`
   È usata per LLM (`social_ai.py`, `social_creative.py`, `support_service.py`) e indirettamente
   dall'object storage (`storage_utils.py`). Fuori piattaforma va sostituita con SDK diretti
   (OpenAI/Gemini) + chiavi proprie.
2. **Object storage** (`storage_utils.py`) punta a `integrations.emergentagent.com/objstore` con
   `EMERGENT_LLM_KEY`. Va migrato su S3-compatibile (boto3 già in requirements) + i file esistenti.
3. **Email managed** (`EMERGENT_EMAIL_KEY`): impostare `EMAIL_PROVIDER=brevo` per usare Brevo diretto.
4. **Cron**: replicare con crontab/systemd-timer la chiamata ogni 15 min a
   `POST /api/cron/brevo-funnel-tick` (protetta da `WEBHOOK_CRON_SECRET`).

## Avvio come servizio (systemd, esempio)
Creare `/etc/systemd/system/crmevent-backend.service` con `ExecStart` che lancia `start.sh`
dentro la virtualenv, poi `systemctl enable --now crmevent-backend`.
