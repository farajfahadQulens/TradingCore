"""Risk manager — gatekeeper for all order submission.
"""
from datetime import datetime, timezone
from app.core.state import trading_state, TradingMode
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class RiskManager:
    def __init__(self):
        self.daily_loss: float = 0.0
        self._seen_client_order_ids: set[str] = set()

    def can_trade(
        self,
        epic: str,
        size: float,
        bid: float,
        ask: float,
        tick_timestamp: datetime,
        client_order_id: str,
        open_positions_count: int,
    ) -> tuple[bool, str]:
        """Returns (approved, reason). reason is empty string if approved."""

        # 1. Trading mode check
        if not trading_state.is_trading_allowed:
            return False, f"trading_not_allowed mode={trading_state.mode}"

        # 2. Position size check
        if size > settings.max_position_size:
            return False, f"size_exceeded size={size} max={settings.max_position_size}"

        # 3. Max open positions check
        if open_positions_count >= settings.max_open_positions:
            return False, f"max_positions_reached count={open_positions_count}"

        # 4. Daily loss check
        if self.daily_loss >= settings.max_daily_loss_pct:
            return False, f"daily_loss_exceeded loss={self.daily_loss}"

        # 5. Spread check
        spread = ask - bid
        max_spread = settings.max_spread.get(epic, 999)
        if spread > max_spread:
            return False, f"spread_too_wide epic={epic} spread={spread} max={max_spread}"

        # 6. Stale tick check
        age_ms = (datetime.now(timezone.utc) - tick_timestamp).total_seconds() * 1000
        if age_ms > settings.stale_tick_threshold_ms:
            return False, f"stale_tick epic={epic} age_ms={age_ms}"

        # 7. Duplicate order check
        if client_order_id in self._seen_client_order_ids:
            return False, f"duplicate_order client_order_id={client_order_id}"

        return True, ""

    def approve(self, client_order_id: str, epic: str, size: float) -> None:
        self._seen_client_order_ids.add(client_order_id)
        log.info("risk_approved", epic=epic, size=size, client_order_id=client_order_id)

    def reject(self, reason: str, epic: str) -> None:
        log.warning("risk_rejected", epic=epic, reason=reason)

    def record_loss(self, amount: float) -> None:
        self.daily_loss += amount
        log.warning("loss_recorded", daily_loss=self.daily_loss, amount=amount)
        if self.daily_loss >= settings.max_daily_loss_pct:
            trading_state.set_degraded(reason=f"daily_loss_limit_reached loss={self.daily_loss}")

    def reset_daily(self) -> None:
        self.daily_loss = 0.0
        self._seen_client_order_ids.clear()
        log.info("risk_daily_reset")


risk_manager = RiskManager()