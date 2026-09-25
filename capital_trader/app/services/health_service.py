"""Deep health checks for Capital Trader runtime dependencies."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import text

from app.broker.session import session_manager
from app.core.config import settings
from app.core.state import trading_state
from app.db.session import engine
from app.services.runtime_status import runtime_status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _age_seconds(timestamp: datetime | None) -> float | None:
    if timestamp is None:
        return None
    return max(0.0, (_now() - timestamp).total_seconds())


def _component(status: str, **details: Any) -> dict[str, Any]:
    return {"status": status, **details}


class HealthService:
    async def deep_health(self) -> dict[str, Any]:
        checks = {
            "broker_session": self._broker_session_status(),
            "database": await self._database_status(),
            "redis": await self._redis_status(),
            "websocket": self._websocket_status(),
            "reconciliation": self._reconciliation_status(),
            "prices": self._price_status(),
            "trading": self._trading_status(),
        }

        statuses = {name: check["status"] for name, check in checks.items()}
        if any(status == "unhealthy" for status in statuses.values()):
            overall = "unhealthy"
        elif any(status == "degraded" for status in statuses.values()):
            overall = "degraded"
        else:
            overall = "healthy"

        return {
            "status": overall,
            "checked_at": _now(),
            "components": checks,
        }

    def _broker_session_status(self) -> dict[str, Any]:
        expires_at = session_manager.token_expiry
        seconds_to_expiry = None
        if expires_at:
            seconds_to_expiry = (expires_at - _now()).total_seconds()

        token_present = bool(session_manager.cst_token and session_manager.security_token)
        connected = bool(session_manager.connected)
        if not connected or not token_present:
            status = "unhealthy"
        elif seconds_to_expiry is not None and seconds_to_expiry <= 60:
            status = "degraded"
        else:
            status = "healthy"

        return _component(
            status,
            connected=connected,
            token_present=token_present,
            expires_at=expires_at,
            seconds_to_expiry=seconds_to_expiry,
        )

    async def _database_status(self) -> dict[str, Any]:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
            return _component("healthy")
        except Exception as exc:
            return _component("unhealthy", error=str(exc))

    async def _redis_status(self) -> dict[str, Any]:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            pong = await redis.ping()
            return _component(
                "healthy" if pong else "unhealthy",
                ping=bool(pong),
                bridge_subscribed=runtime_status.redis_bridge_subscribed,
                last_publish_at=runtime_status.redis_last_publish_at,
                last_error=runtime_status.redis_last_error,
            )
        except Exception as exc:
            return _component(
                "unhealthy",
                error=str(exc),
                bridge_subscribed=runtime_status.redis_bridge_subscribed,
                last_publish_at=runtime_status.redis_last_publish_at,
                last_error=runtime_status.redis_last_error,
            )
        finally:
            await redis.aclose()

    def _websocket_status(self) -> dict[str, Any]:
        snapshot = runtime_status.snapshot()["websocket"]
        status = "healthy" if snapshot["connected"] else "degraded"
        return _component(status, **snapshot)

    def _reconciliation_status(self) -> dict[str, Any]:
        snapshot = runtime_status.snapshot()["reconciliation"]
        last_completed_at = snapshot["last_completed_at"]
        age = _age_seconds(last_completed_at)

        if snapshot["last_error"]:
            status = "unhealthy"
        elif last_completed_at is None:
            status = "degraded"
        elif age is not None and age > 2 * 300:
            status = "degraded"
        else:
            status = "healthy"

        return _component(status, **snapshot, last_completed_age_seconds=age)

    def _price_status(self) -> dict[str, Any]:
        snapshot = runtime_status.snapshot()["prices"]
        age = _age_seconds(snapshot["last_tick_at"])
        if snapshot["last_tick_at"] is None:
            status = "degraded"
        elif age is not None and age > max(settings.stale_tick_threshold_ms / 1000, 30):
            status = "degraded"
        else:
            status = "healthy"

        return _component(status, **snapshot, last_tick_age_seconds=age)

    def _trading_status(self) -> dict[str, Any]:
        status = "healthy" if trading_state.is_trading_allowed else "degraded"
        return _component(
            status,
            mode=trading_state.mode.value,
            is_trading_allowed=trading_state.is_trading_allowed,
            allow_live_trading=settings.allow_live_trading,
        )


health_service = HealthService()
