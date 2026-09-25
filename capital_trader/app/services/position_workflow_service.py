"""Guarded position-management workflows."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.broker.client import BrokerClient
from app.core.events import PositionClosed
from app.core.state import trading_state
from app.db.repositories.positions import PositionRepo
from app.db.session import get_session
from app.services.event_bus import EventBus
from app.services.trade_log_service import append_trade_log
from app.core.logging import get_logger

log = get_logger(__name__)


def _broker_position_item(broker_positions: list[dict[str, Any]], deal_id: str) -> dict[str, Any] | None:
    for item in broker_positions:
        position = item.get("position", {})
        if position.get("dealId") == deal_id:
            return item
    return None


def _market_quote_from_position(item: dict[str, Any]) -> tuple[float | None, float | None]:
    market = item.get("market", {})
    bid = market.get("bid")
    ask = market.get("offer", market.get("ask"))
    return (float(bid) if bid is not None else None, float(ask) if ask is not None else None)


def _estimated_close_price(direction: str | None, bid: float | None, ask: float | None) -> float | None:
    if direction == "BUY":
        return bid
    if direction == "SELL":
        return ask
    return None


def _broker_position_summary(item: dict[str, Any]) -> dict[str, Any]:
    position = item.get("position", {})
    market = item.get("market", {})
    bid, ask = _market_quote_from_position(item)
    direction = position.get("direction")
    return {
        "deal_id": position.get("dealId"),
        "deal_reference": position.get("dealReference"),
        "epic": market.get("epic"),
        "direction": direction,
        "size": float(position.get("size", 0)),
        "entry_price": float(position["level"]) if position.get("level") is not None else None,
        "upl": float(position["upl"]) if position.get("upl") is not None else None,
        "market_status": market.get("marketStatus"),
        "bid": bid,
        "ask": ask,
        "estimated_close_price": _estimated_close_price(direction, bid, ask),
    }


class PositionWorkflowService:
    def __init__(self) -> None:
        self.sequence = 0

    async def preview_close(self, deal_id: str) -> dict[str, Any]:
        """Preview whether a position close would be allowed right now."""

        async with get_session() as session:
            local_position = await PositionRepo.get_position_by_id(session, deal_id)

        if local_position is None:
            raise ValueError(f"Local position not found: {deal_id}")
        if local_position.status != "OPEN":
            raise ValueError(f"Local position is not open: {deal_id}")

        async with BrokerClient() as client:
            broker_data = await client.get_positions()

        broker_item = _broker_position_item(broker_data.get("positions", []), deal_id)
        if broker_item is None:
            raise ValueError(f"Broker position not found: {deal_id}")

        broker_summary = _broker_position_summary(broker_item)
        local_size = float(local_position.size)
        size_matches = local_size == broker_summary["size"]
        epic_matches = local_position.epic == broker_summary["epic"]
        market_tradeable = broker_summary["market_status"] == "TRADEABLE"

        approved = all([
            trading_state.is_trading_allowed,
            market_tradeable,
            size_matches,
            epic_matches,
        ])
        reasons = []
        if not trading_state.is_trading_allowed:
            reasons.append(f"trading_not_allowed mode={trading_state.mode}")
        if not market_tradeable:
            reasons.append(f"market_not_tradeable status={broker_summary['market_status']}")
        if not size_matches:
            reasons.append(f"size_mismatch local={local_size} broker={broker_summary['size']}")
        if not epic_matches:
            reasons.append(f"epic_mismatch local={local_position.epic} broker={broker_summary['epic']}")

        result = {
            "workflow": "close_position_preview",
            "approved": approved,
            "reason": "; ".join(reasons),
            "local_position": {
                "deal_id": local_position.id,
                "epic": local_position.epic,
                "size": local_size,
                "entry_price": float(local_position.entry_price) if local_position.entry_price is not None else None,
                "status": local_position.status,
                "deal_reference": local_position.deal_reference,
            },
            "broker_position": broker_summary,
            "risk": {
                "trading_mode": trading_state.mode.value,
                "is_trading_allowed": trading_state.is_trading_allowed,
            },
        }
        await append_trade_log(
            "close_preview",
            {
                "deal_id": deal_id,
                "approved": approved,
                "reason": result["reason"],
                "local_position": result["local_position"],
                "broker_position": result["broker_position"],
                "risk": result["risk"],
            },
            correlation_id=deal_id,
        )
        return result

    async def close_position(self, deal_id: str) -> dict[str, Any]:
        """Close an open broker position after local/broker validation."""

        preview = await self.preview_close(deal_id)
        if not preview["approved"]:
            await append_trade_log(
                "close_rejected",
                {
                    "deal_id": deal_id,
                    "reason": preview["reason"],
                    "preview": preview,
                },
                correlation_id=deal_id,
            )
            raise PermissionError(f"Close rejected: {preview['reason']}")

        await append_trade_log(
            "position_close_requested",
            {
                "deal_id": deal_id,
                "preview": preview,
            },
            correlation_id=deal_id,
        )
        async with BrokerClient() as client:
            broker_response = await client.close_position(deal_id)

        close_price = preview["broker_position"]["estimated_close_price"]
        async with get_session() as session:
            updated = await PositionRepo.update_position(
                session,
                deal_id,
                status="CLOSED",
                close_price=close_price,
                closed_at=datetime.now(timezone.utc),
            )

        event = PositionClosed.new(
            sequence_id=self.sequence,
            correlation_id=uuid.uuid4(),
            epic=updated.epic,
            deal_reference=updated.deal_reference or deal_id,
            close_price=close_price or 0.0,
        )
        await EventBus.publish(event)
        self.sequence += 1

        log.info("workflow_position_closed", deal_id=deal_id, epic=updated.epic, close_price=close_price)
        await append_trade_log(
            "position_closed",
            {
                "deal_id": deal_id,
                "epic": updated.epic,
                "close_price": close_price,
                "broker_response": broker_response,
            },
            correlation_id=deal_id,
        )
        return {
            "workflow": "close_position",
            "closed": True,
            "position": {
                "deal_id": updated.id,
                "epic": updated.epic,
                "status": updated.status,
                "close_price": float(updated.close_price) if updated.close_price is not None else None,
                "closed_at": updated.closed_at,
            },
            "broker_response": broker_response,
            "preview": preview,
        }


position_workflow_service = PositionWorkflowService()
