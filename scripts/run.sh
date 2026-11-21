#!/usr/bin/env bash
# Starts the real bank (8001), a local shadow bank (8002, skipped when Daytona is used) and the Mirage gateway (8000).
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
PY=.venv/bin/python
pids=()
trap 'kill "${pids[@]}" 2>/dev/null' EXIT INT TERM
BANK_MODE=real $PY -m uvicorn bank.app:app --port 8001 --log-level warning & pids+=($!)
if [ -z "${DAYTONA_API_KEY:-}" ] || [ "${MIRAGE_SHADOW:-daytona}" = "local" ]; then
  BANK_MODE=shadow $PY -m uvicorn bank.app:app --port 8002 --log-level warning & pids+=($!)
fi
sleep 1
$PY -m uvicorn gateway.app:app --port 8000 --log-level warning & pids+=($!)
echo "Mirage console: http://127.0.0.1:8000/console"
wait
