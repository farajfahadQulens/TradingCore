"""Consumes price ticks from the price_queue and publishes PriceUpdated events.
"""
import asyncio
from uuid import uuid4
from datetime import datetime, timezone
from app.queue_manager import price_queue
from app.core.events import PriceUpdated
from app.services.event_bus import EventBus
from app.core.logging import get_logger
from app.services.runtime_status import runtime_status

log = get_logger(__name__)


class MarketStreamer:
    def __init__(self):
        self.sequence = 0

    async def run(self):
        log.info("market_streamer_started")
        while True:
            try:
                tick = await price_queue.get()
                await self._process(tick)
            except Exception as e:
                log.error("market_streamer_error", error=str(e))

    async def _process(self, tick: dict):
        destination = tick.get("destination")
        if destination != "quote":
            log.debug("skipping_non_quote_message", destination=destination)
            return
        try:
            payload = tick.get("payload", {})
            event = PriceUpdated.new(
                sequence_id=self.sequence,
                correlation_id=uuid4(),
                epic=payload.get("epic", ""),
                bid=float(payload.get("bid", 0)),
                ask=float(payload.get("ofr", 0)),
                broker_timestamp=datetime.now(timezone.utc),
            )
            await EventBus.publish(event)
            runtime_status.mark_price_tick(event.epic)
            self.sequence += 1
            log.debug("price_event_published", epic=event.epic, bid=event.bid, ask=event.ask)
        except Exception as e:
            log.error("tick_processing_error", error=str(e), tick=tick)
