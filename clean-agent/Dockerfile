# -------------------------------------------------
# Clean-Agent Docker image
# -------------------------------------------------
FROM python:3.14-slim

# Install system deps that may be needed for wheels (git, build-essential, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirement files first – Docker cache will reuse them on rebuilds
COPY clean-agent/requirements.txt clean-agent/requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

# Copy the entire source tree (including .env.example)
COPY clean-agent/ .

# Create a non‑root user (security best practice)
RUN useradd -m appuser
# USER appuser  # Disabled to allow volume write permissions

EXPOSE 8091

# Use the same command that `run.sh` uses, but without `--reload` in production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8091"]
