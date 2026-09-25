# Capital Trader Testing Log

This file records tests and runtime checks performed while auditing the trading
engine. It is intentionally append-only in spirit: future changes should add new
entries rather than erase useful history.

## 2026-09-19 Audit Checks

### Clean Agent Tests

Command:

```bash
cd /home/frj/TradingCore/clean-agent
PYTHONPATH=. .venv/bin/pytest
```

Result:

```text
9 passed
```

Coverage from these tests:

- Direct order submission tool remains disabled.
- Clean Agent risk blocks missing stop loss.
- Clean Agent risk approves a basic protected ticket.
- Wrong-side stop loss is blocked.
- Missing broker orders snapshot blocks a ticket.
- Broker execution payload omits empty values.
- Capital Trader price query uses `max_points`.
- Existing research tests still pass.

### Capital Trader Unit Tests

Command:

```bash
cd /home/frj/TradingCore/capital_trader
.venv/bin/python -m unittest app.tests.test_broker_client app.tests.test_startup_service
```

Result:

```text
Ran 3 tests
OK
```

Coverage from these tests:

- Market orders preserve `limitDistance` and `stopDistance`.
- Startup remains observe-only when `ALLOW_LIVE_TRADING` is false or unset.
- Startup can enter live mode only when explicitly allowed.

### Python Compile Check

Command:

```bash
python -m py_compile \
  /home/frj/TradingCore/capital_trader/app/broker/client.py \
  /home/frj/TradingCore/capital_trader/app/core/config.py \
  /home/frj/TradingCore/capital_trader/app/services/startup_service.py
```

Result:

```text
passed
```

### Capital Trader Health

Command:

```bash
curl -s -o /tmp/capital-health-audit.json -w '%{http_code}' \
  http://127.0.0.1:8000/api/health
```

Result:

```text
200
```

Response body:

```json
{"status":"healthy"}
```

### Clean Agent View Of Capital Trader

Command:

```bash
curl -s -o /tmp/clean-agent-dashboard-final.json \
  http://127.0.0.1:8091/api/dashboard
```

Summarized result:

```text
health: healthy
positions_count: 1
orders_count: 0
broker snapshot errors: none
trading writes enabled: false
```

### Postgres Readiness

Command:

```bash
pg_isready -h localhost -p 5432
```

Result:

```text
localhost:5432 - no response
```

Interpretation:

- `DATABASE_URL` points to localhost Postgres.
- Capital Trader reconciliation cannot persist/sync until Postgres is running
  and the `trading` database is available.

### Redis Verification

Command:

```bash
redis-cli -u redis://localhost:6379/0 ping
```

Result:

```text
redis-cli: command not found
```

Follow-up command:

```bash
cd /home/frj/TradingCore/capital_trader
.venv/bin/python - <<'PY'
import asyncio
from redis.asyncio import Redis

async def main():
    r = Redis.from_url(
        'redis://localhost:6379/0',
        socket_connect_timeout=1,
        decode_responses=True,
    )
    print(await r.ping())
    await r.aclose()

asyncio.run(main())
PY
```

Result:

```text
Probe hung until manually interrupted.
```

Interpretation:

- Redis availability remains unverified.
- Redis bridge should be treated as a dependency needing explicit health checks.

### Docker / Compose Check

Command:

```bash
find /home/frj/TradingCore/capital_trader -maxdepth 2 \
  \( -name 'docker-compose.yml' -o -name 'compose.yml' -o \
     -name 'docker-compose.yaml' -o -name 'compose.yaml' \) -print
```

Result:

```text
no compose file found
```

Command:

```bash
docker ps --format '{{.Names}} {{.Image}} {{.Ports}}'
```

Result:

```text
permission denied while trying to connect to the docker API
```

Interpretation:

- There is no project-local compose file for Postgres/Redis.
- Docker state was not inspectable from the current sandbox.

## Current Known Runtime Gaps

- Postgres is not reachable on `localhost:5432`.
- Redis is not verified.
- Capital Trader health endpoint reports only shallow app health.
- Reconciliation failure moves state to degraded, but `/api/health` still says
  healthy.
