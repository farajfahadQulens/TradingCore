# Capital Trader Architecture Audit

Audit timestamp: 2026-09-19T21:31:26Z

This document records the current Capital Trader runtime architecture before any
larger service or database changes. It focuses on the database, services, price
streaming, event bus, execution paths, and current runtime gaps.

## Current Runtime Summary

Capital Trader is a FastAPI service in `app/main.py`. Startup performs these
steps:

1. `session_manager.start()` creates a Capital.com REST session.
2. `orchestrator.run()` starts in the background.
3. `StartupService.run()` connects the Capital.com websocket.
4. Market, reconciliation, candle, trading, signal, and Redis bridge services
   are started.

Current `.env` shape:

- `ENVIRONMENT=live`
- `DATABASE_URL=postgresql+asyncpg://<credentials>@localhost/trading`
- `BROKER_WS_URL=wss://api-streaming-capital.backend-capital.com/connect`
- Capital.com credentials are present but redacted in audit output.

Current observed runtime state:

- HTTP health endpoint responds: `GET /api/health -> 200`.
- Broker REST/session calls work.
- Broker websocket connected and subscribed.
- Startup stayed observe-only unless `ALLOW_LIVE_TRADING=true`.
- Original audit found Postgres unavailable on `localhost:5432`; this was fixed
  by the TradingCore compose stack.
- Original audit could not verify Redis; this was fixed by the TradingCore
  Redis container.

Current infrastructure home:

- `/home/frj/TradingCore/docker-compose.yml`
- Postgres: `tradingcore-postgres`
- Redis: `tradingcore-redis`
- Full migration notes: `/home/frj/TradingCore/MIGRATION_LOG.md`

## Database Layer

Database setup lives in `app/db/session.py`.

- Engine: `create_async_engine(settings.database_url)`
- Session factory: `async_sessionmaker(engine, expire_on_commit=False)`
- Sessions rollback on exceptions.

Configured database:

- `postgresql+asyncpg://postgres:postgres@localhost/trading`
- Original runtime check returned `no response`.
- Current TradingCore check returns `accepting connections`.

Models:

- `orders`
  - `id`
  - `epic`
  - `order_type`
  - `state`
  - `size`
  - `limit_price`
  - `broker_order_id`
  - `client_order_id`
  - timestamps

- `positions`
  - `id`
  - `epic`
  - `size`
  - `entry_price`
  - `stop_loss`
  - `take_profit`
  - `deal_reference`
  - `close_price`
  - `status`
  - timestamps

- `candles`
  - `id`
  - `epic`
  - `timeframe`
  - `open`
  - `high`
  - `low`
  - `close`
  - `bid_close`
  - `ask_close`
  - `candle_time`

- `trade_logs`
  - `id`
  - `event_type`
  - `payload`
  - `correlation_id`
  - `created_at`

- `alerts`
  - alert rule fields.

- `dead_letter_events`
  - event failure capture fields.

Migrations:

- One Alembic migration exists: `2511bca9ec79_initial.py`.
- It creates the same main tables listed above.

Repository layer:

- `OrderRepo` creates orders, reads by id/client id/broker id, lists pending,
  and updates state.
- `PositionRepo` creates positions, reads by id, updates fields/status, and
  lists open positions.
- `CandleRepo` batch inserts candles using PostgreSQL `ON CONFLICT DO NOTHING`.
- `TradeRepo` appends trade logs and manages dead letters.
- `AlertRepo` manages alert rules.

Important database notes:

- Services assume the database exists. When Postgres is down, reconciliation
  degrades trading state and candle persistence logs errors.
- Postgres is now started from `/home/frj/TradingCore/docker-compose.yml`.

## Event Bus

The in-process event bus lives in `app/services/event_bus.py`.

Behavior:

- Subscribers are stored in process memory.
- `publish()` holds a lock and schedules subscriber handlers with
  `asyncio.create_task`.
- Publisher does not wait for handlers to finish.
- Handler failures are not centrally collected by the bus.

Event definitions live in `app/core/events.py`.

Main event types:

- `PriceUpdated`
- `CandleClosed`
- `SignalDetected`
- `RiskApproved`
- `RiskRejected`
- `OrderSubmitted`
- `OrderFilled`
- `OrderRejected`
- `PositionOpened`
- `PositionClosed`
- `PartialFillDetected`
- `WebSocketDisconnected`
- `SessionExpired`
- `CircuitBreakerOpened`
- `TradingDisabled`
- `DeadLetterCreated`

Important event-bus risk:

- The bus is fast and simple, but not durable. If the process crashes, in-flight
  events are lost.
- Subscriber exceptions are service-local; the bus does not create dead letters.
- Redis bridge only mirrors selected event types.

## Price Streaming Flow

Capital.com websocket code lives in `app/broker/websocket.py`.

Current subscriptions:

- `GOLD`
- `US500`
- `BTCUSD`

Flow:

1. `BrokerWebSocket.connect()` ensures a valid session.
2. It connects to `settings.broker_ws_url`.
3. It sends one `marketData.subscribe` message per configured epic.
4. Incoming websocket messages are parsed as JSON.
5. Parsed messages are pushed to `price_queue`.

