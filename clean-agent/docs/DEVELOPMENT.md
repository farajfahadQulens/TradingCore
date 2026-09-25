# Development Guide

## Local Workflow

```bash
cd /home/frj/TradingCore/clean-agent
.venv/bin/python -m compileall -q app tests
.venv/bin/python -m pytest -q
```

Keep changes scoped to Clean Agent. Do not edit `/home/frj/TradingCore/capital_trader`.

## Adding a Tool

1. Implement an async function in `app/tools.py`.
2. Add it to `TOOL_FUNCTIONS`.
3. Add its OpenAI-compatible schema to `TOOL_DEFINITIONS`.
4. Add error handling that returns useful data instead of crashing chat.
5. Add a focused test.
6. Update `docs/API.md` and this guide if the behavior is user-facing.

## Adding a Route

1. Add a typed request model when a body is required.
2. Validate external input at the boundary.
3. Return structured JSON errors through `HTTPException`.
4. Keep writes auditable.
5. Document the route in `docs/API.md`.

## Adding Research

Research code must:

- be read-only;
- document assumptions;
- avoid look-ahead bias;
- include costs where possible;
- return a `research_only` marker;
- have deterministic tests;
- remain separate from ticket execution.

## Data and Migrations

SQLite tables are created idempotently in `Store.init()`. Add new tables or
columns with backward-compatible `CREATE TABLE IF NOT EXISTS` or an explicit
migration plan. Never silently delete user tickets, audit events, tokens, or
browser snapshots.

## Testing Boundaries

Tests should cover:

- direct order blocking;
- risk rejection and approval;
- malformed external data;
- research calculations;
- domain and input validation;
- structured failure behavior.

Live broker writes and real Canvas authorization are not test fixtures.
