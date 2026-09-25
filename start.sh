#!/bin/bash

# Choose which service to run via an env var (default: capital_trader)
# Set SERVICE=clean_agent in Railway Variables to run the other one.

PORT=${PORT:-8000}

if [[ "$SERVICE" == "clean_agent" ]]; then
  cd clean-agent
  exec python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
else
  cd capital_trader
  exec python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
fi