Queue implementation:

- `price_queue` is a custom in-memory `SimpleQueue`.
- Max length: `10000`.
- Drop policy: `drop_oldest`.

`MarketStreamer` in `app/market/streaming.py` consumes `price_queue`.

Flow:

1. Wait for next queue item.
2. Ignore non-quote messages.
3. Convert quote payload into `PriceUpdated`.
4. Publish `PriceUpdated` to the in-process event bus.

Important streaming risks:

- Websocket subscriptions are hardcoded.
- Queue is in-memory only.
- Broker timestamps are replaced with local receive time.
- Non-quote messages are skipped.

## Candle Service

`CandleService` lives in `app/services/candle_service.py`.

Configured epics:

- `GOLD`
- `US500`

Configured timeframes:

- `MINUTE`
- `MINUTE_5`
- `HOUR`

Flow:

1. Subscribes to `PriceUpdated`.
2. Aggregates midpoint price into OHLC candles.
3. Persists closed candles through `CandleRepo.batch_insert`.
4. Publishes `CandleClosed`.

Important candle risks:

- `BTCUSD` is subscribed on websocket but not configured in `CandleService`.
- Candle persistence depends on Postgres.
- Persistence failure is logged, but no retry/dead-letter path is used.

## Signal Service

`SignalDetector` lives in `app/market/signals.py`.

Behavior:

- Subscribes to `PriceUpdated`.
- Tracks last midpoint price by epic.
- Emits `SignalDetected` if absolute move from previous tick exceeds threshold.
- Default threshold: `0.01`.
- Suppresses repeated same-direction signals per epic.

Important signal risks:

- This is a simple tick-to-tick threshold detector.
- It does not use candles, volatility, spread-normalization, or market metadata.
- It can fire on noisy ticks if threshold and instruments are not calibrated.

## Trading Service

`TradingService` lives in `app/services/trading_service.py`.

Behavior:

- Subscribes to `SignalDetected`.
- If trading is not allowed, ignores signal.
- If trading is allowed, logs the signal to `trade_logs`.
- Direct operator submission path calls `OrderWorkflowService.submit`.

Important trading-service risks:

- Signal handling logs signals but does not automatically place orders.
- It depends on DB availability for signal logging.
- It uses local DB open positions for order workflow checks.

## Order Workflow

`OrderWorkflowService` lives in `app/services/order_workflow_service.py`.

Flow:

1. Generate `client_order_id`.
2. Run `risk_manager.can_trade`.
3. If rejected, publish `OrderRejected`.
4. If approved, persist `Order` with state `PENDING`.
5. Publish `OrderSubmitted`.

State transitions:

- `PENDING -> FILLED | PARTIALLY_FILLED | CANCELLED | REJECTED`
- `PARTIALLY_FILLED -> FILLED | CANCELLED`
- `FILLED -> CLOSED`

Current order-workflow behavior:

- `POST /api/v1/workflow/risk-preview` runs the same risk gate as workflow
  order submission, but does not persist an order, publish order events, approve
  risk, or place a broker order.
- `POST /api/v1/workflow/orders` runs the Capital Trader risk workflow,
  persists the local order, and only then calls `BrokerClient.place_order`.
- If risk rejects the order, the route returns `403` and no broker order is
  placed.
- `POST /api/v1/orders` is disabled for direct broker placement and returns
  `403` with instructions to use the workflow route.

## Risk Manager

`RiskManager` lives in `app/risk/manager.py`.

Checks:

- Trading mode must allow trading.
- Size must not exceed `settings.max_position_size`.
- Open positions must be below `settings.max_open_positions`.
- Daily loss must be below `settings.max_daily_loss_pct`.
- Spread must be below configured per-epic max spread.
- Tick age must be below `settings.stale_tick_threshold_ms`.
- `client_order_id` must not be duplicate.

Current risk boundary:

- Public direct order placement through `/api/v1/orders` is disabled.
- Risk preview through `/api/v1/workflow/risk-preview` is read-only and exposes
  the decision context for the agent before a ticket is created.
- Workflow placement through `/api/v1/workflow/orders` uses this risk manager.
- Clean Agent still provides the outer ticket gate before it calls Capital
  Trader.

## Reconciliation Service

`ReconciliationService` lives in `app/services/reconciliation_service.py`.

Interval:

- Every 300 seconds.

Flow:

1. Fetch broker positions.
2. Fetch broker working orders.
3. Compare broker positions to local DB.
4. Import orphan broker positions into DB.
5. Update local position size drift.
6. Mark local `OPEN` positions as `CLOSED` if they are missing from broker
   positions.
7. Compare broker working orders to local DB.
8. Import orphan broker working orders into DB.
9. Update order state drift when local broker order exists.
10. Persist a row in `reconciliation_runs` with status, timestamps, error, and
    summary counts.

Observed runtime result:

- Broker calls succeeded.
- DB connection failed.
- Service logged `reconciliation_error`.
- Trading state moved to degraded.