- Public `POST /api/v1/orders` directly calls broker placement and does not use
  Capital Trader's internal `RiskManager`.
- The websocket subscription list is hardcoded.
- `BTCUSD` is subscribed on websocket but is not configured for candle
  aggregation.

## 2026-09-19 TradingCore Move And Infra Fix

Moved active projects into:

```text
/home/frj/TradingCore
```

Moved:

- `clean-agent`
- `capital_trader`

Added:

- `/home/frj/TradingCore/docker-compose.yml`
- Postgres container `tradingcore-postgres`
- Redis container `tradingcore-redis`

### Infrastructure Startup

Command:

```bash
cd /home/frj/TradingCore
docker compose up -d postgres redis
```

Result:

```text
tradingcore-postgres started
tradingcore-redis started
```

Health check:

```bash
docker compose ps
```

Result:

```text
tradingcore-postgres   healthy   0.0.0.0:5432->5432/tcp
tradingcore-redis      healthy   0.0.0.0:6379->6379/tcp
```

### Postgres Check

Command:

```bash
docker compose exec -T postgres pg_isready -U postgres -d trading
```

Result:

```text
/var/run/postgresql:5432 - accepting connections
```

### Redis Check

Command:

```bash
docker compose exec -T redis redis-cli ping
```

Result:

```text
PONG
```

### Alembic Migration

Command:

```bash
cd /home/frj/TradingCore/capital_trader
.venv/bin/python -m alembic upgrade head
```

Result:

```text
Running upgrade  -> 2511bca9ec79, initial
```

Table check:

```bash
docker compose exec -T postgres psql -U postgres -d trading -c '\dt'
```

Result:

```text
alembic_version
alerts
candles
dead_letter_events
orders
positions
trade_logs
```

### Capital Trader Runtime Check

Command:

```bash
cd /home/frj/TradingCore/capital_trader
bash run.sh
```

Observed result:

```text
live_trading_not_enabled mode=observe
Redis event bridge subscribed to EventBus
reconciliation_complete positions=1 orders=0
```

Database count:

```bash
docker compose exec -T postgres psql -U postgres -d trading \
  -c 'select count(*) as positions from positions;'
```

Result:

```text
positions: 1
```

### Clean Agent Runtime Check

Command:

```bash
cd /home/frj/TradingCore/clean-agent
bash run.sh
```

Health checks:

```bash
curl -s -o /tmp/tradingcore-capital-health.json -w '%{http_code}' \
  http://127.0.0.1:8000/api/health

curl -s -o /tmp/tradingcore-clean-dashboard.json -w '%{http_code}' \
  http://127.0.0.1:8091/api/dashboard
```

Result:

```text
Capital Trader health: 200
Clean Agent dashboard: 200
```

Clean Agent broker summary:

```text
broker_health: healthy
positions_count: 1
orders_count: 0
broker_errors: {}
clean_writes_enabled: false
```

### Tests After Move

Clean Agent:

```bash
cd /home/frj/TradingCore/clean-agent
PYTHONPATH=. .venv/bin/python -m pytest
```

Result:

```text
9 passed
```

Capital Trader:

```bash
cd /home/frj/TradingCore/capital_trader
.venv/bin/python -m unittest app.tests.test_broker_client app.tests.test_startup_service
```

Result:

```text
Ran 3 tests
OK
```

### Updated Gap List

Fixed:

- Postgres is now reachable through the TradingCore compose stack.
- Redis is now reachable through the TradingCore compose stack.
- Capital Trader migrations have been applied.
- Reconciliation can persist broker positions.

Still open:

- `/api/health` is still intentionally shallow; use `/api/health/deep` for
  dependency health.
- Websocket subscriptions are still hardcoded.
- `BTCUSD` is still streamed but not candle-aggregated.

## 2026-09-19 - Safe Order Workflow Endpoint

Implemented a guarded broker-order path:

- `POST /api/v1/orders` now rejects direct broker placement with `403`.
- `POST /api/v1/workflow/orders` routes through `OrderWorkflowService`.
- The workflow route runs Capital Trader risk checks before broker placement.
- `BaseEvent.new` now accepts event payload fields for inherited dataclass
  events such as `OrderRejected` and `OrderSubmitted`.

