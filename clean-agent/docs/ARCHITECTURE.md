# Architecture

Clean Agent is a local FastAPI service with three intentionally separate
responsibilities:

1. Study context: Canvas OAuth, browser-imported BI pages, and research reports.
2. Trading intelligence: read-only broker data, model tool calls, deterministic
   risk checks, and persistent trade tickets.
3. Trading execution: a guarded handoff to the existing Capital Trader HTTP API.

Capital Trader is an external dependency. Clean Agent never imports its Python
modules and never edits its files.

## Request Flow

### Chat

```text
browser dashboard
    -> POST /chat
    -> GPT OSS /chat/completions
    -> optional tool call
    -> local tool or Capital Trader HTTP API
    -> tool result returned to GPT
    -> final response to dashboard
```

The model may request tools, but tool permissions are implemented in Python.
The model cannot bypass the ticket and approval checks.

### Trade

```text
proposal
    -> create_trade_ticket
    -> deterministic risk evaluation
    -> pending_confirmation
    -> exact confirmation phrase
    -> approved
    -> fresh broker snapshot and risk evaluation
    -> Capital Trader order request
    -> after-state reconciliation
    -> executed or blocked
```

Direct `submit_order` is a compatibility stub and never places an order.

### Study Context

```text
Canvas OAuth or browser extension
    -> local agent
    -> encrypted token or SQLite page snapshot
    -> GPT tool context
```

The browser extension sends data only after a user click. It does not read
passwords or cookies and does not submit forms.

## Module Map

| Module | Responsibility |
| --- | --- |
| `app/config.py` | Environment-backed settings. |
| `app/main.py` | FastAPI app, routes, lifespan, chat loop, CORS. |
| `app/llm.py` | OpenAI-compatible GPT OSS client and response validation. |
| `app/trader.py` | HTTP-only Capital Trader client with bounded timeouts. |
| `app/tools.py` | Model tool implementations and JSON schemas. |
| `app/store.py` | SQLite persistence and audit ledger. |
| `app/risk.py` | Deterministic ticket checks. |
| `app/execution.py` | Ticket lifecycle and broker reconciliation. |
| `app/canvas.py` | Read-only Canvas OAuth, encrypted tokens, and API reads. |
| `app/research.py` | OHLC normalization and research-only baseline backtest. |
| `app/static/` | Operator dashboard. |
| `browser_extension/` | User-triggered Chrome page importer. |
| `tests/` | Focused unit tests for safety and research behavior. |

## Persistence

The default database is `data/agent.sqlite3`.

- `agent_state`: current operating mode.
- `audit_events`: important actions and failures.
- `trade_tickets`: proposals, risk results, approvals, broker responses, and reconciliation.
- `integration_tokens`: encrypted third-party tokens.
- `oauth_states`: short-lived Canvas OAuth CSRF values.
- `browser_snapshots`: user-selected BI page content.

The `data/` directory is ignored by Git.
