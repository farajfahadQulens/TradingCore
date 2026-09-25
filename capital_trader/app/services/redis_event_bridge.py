"""Bridges Capital Trader's in-process event bus to Redis streams.

This allows agent-service (and any other consumer) to observe Capital Trader
events (signals, orders, fills) in real-time via Redis.
"""
import json
import os
import logging

from redis.asyncio import Redis

from app.services.event_bus import EventBus
from app.core.events import SignalDetected, OrderSubmitted, OrderFilled
from app.core.config import settings
from app.services.runtime_status import runtime_status

log = logging.getLogger(__name__)

STREAM_PREFIX = "rafiq"


async def _publish_to_redis(redis: Redis, stream: str, event: object) -> None:
    try:
        await redis.xadd(
            stream,
            {"event": json.dumps(event, default=str)},
            maxlen=10_000,
            approximate=True,
        )
        runtime_status.mark_redis_publish()
    except Exception as exc:
        runtime_status.mark_redis_error(exc)
        log.exception("Failed to bridge event to Redis stream %s", stream)


async def bridge_worker():
    """Subscribe to the Capital Trader event bus and forward to Redis."""
    redis_url = os.getenv("REDIS_URL", settings.redis_url)
    redis = Redis.from_url(redis_url, decode_responses=True)

    async def handler(event: object) -> None:
        stream = None
        if isinstance(event, SignalDetected):
            stream = f"{STREAM_PREFIX}.market.signaldetected"
        elif isinstance(event, OrderSubmitted):
            stream = f"{STREAM_PREFIX}.trading.ordersubmitted"
        elif isinstance(event, OrderFilled):
            stream = f"{STREAM_PREFIX}.trading.orderfilled"

        if stream:
            await _publish_to_redis(redis, stream, {
                "event_id": str(event.event_id),
                "type": type(event).__name__,
                "payload": {
                    k: str(v) if hasattr(v, "isoformat") else v
                    for k, v in event.__dict__.items()
                    if not k.startswith("_")
                },
            })

    await EventBus.subscribe(handler)
    runtime_status.mark_redis_subscribed()
    log.info("Redis event bridge subscribed to EventBus")
