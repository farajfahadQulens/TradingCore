"""Trading service — bridges signal detection and order submission.
"""
from datetime import datetime, timezone
from uuid import uuid4
from app.core.events import SignalDetected, RiskApproved, RiskRejected
from app.services.event_bus import EventBus
from app.services.order_workflow_service import order_workflow_service
from app.db.repositories.positions import PositionRepo
from app.db.repositories.trades import TradeRepo
from app.db.models.trade_log import TradeLog
from app.db.session import get_session
from app.core.state import trading_state
from app.core.logging import get_logger
import json

log = get_logger(__name__)


class TradingService:
    def __init__(self):
        self.sequence = 0

    async def start(self):
        await EventBus.subscribe(self._on_signal_detected)
        log.info("trading_service_started")

    async def _on_signal_detected(self, event):
        if not isinstance(event, SignalDetected):
            return
        await self._handle_signal(event)

    async def _handle_signal(self, event: SignalDetected):
        if not trading_state.is_trading_allowed:
            log.debug("signal_ignored_trading_disabled", epic=event.epic)
            return

        log.info("signal_received",
                 epic=event.epic,
                 direction=event.direction,
                 price=event.price)

        # Persist signal to trade log for audit trail
        async with get_session() as session:
            entry = TradeLog(
                id=str(uuid4()),
                event_type="SignalDetected",
                payload=json.dumps({
                    "epic": event.epic,
                    "direction": event.direction,
                    "price": event.price,
                    "sequence_id": event.sequence_id,
                }),
                correlation_id=str(event.correlation_id),
            )
            await TradeRepo.append_log(session, entry)

    async def submit(
        self,
        epic: str,
        size: float,
        order_type: str,
        limit_price: float,
        bid: float,
        ask: float,
    ):
        """Called when operator approves a signal for execution."""
        async with get_session() as session:
            open_positions = await PositionRepo.get_open_positions(session)

        try:
            order = await order_workflow_service.submit(
                epic=epic,
                size=size,
                order_type=order_type,
                limit_price=limit_price,
                bid=bid,
                ask=ask,
                tick_timestamp=datetime.now(timezone.utc),
                open_positions_count=len(open_positions),
            )
            log.info("order_submitted_by_trading_service",
                     epic=epic, size=size, order_id=order.id)
            return order

        except PermissionError as e:
            log.warning("order_blocked_by_risk", epic=epic, reason=str(e))
            raise

        except Exception as e:
            log.error("order_submission_error", epic=epic, error=str(e))
            raise


trading_service = TradingService()