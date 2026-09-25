import asyncio

from app.execution import _broker_order_payload
from app.risk import evaluate_ticket
from app.trader import TraderClient, normalize_epic
from app.tools import (
    get_capital_trader_capabilities,
    get_capital_trader_snapshot,
    preview_close_position,
    preview_trade_risk,
    submit_order,
)


class FakeTraderClient:
    async def health(self):
        return {"status": "healthy"}

    async def balance(self):
        return {"equity": {"balance": 1000}}

    async def positions(self):
        return {"positions": [{"position": {"dealId": "demo"}}]}

    async def orders(self):
        return {"workingOrders": []}

    async def risk_preview(self, payload):
        return {"workflow": "risk_preview", "request": payload, "approved": False}

    async def close_preview(self, deal_id):
        return {"workflow": "close_position_preview", "deal_id": deal_id, "approved": False}


def test_submit_order_is_disabled_by_default():
    result = asyncio.run(submit_order(
        {
            "epic": "XAUUSD",
            "direction": "BUY",
            "size": 0.1,
            "confirmation_phrase": "CONFIRM_LIVE_ORDER",
        }
    ))

    assert result["submitted"] is False
    assert result["reason"] == "direct order submission is disabled; create and approve a trade ticket first"


def test_capital_trader_capabilities_describe_safe_position_flow():
    result = asyncio.run(get_capital_trader_capabilities({}))

    assert "get_balance" in result["read_tools"]
    assert "list_positions" in result["read_tools"]
    assert result["write_flow"]["create_trade_ticket"].startswith("Prepare")
    assert result["safety"]["direct_submit_order"] == "disabled"
    assert result["safety"]["required_live_flow"] == [
        "create_trade_ticket",
        "approve_ticket",
        "execute_ticket",
    ]
    assert result["safety"]["required_close_flow"] == [
        "create_close_ticket",
        "approve_close_ticket",
        "execute_close_ticket",
    ]
    assert "preview_trade_risk" in result["read_tools"]
    assert "preview_close_position" in result["read_tools"]


def test_capital_trader_snapshot_reads_main_account_state(monkeypatch):
    import app.tools as tools

    monkeypatch.setattr(tools, "trader_client", FakeTraderClient())

    result = asyncio.run(get_capital_trader_snapshot({}))

    assert result["health"] == {"status": "healthy"}
    assert result["balance"] == {"equity": {"balance": 1000}}
    assert len(result["positions"]["positions"]) == 1
    assert result["orders"] == {"workingOrders": []}


def test_risk_blocks_ticket_without_stop_loss():
    result = evaluate_ticket(
        {
            "epic": "XAUUSD",
            "direction": "BUY",
            "size": 0.1,
            "order_type": "LIMIT",
            "level": 2400,
            "stop_loss": None,
        },
        {"positions": {"positions": []}},
    )

    assert result["status"] == "blocked"
    assert "stop loss or stop distance is required" in result["errors"]


def test_risk_approves_basic_ticket_with_stop_loss():
    result = evaluate_ticket(
        {
            "epic": "XAUUSD",
            "direction": "SELL",
            "size": 0.1,
            "order_type": "LIMIT",
            "level": 2400,
            "stop_loss": 2410,
            "take_profit": 2370,
        },
        {"positions": {"positions": []}},
    )

    assert result["status"] == "approved"
    assert result["errors"] == []


def test_risk_blocks_stop_loss_on_wrong_side():
    result = evaluate_ticket(
        {
            "epic": "CS.D.EURUSD.TODAY",
            "direction": "BUY",
            "size": 0.1,
            "order_type": "LIMIT",
            "level": 1.1,
            "stop_loss": 1.11,
            "take_profit": 1.12,
        },
        {"positions": {"positions": []}},
    )

    assert result["status"] == "blocked"
    assert "BUY stop loss must be below entry level" in result["errors"]


def test_risk_blocks_when_orders_are_unavailable():
    result = evaluate_ticket(
        {
            "epic": "CS.D.EURUSD.TODAY",
            "direction": "SELL",
            "size": 0.1,
            "order_type": "MARKET",
            "stop_distance": 0.0005,
            "take_profit": 1.08,
        },
        {"positions": {"positions": []}, "orders_error": "timeout"},
    )

    assert result["status"] == "blocked"
    assert "orders unavailable: timeout" in result["errors"]


def test_broker_order_payload_omits_empty_values():
    payload = _broker_order_payload(
        {
            "epic": "CS.D.EURUSD.TODAY",
            "direction": "BUY",
            "size": 0.1,
            "order_type": "MARKET",
            "level": None,
            "limit_distance": 0.001,
            "stop_distance": 0.0005,
        }
    )

    assert payload == {
        "epic": "CS.D.EURUSD.TODAY",
        "direction": "BUY",
        "size": 0.1,
        "order_type": "MARKET",
        "limit_distance": 0.001,
        "stop_distance": 0.0005,
    }