Unit tests:

```bash
cd /home/frj/TradingCore/capital_trader
.venv/bin/python -m unittest app.tests.test_broker_client app.tests.test_startup_service app.tests.test_order_workflow_api
```

Result:

```text
Ran 8 tests
OK
```

Runtime verification:

```bash
curl -s -o /tmp/direct-order-after.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8000/api/v1/orders \
  -H 'Content-Type: application/json' \
  -d '{"epic":"GOLD","direction":"BUY","size":0.01,"order_type":"MARKET","stop_distance":1}'

curl -s -o /tmp/workflow-order-after.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8000/api/v1/workflow/orders \
  -H 'Content-Type: application/json' \
  -d '{"epic":"GOLD","direction":"BUY","size":0.01,"order_type":"MARKET","stop_distance":1}'

curl -s -o /tmp/capital-health-after.json -w '%{http_code}' \
  http://127.0.0.1:8000/api/health
```

Result:

```text
Direct order endpoint: 403
Workflow order endpoint in observe mode: 403
Capital Trader health: 200
```

Response bodies:

```text
Direct order: Direct broker order placement is disabled. Use POST /api/v1/workflow/orders.
Workflow order: Risk rejected: trading_not_allowed mode=TradingMode.OBSERVE_ONLY
Health: {"status":"healthy"}
```

## 2026-09-20 - Deep Health Endpoint

Implemented component-level health at `GET /api/health/deep`.

Components:

- Broker session token state and expiry.
- Postgres connectivity.
- Redis connectivity and Redis bridge status.
- Websocket connection and subscriptions.
- Reconciliation run status and last broker sync counts.
- Latest price tick freshness.
- Trading mode and whether trading is allowed.

Unit tests:

```bash
cd /home/frj/TradingCore/capital_trader
.venv/bin/python -m unittest app.tests.test_broker_client app.tests.test_startup_service app.tests.test_order_workflow_api app.tests.test_health_service
```

Result:

```text
Ran 11 tests
OK
```

Compile check:

```bash
.venv/bin/python -m py_compile \
  app/services/health_service.py \
  app/services/runtime_status.py \
  app/api/routes.py \
  app/broker/websocket.py \
  app/market/streaming.py \
  app/services/reconciliation_service.py \
  app/services/redis_event_bridge.py
```

Result:

```text
OK
```

Runtime verification:

```bash
curl -s -o /tmp/capital-health-deep.json -w '%{http_code}' \
  http://127.0.0.1:8000/api/health/deep

curl -s -o /tmp/capital-health-shallow.json -w '%{http_code}' \
  http://127.0.0.1:8000/api/health
```

Result:

```text
Deep health: 200
Shallow health: 200
Overall deep health status: degraded
```

Observed deep health components:

```text
broker_session: healthy
database: healthy
redis: healthy
websocket: healthy
reconciliation: healthy
prices: healthy
trading: degraded
```

The overall status was `degraded` because trading is intentionally in observe
mode with `allow_live_trading=false`.

## 2026-09-20 - Reconciliation Source-of-Record Strengthening

Implemented stronger broker-to-database reconciliation.

Behavior added:

- Persist every reconciliation run in `reconciliation_runs`.
- Import orphan broker positions into `positions`.
- Update local position size drift.
- Mark local `OPEN` positions as `CLOSED` when missing from broker positions.
- Import orphan broker working orders into `orders`.
- Update local order state drift.
- Expose the latest reconciliation summary through `/api/health/deep`.

Migration:

```bash
cd /home/frj/TradingCore/capital_trader
.venv/bin/python -m alembic upgrade head
```

Result:

```text
Running upgrade 2511bca9ec79 -> 9f2b7c1a4d30, add reconciliation runs
```

Unit tests:

```bash
cd /home/frj/TradingCore/capital_trader
.venv/bin/python -m unittest \
  app.tests.test_broker_client \
  app.tests.test_startup_service \
  app.tests.test_order_workflow_api \
  app.tests.test_health_service \
  app.tests.test_reconciliation_service
```

