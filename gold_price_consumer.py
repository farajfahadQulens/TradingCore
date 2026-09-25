"""Gold‑only SSE consumer.

- Connects to Capital‑Trader price stream (`/api/v1/sse/stream/prices`).
- Filters messages where `epic == "GOLD"`.
- Keeps a rolling window of the last 20 ticks.
- Prints the latest price and the rolling average bid/ask.
- Appends each tick to `gold_prices.csv` (timestamp, bid, ask).
"""

import asyncio
import csv
import json
import sys
import time
from collections import deque
from pathlib import Path
from typing import Deque

import aiohttp

STREAM_URL = "http://localhost:8000/api/v1/sse/stream/prices"
WINDOW_SIZE = 20
CSV_PATH = Path(__file__).with_name("gold_prices.csv")

class RollingWindow:
    """Simple fixed‑size window for numeric values."""
    def __init__(self, size: int):
        self.size = size
        self.bids: Deque[float] = deque(maxlen=size)
        self.asks: Deque[float] = deque(maxlen=size)

    def add(self, bid: float, ask: float) -> None:
        self.bids.append(bid)
        self.asks.append(ask)

    @property
    def avg_bid(self) -> float:
        return sum(self.bids) / len(self.bids) if self.bids else 0.0

    @property
    def avg_ask(self) -> float:
        return sum(self.asks) / len(self.asks) if self.asks else 0.0

    def __repr__(self) -> str:
        return f"bid={self.avg_bid:.4f} ask={self.avg_ask:.4f} (n={len(self.bids)})"

async def consume_gold() -> None:
    window = RollingWindow(WINDOW_SIZE)
    # Ensure CSV header exists
    if not CSV_PATH.exists():
        CSV_PATH.write_text("timestamp,bid,ask\n")
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
                if payload.get("epic") != "GOLD":
                    continue
                bid = payload.get("bid")
                ask = payload.get("ask")
                if not isinstance(bid, (int, float)) or not isinstance(ask, (int, float)):
                    continue
                # Record in window
                window.add(bid, ask)
                # Append to CSV with epoch timestamp
                ts = int(time.time())
                with CSV_PATH.open("a", newline="") as f:
                    csv.writer(f).writerow([ts, bid, ask])
                print(f"GOLD latest: bid={bid:.4f} ask={ask:.4f} | avg: {window}")

def main() -> None:
    try:
        asyncio.run(consume_gold())
    except KeyboardInterrupt:
        print("\nStopped by user")

if __name__ == "__main__":
    main()
