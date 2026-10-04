#!/usr/bin/env bash
# =========================================================================
# CRMEvent Backend - script di avvio per server Linux (Aruba)
# =========================================================================
set -euo pipefail

cd "$(dirname "$0")"

# 1) Virtualenv (crealo la prima volta: python3.11 -m venv .venv)
if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# 2) Carica le variabili d'ambiente da .env (copiare da .env.example)
if [ ! -f ".env" ]; then
  echo "ERRORE: file .env mancante. Copia .env.example in .env e compila i valori." >&2
  exit 1
fi

# 3) Parametri runtime (override via env)
HOST="${BACKEND_HOST:-0.0.0.0}"
PORT="${BACKEND_PORT:-8001}"
WORKERS="${BACKEND_WORKERS:-4}"

# 4) Avvio produzione con Uvicorn (multi-worker, no reload)
exec uvicorn server:app --host "$HOST" --port "$PORT" --workers "$WORKERS"
