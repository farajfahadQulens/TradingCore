"""Order state machine and submission workflow.
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from app.broker.client import BrokerClient
from app.db.models.order import Order
from app.db.repositories.orders import OrderRepo
from app.db.repositories.positions import PositionRepo
from app.risk.manager import risk_manager
from app.core.config import settings
from app.core.events import OrderSubmitted, OrderRejected
from app.core.state import trading_state
from app.services.event_bus import EventBus
from app.services.trade_log_service import append_trade_log
from app.db.session import get_session
from app.core.logging import get_logger

log = get_logger(__name__)

VALID_TRANSITIONS = {
    "PENDING": ["SUBMITTED", "FILLED", "PARTIALLY_FILLED", "CANCELLED", "REJECTED"],
    "SUBMITTED": ["FILLED", "PARTIALLY_FILLED", "CANCELLED", "REJECTED"],
    "PARTIALLY_FILLED": ["FILLED", "CANCELLED"],
    "FILLED": ["CLOSED"],
}


def _market_quote(market: dict[str, Any]) -> tuple[float, float]:
    """Extract bid/ask from Capital.com market metadata."""

    candidates = [
        market,
        market.get("snapshot") if isinstance(market.get("snapshot"), dict) else {},
        market.get("market") if isinstance(market.get("market"), dict) else {},
    ]
    for candidate in candidates:
        bid = candidate.get("bid")
        ask = candidate.get("offer", candidate.get("ask"))
        if bid is not None and ask is not None:
            return float(bid), float(ask)
    raise ValueError("market quote missing bid/offer")


def _broker_reference(response: dict[str, Any]) -> str | None:
    """Extract the broker reference returned by Capital.com order placement."""

    return response.get("dealReference") or response.get("dealId")


class OrderWorkflowService:
    def __init__(self):
        self.sequence = 0

    async def submit(
        self,
        epic: str,
        size: float,
        order_type: str,
        limit_price: float,
        bid: float,
        ask: float,
        tick_timestamp: datetime,
        open_positions_count: int,
    ) -> Order:
        client_order_id = str(uuid.uuid4())
        correlation_id = uuid.uuid4()

        # 1. Risk check
        approved, reason = risk_manager.can_trade(
            epic=epic,
            size=size,
            bid=bid,
            ask=ask,
            tick_timestamp=tick_timestamp,
            client_order_id=client_order_id,
            open_positions_count=open_positions_count,
        )

        if not approved:
            risk_manager.reject(reason=reason, epic=epic)
            await append_trade_log(
                "order_workflow_rejected",
                {
                    "epic": epic,
                    "size": size,
                    "order_type": order_type,
                    "reason": reason,
                    "client_order_id": client_order_id,
                    "bid": bid,
                    "ask": ask,
                    "open_positions_count": open_positions_count,
                },
                correlation_id=str(correlation_id),
            )
            ev = OrderRejected.new(
                sequence_id=self.sequence,
                correlation_id=correlation_id,
                epic=epic,
                client_order_id=client_order_id,
                reason=reason,
            )
            await EventBus.publish(ev)
            self.sequence += 1
            raise PermissionError(f"Risk rejected: {reason}")

        # 2. Risk approved
        risk_manager.approve(
            client_order_id=client_order_id,
            epic=epic,
            size=size,
        )

        # 3. Persist order
        order = Order(
            id=str(uuid.uuid4()),
            epic=epic,
            order_type=order_type,
            state="PENDING",
            size=size,
            limit_price=limit_price,
            client_order_id=client_order_id,
        )

        async with get_session() as session:
            saved = await OrderRepo.create(session, order)
        await append_trade_log(
            "order_workflow_submitted",
            {
                "order_id": saved.id,
                "epic": epic,
                "size": size,
                "order_type": order_type,
                "client_order_id": client_order_id,
                "bid": bid,
                "ask": ask,
                "open_positions_count": open_positions_count,
            },
            correlation_id=str(correlation_id),
        )

        # 4. Emit event
        ev = OrderSubmitted.new(
            sequence_id=self.sequence,
            correlation_id=correlation_id,
            epic=epic,
            client_order_id=client_order_id,
            size=size,
        )
        await EventBus.publish(ev)
        self.sequence += 1

        log.info("order_submitted", epic=epic, size=size, client_order_id=client_order_id)
        return saved

    async def submit_and_place(
        self,
        *,
        epic: str,
        direction: str,
        size: float,
        order_type: str,
        level: float | None = None,
        limit_distance: float | None = None,
        stop_distance: float | None = None,
    ) -> dict[str, Any]:
        """Run risk workflow, persist the order, then place it with the broker."""

        async with BrokerClient() as client:
            market = await client.get_market(epic)
            bid, ask = _market_quote(market)

        async with get_session() as session:
            open_positions = await PositionRepo.get_open_positions(session)

        order = await self.submit(
            epic=epic,
            size=size,
            order_type=order_type,
            limit_price=level,
            bid=bid,
            ask=ask,
            tick_timestamp=datetime.now(timezone.utc),
            open_positions_count=len(open_positions),
        )

        try:
            async with BrokerClient() as client:
                broker_response = await client.place_order(
                    epic=epic,
                    direction=direction,
                    size=size,
                    order_type=order_type,
                    level=level,
                    limit_distance=limit_distance,
                    stop_distance=stop_distance,
                )
        except Exception:
            async with get_session() as session:
                await OrderRepo.update_fields(session, order.id, state="REJECTED")
            await append_trade_log(
                "broker_order_failed",
                {
                    "order_id": order.id,
                    "epic": epic,
                    "direction": direction,
                    "size": size,
                    "order_type": order_type,
                },
                correlation_id=order.client_order_id,
            )
            log.exception("workflow_broker_place_failed", order_id=order.id, epic=epic)
            raise

        broker_order_id = _broker_reference(broker_response)
        async with get_session() as session:
            updated = await OrderRepo.update_fields(
                session,
                order.id,
                broker_order_id=broker_order_id,
                state="SUBMITTED",
            )

        log.info(
            "workflow_order_placed",
            epic=epic,
            direction=direction,
            size=size,
            order_id=updated.id,
            broker_order_id=broker_order_id,
        )
        await append_trade_log(
            "broker_order_placed",
            {
                "order_id": updated.id,
                "epic": epic,
                "direction": direction,
                "size": size,
                "order_type": order_type,
                "broker_order_id": broker_order_id,
                "client_order_id": updated.client_order_id,
                "broker_response": broker_response,
            },
            correlation_id=updated.client_order_id,
        )
        return {
            "workflow": "order_workflow_service",
            "order": {
                "id": updated.id,
                "epic": updated.epic,
                "order_type": updated.order_type,
                "state": updated.state,
                "size": float(updated.size),
                "limit_price": float(updated.limit_price) if updated.limit_price is not None else None,
                "broker_order_id": updated.broker_order_id,
                "client_order_id": updated.client_order_id,
            },
            "broker_response": broker_response,
            "risk_context": {
                "bid": bid,
                "ask": ask,
                "open_positions_count": len(open_positions),
            },
        }

    async def preview_risk(
        self,
        *,
        epic: str,
        direction: str,
        size: float,
        order_type: str,
    ) -> dict[str, Any]:
        """Run the same risk gate as order submission without creating an order."""

        async with BrokerClient() as client:
            market = await client.get_market(epic)
            bid, ask = _market_quote(market)

        async with get_session() as session:
            open_positions = await PositionRepo.get_open_positions(session)

        spread = ask - bid
        max_spread = settings.max_spread.get(epic, 999)
        tick_timestamp = datetime.now(timezone.utc)
        preview_client_order_id = f"preview:{uuid.uuid4()}"

        approved, reason = risk_manager.can_trade(
            epic=epic,
            size=size,
            bid=bid,
            ask=ask,
            tick_timestamp=tick_timestamp,
            client_order_id=preview_client_order_id,
            open_positions_count=len(open_positions),
        )
        await append_trade_log(
            "risk_preview",
            {
                "approved": approved,
                "reason": reason,
                "request": {
                    "epic": epic,
                    "direction": direction,
                    "size": size,
                    "order_type": order_type,
                },
                "market": {
                    "bid": bid,
                    "ask": ask,
                    "spread": spread,
                    "max_spread": max_spread,
                    "tick_timestamp": tick_timestamp.isoformat(),
                },
                "risk": {
                    "trading_mode": trading_state.mode.value,
                    "is_trading_allowed": trading_state.is_trading_allowed,
                    "open_positions_count": len(open_positions),
                    "max_open_positions": settings.max_open_positions,
                    "max_position_size": settings.max_position_size,
                    "daily_loss": risk_manager.daily_loss,
                    "max_daily_loss_pct": settings.max_daily_loss_pct,
                    "stale_tick_threshold_ms": settings.stale_tick_threshold_ms,
                },
            },
            correlation_id=preview_client_order_id,
        )

        return {
            "workflow": "risk_preview",
            "approved": approved,
            "reason": reason,
            "request": {
                "epic": epic,
                "direction": direction,
                "size": size,
                "order_type": order_type,
            },
            "market": {
                "bid": bid,
                "ask": ask,
                "spread": spread,
                "max_spread": max_spread,
                "tick_timestamp": tick_timestamp,
            },
            "risk": {
                "trading_mode": trading_state.mode.value,
                "is_trading_allowed": trading_state.is_trading_allowed,
                "open_positions_count": len(open_positions),
                "max_open_positions": settings.max_open_positions,
                "max_position_size": settings.max_position_size,
                "daily_loss": risk_manager.daily_loss,
                "max_daily_loss_pct": settings.max_daily_loss_pct,
                "stale_tick_threshold_ms": settings.stale_tick_threshold_ms,
            },
        }

    async def transition(self, session, order_id: str, new_state: str) -> Order:
        order = await OrderRepo.get_by_id(session, order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        allowed = VALID_TRANSITIONS.get(order.state, [])
        if new_state not in allowed:
            raise ValueError(f"Invalid transition {order.state} → {new_state}")

        updated = await OrderRepo.update_state(session, order_id, new_state)
        log.info("order_transition", order_id=order_id, from_state=order.state, to_state=new_state)
        return updated


order_workflow_service = OrderWorkflowService()
