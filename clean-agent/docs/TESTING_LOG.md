# Clean Agent Testing Log

This file records tests and runtime checks for Clean Agent.

## 2026-09-19T21:45:03Z Capital Trader Tool Upgrade

Added explicit Capital Trader capability and snapshot tools:

- `get_capital_trader_capabilities`
- `get_capital_trader_snapshot`

Updated the system prompt so the model treats Capital Trader as a first-class
toolset:

- Read balance with `get_balance`.
- Read open positions with `list_positions`.
- Read working orders with `list_orders`.
- Read all main broker state with `get_capital_trader_snapshot`.
- Prepare opening or adding a position with `create_trade_ticket`.
- Never submit direct orders through `submit_order`.

### Unit Tests

Command:

```bash
cd /home/frj/TradingCore/clean-agent
PYTHONPATH=. .venv/bin/python -m pytest
```

Result:

```text
11 passed
```

New coverage:

- Capital Trader capabilities describe read tools and safe position flow.
- Capital Trader snapshot returns health, balance, positions, and orders.

### Runtime Tool Registration

Command:

```bash
curl -s -X POST http://127.0.0.1:8091/tools/run \
  -H 'Content-Type: application/json' \
  -d '{"name":"get_capital_trader_capabilities","arguments":{}}'
```

Result:

```text
Tool returned read tools, write flow, and safety map.
```

Command:

```bash
curl -s -X POST http://127.0.0.1:8091/tools/run \
  -H 'Content-Type: application/json' \
  -d '{"name":"get_capital_trader_snapshot","arguments":{}}'
```

Result summary:

```text
health: healthy
balance: returned
positions: 1
working orders: 0
```

## 2026-09-19 Agent Memory

Added durable SQLite-backed agent memory.

Memory API:

- `GET /api/memories`
- `POST /api/memories`
- `DELETE /api/memories/{id}`

Memory tools:

- `list_agent_memories`
- `search_agent_memories`
- `get_trading_profile`
- `remember_trading_preference`
- `remember_strategy_note`
- `remember_operational_note`
- `deactivate_memory`

Seeded default memories:

- Active stack lives at `/home/frj/TradingCore`.
- Capital Trader runs at `http://127.0.0.1:8000`.
- Clean Agent runs at `http://127.0.0.1:8091`.
- Postgres and Redis run from `/home/frj/TradingCore/docker-compose.yml`.
- Trading writes are disabled by default.
- Direct order submission is disabled.
- Opening/adding a position must use ticket flow.
- Stop loss or stop distance is required.
- Live broker facts must come from Capital Trader tools, not memory.

### Unit Tests

Command:

```bash
cd /home/frj/TradingCore/clean-agent
PYTHONPATH=. .venv/bin/python -m pytest
```

Result:

```text
14 passed
```

New coverage:

- Store creates, searches, and deactivates memories.
- Default seeding does not duplicate memories.
- Memory tools create trading preferences, strategy notes, operational notes,
  list/search memories, and build the trading profile.

### Runtime Verification

Command:

```bash
curl -s http://127.0.0.1:8091/api/memories?limit=20
```

Result:

```text
8 seeded active memories returned
```

Command:

```bash
curl -s -X POST http://127.0.0.1:8091/tools/run \
  -H 'Content-Type: application/json' \
  -d '{"name":"get_trading_profile","arguments":{}}'
```

Result:

```text
Trading profile returned operational notes, risk preferences, and trading rule.
```

## 2026-09-19 - Capital Trader Workflow Order Endpoint

Clean Agent now sends approved ticket execution to Capital Trader's guarded
workflow route instead of the disabled direct broker route.

Changed behavior:

- `execute_ticket` still requires Clean Agent trading writes to be enabled.
- `TraderClient.submit_order` posts to
  `POST /api/v1/workflow/orders`.
- `submit_order` remains a disabled compatibility tool; user-requested
  position changes must go through tickets.

Unit tests:

```bash
cd /home/frj/TradingCore/clean-agent
PYTHONPATH=. .venv/bin/python -m pytest
```

Result:

```text
15 passed
```

## 2026-09-20 - Capital Trader Risk Preview Tool

