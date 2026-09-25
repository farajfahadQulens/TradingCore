"""Persistent trade/action logging helpers."""
from __future__ import annotations

import uuid
from typing import Any

from app.db.models.trade_log import TradeLog
from app.db.repositories.trades import TradeRepo
from app.db.session import get_session


async def append_trade_log(
    event_type: str,
    payload: dict[str, Any],
    *,
    correlation_id: str | None = None,
) -> TradeLog:
    """Append one trade log row and return it."""

    log = TradeLog(
        id=str(uuid.uuid4()),
        event_type=event_type,
        payload=payload,
        correlation_id=correlation_id or str(uuid.uuid4()),
    )
    async with get_session() as session:
        return await TradeRepo.append_log(session, log)


def trade_log_to_dict(log: TradeLog) -> dict[str, Any]:
    """Serialize a TradeLog model for APIs."""

    return {
        "id": log.id,
        "event_type": log.event_type,
        "payload": log.payload,
        "correlation_id": log.correlation_id,
        "created_at": log.created_at,
    }
