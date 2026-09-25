"""SQLite persistence for tickets, audit events, and agent mode.

The store is deliberately small and uses only Python's standard library. It is
not meant to be a trading database; it is the agent's local ledger of what it
said, checked, proposed, blocked, and executed.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""

    return datetime.now(UTC).isoformat()


class Store:
    """Tiny SQLite wrapper with explicit methods for each persisted concept."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def connect(self) -> sqlite3.Connection:
        """Open a connection configured for row dictionaries and foreign keys."""

        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init(self) -> None:
        """Create all tables if they do not exist."""

        with self._lock, self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trade_tickets (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    ticket_type TEXT NOT NULL DEFAULT 'open_position',
                    deal_id TEXT,
                    status TEXT NOT NULL,
                    epic TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    size REAL NOT NULL,
                    order_type TEXT NOT NULL,
                    level REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    limit_distance REAL,
                    stop_distance REAL,
                    reason TEXT NOT NULL,
                    invalidated_if TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    risk_status TEXT NOT NULL,
                    risk_errors TEXT NOT NULL,
                    risk_warnings TEXT NOT NULL,
                    confirmation_phrase TEXT NOT NULL,
                    broker_response TEXT,
                    reconciliation_before TEXT,
                    reconciliation_after TEXT
                );

                CREATE TABLE IF NOT EXISTS integration_tokens (
                    provider TEXT PRIMARY KEY,
                    token TEXT NOT NULL,
                    expires_at REAL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS oauth_states (
                    state TEXT PRIMARY KEY,
                    expires_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS browser_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    tags TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS ix_agent_memories_active
                ON agent_memories(active);

                CREATE INDEX IF NOT EXISTS ix_agent_memories_type_scope
                ON agent_memories(memory_type, scope);

                CREATE TABLE IF NOT EXISTS notification_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    rule_type TEXT NOT NULL,
                    epic TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    threshold REAL,
                    channel TEXT NOT NULL,
                    message TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    cooldown_seconds INTEGER NOT NULL DEFAULT 900,
                    state TEXT NOT NULL DEFAULT 'inactive',
                    notify_recovery INTEGER NOT NULL DEFAULT 1,
                    last_triggered_at TEXT,
                    last_checked_at TEXT,
                    last_value REAL,
                    metadata TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS ix_notification_rules_enabled
                ON notification_rules(enabled);

                CREATE TABLE IF NOT EXISTS notification_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    rule_id INTEGER,
                    channel TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    value REAL,
                    delivered INTEGER NOT NULL,
                    error TEXT,
                    metadata TEXT NOT NULL,
                    FOREIGN KEY(rule_id) REFERENCES notification_rules(id)
                );

                CREATE INDEX IF NOT EXISTS ix_notification_events_rule_id
                ON notification_events(rule_id);
                """
            )
            self._ensure_column(conn, "trade_tickets", "ticket_type", "TEXT NOT NULL DEFAULT 'open_position'")
            self._ensure_column(conn, "trade_tickets", "deal_id", "TEXT")
            self._ensure_column(conn, "notification_rules", "state", "TEXT NOT NULL DEFAULT 'inactive'")
            self._ensure_column(conn, "notification_rules", "notify_recovery", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "notification_rules", "last_checked_at", "TEXT")
            conn.execute(
                """
                INSERT OR IGNORE INTO agent_state (key, value, updated_at)
                VALUES ('mode', 'observe', ?)
                """,
                (utc_now(),),
            )

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        """Add a column if an older local SQLite DB does not have it yet."""

        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def get_mode(self) -> str:
        """Return the current operating mode."""

        with self._lock, self.connect() as conn:
            row = conn.execute("SELECT value FROM agent_state WHERE key = 'mode'").fetchone()
            return row["value"] if row else "observe"

    def set_mode(self, mode: str) -> str:
        """Persist the current operating mode."""

        with self._lock, self.connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_state (key, value, updated_at)
                VALUES ('mode', ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (mode, utc_now()),
            )
        self.audit("mode_changed", {"mode": mode})
        return mode

    def audit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Append one audit event."""

        with self._lock, self.connect() as conn:
            conn.execute(
                "INSERT INTO audit_events (created_at, event_type, payload) VALUES (?, ?, ?)",
                (utc_now(), event_type, json.dumps(payload, default=str)),
            )

    def recent_audit(self, limit: int = 25) -> list[dict[str, Any]]:
        """Return recent audit events newest first."""

        with self._lock, self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, event_type, payload
                FROM audit_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload"]),
            }
            for row in rows
        ]

    def create_ticket(self, ticket: dict[str, Any]) -> dict[str, Any]:
        """Persist a new trade ticket."""

        now = utc_now()
        with self._lock, self.connect() as conn:
            conn.execute(
                """
                INSERT INTO trade_tickets (
                    id, created_at, updated_at, ticket_type, deal_id, status, epic, direction, size, order_type,
                    level, stop_loss, take_profit, limit_distance, stop_distance,
                    reason, invalidated_if, confidence, risk_status, risk_errors,
                    risk_warnings, confirmation_phrase, broker_response,
                    reconciliation_before, reconciliation_after
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticket["id"],
                    now,
                    now,
                    ticket.get("ticket_type", "open_position"),
                    ticket.get("deal_id"),
                    ticket["status"],
                    ticket["epic"],
                    ticket["direction"],
                    ticket["size"],
                    ticket["order_type"],
                    ticket.get("level"),
                    ticket.get("stop_loss"),
                    ticket.get("take_profit"),
                    ticket.get("limit_distance"),
                    ticket.get("stop_distance"),
                    ticket["reason"],
                    ticket["invalidated_if"],
                    ticket["confidence"],
                    ticket["risk"]["status"],
                    json.dumps(ticket["risk"]["errors"]),
                    json.dumps(ticket["risk"]["warnings"]),
                    ticket["confirmation_phrase"],
                    None,
                    None,
                    None,
                ),
            )
        self.audit(
            "ticket_created",
            {
                "ticket_id": ticket["id"],
                "ticket_type": ticket.get("ticket_type", "open_position"),
                "deal_id": ticket.get("deal_id"),
                "status": ticket["status"],
                "epic": ticket["epic"],
                "direction": ticket["direction"],
                "size": ticket["size"],
                "risk": ticket["risk"],
            },
        )
        return self.get_ticket(ticket["id"]) or ticket

    def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        """Return a ticket by id."""

        with self._lock, self.connect() as conn:
            row = conn.execute("SELECT * FROM trade_tickets WHERE id = ?", (ticket_id,)).fetchone()
        return self._ticket_from_row(row) if row else None

    def list_tickets(self, limit: int = 25, status: str | None = None) -> list[dict[str, Any]]:
        """List tickets newest first."""

        query = "SELECT * FROM trade_tickets"
        params: tuple[Any, ...]
        if status:
            query += " WHERE status = ?"
            params = (status,)
        else:
            params = ()
        query += " ORDER BY created_at DESC LIMIT ?"
        params = (*params, limit)

        with self._lock, self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._ticket_from_row(row) for row in rows]

    def update_ticket(self, ticket_id: str, **updates: Any) -> dict[str, Any]:
        """Update ticket fields and return the refreshed ticket."""

        if not updates:
            ticket = self.get_ticket(ticket_id)
            if ticket is None:
                raise KeyError(ticket_id)
            return ticket

        columns = []
        values = []
        for key, value in updates.items():
            columns.append(f"{key} = ?")
            if key in {"broker_response", "reconciliation_before", "reconciliation_after"}:
                values.append(json.dumps(value, default=str) if value is not None else None)
            else:
                values.append(value)
        columns.append("updated_at = ?")
        values.append(utc_now())
        values.append(ticket_id)

        with self._lock, self.connect() as conn:
            conn.execute(f"UPDATE trade_tickets SET {', '.join(columns)} WHERE id = ?", tuple(values))
        ticket = self.get_ticket(ticket_id)
        if ticket is None:
            raise KeyError(ticket_id)
        return ticket

    def dashboard(self) -> dict[str, Any]:
        """Return local agent state for the dashboard."""

        return {
            "mode": self.get_mode(),
            "tickets": self.list_tickets(limit=10),
            "audit": self.recent_audit(limit=15),
            "memories": self.list_memories(limit=8),
            "notification_rules": self.list_notification_rules(limit=10),
            "notification_events": self.list_notification_events(limit=10),
        }

    def create_notification_rule(
        self,
        *,
        rule_type: str,
        epic: str,
        condition: str,
        threshold: float | None = None,
        channel: str = "telegram",
        message: str = "",
        enabled: bool = True,
        cooldown_seconds: int = 900,
        notify_recovery: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist one notification rule."""

        now = utc_now()
        with self._lock, self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO notification_rules (
                    created_at, updated_at, rule_type, epic, condition, threshold,
                    channel, message, enabled, cooldown_seconds, notify_recovery, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    now,
                    rule_type,
                    epic.upper(),
                    condition,
                    threshold,
                    channel,
                    message,
                    1 if enabled else 0,
                    int(cooldown_seconds),
                    1 if notify_recovery else 0,
                    json.dumps(metadata or {}, default=str),
                ),
            )
            rule_id = cursor.lastrowid
        self.audit(
            "notification_rule_created",
            {"rule_id": rule_id, "rule_type": rule_type, "epic": epic.upper(), "condition": condition},
        )
        rule = self.get_notification_rule(int(rule_id))
        if rule is None:
            raise KeyError(rule_id)
        return rule

    def get_notification_rule(self, rule_id: int) -> dict[str, Any] | None:
        """Return one notification rule."""

        with self._lock, self.connect() as conn:
            row = conn.execute("SELECT * FROM notification_rules WHERE id = ?", (rule_id,)).fetchone()
        return self._notification_rule_from_row(row) if row else None

    def list_notification_rules(self, limit: int = 25, enabled: bool | None = None) -> list[dict[str, Any]]:
        """List notification rules newest first."""

        query = "SELECT * FROM notification_rules"
        params: list[Any] = []
        if enabled is not None:
            query += " WHERE enabled = ?"
            params.append(1 if enabled else 0)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 100)))
        with self._lock, self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._notification_rule_from_row(row) for row in rows]

    def update_notification_rule(self, rule_id: int, **updates: Any) -> dict[str, Any]:
        """Update one notification rule and return it."""

        if not updates:
            rule = self.get_notification_rule(rule_id)
            if rule is None:
                raise KeyError(rule_id)
            return rule
        columns = []
        values = []
        for key, value in updates.items():
            columns.append(f"{key} = ?")
            if key == "metadata":
                values.append(json.dumps(value or {}, default=str))
            elif key in {"enabled", "notify_recovery"}:
                values.append(1 if value else 0)
            else:
                values.append(value)
        columns.append("updated_at = ?")
        values.append(utc_now())
        values.append(rule_id)
        with self._lock, self.connect() as conn:
            conn.execute(f"UPDATE notification_rules SET {', '.join(columns)} WHERE id = ?", tuple(values))
        rule = self.get_notification_rule(rule_id)
        if rule is None:
            raise KeyError(rule_id)
        return rule

    def record_notification_event(
        self,
        *,
        rule_id: int | None,
        channel: str,
        title: str,
        message: str,
        value: float | None = None,
        delivered: bool = False,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist one attempted or delivered notification."""

        now = utc_now()
        with self._lock, self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO notification_events (
                    created_at, rule_id, channel, title, message, value,
                    delivered, error, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    rule_id,
                    channel,
                    title,
                    message,
                    value,
                    1 if delivered else 0,
                    error,
                    json.dumps(metadata or {}, default=str),
                ),
            )
            event_id = cursor.lastrowid
        if rule_id is not None:
            self.update_notification_rule(rule_id, last_triggered_at=now, last_value=value)
        return {
            "id": event_id,
            "created_at": now,
            "rule_id": rule_id,
            "channel": channel,
            "title": title,
            "message": message,
            "value": value,
            "delivered": delivered,
            "error": error,
            "metadata": metadata or {},
        }

    def list_notification_events(self, limit: int = 25, rule_id: int | None = None) -> list[dict[str, Any]]:
        """List recent notification events newest first."""

        query = "SELECT * FROM notification_events"
        params: list[Any] = []
        if rule_id is not None:
            query += " WHERE rule_id = ?"
            params.append(rule_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 100)))
        with self._lock, self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._notification_event_from_row(row) for row in rows]

    def action_audit(self, limit: int = 50, ticket_id: str | None = None) -> list[dict[str, Any]]:
        """Return a unified action timeline from audit events and ticket state."""

        normalized_limit = max(1, min(int(limit), 200))
        events = self.recent_audit(limit=normalized_limit * 2)
        tickets = self.list_tickets(limit=normalized_limit * 2)
        actions: list[dict[str, Any]] = []

        for event in events:
            payload = event["payload"]
            event_ticket_id = payload.get("ticket_id") if isinstance(payload, dict) else None
            if ticket_id and event_ticket_id != ticket_id:
                continue
            actions.append(
                {
                    "id": f"audit-{event['id']}",
                    "created_at": event["created_at"],
                    "source": "audit",
                    "action": event["event_type"],
                    "ticket_id": event_ticket_id,
                    "ticket_type": payload.get("ticket_type") if isinstance(payload, dict) else None,
                    "status": payload.get("status") if isinstance(payload, dict) else None,
                    "summary": self._audit_summary(event["event_type"], payload),
                    "payload": payload,
                }
            )

        for ticket in tickets:
            if ticket_id and ticket["id"] != ticket_id:
                continue
            actions.append(
                {
                    "id": f"ticket-{ticket['id']}",
                    "created_at": ticket["updated_at"],
                    "source": "ticket",
                    "action": "ticket_current_state",
                    "ticket_id": ticket["id"],
                    "ticket_type": ticket["ticket_type"],
                    "status": ticket["status"],
                    "summary": self._ticket_summary(ticket),
                    "payload": {
                        "ticket": ticket,
                    },
                }
            )

        actions.sort(key=lambda item: item["created_at"], reverse=True)
        return actions[:normalized_limit]

    def _audit_summary(self, event_type: str, payload: dict[str, Any]) -> str:
        """Build a compact human-readable audit summary."""

        if not isinstance(payload, dict):
            return event_type
        ticket_id = payload.get("ticket_id")
        reason = payload.get("reason")
        error = payload.get("error")
        if reason:
            return f"{event_type} for {ticket_id}: {reason}" if ticket_id else f"{event_type}: {reason}"
        if error:
            return f"{event_type} for {ticket_id}: {error}" if ticket_id else f"{event_type}: {error}"
        if ticket_id:
            return f"{event_type} for {ticket_id}"
        return event_type

    def _ticket_summary(self, ticket: dict[str, Any]) -> str:
        """Build a compact summary of the current ticket state."""

        ticket_type = ticket.get("ticket_type", "open_position")
        if ticket_type == "close_position":
            return (
                f"{ticket['status']} close ticket for {ticket['epic']} "
                f"deal {ticket.get('deal_id')}"
            )
        return (
            f"{ticket['status']} {ticket['direction']} {ticket['size']} "
            f"{ticket['epic']} ticket"
        )

    def create_memory(
        self,
        *,
        memory_type: str,
        scope: str,
        content: str,
        source: str = "user",
        confidence: float = 1.0,
        tags: list[str] | None = None,
        active: bool = True,
    ) -> dict[str, Any]:
        """Persist one durable agent memory."""

        now = utc_now()
        normalized_tags = [str(tag).strip().lower() for tag in tags or [] if str(tag).strip()]
        with self._lock, self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO agent_memories (
                    created_at, updated_at, memory_type, scope, content, source,
                    confidence, tags, active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    now,
                    memory_type,
                    scope,
                    content,
                    source,
                    float(confidence),
                    json.dumps(normalized_tags),
                    1 if active else 0,
                ),
            )
            memory_id = cursor.lastrowid
        self.audit("memory_created", {"memory_id": memory_id, "memory_type": memory_type, "scope": scope})
        return self.get_memory(int(memory_id)) or {
            "id": memory_id,
            "created_at": now,
            "updated_at": now,
            "memory_type": memory_type,
            "scope": scope,
            "content": content,
            "source": source,
            "confidence": float(confidence),
            "tags": normalized_tags,
            "active": active,
        }

    def seed_memory_once(
        self,
        *,
        memory_type: str,
        scope: str,
        content: str,
        source: str,
        confidence: float = 1.0,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a default memory only if the same active content is absent."""

        with self._lock, self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM agent_memories
                WHERE active = 1
                  AND memory_type = ?
                  AND scope = ?
                  AND content = ?
                LIMIT 1
                """,
                (memory_type, scope, content),
            ).fetchone()
        if row:
            return self._memory_from_row(row)
        return self.create_memory(
            memory_type=memory_type,
            scope=scope,
            content=content,
            source=source,
            confidence=confidence,
            tags=tags,
        )

    def get_memory(self, memory_id: int) -> dict[str, Any] | None:
        """Return one memory by id."""

        with self._lock, self.connect() as conn:
            row = conn.execute("SELECT * FROM agent_memories WHERE id = ?", (memory_id,)).fetchone()
        return self._memory_from_row(row) if row else None

    def list_memories(
        self,
        *,
        limit: int = 25,
        memory_type: str | None = None,
        scope: str | None = None,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """List memories newest first, optionally filtered."""

        query = "SELECT * FROM agent_memories"
        clauses = []
        params: list[Any] = []
        if active_only:
            clauses.append("active = 1")
        if memory_type:
            clauses.append("memory_type = ?")
            params.append(memory_type)
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 100)))

        with self._lock, self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def search_memories(
        self,
        query_text: str,
        *,
        limit: int = 10,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Search active memory content, type, scope, source, and tags."""

        pattern = f"%{query_text.strip()}%"
        clauses = [
            """
            (
                content LIKE ?
                OR memory_type LIKE ?
                OR scope LIKE ?
                OR source LIKE ?
                OR tags LIKE ?
            )
            """
        ]
        params: list[Any] = [pattern, pattern, pattern, pattern, pattern]
        if active_only:
            clauses.append("active = 1")
        sql = f"""
            SELECT *
            FROM agent_memories
            WHERE {' AND '.join(clauses)}
            ORDER BY id DESC
            LIMIT ?
        """
        params.append(max(1, min(int(limit), 50)))

        with self._lock, self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def deactivate_memory(self, memory_id: int) -> dict[str, Any] | None:
        """Mark a memory inactive without deleting history."""

        with self._lock, self.connect() as conn:
            conn.execute(
                "UPDATE agent_memories SET active = 0, updated_at = ? WHERE id = ?",
                (utc_now(), memory_id),
            )
        memory = self.get_memory(memory_id)
        if memory:
            self.audit("memory_deactivated", {"memory_id": memory_id})
        return memory

    def save_integration_token(self, provider: str, token: str, expires_at: float | None) -> None:
        """Store one encrypted third-party token."""

        with self._lock, self.connect() as conn:
            conn.execute(
                """
                INSERT INTO integration_tokens (provider, token, expires_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    token = excluded.token,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (provider, token, expires_at, utc_now()),
            )

    def get_integration_token(self, provider: str) -> dict[str, Any] | None:
        """Return one encrypted token record."""

        with self._lock, self.connect() as conn:
            row = conn.execute(
                "SELECT token, expires_at, updated_at FROM integration_tokens WHERE provider = ?",
                (provider,),
            ).fetchone()
        return dict(row) if row else None

    def delete_integration_token(self, provider: str) -> None:
        """Remove one third-party connection."""

        with self._lock, self.connect() as conn:
            conn.execute("DELETE FROM integration_tokens WHERE provider = ?", (provider,))

    def save_oauth_state(self, state: str, expires_at: float) -> None:
        """Store a short-lived OAuth CSRF state value."""

        with self._lock, self.connect() as conn:
            conn.execute("DELETE FROM oauth_states WHERE expires_at < ?", (datetime.now(UTC).timestamp(),))
            conn.execute("INSERT INTO oauth_states (state, expires_at) VALUES (?, ?)", (state, expires_at))

    def consume_oauth_state(self, state: str) -> bool:
        """Consume a valid one-time OAuth state value."""

        with self._lock, self.connect() as conn:
            row = conn.execute(
                "SELECT expires_at FROM oauth_states WHERE state = ?",
                (state,),
            ).fetchone()
            conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        return bool(row and row["expires_at"] >= datetime.now(UTC).timestamp())

    def save_browser_snapshot(
        self,
        *,
        source: str,
        url: str,
        title: str,
        content: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist one user-selected page snapshot from the local extension."""

        created_at = utc_now()
        with self._lock, self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO browser_snapshots (created_at, source, url, title, content, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (created_at, source, url, title, content, json.dumps(metadata, default=str)),
            )
            snapshot_id = cursor.lastrowid
        return {
            "id": snapshot_id,
            "created_at": created_at,
            "source": source,
            "url": url,
            "title": title,
            "content": content,
            "metadata": metadata,
        }

    def recent_browser_snapshots(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return recent browser snapshots newest first."""

        with self._lock, self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, source, url, title, content, metadata
                FROM browser_snapshots
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "source": row["source"],
                "url": row["url"],
                "title": row["title"],
                "content": row["content"],
                "metadata": json.loads(row["metadata"]),
            }
            for row in rows
        ]

    def _ticket_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert one SQLite row into API-shaped ticket JSON."""

        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "ticket_type": row["ticket_type"],
            "deal_id": row["deal_id"],
            "status": row["status"],
            "epic": row["epic"],
            "direction": row["direction"],
            "size": row["size"],
            "order_type": row["order_type"],
            "level": row["level"],
            "stop_loss": row["stop_loss"],
            "take_profit": row["take_profit"],
            "limit_distance": row["limit_distance"],
            "stop_distance": row["stop_distance"],
            "reason": row["reason"],
            "invalidated_if": row["invalidated_if"],
            "confidence": row["confidence"],
            "risk": {
                "status": row["risk_status"],
                "errors": json.loads(row["risk_errors"]),
                "warnings": json.loads(row["risk_warnings"]),
            },
            "confirmation_phrase": row["confirmation_phrase"],
            "broker_response": json.loads(row["broker_response"]) if row["broker_response"] else None,
            "reconciliation_before": json.loads(row["reconciliation_before"]) if row["reconciliation_before"] else None,
            "reconciliation_after": json.loads(row["reconciliation_after"]) if row["reconciliation_after"] else None,
        }

    def _memory_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert one SQLite row into API-shaped memory JSON."""

        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "memory_type": row["memory_type"],
            "scope": row["scope"],
            "content": row["content"],
            "source": row["source"],
            "confidence": row["confidence"],
            "tags": json.loads(row["tags"]),
            "active": bool(row["active"]),
        }

    def _notification_rule_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert one SQLite row into API-shaped notification rule JSON."""

        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "rule_type": row["rule_type"],
            "epic": row["epic"],
            "condition": row["condition"],
            "threshold": row["threshold"],
            "channel": row["channel"],
            "message": row["message"],
            "enabled": bool(row["enabled"]),
            "cooldown_seconds": row["cooldown_seconds"],
            "state": row["state"],
            "notify_recovery": bool(row["notify_recovery"]),
            "last_triggered_at": row["last_triggered_at"],
            "last_checked_at": row["last_checked_at"],
            "last_value": row["last_value"],
            "metadata": json.loads(row["metadata"]),
        }

    def _notification_event_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert one SQLite row into API-shaped notification event JSON."""

        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "rule_id": row["rule_id"],
            "channel": row["channel"],
            "title": row["title"],
            "message": row["message"],
            "value": row["value"],
            "delivered": bool(row["delivered"]),
            "error": row["error"],
            "metadata": json.loads(row["metadata"]),
        }


store = Store(settings.database_path)
