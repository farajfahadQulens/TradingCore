import asyncio

from app.execution import (
    approve_close_ticket,
    create_close_ticket,
    execute_close_ticket,
)
from app.store import Store


class CloseTrader:
    def __init__(self, preview):
        self.preview = preview
        self.closed = []
        self.preview_calls = 0

    async def close_preview(self, deal_id):
        self.preview_calls += 1
        return self.preview

    async def close_position(self, deal_id):
        self.closed.append(deal_id)
        return {"workflow": "close_position", "closed": True, "deal_id": deal_id}

    async def health(self):
        return {"status": "healthy"}

    async def balance(self):
        return {"equity": {"balance": 1000}}

    async def positions(self):
        return {"positions": []}

    async def orders(self):
        return {"workingOrders": []}


def close_preview(approved=True, reason=""):
    return {
        "workflow": "close_position_preview",
        "approved": approved,
        "reason": reason,
        "local_position": {
            "deal_id": "deal-1",
            "epic": "GOLD",
            "size": 3.66,
            "entry_price": 4394.3,
            "status": "OPEN",
        },
        "broker_position": {
            "deal_id": "deal-1",
            "epic": "GOLD",
            "direction": "SELL",
            "size": 3.66,
            "market_status": "TRADEABLE" if approved else "CLOSED",
            "estimated_close_price": 4378.35,
        },
        "risk": {"trading_mode": "live" if approved else "observe"},
    }


def install_store(monkeypatch, tmp_path):
    import app.execution as execution

    test_store = Store(str(tmp_path / "agent.sqlite3"))
    test_store.init()
    monkeypatch.setattr(execution, "store", test_store)
    return test_store


def test_create_close_ticket_from_rejected_preview_is_blocked(monkeypatch, tmp_path):
    import app.execution as execution

    store = install_store(monkeypatch, tmp_path)
    trader = CloseTrader(close_preview(approved=False, reason="trading_not_allowed mode=observe"))
    monkeypatch.setattr(execution, "trader_client", trader)

    result = asyncio.run(create_close_ticket({"deal_id": "deal-1", "reason": "Reduce exposure"}))

    ticket = result["ticket"]
    assert ticket["ticket_type"] == "close_position"
    assert ticket["deal_id"] == "deal-1"
    assert ticket["status"] == "blocked"
    assert ticket["risk"]["status"] == "blocked"
    assert "trading_not_allowed" in ticket["risk"]["errors"][0]
    assert ticket["confirmation_phrase"].startswith("CONFIRM CLOSE")
    assert store.get_ticket(ticket["id"])["ticket_type"] == "close_position"


def test_approve_close_ticket_requires_close_ticket_type(monkeypatch, tmp_path):
    store = install_store(monkeypatch, tmp_path)
    ticket = store.create_ticket(
        {
            "id": "T-open",
            "ticket_type": "open_position",
            "deal_id": None,
            "status": "pending_confirmation",
            "epic": "GOLD",
            "direction": "BUY",
            "size": 0.1,
            "order_type": "MARKET",
            "reason": "test",
            "invalidated_if": "test",
            "confidence": "medium",
            "risk": {"status": "approved", "errors": [], "warnings": []},
            "confirmation_phrase": "CONFIRM T-open GOLD BUY 0.1",
        }
    )

    result = asyncio.run(
        approve_close_ticket(
            {
                "ticket_id": ticket["id"],
                "confirmation_phrase": ticket["confirmation_phrase"],
            }
        )
    )

    assert result == {"approved": False, "reason": "ticket type is open_position"}


def test_execute_close_ticket_respects_writes_disabled(monkeypatch, tmp_path):
    import app.execution as execution

    store = install_store(monkeypatch, tmp_path)
    monkeypatch.setattr(execution.settings, "allow_trading_writes", False)
    ticket = store.create_ticket(
        {
            "id": "T-close",
            "ticket_type": "close_position",
            "deal_id": "deal-1",
            "status": "approved",
            "epic": "GOLD",
            "direction": "SELL",
            "size": 3.66,
            "order_type": "CLOSE",
            "level": 4378.35,
            "reason": "test",
            "invalidated_if": "test",
            "confidence": "medium",
            "risk": {"status": "approved", "errors": [], "warnings": []},
            "confirmation_phrase": "CONFIRM CLOSE T-close GOLD deal-1",
        }
    )

    result = asyncio.run(execute_close_ticket({"ticket_id": ticket["id"]}))

    assert result == {"executed": False, "reason": "trading writes are disabled"}


def test_execute_close_ticket_reruns_preview_then_closes(monkeypatch, tmp_path):
    import app.execution as execution

    store = install_store(monkeypatch, tmp_path)
    trader = CloseTrader(close_preview(approved=True))
    monkeypatch.setattr(execution.settings, "allow_trading_writes", True)
    monkeypatch.setattr(execution, "trader_client", trader)
    ticket = store.create_ticket(
        {
            "id": "T-close",
            "ticket_type": "close_position",
            "deal_id": "deal-1",
            "status": "approved",
            "epic": "GOLD",
            "direction": "SELL",
            "size": 3.66,
            "order_type": "CLOSE",
            "level": 4378.35,
            "reason": "test",
            "invalidated_if": "test",
            "confidence": "medium",
            "risk": {"status": "approved", "errors": [], "warnings": []},
            "confirmation_phrase": "CONFIRM CLOSE T-close GOLD deal-1",
        }
    )

    result = asyncio.run(execute_close_ticket({"ticket_id": ticket["id"]}))

    assert result["executed"] is True
    assert result["ticket"]["status"] == "executed"
    assert trader.preview_calls == 1
    assert trader.closed == ["deal-1"]


def test_execute_close_ticket_blocks_when_fresh_preview_rejects(monkeypatch, tmp_path):
    import app.execution as execution

    store = install_store(monkeypatch, tmp_path)
    trader = CloseTrader(close_preview(approved=False, reason="market_not_tradeable status=CLOSED"))
    monkeypatch.setattr(execution.settings, "allow_trading_writes", True)
    monkeypatch.setattr(execution, "trader_client", trader)
    ticket = store.create_ticket(
        {
            "id": "T-close",
            "ticket_type": "close_position",
            "deal_id": "deal-1",
            "status": "approved",
            "epic": "GOLD",
            "direction": "SELL",
            "size": 3.66,
            "order_type": "CLOSE",
            "level": 4378.35,
            "reason": "test",
            "invalidated_if": "test",
            "confidence": "medium",
            "risk": {"status": "approved", "errors": [], "warnings": []},
            "confirmation_phrase": "CONFIRM CLOSE T-close GOLD deal-1",
        }
    )

    result = asyncio.run(execute_close_ticket({"ticket_id": ticket["id"]}))

    assert result["executed"] is False
    assert result["reason"] == "fresh close preview blocked execution"
    assert trader.closed == []
    assert store.get_ticket(ticket["id"])["status"] == "blocked"