Result:

```text
Ran 16 tests
OK
```

Compile check:

```bash
.venv/bin/python -m py_compile \
  app/services/reconciliation_service.py \
  app/db/models/reconciliation_run.py \
  app/db/repositories/reconciliation_runs.py \
  app/db/repositories/orders.py \
  app/db/repositories/positions.py \
  app/services/runtime_status.py \
  migrations/versions/9f2b7c1a4d30_add_reconciliation_runs.py
```

Result:

```text
OK
```

Runtime verification:

```bash
docker compose exec -T postgres psql -U postgres -d trading \
  -c "select status, summary from reconciliation_runs order by started_at desc limit 1;"
```

Result:

```text
status: COMPLETED
summary: {"broker_positions_seen": 1, "broker_orders_seen": 0, "orphan_positions_imported": 0, "position_size_drifts_updated": 0, "positions_closed_locally": 0, "orphan_orders_imported": 0, "order_state_drifts_updated": 0}
```

Deep health check:

```bash
curl -s -o /tmp/capital-health-reconcile.json -w '%{http_code}' \
  http://127.0.0.1:8000/api/health/deep
```

Result:

```text
HTTP 200
reconciliation.status: healthy
reconciliation.last_counts.positions: 1
reconciliation.last_counts.orders: 0
reconciliation.last_summary.broker_positions_seen: 1
reconciliation.last_summary.broker_orders_seen: 0
```

## 2026-09-20 - Read-Only Risk Preview

Implemented `POST /api/v1/workflow/risk-preview`.

Behavior:

- Fetches current market quote for the requested epic.
- Reads local open-position count.
- Runs `RiskManager.can_trade`.
- Returns approval status, rejection reason, market context, trading mode, and
  configured risk limits.
- Does not create an order.
- Does not call broker order placement.
- Does not mark the preview as an approved client order.

Unit tests:

```bash
cd /home/frj/TradingCore/capital_trader
.venv/bin/python -m unittest \
  app.tests.test_broker_client \
  app.tests.test_startup_service \
  app.tests.test_order_workflow_api \
  app.tests.test_health_service \
  app.tests.test_reconciliation_service
```

Result:

```text
Ran 19 tests
OK
```

Compile check:

```bash
.venv/bin/python -m py_compile \
  app/services/order_workflow_service.py \
  app/api/v1/orders.py \
  app/tests/test_order_workflow_api.py
```

Result:

```text
OK
```

Runtime verification:

```bash
curl -s -o /tmp/risk-preview.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8000/api/v1/workflow/risk-preview \
  -H 'Content-Type: application/json' \
  -d '{"epic":"GOLD","direction":"BUY","size":0.01,"order_type":"MARKET","stop_distance":1}'
```

Result:

```text
HTTP 200
approved: false
reason: trading_not_allowed mode=TradingMode.OBSERVE_ONLY
market.bid: 4377.85
market.ask: 4378.35
market.spread: 0.5
risk.trading_mode: observe
risk.open_positions_count: 1
risk.max_open_positions: 5
risk.max_position_size: 0.5
```

## 2026-09-20 - Guarded Position Close Preview And Workflow

Implemented guarded position-close workflows.

Endpoints:

- `POST /api/v1/workflow/positions/{deal_id}/close-preview`
- `POST /api/v1/workflow/positions/{deal_id}/close`

Behavior:

- Close preview validates local position exists and is `OPEN`.
- Close preview confirms the broker still reports the same `dealId`.
- Close preview compares local and broker epic/size.
- Close preview returns broker direction, current bid/offer, market status, and
  estimated close price.
- Close workflow runs preview first.
- Close workflow blocks when trading mode is observe-only.
- Close workflow blocks when broker market status is not `TRADEABLE`.
- Close workflow only calls broker close after preview approval.
- Successful close marks the local DB position `CLOSED` and emits
  `PositionClosed`.

Unit tests:

```bash
cd /home/frj/TradingCore/capital_trader
.venv/bin/python -m unittest \
  app.tests.test_broker_client \
  app.tests.test_startup_service \
  app.tests.test_order_workflow_api \
  app.tests.test_health_service \
  app.tests.test_reconciliation_service \
  app.tests.test_position_workflow_service
```

