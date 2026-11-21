#!/usr/bin/env bash
# Starts the real bank (8001), a local shadow bank (8002, skipped when Daytona is used) and the Mirage gateway (8000).
set -euo pipefail
cd "$(dirname "$0")/.."
# Variables already set in the environment win over .env (e.g. DEVIN_AUTO=0 ./scripts/run.sh for rehearsals)
if [ -f .env ]; then
  while IFS='=' read -r k v || [ -n "$k" ]; do
    if [[ $k =~ ^[A-Z_]+$ ]] && [ -z "${!k:-}" ]; then export "$k=$v"; fi
  done < .env
fi
PY=.venv/bin/python
# Fresh internal key per run, shared only by the gateway and the banks it starts
export BANK_INTERNAL_KEY="${BANK_INTERNAL_KEY:-$($PY -c 'import secrets; print(secrets.token_urlsafe(24))')}"
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
