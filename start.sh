#!/usr/bin/env bash
set -uo pipefail

CAPITAL_TRADER_DIR=/app/capital_trader
CLEAN_AGENT_DIR=/app/clean_agent
CAPITAL_TRADER_PORT=${PORT:-8000}
CLEAN_AGENT_PORT=${CLEAN_AGENT_PORT:-8091}

mkdir -p /app/clean_agent/data

(
  cd "$CAPITAL_TRADER_DIR" || exit 1
  exec uvicorn app.main:app --host 0.0.0.0 --port "$CAPITAL_TRADER_PORT"
) &

(
  cd "$CLEAN_AGENT_DIR" || exit 1
  exec uvicorn app.main:app --host 0.0.0.0 --port "$CLEAN_AGENT_PORT"
) &

wait -n
