# Capital.com Async Trading Platform – Documentation

## Current Audit Notes

The current architecture and runtime status were audited on 2026-09-19 before
further Capital Trader changes. Read these first when planning trading-engine
work:

- [Architecture audit](ARCHITECTURE_AUDIT.md)
- [Testing log](TESTING_LOG.md)

Important current facts:

- Startup now stays in observe-only mode unless `ALLOW_LIVE_TRADING=true`.
- `POST /api/v1/orders` is disabled for direct broker placement.
- `POST /api/v1/workflow/orders` is the guarded broker execution path.
- `POST /api/v1/workflow/risk-preview` checks risk without creating or placing
  an order.
- Postgres and Redis are now provided by `/home/frj/TradingCore/docker-compose.yml`.
- Migration and runtime verification are recorded in `/home/frj/TradingCore/MIGRATION_LOG.md`.

## Project Overview

This repository implements a production‑oriented, **async‑first** trading platform for Capital.com.  The architecture follows the layered, event‑driven design you described:

| Layer | Responsibility |
|------|----------------|
| **broker** | Direct HTTP/WebSocket communication with Capital.com – authentication, session handling, order & position endpoints. |
| **market** | Ingests raw tick data, builds candles, detects signals, emits typed events. |
| **risk** | Central gate‑keeper that validates every order against position size, daily‑loss caps, stale‑tick checks, etc. |
| **services** | Orchestrates workflows (order submission, reconciliation, startup/shutdown, health checks). |
| **db** | SQLAlchemy async ORM models and repository abstractions for persistence. |
| **core** | Configuration (`pydantic‑settings`), structured logging (`structlog`), global trading state, base event contract. |
| **api** | FastAPI HTTP endpoints exposing health, position query, etc. |
| **queue_manager** | Simple in‑memory queues (`price_queue`, `order_queue`, `alert_queue`). |

The code is fully async, uses **Python 3.11+**, and is container‑ready (Dockerfile & compose placeholder included).

---

## Key Files & Their Roles

- `app/core/config.py` – typed configuration loaded from `.env`.
- `app/core/logging.py` – configures JSON‑structured logs via `structlog`.
- `app/core/events.py` – base `BaseEvent` dataclass for all events.
- `app/core/state.py` – runtime `TradingState` and `TradingMode` enum.
- `app/db/models/*.py` – ORM models (`Position`, `Order`, …).
- `app/db/repositories/*.py` – repository layer (no raw SQL in services).
- `app/broker/client.py` – generic async HTTP client with `backoff` retry.
- `app/broker/session.py` – token lifecycle (refreshes 5 min before expiry).
- `app/broker/websocket.py` – price WebSocket; pushes raw ticks onto `price_queue`.
- `app/market/streaming.py` – consumes `price_queue`, creates `BaseEvent`s.
- `app/market/candles.py` – pure candle aggregation logic.
- `app/market/signals.py` – simple threshold‑crossing detector.
- `app/risk/manager.py` – risk checks (size caps, daily‑loss, mode gating).
- `app/services/event_bus.py` – tiny in‑process pub/sub bus.
- `app/services/order_workflow_service.py` – previews risk, validates workflow
  orders, persists them, emits events, and places broker orders only after risk
  approval.
- `app/services/reconciliation_service.py` – syncs local DB with broker state (positions & orders).
- `app/services/startup_service.py` – orchestrates config, DB init, auth, reconciliation, websocket, then enables trading.
- `app/orchestrator.py` – boots `StartupService` and runs `MarketStreamer` in background.
- `app/api/routes.py` – FastAPI endpoints (`/health`, `/positions`).
- `app/main.py` – entry point, starts FastAPI and the orchestrator.
- `requirements.txt` – minimal pip requirements.
- `.env.example` – template for required environment variables.

---

## How the System Starts

1. **FastAPI starts** (`uvicorn app.main:app`).
2. `app.main` registers a `startup` event.
3. The startup event creates an `Orchestrator` instance and runs `orchestrator.run()` in a background task.
4. `Orchestrator.run()`:
   - Calls `StartupService.run()` → broker websocket setup → trading mode setup.
   - Starts market streaming, reconciliation, candle aggregation, signal detection, trading service, and Redis event bridge.
   - Trading mode stays observe-only unless `ALLOW_LIVE_TRADING=true`.
