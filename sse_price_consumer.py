"""Simple SSE price consumer for TradingCore.

- Connects to the capital‑trader price stream (`/api/v1/sse/stream/prices`).
- Parses each `data:` line as JSON containing `epic`, `bid`, `ask`.
- Maintains a rolling window (last 10 values) per epic and prints a moving average.
- Runs until interrupted (Ctrl‑C).
"""

import asyncio
import json
import sys
from collections import deque
from typing import Dict, Deque

import aiohttp

STREAM_URL = "http://localhost:8000/api/v1/sse/stream/prices"
WINDOW_SIZE = 10  # number of recent ticks for moving average

class PriceWindow:
    def __init__(self, size: int):
        self.size = size
        self.bids: Deque[float] = deque(maxlen=size)
        self.asks: Deque[float] = deque(maxlen=size)

    def add(self, bid: float, ask: float) -> None:
        self.bids.append(bid)
        self.asks.append(ask)

    def avg_bid(self) -> float:
        return sum(self.bids) / len(self.bids) if self.bids else 0.0

    def avg_ask(self) -> float:
        return sum(self.asks) / len(self.asks) if self.asks else 0.0

    def __repr__(self) -> str:
        return f"bid={self.avg_bid():.4f} ask={self.avg_ask():.4f} (n={len(self.bids)})"

async def consume_stream() -> None:
    windows: Dict[str, PriceWindow] = {}
    count = 0
    max_messages = 20  # stop after this many messages
    async with aiohttp.ClientSession() as session:
        async with session.get(STREAM_URL) as resp:
            if resp.status != 200:
                print(f"Failed to connect, status {resp.status}", file=sys.stderr)
                return
            async for line_bytes in resp.content:
                line = line_bytes.decode().strip()
                if not line.startswith("data:"):
                    continue
                try:
                    payload = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                epic = payload.get("epic")
                bid = payload.get("bid")
                ask = payload.get("ask")
                if not all([epic, isinstance(bid, (int, float)), isinstance(ask, (int, float))]):
                    continue
                win = windows.setdefault(epic, PriceWindow(WINDOW_SIZE))
                win.add(bid, ask)
                print(f"{epic}: {win}")
                count += 1
                if count >= max_messages:
                    return


def main() -> None:
    try:
        asyncio.run(consume_stream())
    except KeyboardInterrupt:
        print("\nStream stopped by user.")

if __name__ == "__main__":
    main()
