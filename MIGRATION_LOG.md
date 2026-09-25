# TradingCore Migration Log

## 2026-09-19T21:40:39Z

Moved the active trading system out of the busy `/home/frj/Projects` folder and
into:

```text
/home/frj/TradingCore
```

Moved projects:

- `/home/frj/Projects/clean-agent` -> `/home/frj/TradingCore/clean-agent`
- `/home/frj/Projects/capital_trader` -> `/home/frj/TradingCore/capital_trader`

Added shared infrastructure:

- `/home/frj/TradingCore/docker-compose.yml`
- Postgres container: `tradingcore-postgres`
- Redis container: `tradingcore-redis`
- Postgres database: `trading`
- Redis URL: `redis://localhost:6379/0`

Added run scripts:

- `/home/frj/TradingCore/capital_trader/run.sh`
- Updated `/home/frj/TradingCore/clean-agent/run.sh`

The run scripts call `.venv/bin/python -m ...` instead of venv console
wrappers. This matters because venv console wrappers contained old absolute
paths from `/home/frj/Projects`.

Capital Trader environment changes:

- Added `REDIS_URL=redis://localhost:6379/0`.
- Added `ALLOW_LIVE_TRADING=false`.
- Added sanitized `.env.example`.
- Added `redis_url` to typed settings so `REDIS_URL` is accepted by Pydantic.

Infrastructure startup:

```bash
cd /home/frj/TradingCore
docker compose up -d postgres redis
```

Migration:

```bash
cd /home/frj/TradingCore/capital_trader
.venv/bin/python -m alembic upgrade head
```

Result:

- Alembic created:
  - `alembic_version`
  - `alerts`
  - `candles`
  - `dead_letter_events`
  - `orders`
  - `positions`
  - `trade_logs`

Runtime verification:

- Capital Trader started from `/home/frj/TradingCore/capital_trader`.
- Clean Agent started from `/home/frj/TradingCore/clean-agent`.
- Capital Trader remained observe-only on startup.
- Reconciliation completed successfully.
- Existing broker position was imported into Postgres.
- Clean Agent saw Capital Trader as healthy with 1 position, 0 working orders,
  and no broker snapshot errors.

Current URLs:

- Capital Trader: `http://127.0.0.1:8000`
- Clean Agent: `http://127.0.0.1:8091`