5. `MarketStreamer.run()` continuously pulls ticks from `price_queue`, turns each tick into a `BaseEvent`, and publishes it on the internal `EventBus`.
6. Consumers (e.g., a future order‑executor) would subscribe to the `EventBus` and act on events such as `OrderSubmitted`, `SignalDetected`, etc.

---

## Running the Project Locally

### Prerequisites

- **Python 3.11+** (the repository was built with 3.14 on Arch Linux).
- **Git** (to clone the repo if you haven’t already).
- **Docker & Docker‑Compose** (optional, for containerised deployment).

### Step‑by‑Step

1. **Clone the repository** (if you aren’t already in the folder):
   ```bash
   git clone <repo‑url> capital_trader
   cd capital_trader
   ```
2. **Create a virtual environment** (recommended to keep dependencies isolated):
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
3. **Upgrade pip and install the requirements**:
   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```
4. **Configure environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your values
   nano .env
   ```
   Required keys:
   - `CAPITAL_API_KEY` (or leave empty – the `SessionManager` will request a token via username/password).
   - `CAPITAL_USERNAME`
   - `CAPITAL_PASSWORD`
   - `DATABASE_URL` – e.g., `postgresql+asyncpg://postgres:postgres@localhost/trading`
   - `ENVIRONMENT` – usually `demo` or `prod`.
5. **(Optional) Set up the PostgreSQL database** – you can use Docker:
   ```bash
   docker run -d --name pg -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16-alpine
   ```
   The first time the ORM accesses the DB it will automatically create the tables defined in `app/db/models`.
6. **Run the FastAPI server**:
   ```bash
   .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   You should see logs similar to:
   ```
   INFO: Started server process [...] 
   INFO: Uvicorn running on http://0.0.0.0:8000
   ```
7. **Verify the service** – open a browser or curl:
   ```bash
   curl http://localhost:8000/api/health
   curl http://localhost:8000/api/health/deep
   curl http://localhost:8000/api/v1/audit/trade-log
   curl http://localhost:8000/api/positions
   ```
   The shallow health endpoint returns a JSON payload indicating the service is up. The deep health endpoint reports broker session, database, Redis, websocket, reconciliation, price freshness, and trading mode. Reconciliation health includes the latest sync counts and action summary from the broker-to-database source-of-record check. The trade-log endpoint returns persisted trading-core audit events. The positions endpoint returns the list of positions stored in the DB (empty on first run).
8. **Observe the background orchestration** – the console will show reconnection/back‑off attempts if the placeholder broker URL (`https://api-capital.com/auth/login`) is not reachable. Replace the URLs in `app/broker/client.py` and `app/broker/websocket.py` with the real Capital.com endpoints, then restart the server.

---

## Docker & Compose (quick start)

A minimal `Dockerfile` and `docker-compose.yml` are already present in the repo (you can find them under the project root). To build and run the whole stack:

```bash
docker compose up --build
```

The compose file will start the app container and a PostgreSQL container. The app will wait for the DB to become reachable, then start exactly as described in the local steps.

---

## Extending the Platform

- **Order Execution Consumer** – register a coroutine with `EventBus.subscribe()` that listens for `OrderSubmitted` events, calls `BrokerClient.request("POST", "/orders", ...)`, and updates the `Order` model based on the broker response.
- **Metrics Exporter** – `app/metrics.py` already imports `prometheus_client`. Expose `/metrics` via FastAPI and register counters (e.g., `order_submitted_total`).
- **Alert Channels** – extend `app/alerts/notifications.py` with Slack or email senders, then have the `AlertService` publish to those channels.
- **Testing** – add `pytest‑asyncio` test modules under `app/tests/` that spin up an in‑memory SQLite DB (`sqlite+aiosqlite:///:memory:`) and verify repository behaviour, risk checks, and orchestrator startup.
- **Reconciliation Frequency** – adjust the schedule in `StartupService` (currently called once at startup). For a recurring job you could use the `loop` skill or a background `asyncio` task that sleeps `5*60` seconds.

---

## License & Contributions

The code is provided **as‑is** under the MIT license (feel free to replace with your preferred license). Contributions should follow the same architectural guidelines: keep layers thin, avoid heavy logic in the API layer, and always route DB work through repositories.

---

*Generated by Claude Code on 2026‑05‑09.*
