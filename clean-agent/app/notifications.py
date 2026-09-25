"""Notification rules and Telegram delivery for Clean Agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import settings
from app.store import Store, store
from app.trader import TraderClient, trader_client


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _market_status(payload: dict[str, Any]) -> str:
    return str(
        payload.get("marketStatus")
        or payload.get("market_status")
        or payload.get("snapshot", {}).get("marketStatus")
        or payload.get("status")
        or "unknown"
    ).upper()


def _price_value(payload: dict[str, Any]) -> float | None:
    snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
    candidates = (
        "bid",
        "offer",
        "ask",
    )
    for key in candidates:
        value = payload.get(key, snapshot.get(key))
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    bid = payload.get("bid", snapshot.get("bid"))
    offer = payload.get("offer", payload.get("ask", snapshot.get("offer", snapshot.get("ask"))))
    try:
        return (float(bid) + float(offer)) / 2
    except (TypeError, ValueError):
        return None


def _position_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("positions", payload)
    return rows if isinstance(rows, list) else []


def _position_upl_total(payload: dict[str, Any], epic: str) -> float | None:
    total = 0.0
    seen = False
    for row in _position_rows(payload):
        position = row.get("position", row) if isinstance(row, dict) else {}
        market = row.get("market", {}) if isinstance(row, dict) else {}
        row_epic = str(position.get("epic") or market.get("epic") or "").upper()
        if row_epic != epic.upper():
            continue
        value = position.get("upl", position.get("profitLoss", position.get("pnl")))
        try:
            total += float(value)
            seen = True
        except (TypeError, ValueError):
            continue
    return total if seen else None


def _deep_health_status(payload: dict[str, Any]) -> str:
    return str(payload.get("status") or "unknown").lower()


def _dashboard_url() -> str:
    return f"http://{settings.agent_host}:{settings.agent_port}/"


def _market_line(payload: dict[str, Any]) -> str:
    bid = payload.get("bid", payload.get("snapshot", {}).get("bid"))
    offer = payload.get("offer", payload.get("ask", payload.get("snapshot", {}).get("offer")))
    return f"Status: {_market_status(payload)}\nBid: {bid}\nOffer: {offer}"


@dataclass(frozen=True)
class RuleEvaluation:
    """Result of evaluating one rule against fresh broker data."""

    passed: bool
    value: float | None
    context: dict[str, Any]


class TelegramNotifier:
    """Small Telegram Bot API sender."""

    def __init__(self, bot_token: str | None = None, chat_id: str | None = None) -> None:
        self.bot_token = bot_token if bot_token is not None else settings.telegram_bot_token
        self.chat_id = chat_id if chat_id is not None else settings.telegram_chat_id

    def configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    async def send(self, title: str, message: str) -> dict[str, Any]:
        """Send one Telegram message or return a configuration error."""

        if not self.configured():
            return {"delivered": False, "error": "telegram is not configured"}

        text = f"{title}\n{message}"
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=settings.telegram_timeout_seconds) as client:
            response = await client.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()
            return {"delivered": True, "response": response.json()}


class NotificationEngine:
    """Evaluate alert rules and record delivery outcomes."""

    def __init__(
        self,
        *,
        db: Store = store,
        trader: TraderClient = trader_client,
        notifier: TelegramNotifier | None = None,
    ) -> None:
        self.store = db
        self.trader = trader
        self.notifier = notifier or TelegramNotifier()

    async def send_test(self, message: str = "TradingCore Telegram notifications are connected.") -> dict[str, Any]:
        """Send a test Telegram message and record the outcome."""

        title = "TradingCore notification test"
        try:
            result = await self.notifier.send(title, message)
            error = result.get("error")
            delivered = bool(result.get("delivered"))
        except Exception as exc:
            delivered = False
            error = str(exc)
        event = self.store.record_notification_event(
            rule_id=None,
            channel="telegram",
            title=title,
            message=message,
            delivered=delivered,
            error=error,
            metadata={"kind": "test"},
        )
        return {"delivered": delivered, "event": event}

    async def evaluate_once(self) -> dict[str, Any]:
        """Evaluate active rules once."""

        rules = self.store.list_notification_rules(limit=100, enabled=True)
        triggered: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        market_cache: dict[str, dict[str, Any]] = {}
        positions: dict[str, Any] | None = None
        deep_health: dict[str, Any] | None = None

        for rule in rules:
            epic = rule["epic"]
            try:
                if rule["rule_type"] in {"market_open", "price"}:
                    if epic not in market_cache:
                        market_cache[epic] = await self.trader.market(epic)
                    event = await self._evaluate_rule(rule, market_cache[epic])
                elif rule["rule_type"] == "position_pl":
                    if positions is None:
                        positions = await self.trader.positions()
                    event = await self._evaluate_rule(rule, positions)
                elif rule["rule_type"] == "health":
                    if deep_health is None:
                        deep_health = await self.trader.deep_health()
                    event = await self._evaluate_rule(rule, deep_health)
                else:
                    event = None
                if event:
                    triggered.append(event)
            except Exception as exc:
                errors.append({"rule_id": rule["id"], "error": str(exc)})

        return {"checked": len(rules), "triggered": triggered, "errors": errors}

    def _in_cooldown(self, rule: dict[str, Any]) -> bool:
        last = _parse_time(rule.get("last_triggered_at"))
        if last is None:
            return False
        cooldown = max(0, int(rule.get("cooldown_seconds") or 0))
        return (datetime.now(UTC) - last).total_seconds() < cooldown

    async def _evaluate_rule(self, rule: dict[str, Any], market: dict[str, Any]) -> dict[str, Any] | None:
        evaluation = self._condition(rule, market)
        if evaluation is None:
            self.store.update_notification_rule(rule["id"], last_checked_at=datetime.now(UTC).isoformat())
            return None

        state = str(rule.get("state") or "inactive")
        if evaluation.passed:
            if state == "active" or self._in_cooldown(rule):
                self.store.update_notification_rule(
                    rule["id"],
                    last_checked_at=datetime.now(UTC).isoformat(),
                    last_value=evaluation.value,
                )
                return None
            event = await self._send_rule_event(rule, evaluation, recovery=False)
            self.store.update_notification_rule(rule["id"], state="active")
            return event

        if state == "active":
            self.store.update_notification_rule(
                rule["id"],
                state="recovered",
                last_checked_at=datetime.now(UTC).isoformat(),
                last_value=evaluation.value,
            )
            if rule.get("notify_recovery", True):
                return await self._send_rule_event(rule, evaluation, recovery=True)
            return None

        self.store.update_notification_rule(
            rule["id"],
            state="inactive" if state not in {"inactive", "recovered"} else state,
            last_checked_at=datetime.now(UTC).isoformat(),
            last_value=evaluation.value,
        )
        return None

    def _condition(self, rule: dict[str, Any], market: dict[str, Any]) -> RuleEvaluation | None:
        value: float | None = None
        passed = False
        rule_type = rule["rule_type"]
        condition = rule["condition"]

        if rule_type == "market_open":
            status = _market_status(market)
            value = 1.0 if status == "TRADEABLE" else 0.0
            passed = status == "TRADEABLE"
        elif rule_type == "price":
            value = _price_value(market)
            threshold = rule.get("threshold")
            if value is None or threshold is None:
                return None
            if condition == "above":
                passed = value >= float(threshold)
            elif condition == "below":
                passed = value <= float(threshold)
        elif rule_type == "position_pl":
            value = _position_upl_total(market, rule["epic"])
            threshold = rule.get("threshold")
            if value is None or threshold is None:
                return None
            if condition == "above":
                passed = value >= float(threshold)
            elif condition == "below":
                passed = value <= float(threshold)
        elif rule_type == "health":
            status = _deep_health_status(market)
            value = 1.0 if status in {"degraded", "unhealthy", "error"} else 0.0
            passed = condition == "degraded" and value == 1.0
        else:
            return None

        return RuleEvaluation(passed=passed, value=value, context=market)

    async def _send_rule_event(
        self,
        rule: dict[str, Any],
        evaluation: RuleEvaluation,
        *,
        recovery: bool,
    ) -> dict[str, Any]:
        title = self._recovery_title(rule) if recovery else self._title(rule)
        message = self._recovery_message(rule, evaluation.context, evaluation.value) if recovery else self._message(
            rule, evaluation.context, evaluation.value
        )
        try:
            result = await self.notifier.send(title, message)
            delivered = bool(result.get("delivered"))
            error = result.get("error")
        except Exception as exc:
            delivered = False
            error = str(exc)
        return self.store.record_notification_event(
            rule_id=rule["id"],
            channel=rule["channel"],
            title=title,
            message=message,
            value=evaluation.value,
            delivered=delivered,
            error=error,
            metadata={"kind": "recovery" if recovery else "alert", "context": evaluation.context},
        )

    def _title(self, rule: dict[str, Any]) -> str:
        if rule["rule_type"] == "market_open":
            return f"{rule['epic']} market is open"
        if rule["rule_type"] == "position_pl":
            return f"{rule['epic']} P/L {rule['condition']} {rule.get('threshold')}"
        if rule["rule_type"] == "health":
            return "Capital Trader health degraded"
        threshold = rule.get("threshold")
        return f"{rule['epic']} price {rule['condition']} {threshold}"

    def _recovery_title(self, rule: dict[str, Any]) -> str:
        if rule["rule_type"] == "market_open":
            return f"{rule['epic']} market no longer open"
        if rule["rule_type"] == "position_pl":
            return f"{rule['epic']} P/L recovered"
        if rule["rule_type"] == "health":
            return "Capital Trader health recovered"
        return f"{rule['epic']} price alert cleared"

    def _message(self, rule: dict[str, Any], market: dict[str, Any], value: float | None) -> str:
        custom = rule.get("message")
        if custom:
            return custom
        status = _market_status(market)
        if rule["rule_type"] == "market_open":
            return (
                f"{rule['epic']} is {status}.\n"
                f"{_market_line(market)}\n"
                "Trading mode and ticket guards still apply.\n"
                f"Dashboard: {_dashboard_url()}"
            )
        if rule["rule_type"] == "position_pl":
            return (
                f"{rule['epic']} open P/L matched {rule['condition']} {rule['threshold']}.\n"
                f"Current P/L: {value}\n"
                f"Dashboard: {_dashboard_url()}"
            )
        if rule["rule_type"] == "health":
            return (
                f"Capital Trader health is {_deep_health_status(market)}.\n"
                "Check dashboard before trading.\n"
                f"Dashboard: {_dashboard_url()}"
            )
        return (
            f"{rule['epic']} matched {rule['condition']} {rule['threshold']}.\n"
            f"Current value: {value}\n"
            f"{_market_line(market)}\n"
            f"Dashboard: {_dashboard_url()}"
        )

    def _recovery_message(self, rule: dict[str, Any], market: dict[str, Any], value: float | None) -> str:
        if rule["rule_type"] == "market_open":
            return f"{rule['epic']} is now {_market_status(market)}.\n{_market_line(market)}\nDashboard: {_dashboard_url()}"
        if rule["rule_type"] == "position_pl":
            return (
                f"{rule['epic']} open P/L no longer matches {rule['condition']} {rule['threshold']}.\n"
                f"Current P/L: {value}\n"
                f"Dashboard: {_dashboard_url()}"
            )
        if rule["rule_type"] == "health":
            return f"Capital Trader health is {_deep_health_status(market)}.\nDashboard: {_dashboard_url()}"
        return (
            f"{rule['epic']} no longer matches {rule['condition']} {rule['threshold']}.\n"
            f"Current value: {value}\n"
            f"{_market_line(market)}\n"
            f"Dashboard: {_dashboard_url()}"
        )


notification_engine = NotificationEngine()


async def notification_watch_loop(engine: NotificationEngine = notification_engine) -> None:
    """Background loop for notification rules."""

    while True:
        try:
            await engine.evaluate_once()
        except Exception as exc:
            engine.store.audit("notification_watcher_error", {"error": str(exc)})
        await asyncio.sleep(max(5.0, float(settings.notification_poll_seconds)))
