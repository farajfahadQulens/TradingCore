import csv
import io
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

CSV_FIELDS = [
    "timestamp",
    "snapshot_time_utc",
    "open_bid",
    "open_ask",
    "high_bid",
    "high_ask",
    "low_bid",
    "low_ask",
    "close_bid",
    "close_ask",
    "volume",
]


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _timestamp(value: str) -> int:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _pair(value: Any) -> tuple[float, float] | None:
    if isinstance(value, Mapping):
        bid = _number(value.get("bid"))
        ask = _number(value.get("ask"))
        if bid is not None and ask is not None:
            return bid, ask
        return None
    price = _number(value)
    if price is None:
        return None
    return price, price


def _pair_values(value: Any) -> tuple[str, str] | None:
    pair = _pair(value)
    if pair is None:
        return None
    return str(pair[0]), str(pair[1])


def normalize_candle(candle: Mapping[str, Any]) -> dict[str, str] | None:
    snapshot = candle.get("snapshotTimeUTC") or candle.get("snapshotTime")
    if not snapshot:
        return None
    try:
        timestamp = _timestamp(str(snapshot))
    except ValueError:
        return None
    open_values = _pair_values(candle.get("openPrice", candle.get("open")))
    high_values = _pair_values(candle.get("highPrice", candle.get("high")))
    low_values = _pair_values(candle.get("lowPrice", candle.get("low")))
    close_values = _pair_values(candle.get("closePrice", candle.get("close")))
    if not all((open_values, high_values, low_values, close_values)):
        return None
    volume = _number(candle.get("lastTradedVolume", candle.get("volume")))
    return {
        "timestamp": str(timestamp),
        "snapshot_time_utc": str(snapshot),
        "open_bid": open_values[0],
        "open_ask": open_values[1],
        "high_bid": high_values[0],
        "high_ask": high_values[1],
        "low_bid": low_values[0],
        "low_ask": low_values[1],
        "close_bid": close_values[0],
        "close_ask": close_values[1],
        "volume": str(int(volume)) if volume is not None else "",
    }


def _legacy_row(row: Mapping[str, Any]) -> dict[str, str] | None:
    timestamp = _number(row.get("timestamp"))
    bid = _number(row.get("bid", row.get("close_bid")))
    ask = _number(row.get("ask", row.get("close_ask")))
    if timestamp is None or bid is None or ask is None:
        return None
    volume = _number(row.get("volume")) or 0
    values = {
        "timestamp": str(int(timestamp)),
        "snapshot_time_utc": str(row.get("snapshot_time_utc", "")),
        "open_bid": str(row.get("open_bid", bid)),
        "open_ask": str(row.get("open_ask", ask)),
        "high_bid": str(row.get("high_bid", bid)),
        "high_ask": str(row.get("high_ask", ask)),
        "low_bid": str(row.get("low_bid", bid)),
        "low_ask": str(row.get("low_ask", ask)),
        "close_bid": str(row.get("close_bid", bid)),
        "close_ask": str(row.get("close_ask", ask)),
        "volume": str(int(volume)),
    }
    return values


def load_candle_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, str]] = []
        for raw in reader:
            if reader.fieldnames == CSV_FIELDS:
                if all(raw.get(field) is not None for field in CSV_FIELDS):
                    rows.append({field: str(raw.get(field, "")) for field in CSV_FIELDS})
            else:
                row = _legacy_row(raw)
                if row is not None:
                    rows.append(row)
    return rows


def _row_key(row: Mapping[str, str]) -> str:
    snapshot = str(row.get("snapshot_time_utc", "")).strip()
    return snapshot or f"timestamp:{row.get('timestamp', '')}"


def _write_rows(path: Path, rows: Iterable[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def merge_candles(
    path: Path,
    candles: Iterable[Mapping[str, Any]],
    retention_days: int = 0,
    now: float | None = None,
) -> dict[str, int]:
    existing_rows = load_candle_rows(path)
    existing = {_row_key(row): row for row in existing_rows}
    inserted = 0
    updated = 0
    for candle in candles:
        normalized = normalize_candle(candle)
        if normalized is None:
            continue
        key = _row_key(normalized)
        if key in existing:
            if existing[key] != normalized:
                existing[key] = normalized
                updated += 1
        else:
            existing[key] = normalized
            inserted += 1
    rows = list(existing.values())
    if retention_days > 0:
        current_time = now if now is not None else datetime.now(timezone.utc).timestamp()
        cutoff = int(current_time - retention_days * 86400)
        retained = [row for row in rows if int(float(row.get("timestamp", 0))) >= cutoff]
        pruned = len(rows) - len(retained)
        rows = retained
    else:
        pruned = 0
    rows.sort(key=lambda row: int(float(row.get("timestamp", 0))))
    _write_rows(path, rows)
    return {"rows": len(rows), "inserted": inserted, "updated": updated, "pruned": pruned}


def _boundary(value: str | int | float | None) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(value)
    except ValueError:
        return _timestamp(value)


def filter_candle_rows(
    rows: Iterable[Mapping[str, str]],
    start: str | int | float | None = None,
    end: str | int | float | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict[str, str]]:
    start_timestamp = _boundary(start)
    end_timestamp = _boundary(end)
    filtered = []
    for row in rows:
        timestamp = int(float(row.get("timestamp", 0)))
        if start_timestamp is not None and timestamp < start_timestamp:
            continue
        if end_timestamp is not None and timestamp > end_timestamp:
            continue
        filtered.append(dict(row))
    filtered.sort(key=lambda row: int(float(row.get("timestamp", 0))))
    end_index = None if limit is None else offset + limit
    return filtered[offset:end_index]


def render_csv(rows: Iterable[Mapping[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def candle_summary(rows: list[dict[str, str]], path: Path) -> dict[str, Any]:
    timestamps = [int(float(row["timestamp"])) for row in rows if row.get("timestamp")]
    return {
        "path": str(path),
        "rows": len(rows),
        "first_timestamp": min(timestamps) if timestamps else None,
        "last_timestamp": max(timestamps) if timestamps else None,
        "exists": path.exists(),
    }
