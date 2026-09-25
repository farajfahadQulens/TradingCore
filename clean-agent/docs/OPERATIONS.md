# Operations Runbook

## Start

```bash
cd /home/frj/TradingCore/clean-agent
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8091 --reload
```

Use `bash run.sh` for the same project-local command.

Open `http://127.0.0.1:8091/` for the dashboard and
`http://127.0.0.1:8091/health` for a simple health check.

The dashboard is the trading workspace. It shows account equity, available
funds, open P/L, broker positions, guarded tickets, Clean Agent action audit,
Capital Trader trade logs, and deep component health from one `/api/dashboard`
payload. If Capital Trader is degraded or unreachable, the affected panels
should show data/errors without freezing the page.

## Stop

Press `Ctrl+C` in the terminal running Uvicorn. The reload process should also
terminate. Do not kill Capital Trader as part of stopping Clean Agent.

## First Checks

```bash
.venv/bin/python -m compileall -q app tests
.venv/bin/python -m pytest -q
curl -s http://127.0.0.1:8091/health
```

## Chat Failure Diagnosis

The browser should display the server's structured error. Check the Uvicorn
terminal and verify:

1. `OLLAMA_BASE_URL` is reachable.
2. `OLLAMA_MODEL` exists at the configured provider.
3. The provider implements `/chat/completions`.
4. The response contains `choices[0].message`.
5. The model is not returning malformed tool-call arguments.

The API returns `502` for model transport or response-contract failures.

## Broker Failure Diagnosis

The dashboard should show endpoint-specific broker errors rather than hanging.
Check:

1. Capital Trader is running on `TRADER_BASE_URL`.
2. Its health endpoint responds.
3. The requested epic and resolution are supported.
4. Capital Trader's own credentials/session are valid.

The clean agent does not repair or restart Capital Trader.

## Telegram Notifications

Create the bot in Telegram with `@BotFather`, set `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID` in `.env`, then restart Clean Agent.

Test delivery:

```bash
curl -s -X POST http://127.0.0.1:8091/api/notifications/test \
  -H 'Content-Type: application/json' \
  -d '{"message":"TradingCore Telegram test"}'
```

Create a price alert:

```bash
curl -s -X POST http://127.0.0.1:8091/api/notifications/rules \
  -H 'Content-Type: application/json' \
  -d '{"rule_type":"price","epic":"GOLD","condition":"below","threshold":4375}'
```

Create a market-open alert:

```bash
curl -s -X POST http://127.0.0.1:8091/api/notifications/rules \
  -H 'Content-Type: application/json' \
  -d '{"rule_type":"market_open","epic":"GOLD"}'
```

Create an open P/L alert:

```bash
curl -s -X POST http://127.0.0.1:8091/api/notifications/rules \
  -H 'Content-Type: application/json' \
  -d '{"rule_type":"position_pl","epic":"GOLD","condition":"above","threshold":500}'
```

Create a health-degraded alert:

```bash
curl -s -X POST http://127.0.0.1:8091/api/notifications/rules \
  -H 'Content-Type: application/json' \
  -d '{"rule_type":"health","epic":"CAPITAL_TRADER"}'
```

Create current-position presets:

```bash
curl -s -X POST http://127.0.0.1:8091/api/notifications/presets/position \
  -H 'Content-Type: application/json' \
  -d '{"epic":"GOLD","delta":50,"cooldown_seconds":900}'
```

This creates or reuses a market-open alert and adds P/L alerts above and below
the current open P/L by the requested delta.

The watcher evaluates enabled rules in the background. Manual evaluation is
available with `POST /api/notifications/evaluate`. Alert attempts are stored in
SQLite and shown on the dashboard.

Alerts are stateful. The normal flow is:

- `inactive` - condition is not matching.
- `active` - condition matched and an alert was sent.
- `recovered` - condition cleared and a recovery alert was sent.

Use the dashboard Telegram panel to create rules, evaluate them immediately, or
disable noisy rules.

## Canvas Connection

If Canvas says `not configured`, set the three local values in `.env` and
restart. If it says `ready` but authorization fails, verify that the callback
URL exactly matches the developer-key registration. If BI has not issued a
developer key, use the browser extension instead.

## Browser Extension

After changing extension files, open `chrome://extensions` and click Reload on
the unpacked extension. The agent must be running on port 8091. The extension
only accepts pages on BI domains and only imports after the button is clicked.

## Database Inspection

The SQLite database is local application state. Back it up before manual
inspection or migration:

```bash
cp data/agent.sqlite3 data/agent.sqlite3.backup
```

Do not paste the database into chat or commit it to source control.
