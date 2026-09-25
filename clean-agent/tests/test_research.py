from app.research import normalize_prices, run_moving_average_backtest


def test_normalize_capital_style_prices():
    candles = normalize_prices(
        {
            "prices": [
                {
                    "snapshotTime": "2026-01-01T00:00:00",
                    "openPrice": {"bid": 99, "ask": 101},
                    "highPrice": {"bid": 102, "ask": 104},
                    "lowPrice": {"bid": 98, "ask": 100},
                    "closePrice": {"bid": 100, "ask": 102},
                },
                {
                    "snapshotTime": "2026-01-01T01:00:00",
                    "openPrice": {"bid": 100, "ask": 102},
                    "highPrice": {"bid": 103, "ask": 105},
                    "lowPrice": {"bid": 99, "ask": 101},
                    "closePrice": {"bid": 102, "ask": 104},
                },
                {
                    "snapshotTime": "2026-01-01T02:00:00",
                    "openPrice": {"bid": 102, "ask": 104},
                    "highPrice": {"bid": 106, "ask": 108},
                    "lowPrice": {"bid": 101, "ask": 103},
                    "closePrice": {"bid": 105, "ask": 107},
                },
            ]
        }
    )

    assert candles[0]["close"] == 101
    assert candles[-1]["close"] == 106


def test_backtest_has_no_lookahead_and_reports_metrics():
    candles = [
        {"time": str(index), "open": value, "high": value, "low": value, "close": value}
        for index, value in enumerate([100, 99, 98, 99, 101, 103, 102, 104, 106, 105, 107, 109])
    ]

    report = run_moving_average_backtest(
        candles,
        fast_window=2,
        slow_window=4,
        initial_cash=1000,
        fee_bps=0,
        slippage_bps=0,
    )

    assert report["kind"] == "research_only"
    assert report["metrics"]["trade_count"] >= 1
    assert "signal_uses_previous_candle" in report["assumptions"]