Important reconciliation risks:

- If DB is down, Capital Trader can still answer direct broker read endpoints,
  but local persistence and reconciliation are unhealthy.
- Imported orphan orders use `client_order_id="broker:{broker_order_id}"`.
- Missing local positions are marked closed without a broker close price when
  the broker no longer reports them.

## Redis Event Bridge

`redis_event_bridge.py` mirrors selected in-process events to Redis streams.

Streams:

- `rafiq.market.signaldetected`
- `rafiq.trading.ordersubmitted`
- `rafiq.trading.orderfilled`

Current verification:

- `redis` Python dependency is installed in the venv.
- Redis is now started from `/home/frj/TradingCore/docker-compose.yml`.
- `docker compose exec -T redis redis-cli ping` returns `PONG`.

Important Redis risks:

- Deep health now checks Redis with `PING` and reports bridge subscription,
  last publish time, and last bridge error.
- Bridge publish failures are visible in `/api/health/deep`, but they do not
  stop trading by themselves.
- It does not mirror all event types.

## Deep Health

`GET /api/health/deep` reports component-level health for:

- Broker session token state and expiry.
- Postgres connectivity.
- Redis connectivity and bridge status.
- Websocket connection, subscriptions, and last websocket error.
- Reconciliation running state, last completion time, last counts, and last
  error.
- Reconciliation last summary, including orphan imports, drift updates, and
  local closures.
- Latest price tick time and epic.
- Trading mode and whether trading is allowed.

Overall status rules:

- `unhealthy` if any component is unhealthy.
- `degraded` if no component is unhealthy but at least one component is
  degraded.
- `healthy` only when all components are healthy.

Runtime note:

- Observe-only mode intentionally makes the trading component `degraded`, so
  the overall status can be `degraded` even when broker, DB, Redis, websocket,
  reconciliation, and prices are healthy.

## Public API Execution Path

Order routes:

- `POST /api/v1/workflow/risk-preview`
- `POST /api/v1/workflow/orders`
- `POST /api/v1/orders`
- Implemented in `app/api/v1/orders.py`.

Risk preview behavior:

- Fetches current market quote.
- Reads local open-position count.
- Runs `RiskManager.can_trade`.
- Returns approval status, rejection reason, bid/ask, spread, trading mode,
  open-position count, and configured risk limits.
- Does not create an order, publish order events, mark risk approval, or call
  broker order placement.

Workflow route behavior:

- Checks current market quote and local open-position count.
- Runs `OrderWorkflowService.submit`.
- Persists the internal order as `PENDING`.
- Calls `BrokerClient.place_order`.
- Stores the broker reference and moves the local order to `SUBMITTED`.

Direct route behavior:

- Direct broker placement is disabled.
- The endpoint returns `403` and points callers to
  `/api/v1/workflow/orders`.

Broker behavior:

- Market orders call Capital.com positions endpoint.
- Non-market orders call Capital.com working orders endpoint.
- After the 2026-09-19 patch, market orders preserve `limitDistance` and
  `stopDistance` when provided.

Important execution notes:

- Observe-only mode rejects workflow placement with
  `Risk rejected: trading_not_allowed mode=TradingMode.OBSERVE_ONLY`.
- `OrderSubmitted` and `OrderRejected` event publishing now uses the shared
  `BaseEvent.new(..., **payload)` factory.

## Position Close Workflow

`PositionWorkflowService` lives in `app/services/position_workflow_service.py`.

Routes:

- `POST /api/v1/workflow/positions/{deal_id}/close-preview`
- `POST /api/v1/workflow/positions/{deal_id}/close`

Close preview behavior:

- Confirms a local `OPEN` position exists.
- Confirms the broker still reports the same `dealId`.
- Compares local and broker epic/size.
- Reads broker direction, market status, bid, and offer.
- Estimates close price using bid for `BUY` positions and offer for `SELL`
  positions.
- Reports whether close is allowed without closing anything.

Close workflow behavior:

- Runs close preview first.
- Rejects if trading mode is not allowed.
- Rejects if broker market status is not `TRADEABLE`.
- Rejects if local and broker position size/epic do not match.
- Calls `BrokerClient.close_position` only after preview approval.
- Marks the local position `CLOSED` with close price and close time.
- Publishes `PositionClosed`.

## Trade Log Audit

`trade_logs` stores Capital Trader trading-core audit events in Postgres.

API:

- `GET /api/v1/audit/trade-log`

Filters:

- `limit`
- `event_type`
- `correlation_id`

Workflow events currently written:

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

This is separate from Clean Agent's action audit. Clean Agent records what the
agent proposed or attempted; Capital Trader trade logs record what the trading
core decided and persisted.

## Recommended Next Planning Topics

No implementation should happen until these are decided:

1. Should the database be required for service startup, or should read-only
   broker mode be explicit?
2. Should Redis be optional with visible degraded health, or required?
3. Should websocket subscriptions be config-driven?
4. Should Clean Agent consume Redis streams or keep polling Capital Trader HTTP?
5. Should reconciliation import orphan orders and close missing local positions?