Clean Agent now exposes `preview_trade_risk`, a read-only tool that calls
Capital Trader's guarded risk preview endpoint.

Behavior:

- Posts to `POST /api/v1/workflow/risk-preview`.
- Normalizes direction and order type to uppercase.
- Converts numeric fields to numbers.
- Does not create a ticket.
- Does not execute a broker order.

Unit tests:

```bash
cd /home/frj/TradingCore/clean-agent
PYTHONPATH=. .venv/bin/python -m pytest
```

Result:

```text
17 passed
```

Compile check:

```bash
.venv/bin/python -m py_compile app/trader.py app/tools.py tests/test_tools.py
```

Result:

```text
OK
```

Runtime verification:

```bash
curl -s -o /tmp/clean-preview-risk.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8091/tools/run \
  -H 'Content-Type: application/json' \
  -d '{"name":"preview_trade_risk","arguments":{"epic":"GOLD","direction":"BUY","size":0.01,"order_type":"MARKET","stop_distance":1}}'
```

Result:

```text
HTTP 200
workflow: risk_preview
approved: false
reason: trading_not_allowed mode=TradingMode.OBSERVE_ONLY
risk.trading_mode: observe
risk.open_positions_count: 1
```

## 2026-09-20 - Capital Trader Close Preview Tool

Clean Agent now exposes `preview_close_position`, a read-only tool that calls
Capital Trader's guarded close-preview endpoint.

Behavior:

- Posts to `POST /api/v1/workflow/positions/{deal_id}/close-preview`.
- Returns local position state, broker position state, market status, and close
  approval reason.
- Does not close a broker position.
- Does not create an execution ticket.

Unit tests:

```bash
cd /home/frj/TradingCore/clean-agent
PYTHONPATH=. .venv/bin/python -m pytest
```

Result:

```text
19 passed
```

Compile check:

```bash
.venv/bin/python -m py_compile app/trader.py app/tools.py tests/test_tools.py
```

Result:

```text
OK
```

Runtime verification:

```bash
curl -s -o /tmp/clean-close-preview.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8091/tools/run \
  -H 'Content-Type: application/json' \
  -d '{"name":"preview_close_position","arguments":{"deal_id":"00601567-0001-54c4-0000-00009222a0f8"}}'
```

Result:

```text
HTTP 200
workflow: close_position_preview
approved: false
reason: trading_not_allowed mode=TradingMode.OBSERVE_ONLY; market_not_tradeable status=CLOSED
local_position.status: OPEN
broker_position.epic: GOLD
broker_position.direction: SELL
```

## 2026-09-20 - Close Position Ticket Flow

Clean Agent now supports a close-position ticket flow.

Tools:

- `create_close_ticket`
- `approve_close_ticket`
- `execute_close_ticket`

Behavior:

- `create_close_ticket` calls Capital Trader close preview and stores the
  preview on the ticket.
- Rejected close previews create `blocked` tickets.
- Close tickets use confirmation phrases beginning with `CONFIRM CLOSE`.
- `approve_close_ticket` only approves close-position tickets.
- `execute_close_ticket` re-runs close preview before close execution.
- Execution still requires `ALLOW_TRADING_WRITES=true`.

Unit tests:

```bash
cd /home/frj/TradingCore/clean-agent
PYTHONPATH=. .venv/bin/python -m pytest
```

Result:

```text
24 passed
```

Compile check:

```bash
.venv/bin/python -m py_compile \
  app/execution.py \
  app/store.py \
  app/trader.py \
  app/tools.py \
  tests/test_close_tickets.py \
  tests/test_tools.py
```

Result:

```text
OK
```

Runtime verification:

```bash
curl -s -o /tmp/create-close-ticket.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8091/tools/run \
  -H 'Content-Type: application/json' \
  -d '{"name":"create_close_ticket","arguments":{"deal_id":"00601567-0001-54c4-0000-00009222a0f8","reason":"Prepare a safe close plan for current GOLD exposure","invalidated_if":"Market opens with a materially different quote or broker position changes"}}'
```

Result:

