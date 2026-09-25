"""Threshold-based signal detector — subscribes to PriceUpdated, emits SignalDetected.
"""
from uuid import uuid4
from app.core.events import PriceUpdated, SignalDetected
from app.services.event_bus import EventBus
from app.core.logging import get_logger

log = get_logger(__name__)


class SignalDetector:
    def __init__(self, threshold: float = 0.01):
        self.threshold = threshold
        self._last_price: dict[str, float] = {}  # epic -> last price
        self._last_signal: dict[str, str] = {}   # epic -> last direction (duplicate suppression)
        self.sequence = 0

    async def start(self):
        await EventBus.subscribe(self._on_price_updated)
        log.info("signal_detector_started", threshold=self.threshold)

    async def _on_price_updated(self, event):
        if not isinstance(event, PriceUpdated):
            return
        await self._process(event)

    async def _process(self, event: PriceUpdated):
        epic = event.epic
        mid = (event.bid + event.ask) / 2

        if epic not in self._last_price:
            self._last_price[epic] = mid
            return

        last = self._last_price[epic]
        change = (mid - last) / last
        self._last_price[epic] = mid

        if abs(change) < self.threshold:
            return

        direction = "BUY" if change > 0 else "SELL"

        # Duplicate suppression — don't fire same direction twice in a row
        if self._last_signal.get(epic) == direction:
            return

        self._last_signal[epic] = direction

        signal = SignalDetected.new(
            sequence_id=self.sequence,
            correlation_id=uuid4(),
            epic=epic,
            direction=direction,
            price=mid,
        )
        self.sequence += 1

        await EventBus.publish(signal)
        log.info("signal_detected", epic=epic, direction=direction,
                 price=mid, change=round(change * 100, 4))


signal_detector = SignalDetector()