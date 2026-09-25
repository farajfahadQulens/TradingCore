"""Gold price + volume consumer.

- Periodically (default 1 s) queries the REST endpoint
  `/api/v1/market/prices/GOLD?resolution=MINUTE&max_points=1`.
- Extracts the most recent candle: bid/ask (mid‑price) and `lastTradedVolume`.
- Appends a CSV line: timestamp, bid, ask, volume.
- Prints a short summary with a rolling 10‑tick average of bid/ask and total volume.
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

STREAM_URL = "http://localhost:8000/api/v1/market/prices/GOLD?resolution=MINUTE&max_points=1"
CSV_PATH = Path(__file__).with_name("gold_prices_with_volume.csv")
WINDOW_SIZE = 10

class RollingWindow:
    def __init__(self, size: int):
        self.size = size
        self.bids: Deque[float] = deque(maxlen=size)
        self.asks: Deque[float] = deque(maxlen=size)
        self.volumes: Deque[int] = deque(maxlen=size)

    def add(self, bid: float, ask: float, volume: int) -> None:
        self.bids.append(bid)
        self.asks.append(ask)
        self.volumes.append(volume)

    @property
    def avg_bid(self) -> float:
        return sum(self.bids) / len(self.bids) if self.bids else 0.0

    @property
    def avg_ask(self) -> float:
        return sum(self.asks) / len(self.asks) if self.asks else 0.0

    @property
    def total_volume(self) -> int:
        return sum(self.volumes)

    def __repr__(self) -> str:
        return (
            f"bid={self.avg_bid:.4f} ask={self.avg_ask:.4f} "
            f"vol={self.total_volume} (n={len(self.bids)})"
        )

async def fetch_latest(session: aiohttp.ClientSession) -> dict:
    async with session.get(STREAM_URL) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Bad status {resp.status}")
        data = await resp.json()
        # The endpoint returns a list under "prices" – we asked for max_points=1
        if not data.get("prices"):
            raise RuntimeError("No price data returned")
        return data["prices"][-1]

async def consume(interval: float = 1.0) -> None:
    # Ensure CSV header
    if not CSV_PATH.exists():
        CSV_PATH.write_text("timestamp,bid,ask,volume\n")
    window = RollingWindow(WINDOW_SIZE)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                candle = await fetch_latest(session)
                bid = candle["closePrice"]["bid"]
                ask = candle["closePrice"]["ask"]
                volume = int(candle.get("lastTradedVolume", 0))
                ts = int(time.time())
                with CSV_PATH.open("a", newline="") as f:
                    csv.writer(f).writerow([ts, bid, ask, volume])
                window.add(bid, ask, volume)
                print(f"GOLD latest: {window}")
            except Exception as e:
                print(f"Error fetching price: {e}", file=sys.stderr)
            await asyncio.sleep(interval)

def main() -> None:
    try:
        asyncio.run(consume())
    except KeyboardInterrupt:
        print("\nStopped by user")

if __name__ == "__main__":
    main()
