import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app import main


class FakeStore:
    def dashboard(self):
        return {
            "mode": "observe",
            "tickets": [
                {
                    "id": "T-1",
                    "status": "blocked",
                    "epic": "GOLD",
                    "direction": "SELL",
                    "size": 1.0,
                    "order_type": "CLOSE",
                    "deal_id": "deal-1",
                    "risk": {"status": "blocked", "errors": ["market closed"], "warnings": []},
                }
            ],
            "audit": [],
            "memories": [],
        }

    def action_audit(self, limit=12):
        return [{"id": "audit-1", "action": "ticket_created", "summary": "created ticket"}]

    def recent_browser_snapshots(self, limit=5):
        return []


class FakeTrader:
    async def deep_health(self):
        return {"status": "degraded", "components": {"trading": {"status": "degraded", "mode": "observe"}}}

    async def trade_logs(self, limit=12):
        return {"logs": [{"event_type": "close_rejected", "payload": {"status": "blocked"}}]}


class FakeGoldCandlesTrader:
    def __init__(self):
        self.request = None

    async def gold_candles_csv(self, **kwargs):
        self.request = kwargs
        return "timestamp,volume\n1790314800,267\n"


class FailedGoldCandlesTrader:
    async def gold_candles_csv(self, **kwargs):
        raise httpx.ConnectError("capital trader unavailable")


async def fake_broker_snapshot():
    return {"health": {"status": "ok"}, "positions": {"positions": []}}


def test_dashboard_includes_ui_trading_streams(monkeypatch):
    monkeypatch.setattr(main, "store", FakeStore())
    monkeypatch.setattr(main, "trader_client", FakeTrader())
    monkeypatch.setattr(main, "broker_snapshot", fake_broker_snapshot)
    monkeypatch.setattr(main, "canvas_status", lambda: {"configured": False, "connected": False})

    dashboard = asyncio.run(main.dashboard())

    assert dashboard["agent"]["actions"][0]["action"] == "ticket_created"
    assert dashboard["agent"]["ticket_summary"] == {"blocked": 1}
    assert dashboard["capital"]["deep_health"]["status"] == "degraded"
    assert dashboard["capital"]["trade_logs"]["logs"][0]["event_type"] == "close_rejected"
    assert dashboard["broker"]["health"]["status"] == "ok"


def test_gold_candles_route_proxies_csv(monkeypatch):
    trader = FakeGoldCandlesTrader()
    monkeypatch.setattr(main, "trader_client", trader)

    response = asyncio.run(
        main.gold_candles_csv(
            limit=500,
            start="2026-09-25T00:00:00Z",
            end="2026-09-25T12:00:00Z",
            offset=5,
        )
    )

    assert trader.request == {
        "limit": 500,
        "start": "2026-09-25T00:00:00Z",
        "end": "2026-09-25T12:00:00Z",
        "offset": 5,
    }
    assert response.media_type == "text/csv"
    assert response.body == b"timestamp,volume\n1790314800,267\n"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_gold_candles_route_reports_unavailable_capital_trader(monkeypatch):
    monkeypatch.setattr(main, "trader_client", FailedGoldCandlesTrader())

    with pytest.raises(HTTPException) as error:
        asyncio.run(main.gold_candles_csv(limit=500, start=None, end=None, offset=0))

    assert error.value.status_code == 502
    assert error.value.detail == "stored GOLD candles are unavailable"
