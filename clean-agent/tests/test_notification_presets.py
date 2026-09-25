import asyncio

from app import main
from app.store import Store


class FakeTrader:
    async def positions(self):
        return {
            "positions": [
                {"position": {"epic": "GOLD", "upl": 550.0}},
            ]
        }


def test_position_notification_presets_create_pl_bundle(monkeypatch, tmp_path):
    store = Store(str(tmp_path / "agent.sqlite3"))
    store.init()
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "trader_client", FakeTrader())

    req = main.PositionPresetRequest(epic="GOLD", delta=50, cooldown_seconds=900)
    result = asyncio.run(main.create_position_notification_presets(req))

    assert result["current_upl"] == 550.0
    assert len(result["rules"]) == 3
    assert {rule["rule_type"] for rule in result["rules"]} == {"market_open", "position_pl"}
    thresholds = sorted(rule["threshold"] for rule in result["rules"] if rule["threshold"] is not None)
    assert thresholds == [500.0, 600.0]


def test_position_notification_presets_reuse_existing_market_open(monkeypatch, tmp_path):
    store = Store(str(tmp_path / "agent.sqlite3"))
    store.init()
    existing = store.create_notification_rule(rule_type="market_open", epic="GOLD", condition="open")
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "trader_client", FakeTrader())

    req = main.PositionPresetRequest(epic="GOLD", delta=50, cooldown_seconds=900)
    result = asyncio.run(main.create_position_notification_presets(req))

    assert result["rules"][0]["id"] == existing["id"]
    assert len(store.list_notification_rules(limit=10)) == 3


def test_position_notification_presets_accept_gold_alias(monkeypatch, tmp_path):
    store = Store(str(tmp_path / "agent.sqlite3"))
    store.init()
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "trader_client", FakeTrader())

    req = main.PositionPresetRequest(epic="XAUUSD", delta=50, cooldown_seconds=900)
    result = asyncio.run(main.create_position_notification_presets(req))

    assert result["epic"] == "GOLD"
    assert {rule["epic"] for rule in result["rules"]} == {"GOLD"}
