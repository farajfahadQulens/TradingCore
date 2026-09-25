#!/bin/bash

# Choose which service to run via an env var (default: capital_trader)
# You can set SERVICE=clean_agent in Railway Variables to run the other one.

if [[ "$SERVICE" == "clean_agent" ]]; then
  cd clean-agent
  exec uvicorn main:app --host 0.0.0.0 --port $PORT
else
  cd capital_trader
  exec uvicorn main:app --host 0.0.0.0 --port $PORT
fi