def test_trader_prices_uses_capital_trader_query_name(monkeypatch):
    captured = {}

    async def fake_request(self, method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["kwargs"] = kwargs
        return {"prices": []}

    monkeypatch.setattr(TraderClient, "request", fake_request)

    result = asyncio.run(
        TraderClient(base_url="http://capital.test").prices(
            "CS.D.EURUSD.TODAY",
            resolution="HOUR",
            max_points=123,
        )
    )

    assert result == {"prices": []}
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/market/prices/CS.D.EURUSD.TODAY"
    assert captured["kwargs"]["params"] == {"resolution": "HOUR", "max_points": 123}


def test_trader_gold_candles_uses_stored_csv_endpoint(monkeypatch):
    captured = {}

    async def fake_request_text(self, method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["kwargs"] = kwargs
        return "timestamp,volume\n1790314800,267\n"

    monkeypatch.setattr(TraderClient, "request_text", fake_request_text)

    result = asyncio.run(
        TraderClient(base_url="http://capital.test").gold_candles_csv(
            limit=500,
            start="2026-09-25T00:00:00Z",
            end="2026-09-25T12:00:00Z",
            offset=10,
        )
    )

    assert result.endswith("1790314800,267\n")
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/market/gold/candles.csv"
    assert captured["kwargs"]["params"] == {
        "limit": 500,
        "offset": 10,
        "start": "2026-09-25T00:00:00Z",
        "end": "2026-09-25T12:00:00Z",
    }


def test_gold_aliases_normalize_to_capital_trader_gold_epic(monkeypatch):
    captured = {}

    async def fake_request(self, method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["kwargs"] = kwargs
        return {"market": "gold"}

    monkeypatch.setattr(TraderClient, "request", fake_request)

    assert normalize_epic("XAUUSD") == "GOLD"
    result = asyncio.run(TraderClient(base_url="http://capital.test").market("XAUUSD"))

    assert result == {"market": "gold"}
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/market/GOLD"


def test_trader_submit_order_uses_capital_trader_workflow_endpoint(monkeypatch):
    captured = {}

    async def fake_request(self, method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["kwargs"] = kwargs
        return {"workflow": "order_workflow_service"}

    monkeypatch.setattr(TraderClient, "request", fake_request)

    payload = {"epic": "GOLD", "direction": "BUY", "size": 0.1}
    result = asyncio.run(TraderClient(base_url="http://capital.test").submit_order(payload))

    assert result == {"workflow": "order_workflow_service"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/workflow/orders"
    assert captured["kwargs"]["json"] == payload


def test_trader_risk_preview_uses_capital_trader_preview_endpoint(monkeypatch):
    captured = {}

    async def fake_request(self, method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["kwargs"] = kwargs
        return {"workflow": "risk_preview"}

    monkeypatch.setattr(TraderClient, "request", fake_request)

    payload = {"epic": "XAUUSD", "direction": "BUY", "size": 0.1}
    result = asyncio.run(TraderClient(base_url="http://capital.test").risk_preview(payload))

    assert result == {"workflow": "risk_preview"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/workflow/risk-preview"
    assert captured["kwargs"]["json"] == {"epic": "GOLD", "direction": "BUY", "size": 0.1}


def test_preview_trade_risk_normalizes_payload(monkeypatch):
    import app.tools as tools

    class PreviewTrader:
        async def risk_preview(self, payload):
            return {"workflow": "risk_preview", "request": payload}

    monkeypatch.setattr(tools, "trader_client", PreviewTrader())

    result = asyncio.run(
        preview_trade_risk(
            {
                "epic": "xauusd",
                "direction": "buy",
                "size": "0.1",
                "order_type": "market",
                "stop_distance": "1.5",
            }
        )
    )

    assert result["request"] == {
        "epic": "GOLD",
        "direction": "BUY",
        "size": 0.1,
        "order_type": "MARKET",
        "stop_distance": 1.5,
    }


def test_trader_close_preview_uses_capital_trader_preview_endpoint(monkeypatch):
    captured = {}

    async def fake_request(self, method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["kwargs"] = kwargs
        return {"workflow": "close_position_preview"}

    monkeypatch.setattr(TraderClient, "request", fake_request)

    result = asyncio.run(TraderClient(base_url="http://capital.test").close_preview("deal-1"))

    assert result == {"workflow": "close_position_preview"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/workflow/positions/deal-1/close-preview"
    assert captured["kwargs"] == {}


def test_preview_close_position_calls_trader(monkeypatch):
    import app.tools as tools

    class PreviewTrader:
        async def close_preview(self, deal_id):
            return {"workflow": "close_position_preview", "deal_id": deal_id}

    monkeypatch.setattr(tools, "trader_client", PreviewTrader())

    result = asyncio.run(preview_close_position({"deal_id": "deal-1"}))

    assert result == {"workflow": "close_position_preview", "deal_id": "deal-1"}