```text
HTTP 200
ticket_type: close_position
status: blocked
epic: GOLD
direction: SELL
size: 3.66
risk.error: trading_not_allowed mode=TradingMode.OBSERVE_ONLY; market_not_tradeable status=CLOSED
```

Guard verification:

```bash
curl -s -o /tmp/approve-close-ticket.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8091/tools/run \
  -H 'Content-Type: application/json' \
  -d '{"name":"approve_close_ticket","arguments":{"ticket_id":"T-20260919-230247-EC03","confirmation_phrase":"CONFIRM CLOSE T-20260919-230247-EC03 GOLD 00601567-0001-54c4-0000-00009222a0f8"}}'

curl -s -o /tmp/execute-close-ticket.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8091/tools/run \
  -H 'Content-Type: application/json' \
  -d '{"name":"execute_close_ticket","arguments":{"ticket_id":"T-20260919-230247-EC03"}}'
```

Result:

```text
approve_close_ticket: HTTP 200, approved=false, reason=ticket status is blocked
execute_close_ticket: HTTP 200, executed=false, reason=trading writes are disabled
```

## 2026-09-20 - Unified Action Audit

Clean Agent now exposes a unified action timeline from audit events and ticket
state.

API:

- `GET /api/audit/actions`
- Optional query params: `limit`, `ticket_id`

Tool:

- `get_action_audit`

Behavior:

- Merges `audit_events` with current ticket state snapshots.
- Sorts newest first.
- Includes source, action, ticket id, ticket type, status, summary, and payload.
- Can filter by one ticket id.

Unit tests:

```bash
cd /home/frj/TradingCore/clean-agent
PYTHONPATH=. .venv/bin/python -m pytest
```

Result:

```text
27 passed
```

Compile check:

```bash
.venv/bin/python -m py_compile \
  app/store.py \
  app/main.py \
  app/tools.py \
  tests/test_action_audit.py
```

Result:

```text
OK
```

Runtime verification:

```bash
curl -s -o /tmp/action-audit-api.json -w '%{http_code}' \
  'http://127.0.0.1:8091/api/audit/actions?limit=10'

curl -s -o /tmp/action-audit-tool.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8091/tools/run \
  -H 'Content-Type: application/json' \
  -d '{"name":"get_action_audit","arguments":{"limit":5}}'
```

Result:

```text
Action audit API: HTTP 200
Action audit tool: HTTP 200
Timeline includes audit events and ticket_current_state entries.
Observed close ticket summary: blocked close ticket for GOLD deal 00601567-0001-54c4-0000-00009222a0f8
```

## 2026-09-20 - Trading Workspace UI

Clean Agent's browser UI was rebuilt as a trading workspace instead of a raw
status console.

Behavior:

- `/api/dashboard` now includes unified action audit, ticket status counts,
  Capital Trader deep health, and Capital Trader trade logs.
- The UI renders account equity, available funds, open P/L, exposure, broker
  positions, guarded tickets, Clean Agent actions, Capital Trader events,
  component health, memories, and browser imports.
- The browser still uses Clean Agent as the single data source; it does not call
  Capital Trader directly.

Unit tests:

```bash
cd /home/frj/TradingCore/clean-agent
PYTHONPATH=. .venv/bin/python -m pytest
```

Result:

```text
28 passed
```

Compile and JavaScript syntax checks:

```bash
.venv/bin/python -m py_compile app/main.py app/trader.py tests/test_dashboard.py
node --check app/static/app.js
```

Result:

```text
OK
```

Runtime verification:

```bash
curl -s -o /tmp/clean-agent-dashboard.json -w '%{http_code}' \
  http://127.0.0.1:8091/api/dashboard

curl -s -o /tmp/clean-agent-ui.html -w '%{http_code}' \
  http://127.0.0.1:8091/

curl -s -o /tmp/clean-agent-app.js -w '%{http_code}' \
  http://127.0.0.1:8091/static/app.js
```

Result:

```text
Dashboard API: HTTP 200
Dashboard HTML: HTTP 200
Dashboard JS: HTTP 200
Payload includes agent.actions, agent.ticket_summary, capital.deep_health, and
capital.trade_logs.
```

## 2026-09-20 - Telegram Notification Alerts

Clean Agent now supports Telegram-backed informational alerts.

