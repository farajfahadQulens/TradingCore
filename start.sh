#!/bin/bash
# Railway start script – runs the FastAPI app in this image.
# This image is built from the capital_trader directory, so the
# FastAPI package lives directly under /app (no extra subdirectory).

PORT=${PORT:-8000}
exec python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
