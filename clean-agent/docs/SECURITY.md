# Security and Safety Model

## Credentials

- Never put broker, Canvas, or model credentials in source files.
- `.env` is ignored by Git.
- Canvas OAuth tokens are encrypted before SQLite storage.
- The Fernet encryption key is separate from the encrypted token database.
- The browser extension does not read cookies, passwords, or password-field values.

## Browser Data

The extension sends visible text from the current page after an explicit click.
Visible grades, student numbers, addresses, or other private information may be
included in that text. Snapshots are stored locally in SQLite. Delete the
database or add a retention policy before sharing the machine with another
user.

## Trading

Trading writes are disabled by default. The execution path requires all of:

1. `ALLOW_TRADING_WRITES=true`.
2. A ticket in `approved` state.
3. A fresh broker snapshot.
4. Fresh deterministic risk checks passing.
5. Broker submission succeeding.
6. A recorded after-state reconciliation.

The model is not a safety boundary. Python checks and Capital Trader's own
server-side protections must enforce the final decision.

## Research

Backtests are hypothetical. The baseline includes simple fee and slippage
assumptions, but it is not a production simulator and does not prove future
performance. Do not enable live writes based on one report.

## Network Scope

The application is intended for local binding on `127.0.0.1`. Do not expose it
to a LAN or the public internet without authentication, HTTPS, CSRF protection,
rate limiting, and a deliberate credential review.
