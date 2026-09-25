"""Candle aggregation service — builds OHLCV candles from price ticks.
"""
import asyncio
from datetime import datetime, timezone
from uuid import uuid4
from app.core.events import PriceUpdated, CandleClosed
from app.services.event_bus import EventBus
from app.db.models.candle import Candle
from app.db.repositories.candles import CandleRepo
from app.db.session import get_session
from app.core.logging import get_logger

log = get_logger(__name__)

TIMEFRAME_SECONDS = {
    "MINUTE":    60,
    "MINUTE_5":  300,
    "MINUTE_15": 900,
    "MINUTE_30": 1800,
    "HOUR":      3600,
    "HOUR_4":    14400,
    "DAY":       86400,
}

DEFAULT_TIMEFRAMES = ["MINUTE", "MINUTE_5", "HOUR"]


class CandleAggregator:
    """Aggregates ticks into OHLC candles for one epic and one timeframe."""

    def __init__(self, epic: str, timeframe: str):
        self.epic = epic
        self.timeframe = timeframe
        self.interval = TIMEFRAME_SECONDS[timeframe]
        self._candle: dict | None = None

    def _bucket(self, ts: datetime) -> datetime:
        """Round timestamp down to the nearest candle boundary."""
        epoch = int(ts.timestamp())
        floored = epoch - (epoch % self.interval)
        return datetime.fromtimestamp(floored, tz=timezone.utc)

    def on_tick(self, event: PriceUpdated) -> Candle | None:
        """Feed a price tick. Returns a closed Candle if the bucket rolled over."""
        mid = (event.bid + event.ask) / 2
        bucket = self._bucket(event.broker_timestamp)
        closed = None

        if self._candle is None:
            self._candle = self._new_candle(bucket, mid, event)
        elif bucket > self._candle["candle_time"]:
            closed = self._finalise()
            self._candle = self._new_candle(bucket, mid, event)
        else:
            c = self._candle
            c["high"] = max(c["high"], mid)
            c["low"] = min(c["low"], mid)
            c["close"] = mid
            c["bid_close"] = event.bid
            c["ask_close"] = event.ask

        return closed

    def _new_candle(self, bucket: datetime, mid: float, event: PriceUpdated) -> dict:
        return {
            "candle_time": bucket,
            "open": mid, "high": mid, "low": mid, "close": mid,
            "bid_close": event.bid, "ask_close": event.ask,
        }

    def _finalise(self) -> Candle:
        c = self._candle
        return Candle(
            id=str(uuid4()),
            epic=self.epic,
            timeframe=self.timeframe,
            open=c["open"], high=c["high"],
            low=c["low"],  close=c["close"],
            bid_close=c["bid_close"],
            ask_close=c["ask_close"],
            candle_time=c["candle_time"],
        )


class CandleService:
    """Subscribes to PriceUpdated, aggregates candles, persists and emits CandleClosed."""

    def __init__(self, epics: list[str], timeframes: list[str] = DEFAULT_TIMEFRAMES):
        self._aggregators: dict[tuple, CandleAggregator] = {}
        self.sequence = 0
        for epic in epics:
            for tf in timeframes:
                self._aggregators[(epic, tf)] = CandleAggregator(epic, tf)

    async def start(self):
        await EventBus.subscribe(self._on_price_updated)
        log.info("candle_service_started",
                 epics=list({k[0] for k in self._aggregators}),
                 timeframes=list({k[1] for k in self._aggregators}))

    async def _on_price_updated(self, event):
        if not isinstance(event, PriceUpdated):
            return
        for tf in DEFAULT_TIMEFRAMES:
            key = (event.epic, tf)
            agg = self._aggregators.get(key)
            if agg:
                closed = agg.on_tick(event)
                if closed:
                    await self._persist_and_emit(closed)

    async def _persist_and_emit(self, candle: Candle):
        try:
            async with get_session() as session:
                await CandleRepo.batch_insert(session, [candle])
            log.debug("candle_persisted", epic=candle.epic,
                      timeframe=candle.timeframe, candle_time=str(candle.candle_time))

            event = CandleClosed.new(
                sequence_id=self.sequence,
                correlation_id=uuid4(),
                epic=candle.epic,
                timeframe=candle.timeframe,
                open=float(candle.open),
                high=float(candle.high),
                low=float(candle.low),
                close=float(candle.close),
                candle_time=candle.candle_time,
            )
            await EventBus.publish(event)
            self.sequence += 1
        except Exception as e:
            log.error("candle_persist_error", epic=candle.epic, error=str(e))

candle_service = CandleService(epics=["GOLD", "US500"])