Behavior:

- Adds SQLite-backed notification rules and notification events.
- Adds Telegram delivery through `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
- Adds a background watcher that evaluates enabled rules.
- Supports price threshold alerts and market-open alerts.
- Adds dashboard visibility for alert rules and recent delivery attempts.
- Adds agent tools: `create_price_alert`, `create_market_open_alert`,
  `list_notification_rules`, `disable_notification_rule`, and
  `send_test_notification`.

Unit tests:

```bash
cd /home/frj/TradingCore/clean-agent
PYTHONPATH=. .venv/bin/python -m pytest
```

Result:

```text
31 passed
```

Compile and JavaScript syntax checks:

```bash
.venv/bin/python -m py_compile \
  app/config.py \
  app/store.py \
  app/notifications.py \
  app/main.py \
  app/tools.py \
  tests/test_notifications.py

node --check app/static/app.js
```

Result:

```text
OK
```

Runtime verification:

```bash
curl -s -o /tmp/clean-agent-health.json -w '%{http_code}' \
  http://127.0.0.1:8091/health

curl -s -o /tmp/clean-agent-notification-rules.json -w '%{http_code}' \
  http://127.0.0.1:8091/api/notifications/rules

curl -s -o /tmp/clean-agent-dashboard.json -w '%{http_code}' \
  http://127.0.0.1:8091/api/dashboard

curl -s -o /tmp/clean-agent-notification-evaluate.json -w '%{http_code}' \
  -X POST http://127.0.0.1:8091/api/notifications/evaluate
```

Result:

```text
Health: HTTP 200
Notification rules: HTTP 200
Dashboard: HTTP 200
Manual evaluation: HTTP 200
Telegram configured: false
Manual evaluation result: checked=0, triggered=0, errors=0
```

## 2026-09-20 - Telegram Credentials Connected

Local `.env` was created from the project defaults and Telegram notification
credentials were added locally. The token is intentionally not recorded in
docs.

Runtime verification:

```bash
curl -i --max-time 10 http://127.0.0.1:8091/health

curl -i --max-time 20 \
  -X POST http://127.0.0.1:8091/api/notifications/test \
  -H 'Content-Type: application/json' \
  -d '{"message":"TradingCore Telegram test"}'
```

Result:

```text
Health: HTTP 200
telegram_configured: true
Telegram test: HTTP 200
delivered: true
event id: 1
```

## 2026-09-20 - Starter Telegram Alert Rules

Created the first live Telegram alert rules:

- `GOLD` market-open alert.
- `GOLD` price-below alert at `4375`.

Runtime verification:

```bash
curl -i --max-time 10 http://127.0.0.1:8091/api/notifications/rules

curl -i --max-time 20 \
  -X POST http://127.0.0.1:8091/api/notifications/evaluate

curl -i --max-time 10 http://127.0.0.1:8091/api/notifications/events
```

Result:

```text
Rules: HTTP 200
Rules active: 2
Manual evaluation: HTTP 200
Evaluation checked: 2
Evaluation triggered: 0
Evaluation errors: 0
Events: HTTP 200
```

## 2026-09-20 - Alert Upgrade: P/L, Health, and UI Creator

Notification alerts were upgraded with richer rule types and a dashboard
creator.

Behavior:

- Added `position_pl` rules for aggregate open P/L on one epic.
- Added `health` rules for Capital Trader degraded health.
- Kept `price` and `market_open` rules.
- Added tools: `create_position_pl_alert` and `create_health_alert`.
- Added dashboard form controls for creating price, market-open, P/L, and
  health alerts without curl.

Unit tests:

```bash
cd /home/frj/TradingCore/clean-agent
PYTHONPATH=. .venv/bin/python -m pytest
```

Result:

```text
33 passed
```

Compile and JavaScript syntax checks:

```bash
.venv/bin/python -m py_compile \
  app/notifications.py \
  app/main.py \
  app/tools.py \
  tests/test_notifications.py

node --check app/static/app.js
```

Result:

```text
OK
```

Runtime verification:

```bash
curl -i --max-time 10 http://127.0.0.1:8091/api/dashboard

