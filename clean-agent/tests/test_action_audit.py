import asyncio

from app.store import Store
from app.tools import get_action_audit


def open_ticket(ticket_id="T-open"):
    return {
        "id": ticket_id,
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
        "confirmation_phrase": f"CONFIRM {ticket_id} GOLD BUY 0.1",
    }


def close_ticket(ticket_id="T-close"):
    ticket = open_ticket(ticket_id)
    ticket.update(
        {
            "ticket_type": "close_position",
            "deal_id": "deal-1",
            "status": "blocked",
            "direction": "SELL",
            "size": 3.66,
            "order_type": "CLOSE",
            "level": 4378.35,
            "risk": {
                "status": "blocked",
                "errors": ["trading_not_allowed mode=observe"],
                "warnings": ["market status is CLOSED"],
            },
            "confirmation_phrase": f"CONFIRM CLOSE {ticket_id} GOLD deal-1",
        }
    )
    return ticket


def test_action_audit_merges_audit_events_and_ticket_state(tmp_path):
    store = Store(str(tmp_path / "agent.sqlite3"))
    store.init()
    ticket = store.create_ticket(close_ticket())
    store.audit("close_ticket_execution_blocked", {"ticket_id": ticket["id"], "reason": "fresh close preview blocked"})

    actions = store.action_audit(limit=10)

    assert actions[0]["source"] in {"audit", "ticket"}
    assert any(action["action"] == "ticket_current_state" for action in actions)
    assert any(action["action"] == "close_ticket_execution_blocked" for action in actions)
    state = next(action for action in actions if action["action"] == "ticket_current_state")
    assert state["ticket_type"] == "close_position"
    assert state["status"] == "blocked"
    assert "close ticket" in state["summary"]


def test_action_audit_filters_by_ticket_id(tmp_path):
    store = Store(str(tmp_path / "agent.sqlite3"))
    store.init()
    store.create_ticket(open_ticket("T-open"))
    store.create_ticket(close_ticket("T-close"))

    actions = store.action_audit(limit=20, ticket_id="T-close")

    assert actions
    assert {action["ticket_id"] for action in actions} == {"T-close"}


def test_get_action_audit_tool_uses_store(monkeypatch, tmp_path):
    import app.tools as tools

    store = Store(str(tmp_path / "agent.sqlite3"))
    store.init()
    store.create_ticket(open_ticket())
    monkeypatch.setattr(tools, "store", store)

    result = asyncio.run(get_action_audit({"limit": 5}))

    assert result["actions"]
    assert result["actions"][0]["source"] in {"audit", "ticket"}
