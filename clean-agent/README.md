# Clean Agent

Clean Agent is a small FastAPI service that connects to the same OpenAI-compatible GPT OSS 120 cloud endpoint used by the existing Rafiq agent.

It talks to the existing `capital_trader` service over HTTP. It does not import, edit, or replace `capital_trader`.

## Design

The code is intentionally boring:

- `app/config.py` loads environment settings.
- `app/llm.py` calls `/chat/completions` on `OLLAMA_BASE_URL`.
- `app/trader.py` is a tiny HTTP client for the existing Capital Trader API.
- `app/tools.py` exposes the tools the model may call.
- `app/store.py` persists audit events, operating mode, and trade tickets.
- `app/risk.py` applies deterministic ticket risk checks.
- `app/execution.py` owns ticket creation, approval, execution, and reconciliation.
- `app/canvas.py` owns the read-only BI Canvas OAuth2 connection and API client.
- `app/main.py` owns the FastAPI routes and the tool-call loop.

Trading writes are disabled by default. Read tools work with only `TRADER_BASE_URL`.

## Documentation

- [Architecture](docs/ARCHITECTURE.md): components, request flows, and persistence.
- [Configuration](docs/CONFIGURATION.md): every environment variable and default.
- [API reference](docs/API.md): routes, tools, request bodies, and boundaries.
- [Operations runbook](docs/OPERATIONS.md): start, diagnose, and maintain the service.
- [Security model](docs/SECURITY.md): credentials, browser data, and trading guards.
- [Development guide](docs/DEVELOPMENT.md): adding tools, routes, research, and tests.
- [Testing log](docs/TESTING_LOG.md): exact test and runtime verification history.

## Tools

Read-only tools:

- `get_capital_trader_capabilities`
- `get_capital_trader_snapshot`
- `get_health`
- `get_balance`
- `list_positions`
- `list_orders`
- `get_market_info`
- `get_market_prices`

Ticket tools:

- `create_trade_ticket`
- `approve_ticket`
- `execute_ticket`
- `list_trade_tickets`

Memory tools:

- `list_agent_memories`
- `search_agent_memories`
- `get_trading_profile`
- `remember_trading_preference`
- `remember_strategy_note`
- `remember_operational_note`
- `deactivate_memory`

Memory stores durable preferences, lessons, strategy notes, and operational
facts. It does not replace live Capital Trader reads for balance, positions,
orders, prices, or market state.

Direct `submit_order` is intentionally disabled. A live order must flow through a ticket:

1. Create a ticket.
2. Review deterministic risk checks.
3. Approve it with the exact ticket phrase.
4. Execute it after fresh broker reconciliation.

`execute_ticket` requires:

- `ALLOW_TRADING_WRITES=true`
- ticket status `approved`
- fresh risk checks passing

This guard lives in the new agent only. Capital Trader should still enforce its own risk rules before any live use.

## Setup

```bash
cd /home/frj/TradingCore/clean-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` if your ports differ.

## Run

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8091 --reload
```

Then open:

```text
http://127.0.0.1:8091/health
```

The operator dashboard is served at:

```text
http://127.0.0.1:8091/
```

## Connect BI Canvas

Canvas must have a developer key registered by the BI Canvas administrator. Use
the exact callback URL configured in `.env`:

```text
http://127.0.0.1:8091/integrations/canvas/callback
```

Set `CANVAS_CLIENT_ID`, `CANVAS_CLIENT_SECRET`, and a generated
`CANVAS_TOKEN_ENCRYPTION_KEY` in `.env`, restart the agent, then open:

```text
http://127.0.0.1:8091/integrations/canvas/connect
```

After authorization, the agent can read active courses, upcoming calendar
events, and Canvas to-do items. It does not submit assignments, change grades,
send messages, or modify Canvas content.

## Browser Assistant

The `browser_extension/` folder contains a local Chrome extension for pages
where Canvas OAuth is unavailable, including BI student-portal pages. Install it
through Chrome's `chrome://extensions` page using Developer mode and **Load
unpacked**, selecting that folder.

Open a BI Canvas or BI portal page, click the extension, and choose **Send
current page**. Only visible text and page headings are sent to
`http://127.0.0.1:8091`; the extension does not read passwords, cookies, or
submit forms. Imported pages are available to the agent through
`get_browser_context` and `/api/browser/snapshots`.

This is deliberately user-triggered and read-only. It depends on the page being
open and should be treated as a convenience bridge, not a replacement for an
official Canvas API integration.

## Research Backtests

The first research strategy is a transparent long/flat simple-moving-average
crossover. It is intentionally a baseline for validating the research pipeline,
not a claim of profitability. It uses the previous candle to form each signal,
includes configurable fee and slippage assumptions, and returns metrics plus a
trade log without touching the ticket or execution flow.

Run it through the API:

```bash
curl -s http://127.0.0.1:8091/api/research/backtest \
  -H 'Content-Type: application/json' \
  -d '{"epic":"CS.D.EURUSD.TODAY","resolution":"HOUR","max_points":300,"fast_window":10,"slow_window":30}'
```

The model can also call `run_research_backtest`. Every result is marked
`research_only`; it is not an order recommendation and cannot execute a trade.
The next research improvements should be walk-forward testing, more realistic
broker costs, and paper-trading comparison before any strategy is considered for
ticket preparation.

If your shell finds a global `uvicorn`, use the project venv explicitly:

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8091 --reload
```

Or run:

```bash
bash run.sh
```

## Chat

```bash
curl -s http://127.0.0.1:8091/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Check trader health and tell me if the broker bridge is alive."}'
```

The response includes the agent text, session id, and any tools used.

## Direct Tool Calls

```bash
curl -s http://127.0.0.1:8091/tools/run \
  -H 'Content-Type: application/json' \
  -d '{"name":"get_balance","arguments":{}}'
```

## Safety Notes

This is a clean agent, not a full trading risk engine.

Keep `ALLOW_TRADING_WRITES=false` until `capital_trader` has hard server-side risk enforcement and you are intentionally testing live order placement.

The local safety model is:

- Operating mode is explicit: `observe`, `analyze`, `prepare`, `confirm`, `execute`.
- Proposed trades become persistent tickets.
- Stop loss is required by default.
- Oversized tickets are blocked by `MAX_TICKET_SIZE`.
- Too many open broker positions blocks new tickets.
- Every important action writes an audit event to SQLite.
- Broker state is captured before and after execution.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