curl -i --max-time 10 http://127.0.0.1:8091/static/app.js

curl -i --max-time 20 \
  -X POST http://127.0.0.1:8091/api/notifications/evaluate
```

Result:

```text
Dashboard: HTTP 200
Dashboard JS: HTTP 200
Manual evaluation: HTTP 200
Evaluation checked: 2
Evaluation triggered: 0
Evaluation errors: 0
```

## 2026-09-20 - Stateful Alerts and Dashboard Controls

Notification rules now use a state machine instead of cooldown-only behavior.

Behavior:

- Rules track `inactive`, `active`, and `recovered` states.
- A rule sends one alert when its condition first becomes true.
- A rule sends one recovery notification when the condition clears, unless
  `notify_recovery=false`.
- Existing rules migrate with `state=inactive` and `notify_recovery=true`.
- The dashboard Telegram panel now includes:
  - rule creation,
  - recovery toggle,
  - manual evaluation button,
  - per-rule disable button.

Unit tests:

```bash
cd /home/frj/TradingCore/clean-agent
PYTHONPATH=. .venv/bin/python -m pytest
```

Result:

```text
34 passed
```

Compile and JavaScript syntax checks:

```bash
.venv/bin/python -m py_compile \
  app/store.py \
  app/notifications.py \
  app/main.py \
  app/tools.py \
  tests/test_notifications.py

node --check app/static/app.js
```

Result:

```text
OK
```

Runtime verification:

```bash
curl -i --max-time 10 http://127.0.0.1:8091/api/notifications/rules

curl -i --max-time 20 \
  -X POST http://127.0.0.1:8091/api/notifications/evaluate

curl -s --max-time 10 http://127.0.0.1:8091/ \
  -o /tmp/clean-agent-ui.html -w '%{http_code}'

curl -s --max-time 10 http://127.0.0.1:8091/static/app.js \
  -o /tmp/clean-agent-app.js -w '%{http_code}'
```

Result:

```text
Rules: HTTP 200
Existing rules include state, notify_recovery, last_checked_at, and last_value.
Manual evaluation: HTTP 200
Evaluation checked: 2
Evaluation triggered: 0
Evaluation errors: 0
Dashboard HTML: HTTP 200
Dashboard JS: HTTP 200
```

## 2026-09-20 - Position Presets and Rich Telegram Messages

Telegram alert messages now include richer context, and Clean Agent can create
position-focused alert presets from live broker state.

Behavior:

- Price and market alerts include market status, bid, offer, and dashboard URL.
- P/L alerts include condition, threshold, current P/L, and dashboard URL.
- Health alerts include health status and dashboard URL.
- Added `POST /api/notifications/presets/position`.
- The dashboard Telegram panel now has a `Preset` button that creates current
  position presets for the selected epic.
- Preset creation reuses an existing market-open rule when present and adds
  P/L rules at current open P/L plus/minus the requested delta.

Unit tests:

```bash
cd /home/frj/TradingCore/clean-agent
PYTHONPATH=. .venv/bin/python -m pytest
```

Result:

```text
36 passed
```

Compile and JavaScript syntax checks:

```bash
.venv/bin/python -m py_compile \
  app/notifications.py \
  app/main.py \
  tests/test_notifications.py \
  tests/test_notification_presets.py

node --check app/static/app.js
```

Result:

```text
OK
```

Runtime verification:

```bash
curl -i --max-time 20 \
  -X POST http://127.0.0.1:8091/api/notifications/presets/position \
  -H 'Content-Type: application/json' \
  -d '{"epic":"GOLD","delta":50,"cooldown_seconds":900,"notify_recovery":true}'

curl -i --max-time 20 \
  -X POST http://127.0.0.1:8091/api/notifications/evaluate

curl -i --max-time 10 http://127.0.0.1:8091/api/notifications/rules
```

Result:

```text
Preset API: HTTP 200
Current GOLD open P/L: 549.47
Reused market-open rule: id=1
Created GOLD P/L above rule: threshold=599.47
Created GOLD P/L below rule: threshold=499.47
Manual evaluation: HTTP 200
Evaluation checked: 4
Evaluation triggered: 0
Evaluation errors: 0
```
