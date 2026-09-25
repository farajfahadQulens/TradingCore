import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.api.v1 import market
from app.services.gold_candle_store import (
    CSV_FIELDS,
    filter_candle_rows,
    load_candle_rows,
    merge_candles,
    normalize_candle,
    render_csv,
)


def candle(snapshot: str, close: float, volume: int) -> dict:
    return {
        "snapshotTimeUTC": snapshot,
        "openPrice": {"bid": close - 0.2, "ask": close + 0.2},
        "highPrice": {"bid": close + 0.4, "ask": close + 0.6},
        "lowPrice": {"bid": close - 0.6, "ask": close - 0.4},
        "closePrice": {"bid": close, "ask": close + 0.5},
        "lastTradedVolume": volume,
    }


class GoldCandleStoreTests(unittest.TestCase):
    def test_normalize_candle_keeps_bid_ask_ohlc_and_volume(self):
        row = normalize_candle(candle("2026-09-25T10:00:00Z", 4300, 125))

        self.assertEqual(row["snapshot_time_utc"], "2026-09-25T10:00:00Z")
        self.assertEqual(row["open_bid"], "4299.8")
        self.assertEqual(row["close_ask"], "4300.5")
        self.assertEqual(row["volume"], "125")

    def test_merge_updates_current_candle_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gold.csv"
            first = merge_candles(path, [candle("2026-09-25T10:00:00Z", 4300, 100)])
            second = merge_candles(path, [candle("2026-09-25T10:00:00Z", 4302, 125)])

            rows = load_candle_rows(path)
            self.assertEqual(first, {"rows": 1, "inserted": 1, "updated": 0, "pruned": 0})
            self.assertEqual(second, {"rows": 1, "inserted": 0, "updated": 1, "pruned": 0})
            self.assertEqual(rows[0]["close_bid"], "4302.0")
            self.assertEqual(rows[0]["volume"], "125")

    def test_retention_prunes_old_candles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gold.csv"
            rows = [
                candle("2026-09-20T10:00:00Z", 4200, 10),
                candle("2026-09-24T10:00:00Z", 4300, 20),
            ]
            result = merge_candles(
                path,
                rows,
                retention_days=2,
                now=datetime(2026, 9, 24, 10, tzinfo=timezone.utc).timestamp(),
            )

            self.assertEqual(result["pruned"], 1)
            self.assertEqual(result["rows"], 1)
            self.assertEqual(load_candle_rows(path)[0]["close_bid"], "4300.0")

    def test_legacy_csv_is_upgraded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gold.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["timestamp", "bid", "ask", "volume"])
                writer.writerow([1787558400, 4300, 4300.5, 90])

            rows = load_candle_rows(path)
            rendered = render_csv(rows)

            self.assertEqual(rows[0]["snapshot_time_utc"], "")
            self.assertEqual(rows[0]["close_bid"], "4300.0")
            self.assertEqual(rendered.splitlines()[0], ",".join(CSV_FIELDS))

    def test_filter_and_pagination_are_chronological(self):
        rows = merge_candles(
            Path(tempfile.gettempdir()) / "gold-filter-test.csv",
            [
                candle("2026-09-25T10:01:00Z", 4301, 2),
                candle("2026-09-25T10:00:00Z", 4300, 1),
                candle("2026-09-25T10:02:00Z", 4302, 3),
            ],
        )
        self.assertGreater(rows["rows"], 0)
        path = Path(tempfile.gettempdir()) / "gold-filter-test.csv"
        try:
            filtered = filter_candle_rows(
                load_candle_rows(path),
                start="2026-09-25T10:00:00Z",
                offset=1,
                limit=1,
            )
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0]["close_bid"], "4301.0")
        finally:
            path.unlink(missing_ok=True)


class GoldCandleApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_csv_endpoint_returns_csv_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gold.csv"
            merge_candles(path, [candle("2026-09-25T10:00:00Z", 4300, 100)])
            original_path = market.GOLD_CSV_PATH
            market.GOLD_CSV_PATH = path
            try:
                response = await market.get_gold_candles_csv(offset=0, limit=10)
            finally:
                market.GOLD_CSV_PATH = original_path

            self.assertTrue(response.media_type.startswith("text/csv"))
            self.assertIn("timestamp,snapshot_time_utc", response.body.decode())
            self.assertIn("2026-09-25T10:00:00Z", response.body.decode())


if __name__ == "__main__":
    unittest.main()
