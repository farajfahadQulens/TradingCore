import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

from app.services.gold_candle_store import merge_candles

LOGGER = logging.getLogger("gold-candle-recorder")
TRADER_URL = os.getenv("GOLD_TRADER_URL", "http://capital-trader:8000").rstrip("/")
EPIC = os.getenv("GOLD_EPIC", "GOLD")
CSV_PATH = Path(os.getenv("GOLD_CSV_PATH", "/data/gold_candles.csv"))
STATUS_PATH = Path(os.getenv("GOLD_STATUS_PATH", "/data/gold_recorder_status.json"))
POLL_SECONDS = max(5, int(os.getenv("GOLD_POLL_SECONDS", "15")))
MAX_POINTS = max(1, int(os.getenv("GOLD_MAX_POINTS", "300")))
RETENTION_DAYS = max(0, int(os.getenv("GOLD_RETENTION_DAYS", "0")))
TIMEOUT_SECONDS = max(5, int(os.getenv("GOLD_REQUEST_TIMEOUT_SECONDS", "45")))


def write_status(status: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(status, indent=2), encoding="utf-8")
    temporary.replace(STATUS_PATH)


async def fetch_candles(session: aiohttp.ClientSession) -> list[dict]:
    url = f"{TRADER_URL}/api/v1/market/prices/{EPIC}"
    params = {"resolution": "MINUTE", "max_points": str(MAX_POINTS)}
    async with session.get(url, params=params) as response:
        response.raise_for_status()
        payload = await response.json()
    prices = payload.get("prices", [])
    return prices if isinstance(prices, list) else []


async def record_forever() -> None:
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            started = time.time()
            try:
                prices = await fetch_candles(session)
                stats = merge_candles(CSV_PATH, prices, retention_days=RETENTION_DAYS)
                now = time.time()
                write_status(
                    {
                        "status": "healthy",
                        "epic": EPIC,
                        "resolution": "MINUTE",
                        "last_success": datetime.now(timezone.utc).isoformat(),
                        "last_success_epoch": now,
                        "duration_seconds": round(now - started, 3),
                        "retention_days": RETENTION_DAYS,
                        **stats,
                    }
                )
                LOGGER.info("gold_candles_recorded", extra=stats)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                LOGGER.exception("gold_candle_recording_failed", extra={"error": str(error)})
                write_status(
                    {
                        "status": "unhealthy",
                        "epic": EPIC,
                        "resolution": "MINUTE",
                        "last_error": str(error),
                        "last_error_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            await asyncio.sleep(POLL_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        asyncio.run(record_forever())
    except KeyboardInterrupt:
        LOGGER.info("gold_candle_recorder_stopped")


if __name__ == "__main__":
    main()
