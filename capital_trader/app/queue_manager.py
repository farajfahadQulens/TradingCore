"""Simple in‑memory queues used by the platform.
"""
import asyncio
from collections import deque
from typing import Any
from app.core.logging import get_logger
log = get_logger(__name__)

class SimpleQueue:
    def __init__(self, maxlen: int | None = None, drop_policy: str = "drop_oldest"):
        self._maxlen = maxlen
        self._queue = deque(maxlen=maxlen)
        self._cond = asyncio.Condition()
        self.drop_policy = drop_policy

    async def put(self, item: Any):
        async with self._cond:
            if self._maxlen and len(self._queue) >= self._maxlen:
                if self.drop_policy == "drop_oldest":
                    self._queue.popleft()
                else:
                    raise asyncio.QueueFull()
            self._queue.append(item)
            self._cond.notify()

    async def get(self) -> Any:
        async with self._cond:
            while not self._queue:
                await self._cond.wait()
            return self._queue.popleft()

    def qsize(self) -> int:
        return len(self._queue)

# Global queues ------------------------------------------------------------
price_queue = SimpleQueue(maxlen=10000, drop_policy="drop_oldest")
order_queue = SimpleQueue(maxlen=10000, drop_policy="never_drop")
alert_queue = SimpleQueue(maxlen=5000, drop_policy="drop_oldest")
metrics_queue = SimpleQueue(maxlen=5000, drop_policy="drop_oldest")
