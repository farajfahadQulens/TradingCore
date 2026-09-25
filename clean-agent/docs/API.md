# API Reference

The service listens on `http://127.0.0.1:8091` by default.

## Health and Dashboard

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Operator dashboard. |
| `GET` | `/health` | Local service status and configuration summary. |
| `GET` | `/api/dashboard` | Operator dashboard payload with agent mode, tickets, unified action audit, notification rules/events, broker balance/positions/orders, Capital Trader deep health/trade logs, Canvas status, browser imports, and config gates. |
| `GET` | `/api/gold/candles.csv` | Proxy stored one-minute GOLD OHLCV candles; optional `limit`, `start`, `end`, and `offset`. |

`/api/dashboard` is the browser UI's single data source. The page does not call
Capital Trader directly; Clean Agent proxies bounded health/log/broker reads and
returns endpoint-specific errors as data when a dependency is unavailable.

## Chat and Tools

### `POST /chat`

Request:

```json
{"message":"Show my imported course deadlines","session_id":null}
```

Response includes `session_id`, `response`, and `tools_used`.

### `POST /tools/run`

Run a registered tool directly:

```json
{"name":"get_browser_context","arguments":{"limit":5}}
```

### Capital Trader Tools

Read-only tools:

- `get_capital_trader_capabilities` - list available Capital Trader abilities
  and the safe position-opening flow.
- `get_capital_trader_snapshot` - read health, balance, open positions, and
  working orders in one call.
- `get_health` - check Capital Trader health.
- `get_balance` - read account equity/balance from Capital Trader.
- `list_positions` - read open broker positions.
- `list_orders` - read broker working orders.
- `get_market_info` - read market metadata for an epic.
- `get_market_prices` - read recent broker candles/prices for an epic.
- `preview_trade_risk` - ask Capital Trader whether a proposed trade would
  pass risk checks without creating or placing an order.
- `preview_close_position` - ask Capital Trader whether an existing position
  could be closed without closing it.

Position/write tools:

- `create_trade_ticket` - prepare a proposed position/order. It does not place
  a broker order.
- `approve_ticket` - approve a pending ticket with the exact confirmation
  phrase.
- `execute_ticket` - submit an approved ticket to Capital Trader after fresh
  checks through Capital Trader's `/api/v1/workflow/orders` endpoint. This
  still requires trading writes to be enabled.
- `create_close_ticket` - prepare a close-position ticket from Capital Trader
  close preview. It does not close the broker position.
- `approve_close_ticket` - approve a pending close ticket with the exact
  confirmation phrase.
- `execute_close_ticket` - submit an approved close ticket after a fresh close
  preview through Capital Trader's close workflow endpoint. This still requires
  trading writes to be enabled.

`submit_order` remains a disabled compatibility stub. If the user asks to add
or open a position, the agent must create a ticket first. If the user asks to
close a position, the agent must create a close ticket first.

## Modes

### `POST /api/mode`

Allowed values: `observe`, `analyze`, `prepare`, `confirm`, `execute`.

## Tickets

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/tickets` | List tickets; optional `limit` and `status`. |
| `POST` | `/api/tickets` | Create a non-executing ticket. |
| `POST` | `/api/tickets/{id}/approve` | Approve with the exact phrase. |
| `POST` | `/api/tickets/{id}/execute` | Execute an approved ticket if all guards pass. |

## Audit

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/audit/actions` | Unified action timeline from audit events and ticket state; optional `limit` and `ticket_id`. |

Audit tool:

- `get_action_audit` - inspect the same unified action timeline from chat/tool
  use.

## Notifications

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/notifications/rules` | List notification rules; optional `limit` and `enabled`. |
| `POST` | `/api/notifications/rules` | Create a Telegram-backed `price`, `market_open`, `position_pl`, or `health` rule. |
| `POST` | `/api/notifications/rules/{id}/disable` | Disable a rule without deleting history. |
| `GET` | `/api/notifications/events` | List delivery attempts; optional `limit` and `rule_id`. |
| `POST` | `/api/notifications/test` | Send a Telegram test message. |
| `POST` | `/api/notifications/evaluate` | Evaluate active rules once. |
| `POST` | `/api/notifications/presets/position` | Create market-open and +/- P/L alert presets around a live position. |

Rule examples:

```json
{"rule_type":"price","epic":"GOLD","condition":"below","threshold":4375}
```

```json
{"rule_type":"market_open","epic":"GOLD"}
```

```json
{"rule_type":"position_pl","epic":"GOLD","condition":"above","threshold":500}
```

```json
{"rule_type":"health","epic":"CAPITAL_TRADER"}
```

Position preset example:

```json
{"epic":"GOLD","delta":50,"cooldown_seconds":900}
```

Notification tools:

- `create_price_alert`
- `create_market_open_alert`
- `create_position_pl_alert`
- `create_health_alert`
- `list_notification_rules`
- `disable_notification_rule`
- `send_test_notification`

Notifications are informational only and do not execute trades.

Rules are stateful. A rule moves through `inactive`, `active`, and `recovered`
states so it sends one alert when a condition first becomes true and, by
default, one recovery notification when it clears. Set `notify_recovery=false`
when creating a rule to suppress recovery pings.

## Agent Memory

Memory stores durable preferences, lessons, strategy notes, and operational
facts. It must not be used as live broker truth.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/memories` | List memories; optional `limit`, `memory_type`, `scope`, and `active_only`. |
| `POST` | `/api/memories` | Create a memory. |
| `DELETE` | `/api/memories/{id}` | Deactivate a memory without deleting history. |

Memory tools:

- `list_agent_memories`
- `search_agent_memories`
- `get_trading_profile`
- `remember_trading_preference`
- `remember_strategy_note`
- `remember_operational_note`
- `deactivate_memory`

Each chat request receives a compact active memory context. Live balance,
positions, orders, market metadata, and prices must still come from Capital
Trader tools.

## Canvas

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/integrations/canvas/status` | Connection status without secrets. |
| `GET` | `/integrations/canvas/connect` | Start OAuth authorization. |
| `GET` | `/integrations/canvas/callback` | Complete OAuth authorization. |

Read-only Canvas model tools are `get_canvas_status`, `list_canvas_courses`,
`list_canvas_events`, and `list_canvas_todo`.

## Browser Bridge

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/browser/import` | Accept a user-selected BI page snapshot. |
| `GET` | `/api/browser/snapshots` | Return recent snapshots. |

Imports require HTTPS and a hostname of `bi.instructure.com`, `bi.no`, or a
subdomain of `bi.no`.

## Research

### `POST /api/research/backtest`

Example:

```json
{
  "epic":"CS.D.EURUSD.TODAY",
  "resolution":"HOUR",
  "max_points":300,
  "fast_window":10,
  "slow_window":30,
  "initial_cash":10000,
  "fee_bps":1,
  "slippage_bps":2
}
```

This endpoint is read-only and returns a `research_only` report. It cannot
create or execute a trade ticket.
