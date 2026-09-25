"""Small, transparent research tools for broker price data.

This module is deliberately read-only. It produces a research report and never
creates or executes a trade ticket.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any


class ResearchDataError(ValueError):
    """Raised when a broker response cannot be converted to OHLC candles."""


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _price(value: Any) -> float | None:
    """Extract a numeric price or the midpoint of a bid/ask object."""

    if isinstance(value, dict):
        bid = _number(value.get("bid"))
        ask = _number(value.get("ask"))
        if bid is not None and ask is not None:
            return (bid + ask) / 2
        return bid if bid is not None else ask
    return _number(value)


def normalize_prices(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Capital-style or generic OHLC JSON into ordered candles."""

    raw_prices = payload.get("prices") if isinstance(payload, dict) else None
    if not isinstance(raw_prices, list):
        raise ResearchDataError("price response does not contain a prices list")

    candles: list[dict[str, Any]] = []
    for item in raw_prices:
        if not isinstance(item, dict):
            continue
        open_price = _price(item.get("openPrice", item.get("open")))
        high_price = _price(item.get("highPrice", item.get("high")))
        low_price = _price(item.get("lowPrice", item.get("low")))
        close_price = _price(item.get("closePrice", item.get("close")))
        if None in (open_price, high_price, low_price, close_price):
            continue
        candles.append(
            {
                "time": item.get("snapshotTime", item.get("time", item.get("timestamp"))),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": _number(item.get("lastTradedVolume", item.get("volume"))),
            }
        )

    candles.sort(key=lambda candle: str(candle["time"] or ""))
    if len(candles) < 3:
        raise ResearchDataError("fewer than three complete OHLC candles were returned")
    return candles


def _sma(values: list[float], window: int, end: int) -> float | None:
    if end + 1 < window:
        return None
    sample = values[end - window + 1 : end + 1]
    return sum(sample) / window


def run_moving_average_backtest(
    candles: list[dict[str, Any]],
    *,
    fast_window: int = 10,
    slow_window: int = 30,
    initial_cash: float = 10_000.0,
    fee_bps: float = 1.0,
    slippage_bps: float = 2.0,
) -> dict[str, Any]:
    """Run a long/flat moving-average baseline without look-ahead bias."""

    if fast_window < 2 or slow_window <= fast_window:
        raise ResearchDataError("slow_window must be greater than fast_window >= 2")
    if initial_cash <= 0 or fee_bps < 0 or slippage_bps < 0:
        raise ResearchDataError("cash and trading costs must be non-negative, with cash greater than zero")
    if len(candles) <= slow_window + 1:
        raise ResearchDataError("not enough candles for the selected windows")

    closes = [float(candle["close"]) for candle in candles]
    equity = initial_cash
    position = 0
    entry_price: float | None = None
    equity_curve = [equity]
    trades: list[dict[str, Any]] = []

    for index in range(slow_window, len(candles)):
        previous = index - 1
        fast = _sma(closes, fast_window, previous)
        slow = _sma(closes, slow_window, previous)
        if fast is None or slow is None:
            equity_curve.append(equity)
            continue

        target_position = 1 if fast > slow else 0
        price = closes[index]
        if position:
            equity *= price / closes[index - 1]

        if target_position != position:
            cost_rate = (fee_bps + slippage_bps) / 10_000
            equity *= 1 - cost_rate
            if target_position:
                entry_price = price
                trades.append({"time": candles[index]["time"], "action": "BUY", "price": price})
            else:
                trades.append(
                    {
                        "time": candles[index]["time"],
                        "action": "SELL",
                        "price": price,
                        "entry_price": entry_price,
                        "return": (price / entry_price - 1) if entry_price else None,
                    }
                )
                entry_price = None
            position = target_position
        equity_curve.append(equity)

    if position:
        final_price = closes[-1]
        trades.append(
            {
                "time": candles[-1]["time"],
                "action": "CLOSE",
                "price": final_price,
                "entry_price": entry_price,
                "return": (final_price / entry_price - 1) if entry_price else None,
            }
        )

    returns = [equity_curve[index] / equity_curve[index - 1] - 1 for index in range(1, len(equity_curve))]
    peak = equity_curve[0]
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, 1 - value / peak)
    mean_return = sum(returns) / len(returns) if returns else 0.0
    variance = sum((value - mean_return) ** 2 for value in returns) / max(len(returns) - 1, 1)
    sharpe = (mean_return / math.sqrt(variance)) * math.sqrt(252) if variance > 0 else 0.0

    return {
        "kind": "research_only",
        "strategy": "long_flat_sma_crossover",
        "assumptions": {
            "signal_uses_previous_candle": True,
            "entry_exit_price": "next observed close",
            "fee_bps": fee_bps,
            "slippage_bps": slippage_bps,
            "sharpe_annualization": "sqrt(252), only a rough comparison",
        },
        "sample": {
            "candles": len(candles),
            "start": candles[0]["time"],
            "end": candles[-1]["time"],
        },
        "parameters": {"fast_window": fast_window, "slow_window": slow_window},
        "metrics": {
            "initial_cash": initial_cash,
            "final_equity": round(equity, 6),
            "total_return": round(equity / initial_cash - 1, 8),
            "max_drawdown": round(max_drawdown, 8),
            "sharpe": round(sharpe, 6),
            "trade_count": len(trades),
        },
        "trades": trades,
        "generated_at": datetime.now().astimezone().isoformat(),
    }
