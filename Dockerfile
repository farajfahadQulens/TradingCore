FROM python:3.12-slim

# Use a non‑root user for security
RUN useradd -m appuser

# Install curl (used by health‑check) and any other system deps
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ----- Capital‑Trader dependencies -----
COPY capital_trader/requirements.txt ./capital_trader-requirements.txt
RUN pip install --no-cache-dir -r capital_trader-requirements.txt

# ----- Clean‑Agent dependencies -----
COPY clean-agent/requirements.txt ./clean-agent-requirements.txt
RUN pip install --no-cache-dir -r clean-agent-requirements.txt

# ----- Application source -----
COPY capital_trader/ ./capital_trader/
COPY clean-agent/ ./clean_agent/

# Add a start script that launches both services
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Create writable data directories owned by the runtime user
RUN mkdir -p /app/clean_agent/data /app/capital_trader/data && chown -R appuser:appuser /app

# Switch to non‑root user
USER appuser

# Expose ports (Capital‑Trader = 8000, Clean‑Agent = 8091)
EXPOSE 8000 8091

# Default command runs the start script
CMD ["/usr/local/bin/start.sh"]
