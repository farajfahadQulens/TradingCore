#!/usr/bin/env bash
set -euo pipefail

# Start Capital‑Trader (FastAPI) on the port provided by Railway ($PORT, default 8000)
nohup uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} > /tmp/capital_trader.log 2>&1 &

# Start Clean‑Agent (FastAPI) background service on a fixed port 8091
nohup uvicorn clean-agent.app.main:app --host 0.0.0.0 --port 8091 > /tmp/clean_agent.log 2>&1 &

# Keep the container alive while both processes run
wait
