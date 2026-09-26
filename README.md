# TradingCore

**Environment variables**

The application requires three Capital.com credentials. Provide them via Railway environment variables or a local `.env` file. See `.env.example` for the required format.


This folder keeps the active trading system together without the rest of the
older `Projects` workspace pressing on it.

## Layout

- `capital_trader/` - Capital.com broker bridge, websocket stream, services,
  database models, and trading workflows.
- `clean-agent/` - operator/LLM agent and dashboard that talks to Capital
  Trader through HTTP.
- `docker-compose.yml` - only shared infrastructure: Postgres and Redis.

## Start Infrastructure

```bash
cd /home/frj/TradingCore
docker compose up -d postgres redis
```

## Run Capital Trader

```bash
cd /home/frj/TradingCore/capital_trader
bash run.sh
```

Capital Trader uses:

- Postgres: `postgresql+asyncpg://postgres:postgres@localhost/trading`
- Redis: `redis://localhost:6379/0`
- HTTP: `http://127.0.0.1:8000`

## Run Clean Agent

```bash
cd /home/frj/TradingCore/clean-agent
bash run.sh
```

Clean Agent uses:

- Capital Trader: `http://localhost:8000`
- HTTP dashboard: `http://127.0.0.1:8091`

## Safety Defaults

- Capital Trader stays observe-only unless `ALLOW_LIVE_TRADING=true`.
- Clean Agent trading writes stay disabled unless `ALLOW_TRADING_WRITES=true`.
- Live order flow should stay behind Clean Agent tickets until the Capital
  Trader execution path is fully unified with `OrderWorkflowService`.
