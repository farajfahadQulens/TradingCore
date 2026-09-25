import asyncio

from app.store import Store
from app.tools import (
    get_trading_profile,
    list_agent_memories,
    remember_operational_note,
    remember_strategy_note,
    remember_trading_preference,
    search_agent_memories,
)


def test_store_creates_searches_and_deactivates_memory(tmp_path):
    store = Store(str(tmp_path / "agent.sqlite3"))
    store.init()

    memory = store.create_memory(
        memory_type="risk_preference",
        scope="risk",
        content="Always require a stop before preparing a ticket.",
        source="test",
        tags=["risk", "tickets"],
    )

    assert memory["id"]
    assert memory["active"] is True
    assert store.search_memories("stop")[0]["content"] == memory["content"]

    deactivated = store.deactivate_memory(memory["id"])

    assert deactivated["active"] is False
    assert store.search_memories("stop") == []
    assert store.search_memories("stop", active_only=False)[0]["id"] == memory["id"]


def test_seed_memory_once_does_not_duplicate(tmp_path):
    store = Store(str(tmp_path / "agent.sqlite3"))
    store.init()

    first = store.seed_memory_once(
        memory_type="operational_note",
        scope="operations",
        content="Capital Trader runs at http://127.0.0.1:8000.",
        source="test_seed",
        tags=["capital_trader"],
    )
    second = store.seed_memory_once(
        memory_type="operational_note",
        scope="operations",
        content="Capital Trader runs at http://127.0.0.1:8000.",
        source="test_seed",
        tags=["capital_trader"],
    )

    assert first["id"] == second["id"]
    assert len(store.list_memories()) == 1


def test_memory_tools_use_store(monkeypatch, tmp_path):
    test_store = Store(str(tmp_path / "agent.sqlite3"))
    test_store.init()

    import app.tools as tools

    monkeypatch.setattr(tools, "store", test_store)

    pref = asyncio.run(
        remember_trading_preference(
            {
                "content": "Prefer small ticket size while testing.",
                "tags": ["risk", "testing"],
            }
        )
    )
    strategy = asyncio.run(
        remember_strategy_note(
            {
                "content": "Moving average backtests are research only.",
                "tags": ["research"],
            }
        )
    )
    ops = asyncio.run(
        remember_operational_note(
            {
                "content": "TradingCore owns Postgres and Redis.",
                "tags": ["tradingcore"],
            }
        )
    )

    assert pref["remembered"] is True
    assert strategy["memory"]["scope"] == "strategy"
    assert ops["memory"]["memory_type"] == "operational_note"

    listed = asyncio.run(list_agent_memories({"limit": 10}))
    searched = asyncio.run(search_agent_memories({"query": "research"}))
    profile = asyncio.run(get_trading_profile({}))

    assert len(listed["memories"]) == 3
    assert searched["memories"][0]["memory_type"] == "strategy_note"
    assert "trading_preference" in profile["profile"]
