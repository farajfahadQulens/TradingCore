"""A tiny in‑process event bus. In production you might replace this with
Redis Pub/Sub, NATS, etc.
"""
import asyncio
from typing import Callable, Awaitable

class EventBus:
    _subscribers: list[Callable[[object], Awaitable[None]]] = []
    _lock = asyncio.Lock()

    @classmethod
    async def publish(cls, event: object):
        async with cls._lock:
            for sub in cls._subscribers:
                # fire‑and‑forget; each subscriber handles its own errors
                asyncio.create_task(sub(event))

    @classmethod
    async def subscribe(cls, handler: Callable[[object], Awaitable[None]]):
        async with cls._lock:
            cls._subscribers.append(handler)
