# Configuration

Copy `.env.example` to `.env`. Values are loaded at startup; restart the agent
after changing them.

## Agent and Model

| Variable | Default | Meaning |
| --- | --- | --- |
| `AGENT_HOST` | `127.0.0.1` | Bind address. |
| `AGENT_PORT` | `8091` | Documented service port. `run.sh` currently uses 8091 directly. |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible model base URL. |
| `OLLAMA_MODEL` | `gpt-oss:120b-cloud` | GPT OSS model name. |

The model endpoint must expose `POST /chat/completions` and return an
OpenAI-compatible `choices[0].message` object.

## Capital Trader

| Variable | Default | Meaning |
| --- | --- | --- |
| `TRADER_BASE_URL` | `http://localhost:8000` | Existing Capital Trader HTTP service. |
| `TRADER_TIMEOUT_SECONDS` | `5` | Individual broker request timeout. |
| `BROKER_SNAPSHOT_TIMEOUT_SECONDS` | `3` | Per-endpoint snapshot limit. |

The clean agent uses these read endpoints:

- `GET /api/health`
- `GET /api/debug/equity`
- `GET /api/v1/positions`
- `GET /api/v1/orders`
- `GET /api/v1/market/prices/{epic}`

The only write endpoint is used by the guarded ticket execution path.

## Trading Guards

| Variable | Default | Meaning |
| --- | --- | --- |
| `ALLOW_TRADING_WRITES` | `false` | Master switch for broker order writes. |
| `ORDER_CONFIRMATION_PHRASE` | `CONFIRM_LIVE_ORDER` | Legacy setting; ticket phrases are ticket-specific. |
| `REQUIRE_STOP_LOSS` | `true` | Blocks tickets without stop loss or stop distance. |
| `MAX_TICKET_SIZE` | `0.5` | Maximum requested size. |
| `MAX_OPEN_POSITIONS` | `5` | Maximum open positions before a new ticket is blocked. |

Keep `ALLOW_TRADING_WRITES=false` during development and research.

## Notifications

| Variable | Default | Meaning |
| --- | --- | --- |
| `NOTIFICATION_WATCHER_ENABLED` | `true` | Starts the background alert evaluator with Clean Agent. |
| `NOTIFICATION_POLL_SECONDS` | `20` | Seconds between alert evaluation passes. |
| `TELEGRAM_BOT_TOKEN` | empty | Bot token from Telegram `@BotFather`. |
| `TELEGRAM_CHAT_ID` | empty | Chat id that should receive TradingCore alerts. |
| `TELEGRAM_TIMEOUT_SECONDS` | `5` | Telegram API request timeout. |

Telegram setup:

1. Create a bot with Telegram `@BotFather`.
2. Send a message to the bot from the target Telegram account/chat.
3. Resolve the chat id, then set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
   in `.env`.
4. Restart Clean Agent and call `POST /api/notifications/test`.

Notifications are informational only. They can create urgency, but they never
create, approve, execute, or close trades.

## Canvas

| Variable | Default | Meaning |
| --- | --- | --- |
| `CANVAS_BASE_URL` | `https://bi.instructure.com` | BI Canvas domain. |
| `CANVAS_CLIENT_ID` | empty | OAuth developer-key client ID from BI. |
| `CANVAS_CLIENT_SECRET` | empty | OAuth developer-key secret from BI. |
| `CANVAS_REDIRECT_URI` | `http://127.0.0.1:8091/integrations/canvas/callback` | Must match Canvas registration. |
| `CANVAS_TOKEN_ENCRYPTION_KEY` | empty | Fernet key generated locally. |
| `CANVAS_TIMEOUT_SECONDS` | `10` | Canvas HTTP timeout. |

Generate the encryption key:

```bash
.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Never commit `.env`, the encryption key, Canvas secrets, or the SQLite database
containing encrypted tokens.

## Local Database

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_PATH` | `data/agent.sqlite3` | SQLite path for state and audit data. |
