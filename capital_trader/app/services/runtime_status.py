"""In-memory runtime status shared by background services and health checks."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RuntimeStatus:
    def __init__(self) -> None:
        self.websocket_connected = False
        self.websocket_last_connected_at: datetime | None = None
        self.websocket_last_disconnected_at: datetime | None = None
        self.websocket_last_error: str | None = None
        self.websocket_subscriptions: list[str] = []

        self.last_price_tick_at: datetime | None = None
        self.last_price_tick_epic: str | None = None

        self.redis_bridge_subscribed = False
        self.redis_last_publish_at: datetime | None = None
        self.redis_last_error: str | None = None

        self.reconciliation_running = False
        self.reconciliation_last_started_at: datetime | None = None
        self.reconciliation_last_completed_at: datetime | None = None
        self.reconciliation_last_error: str | None = None
        self.reconciliation_last_counts: dict[str, int] = {"positions": 0, "orders": 0}
        self.reconciliation_last_summary: dict[str, Any] = {}

    def mark_websocket_connected(self, subscriptions: list[str]) -> None:
        self.websocket_connected = True
        self.websocket_last_connected_at = utc_now()
        self.websocket_last_error = None
        self.websocket_subscriptions = list(subscriptions)

    def mark_websocket_disconnected(self, error: Exception | str | None = None) -> None:
        self.websocket_connected = False
        self.websocket_last_disconnected_at = utc_now()
        self.websocket_last_error = str(error) if error else None

    def mark_price_tick(self, epic: str | None) -> None:
        self.last_price_tick_at = utc_now()
        self.last_price_tick_epic = epic

    def mark_redis_subscribed(self) -> None:
        self.redis_bridge_subscribed = True
        self.redis_last_error = None

    def mark_redis_publish(self) -> None:
        self.redis_last_publish_at = utc_now()
        self.redis_last_error = None

    def mark_redis_error(self, error: Exception | str) -> None:
        self.redis_last_error = str(error)

    def mark_reconciliation_started(self) -> None:
        self.reconciliation_running = True
        self.reconciliation_last_started_at = utc_now()

    def mark_reconciliation_completed(
        self,
        positions: int,
        orders: int,
        summary: dict[str, Any] | None = None,
    ) -> None:
        self.reconciliation_running = True
        self.reconciliation_last_completed_at = utc_now()
        self.reconciliation_last_error = None
        self.reconciliation_last_counts = {"positions": positions, "orders": orders}
        self.reconciliation_last_summary = dict(summary or {})

    def mark_reconciliation_error(self, error: Exception | str) -> None:
        self.reconciliation_running = True
        self.reconciliation_last_error = str(error)

    def snapshot(self) -> dict[str, Any]:
        return {
            "websocket": {
                "connected": self.websocket_connected,
                "last_connected_at": self.websocket_last_connected_at,
                "last_disconnected_at": self.websocket_last_disconnected_at,
                "last_error": self.websocket_last_error,
                "subscriptions": self.websocket_subscriptions,
            },
            "prices": {
                "last_tick_at": self.last_price_tick_at,
                "last_tick_epic": self.last_price_tick_epic,
            },
            "redis_bridge": {
                "subscribed": self.redis_bridge_subscribed,
                "last_publish_at": self.redis_last_publish_at,
                "last_error": self.redis_last_error,
            },
            "reconciliation": {
                "running": self.reconciliation_running,
                "last_started_at": self.reconciliation_last_started_at,
                "last_completed_at": self.reconciliation_last_completed_at,
                "last_error": self.reconciliation_last_error,
                "last_counts": dict(self.reconciliation_last_counts),
                "last_summary": dict(self.reconciliation_last_summary),
            },
        }


runtime_status = RuntimeStatus()
