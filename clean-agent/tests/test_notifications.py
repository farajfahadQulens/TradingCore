import asyncio

from app.notifications import NotificationEngine
from app.store import Store


class FakeTrader:
    def __init__(self, market=None, positions=None, deep_health=None):
        self._market = market
        self._positions = positions or {"positions": []}
        self._deep_health = deep_health or {"status": "healthy"}

    async def market(self, epic):
        return self._market

    async def positions(self):
        return self._positions

    async def deep_health(self):
        return self._deep_health


class FakeNotifier:
    def __init__(self):
        self.sent = []

    async def send(self, title, message):
        self.sent.append({"title": title, "message": message})
        return {"delivered": True}


def test_notification_rule_persistence(tmp_path):
    store = Store(str(tmp_path / "agent.sqlite3"))
    store.init()

    rule = store.create_notification_rule(
        rule_type="price",
        epic="gold",
        condition="below",
        threshold=4375,
        message="GOLD watch",
    )

    assert rule["epic"] == "GOLD"
    assert rule["threshold"] == 4375
    assert rule["state"] == "inactive"
    assert rule["notify_recovery"] is True
    assert store.list_notification_rules()[0]["id"] == rule["id"]


def test_price_alert_triggers_and_records_event(tmp_path):
    store = Store(str(tmp_path / "agent.sqlite3"))
    store.init()
    rule = store.create_notification_rule(
        rule_type="price",
        epic="GOLD",
        condition="below",
        threshold=4380,
        cooldown_seconds=900,
    )
    notifier = FakeNotifier()
    engine = NotificationEngine(
        db=store,
        trader=FakeTrader({"marketStatus": "TRADEABLE", "bid": 4377.85, "offer": 4378.35}),
        notifier=notifier,
    )

    result = asyncio.run(engine.evaluate_once())

    assert len(result["triggered"]) == 1
    assert result["triggered"][0]["rule_id"] == rule["id"]
    assert result["triggered"][0]["delivered"] is True
    assert notifier.sent[0]["title"] == "GOLD price below 4380.0"
    assert "Bid: 4377.85" in notifier.sent[0]["message"]
    assert "Dashboard:" in notifier.sent[0]["message"]
    refreshed = store.get_notification_rule(rule["id"])
    assert refreshed["last_triggered_at"] is not None
    assert refreshed["state"] == "active"


def test_market_open_alert_triggers_once_inside_cooldown(tmp_path):
    store = Store(str(tmp_path / "agent.sqlite3"))
    store.init()
    store.create_notification_rule(
        rule_type="market_open",
        epic="GOLD",
        condition="open",
        cooldown_seconds=3600,
    )
    notifier = FakeNotifier()
    engine = NotificationEngine(
        db=store,
        trader=FakeTrader({"marketStatus": "TRADEABLE", "bid": 4377.85, "offer": 4378.35}),
        notifier=notifier,
    )

    first = asyncio.run(engine.evaluate_once())
    second = asyncio.run(engine.evaluate_once())

    assert len(first["triggered"]) == 1
    assert len(second["triggered"]) == 0
    assert len(notifier.sent) == 1


def test_market_open_alert_sends_recovery_when_condition_clears(tmp_path):
    store = Store(str(tmp_path / "agent.sqlite3"))
    store.init()
    rule = store.create_notification_rule(
        rule_type="market_open",
        epic="GOLD",
        condition="open",
        cooldown_seconds=3600,
    )
    notifier = FakeNotifier()
    trader = FakeTrader({"marketStatus": "TRADEABLE", "bid": 4377.85, "offer": 4378.35})
    engine = NotificationEngine(db=store, trader=trader, notifier=notifier)

    first = asyncio.run(engine.evaluate_once())
    trader._market = {"marketStatus": "CLOSED", "bid": 4377.85, "offer": 4378.35}
    second = asyncio.run(engine.evaluate_once())

    assert len(first["triggered"]) == 1
    assert len(second["triggered"]) == 1
    assert notifier.sent[1]["title"] == "GOLD market no longer open"
    assert store.get_notification_rule(rule["id"])["state"] == "recovered"


def test_position_pl_alert_triggers_on_aggregate_upl(tmp_path):
    store = Store(str(tmp_path / "agent.sqlite3"))
    store.init()
    store.create_notification_rule(
        rule_type="position_pl",
        epic="GOLD",
        condition="above",
        threshold=500,
        cooldown_seconds=900,
    )
    notifier = FakeNotifier()
    engine = NotificationEngine(
        db=store,
        trader=FakeTrader(
            positions={
                "positions": [
                    {"position": {"epic": "GOLD", "upl": 450}},
                    {"position": {"epic": "GOLD", "upl": 75}},
                ]
            }
        ),
        notifier=notifier,
    )

    result = asyncio.run(engine.evaluate_once())

    assert len(result["triggered"]) == 1
    assert result["triggered"][0]["value"] == 525
    assert notifier.sent[0]["title"] == "GOLD P/L above 500.0"


def test_health_alert_triggers_when_degraded(tmp_path):
    store = Store(str(tmp_path / "agent.sqlite3"))
    store.init()
    store.create_notification_rule(
        rule_type="health",
        epic="CAPITAL_TRADER",
        condition="degraded",
        cooldown_seconds=900,
    )
    notifier = FakeNotifier()
    engine = NotificationEngine(
        db=store,
        trader=FakeTrader(deep_health={"status": "degraded"}),
        notifier=notifier,
    )

    result = asyncio.run(engine.evaluate_once())

    assert len(result["triggered"]) == 1
    assert result["triggered"][0]["value"] == 1.0
    assert notifier.sent[0]["title"] == "Capital Trader health degraded"
