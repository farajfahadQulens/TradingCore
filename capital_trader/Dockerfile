FROM python:3.12-slim
# Use a non‑root user for security
RUN useradd -m appuser

# Install curl for the health‑check used in docker‑compose
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Copy requirements from the capital_trader subdirectory
COPY capital_trader/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source (the capital_trader directory) into the container
COPY capital_trader/ .

EXPOSE 8000
# Run via uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