Result:

```text
Ran 23 tests
OK
```

Compile check:

```bash
.venv/bin/python -m py_compile \
  app/services/position_workflow_service.py \
  app/api/v1/positions.py \
  app/tests/test_position_workflow_service.py
```

Result:

```text
OK
```

Runtime verification:

```bash
curl -s -o /tmp/close-preview.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8000/api/v1/workflow/positions/00601567-0001-54c4-0000-00009222a0f8/close-preview

curl -s -o /tmp/close-position-blocked.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8000/api/v1/workflow/positions/00601567-0001-54c4-0000-00009222a0f8/close
```

Result:

```text
Close preview: HTTP 200
Close workflow: HTTP 403
```

Observed response:

```text
approved: false
reason: trading_not_allowed mode=TradingMode.OBSERVE_ONLY; market_not_tradeable status=CLOSED
local_position.status: OPEN
broker_position.epic: GOLD
broker_position.direction: SELL
broker_position.market_status: CLOSED
broker_position.estimated_close_price: 4378.35
```

## 2026-09-20 - Persistent Trade Log API

Implemented persistent Capital Trader trade logs in Postgres.

API:

- `GET /api/v1/audit/trade-log`

Filters:

- `limit`
- `event_type`
- `correlation_id`

Events written:

- `risk_preview`
- `order_workflow_rejected`
- `order_workflow_submitted`
- `broker_order_failed`
- `broker_order_placed`
- `close_preview`
- `close_rejected`
- `position_close_requested`
- `position_closed`
- `reconciliation_completed`
- `reconciliation_failed`

Unit tests:

```bash
cd /home/frj/TradingCore/capital_trader
.venv/bin/python -m unittest \
  app.tests.test_broker_client \
  app.tests.test_startup_service \
  app.tests.test_order_workflow_api \
  app.tests.test_health_service \
  app.tests.test_reconciliation_service \
  app.tests.test_position_workflow_service \
  app.tests.test_trade_log_api
```

Result:

```text
Ran 27 tests
OK
```

Compile check:

```bash
.venv/bin/python -m py_compile \
  app/db/repositories/trades.py \
  app/services/trade_log_service.py \
  app/services/order_workflow_service.py \
  app/services/position_workflow_service.py \
  app/services/reconciliation_service.py \
  app/api/v1/audit.py \
  app/main.py \
  app/tests/test_trade_log_api.py
```

Result:

```text
OK
```

Runtime verification:

```bash
curl -s -o /tmp/trade-log-risk-preview.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8000/api/v1/workflow/risk-preview \
  -H 'Content-Type: application/json' \
  -d '{"epic":"GOLD","direction":"BUY","size":0.01,"order_type":"MARKET","stop_distance":1}'

curl -s -o /tmp/trade-log-close-preview.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8000/api/v1/workflow/positions/00601567-0001-54c4-0000-00009222a0f8/close-preview

curl -s -o /tmp/trade-log-api-after.json -w '%{http_code}' \
  'http://127.0.0.1:8000/api/v1/audit/trade-log?limit=10'

curl -s -o /tmp/trade-log-risk-filter.json -w '%{http_code}' \
  'http://127.0.0.1:8000/api/v1/audit/trade-log?limit=5&event_type=risk_preview'

curl -s -o /tmp/trade-log-close-filter.json -w '%{http_code}' \
  'http://127.0.0.1:8000/api/v1/audit/trade-log?limit=5&event_type=close_preview'
```

Result:

```text
risk preview: HTTP 200
close preview: HTTP 200
trade-log list: HTTP 200
risk-preview filter: HTTP 200
close-preview filter: HTTP 200
```

Observed trade-log events:

```text
close_preview: approved=false, reason=trading_not_allowed mode=TradingMode.OBSERVE_ONLY; market_not_tradeable status=CLOSED
risk_preview: approved=false, reason=trading_not_allowed mode=TradingMode.OBSERVE_ONLY
reconciliation_completed: broker_positions_seen=1, broker_orders_seen=0
```
