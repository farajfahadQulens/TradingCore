#!/bin/bash
# Railway start script – runs FastAPI from the built image.
# The Dockerfile sets WORKDIR /app, but we cd explicitly to be safe.

PORT=${PORT:-8000}
cd /app
exec python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
