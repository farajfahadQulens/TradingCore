"""Tool definitions and implementations for the clean agent.

Tools return plain Python values. `app.main` converts them into tool messages
for the model. Read-only tools are always available; order submission is gated
by settings and an explicit confirmation phrase.
"""

from typing import Any, Awaitable, Callable

import httpx

from app.config import settings
from app.canvas import CanvasConfigurationError, canvas_client, canvas_status
from app.execution import (
    approve_close_ticket,
    approve_ticket,
    create_close_ticket,
    create_trade_ticket,
    execute_close_ticket,
    execute_ticket,
)
from app.notifications import notification_engine
from app.research import ResearchDataError, normalize_prices, run_moving_average_backtest
from app.store import store
from app.trader import normalize_epic, trader_client

ToolFunction = Callable[[dict[str, Any]], Awaitable[Any]]


CAPITAL_TRADER_CAPABILITIES: dict[str, Any] = {
    "read_tools": {
        "get_health": "Check whether Capital Trader is reachable.",
        "get_balance": "Read account equity, balance, available funds, and profit/loss.",
        "list_positions": "Read open broker positions.",
        "list_orders": "Read broker working orders.",
        "get_market_info": "Read Capital Trader market metadata for an epic.",
        "get_market_prices": "Read recent broker candles/prices for an epic.",
        "preview_trade_risk": "Ask Capital Trader whether a proposed trade would pass risk without creating an order.",
        "preview_close_position": "Ask Capital Trader whether an existing position could be closed without closing it.",
        "get_capital_trader_snapshot": "Read health, balance, positions, and orders in one call.",
        "list_notification_rules": "Read active Telegram notification rules.",
    },
    "write_flow": {
        "create_trade_ticket": "Prepare a proposed position/order. This does not place a broker order.",
        "approve_ticket": "Approve a pending ticket with its exact confirmation phrase.",
        "execute_ticket": "Submit an approved ticket to Capital Trader after fresh checks.",
        "create_close_ticket": "Prepare a close-position ticket. This does not close the broker position.",
        "approve_close_ticket": "Approve a pending close ticket with its exact confirmation phrase.",
        "execute_close_ticket": "Submit an approved close ticket to Capital Trader after fresh close preview.",
    },
    "safety": {
        "direct_submit_order": "disabled",
        "trading_writes_enabled": settings.allow_trading_writes,
        "required_live_flow": ["create_trade_ticket", "approve_ticket", "execute_ticket"],
        "required_close_flow": ["create_close_ticket", "approve_close_ticket", "execute_close_ticket"],
        "notes": [
            "Opening or adding a position means creating a trade ticket first.",
            "Closing a position means creating a close ticket first.",
            "The agent must not claim execution unless execute_ticket returns executed=true.",
            "The agent must not claim a close unless execute_close_ticket returns executed=true.",
            "Capital Trader and Clean Agent both default to read/observe behavior.",
        ],
    },
}


async def get_capital_trader_capabilities(_args: dict[str, Any]) -> dict[str, Any]:
    """Describe the Capital Trader tools and safe order flow available to the agent."""

    return CAPITAL_TRADER_CAPABILITIES


async def get_health(_args: dict[str, Any]) -> dict[str, Any]:
    """Check whether Capital Trader is reachable."""

    return await trader_client.health()


async def get_balance(_args: dict[str, Any]) -> dict[str, Any]:
    """Fetch current account equity/balance from Capital Trader."""

    return await trader_client.balance()


async def list_positions(_args: dict[str, Any]) -> dict[str, Any]:
    """Fetch open broker positions."""

    return await trader_client.positions()


async def list_orders(_args: dict[str, Any]) -> dict[str, Any]:
    """Fetch pending broker working orders."""

    return await trader_client.orders()


async def get_capital_trader_snapshot(_args: dict[str, Any]) -> dict[str, Any]:
    """Fetch the main read-only Capital Trader account state in one call."""

    snapshot: dict[str, Any] = {}
    calls = {
        "health": trader_client.health,
        "balance": trader_client.balance,
        "positions": trader_client.positions,
        "orders": trader_client.orders,
    }
    for key, fn in calls.items():
        try:
            snapshot[key] = await fn()
        except Exception as exc:
            snapshot[f"{key}_error"] = str(exc)
    return snapshot


async def get_market_prices(args: dict[str, Any]) -> dict[str, Any]:
    """Fetch recent candles/prices for a market epic."""

    epic = normalize_epic(str(args["epic"]))
    resolution = str(args.get("resolution", "MINUTE"))
    max_points = int(args.get("max_points", 20))
    return await trader_client.prices(epic=epic, resolution=resolution, max_points=max_points)


async def get_market_info(args: dict[str, Any]) -> dict[str, Any]:
    """Fetch Capital Trader market metadata for one epic."""

    return await trader_client.market(normalize_epic(str(args["epic"])))


async def preview_trade_risk(args: dict[str, Any]) -> dict[str, Any]:
    """Preview Capital Trader risk for a proposed trade without execution."""

    payload = {
        "epic": normalize_epic(str(args["epic"])),
        "direction": str(args["direction"]).upper(),
        "size": float(args["size"]),
        "order_type": str(args.get("order_type", "MARKET")).upper(),
    }
    for key in ("level", "limit_distance", "stop_distance"):
        if args.get(key) is not None:
            payload[key] = float(args[key])
    return await trader_client.risk_preview(payload)


async def preview_close_position(args: dict[str, Any]) -> dict[str, Any]:
    """Preview closing an existing Capital Trader position without execution."""

    return await trader_client.close_preview(str(args["deal_id"]))


async def submit_order(args: dict[str, Any]) -> dict[str, Any]:
    """Reject direct order submission.

    The serious flow is create ticket -> approve ticket -> execute ticket. The
    function remains for compatibility with earlier prompts but never submits.
    """

    return {
        "submitted": False,
        "reason": "direct order submission is disabled; create and approve a trade ticket first",
        "required_flow": ["create_trade_ticket", "approve_ticket", "execute_ticket"],
    }


async def get_dashboard(_args: dict[str, Any]) -> dict[str, Any]:
    """Return local dashboard state."""

    return store.dashboard()


async def get_action_audit(args: dict[str, Any]) -> dict[str, Any]:
    """Return a unified action timeline from tickets and audit events."""

    return {
        "actions": store.action_audit(
            limit=int(args.get("limit", 50)),
            ticket_id=args.get("ticket_id"),
        )
    }


async def set_mode(args: dict[str, Any]) -> dict[str, Any]:
    """Set the agent operating mode."""

    mode = str(args["mode"]).lower()
    allowed = {"observe", "analyze", "prepare", "confirm", "execute"}
    if mode not in allowed:
        return {"changed": False, "reason": f"mode must be one of {sorted(allowed)}"}
    return {"changed": True, "mode": store.set_mode(mode)}


async def list_trade_tickets(args: dict[str, Any]) -> dict[str, Any]:
    """List persisted trade tickets."""

    limit = int(args.get("limit", 25))
    status = args.get("status")
    return {"tickets": store.list_tickets(limit=limit, status=status)}


async def list_agent_memories(args: dict[str, Any]) -> dict[str, Any]:
    """List active agent memories."""

    return {
        "memories": store.list_memories(
            limit=int(args.get("limit", 25)),
            memory_type=args.get("memory_type"),
            scope=args.get("scope"),
            active_only=bool(args.get("active_only", True)),
        )
    }


async def search_agent_memories(args: dict[str, Any]) -> dict[str, Any]:
    """Search agent memories."""

    query = str(args["query"]).strip()
    if not query:
        return {"memories": []}
    return {
        "memories": store.search_memories(
            query,
            limit=int(args.get("limit", 10)),
            active_only=bool(args.get("active_only", True)),
        )
    }


async def get_trading_profile(_args: dict[str, Any]) -> dict[str, Any]:
    """Return active memories relevant to trading behavior."""

    memories = store.list_memories(limit=100)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for memory in memories:
        if memory["scope"] in {"trading", "risk", "strategy", "operations"}:
            grouped.setdefault(memory["memory_type"], []).append(memory)
    return {
        "rule": "Memory stores preferences and lessons. Live broker facts must come from Capital Trader tools.",
        "profile": grouped,
    }


async def remember_trading_preference(args: dict[str, Any]) -> dict[str, Any]:
    """Remember one trading or risk preference."""

    memory = store.create_memory(
        memory_type=str(args.get("memory_type", "trading_preference")),
        scope=str(args.get("scope", "trading")),
        content=str(args["content"]).strip(),
        source=str(args.get("source", "user")),
        confidence=float(args.get("confidence", 1.0)),
        tags=[str(tag) for tag in args.get("tags", ["trading"])],
    )
    return {"remembered": True, "memory": memory}


async def remember_strategy_note(args: dict[str, Any]) -> dict[str, Any]:
    """Remember one research or strategy note."""

    memory = store.create_memory(
        memory_type="strategy_note",
        scope="strategy",
        content=str(args["content"]).strip(),
        source=str(args.get("source", "user")),
        confidence=float(args.get("confidence", 1.0)),
        tags=[str(tag) for tag in args.get("tags", ["strategy"])],
    )
    return {"remembered": True, "memory": memory}


async def remember_operational_note(args: dict[str, Any]) -> dict[str, Any]:
    """Remember one operational fact about the local stack."""

    memory = store.create_memory(
        memory_type="operational_note",
        scope="operations",
        content=str(args["content"]).strip(),
        source=str(args.get("source", "user")),
        confidence=float(args.get("confidence", 1.0)),
        tags=[str(tag) for tag in args.get("tags", ["operations"])],
    )
    return {"remembered": True, "memory": memory}


async def deactivate_memory(args: dict[str, Any]) -> dict[str, Any]:
    """Deactivate one memory by id."""

    memory = store.deactivate_memory(int(args["memory_id"]))
    return {"deactivated": memory is not None, "memory": memory}


async def create_price_alert(args: dict[str, Any]) -> dict[str, Any]:
    """Create a Telegram price threshold alert."""

    condition = str(args["condition"]).lower()
    if condition not in {"above", "below"}:
        return {"created": False, "reason": "condition must be above or below"}
    rule = store.create_notification_rule(
        rule_type="price",
        epic=normalize_epic(str(args["epic"])),
        condition=condition,
        threshold=float(args["threshold"]),
        channel="telegram",
        message=str(args.get("message", "")),
        cooldown_seconds=int(args.get("cooldown_seconds", 900)),
        notify_recovery=bool(args.get("notify_recovery", True)),
    )
    return {"created": True, "rule": rule}


async def create_market_open_alert(args: dict[str, Any]) -> dict[str, Any]:
    """Create a Telegram alert for when a market becomes tradeable."""

    rule = store.create_notification_rule(
        rule_type="market_open",
        epic=normalize_epic(str(args["epic"])),
        condition="open",
        channel="telegram",
        message=str(args.get("message", "")),
        cooldown_seconds=int(args.get("cooldown_seconds", 3600)),
        notify_recovery=bool(args.get("notify_recovery", True)),
    )
    return {"created": True, "rule": rule}


async def create_position_pl_alert(args: dict[str, Any]) -> dict[str, Any]:
    """Create a Telegram alert for aggregate open P/L on one epic."""

    condition = str(args["condition"]).lower()
    if condition not in {"above", "below"}:
        return {"created": False, "reason": "condition must be above or below"}
    rule = store.create_notification_rule(
        rule_type="position_pl",
        epic=normalize_epic(str(args["epic"])),
        condition=condition,
        threshold=float(args["threshold"]),
        channel="telegram",
        message=str(args.get("message", "")),
        cooldown_seconds=int(args.get("cooldown_seconds", 900)),
        notify_recovery=bool(args.get("notify_recovery", True)),
    )
    return {"created": True, "rule": rule}


async def create_health_alert(args: dict[str, Any]) -> dict[str, Any]:
    """Create a Telegram alert when Capital Trader health is degraded."""

    rule = store.create_notification_rule(
        rule_type="health",
        epic=str(args.get("epic", "CAPITAL_TRADER")),
        condition="degraded",
        channel="telegram",
        message=str(args.get("message", "")),
        cooldown_seconds=int(args.get("cooldown_seconds", 900)),
        notify_recovery=bool(args.get("notify_recovery", True)),
    )
    return {"created": True, "rule": rule}


async def list_notification_rules(args: dict[str, Any]) -> dict[str, Any]:
    """List notification rules."""

    enabled = args.get("enabled")
    return {
        "rules": store.list_notification_rules(
            limit=int(args.get("limit", 25)),
            enabled=bool(enabled) if enabled is not None else None,
        )
    }


async def disable_notification_rule(args: dict[str, Any]) -> dict[str, Any]:
    """Disable one notification rule."""

    return {"rule": store.update_notification_rule(int(args["rule_id"]), enabled=False)}


async def send_test_notification(args: dict[str, Any]) -> dict[str, Any]:
    """Send a Telegram test notification."""

    return await notification_engine.send_test(str(args.get("message", "TradingCore Telegram notifications are connected.")))


async def get_canvas_status(_args: dict[str, Any]) -> dict[str, Any]:
    """Return Canvas connection state."""

    return canvas_status()


async def list_canvas_courses(_args: dict[str, Any]) -> Any:
    """List the connected user's active Canvas courses."""

    try:
        return await canvas_client.courses()
    except (CanvasConfigurationError, httpx.HTTPError) as exc:
        return {"available": False, "error": str(exc)}


async def list_canvas_events(_args: dict[str, Any]) -> Any:
    """List upcoming Canvas calendar events."""

    try:
        return await canvas_client.upcoming_events()
    except (CanvasConfigurationError, httpx.HTTPError) as exc:
        return {"available": False, "error": str(exc)}


async def list_canvas_todo(_args: dict[str, Any]) -> Any:
    """List Canvas to-do items and assignment reminders."""

    try:
        return await canvas_client.todo()
    except (CanvasConfigurationError, httpx.HTTPError) as exc:
        return {"available": False, "error": str(exc)}


async def get_browser_context(args: dict[str, Any]) -> dict[str, Any]:
    """Return recent user-selected BI pages imported from the browser."""

    limit = max(1, min(int(args.get("limit", 5)), 20))
    return {"snapshots": store.recent_browser_snapshots(limit=limit)}


async def run_research_backtest(args: dict[str, Any]) -> dict[str, Any]:
    """Run the transparent read-only moving-average research baseline."""

    try:
        epic = normalize_epic(str(args["epic"]))
        resolution = str(args.get("resolution", "HOUR"))
        payload = await trader_client.prices(epic, resolution, int(args.get("max_points", 300)))
        report = run_moving_average_backtest(
            normalize_prices(payload),
            fast_window=int(args.get("fast_window", 10)),
            slow_window=int(args.get("slow_window", 30)),
            initial_cash=float(args.get("initial_cash", 10_000)),
            fee_bps=float(args.get("fee_bps", 1.0)),
            slippage_bps=float(args.get("slippage_bps", 2.0)),
        )
        return {"epic": epic, "resolution": resolution, "report": report}
    except (ResearchDataError, httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        return {"available": False, "error": str(exc), "research_only": True}


TOOL_FUNCTIONS: dict[str, ToolFunction] = {
    "get_capital_trader_capabilities": get_capital_trader_capabilities,
    "get_health": get_health,
    "get_balance": get_balance,
    "list_positions": list_positions,
    "list_orders": list_orders,
    "get_capital_trader_snapshot": get_capital_trader_snapshot,
    "get_market_prices": get_market_prices,
    "get_market_info": get_market_info,
    "preview_trade_risk": preview_trade_risk,
    "preview_close_position": preview_close_position,
    "submit_order": submit_order,
    "get_dashboard": get_dashboard,
    "get_action_audit": get_action_audit,
    "set_mode": set_mode,
    "create_trade_ticket": create_trade_ticket,
    "approve_ticket": approve_ticket,
    "execute_ticket": execute_ticket,
    "create_close_ticket": create_close_ticket,
    "approve_close_ticket": approve_close_ticket,
    "execute_close_ticket": execute_close_ticket,
    "list_trade_tickets": list_trade_tickets,
    "list_agent_memories": list_agent_memories,
    "search_agent_memories": search_agent_memories,
    "get_trading_profile": get_trading_profile,
    "remember_trading_preference": remember_trading_preference,
    "remember_strategy_note": remember_strategy_note,
    "remember_operational_note": remember_operational_note,
    "deactivate_memory": deactivate_memory,
    "create_price_alert": create_price_alert,
    "create_market_open_alert": create_market_open_alert,
    "create_position_pl_alert": create_position_pl_alert,
    "create_health_alert": create_health_alert,
    "list_notification_rules": list_notification_rules,
    "disable_notification_rule": disable_notification_rule,
    "send_test_notification": send_test_notification,
    "get_canvas_status": get_canvas_status,
    "list_canvas_courses": list_canvas_courses,
    "list_canvas_events": list_canvas_events,
    "list_canvas_todo": list_canvas_todo,
    "get_browser_context": get_browser_context,
    "run_research_backtest": run_research_backtest,
}


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_capital_trader_capabilities",
            "description": "List what Capital Trader tools can read and how opening or adding a position must be done safely.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_health",
            "description": "Check whether the Capital Trader service is healthy.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_balance",
            "description": "Get account equity and balance from Capital Trader.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_positions",
            "description": "List open broker positions.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_orders",
            "description": "List pending broker working orders.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_capital_trader_snapshot",
            "description": "Get Capital Trader health, account balance, open positions, and working orders in one read-only call.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_prices",
            "description": "Fetch recent market prices for an epic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "epic": {"type": "string"},
                    "resolution": {"type": "string", "default": "MINUTE"},
                    "max_points": {"type": "integer", "default": 20},
                },
                "required": ["epic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_info",
            "description": "Fetch Capital Trader market metadata for an epic before preparing a trade ticket.",
            "parameters": {
                "type": "object",
                "properties": {"epic": {"type": "string"}},
                "required": ["epic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_trade_risk",
            "description": "Ask Capital Trader whether a proposed trade would pass risk checks without creating or placing an order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "epic": {"type": "string"},
                    "direction": {"type": "string", "enum": ["BUY", "SELL"]},
                    "size": {"type": "number"},
                    "order_type": {"type": "string", "enum": ["MARKET", "LIMIT", "STOP"], "default": "MARKET"},
                    "level": {"type": "number"},
                    "limit_distance": {"type": "number"},
                    "stop_distance": {"type": "number"},
                },
                "required": ["epic", "direction", "size"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_close_position",
            "description": "Ask Capital Trader whether an existing broker position could be closed without actually closing it.",
            "parameters": {
                "type": "object",
                "properties": {"deal_id": {"type": "string"}},
                "required": ["deal_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_order",
            "description": "Compatibility stub. Direct order submission is disabled; use trade tickets instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "epic": {"type": "string"},
                    "direction": {"type": "string", "enum": ["BUY", "SELL"]},
                    "size": {"type": "number"},
                    "order_type": {"type": "string", "enum": ["MARKET", "LIMIT", "STOP"]},
                    "level": {"type": "number"},
                    "limit_distance": {"type": "number"},
                    "stop_distance": {"type": "number"},
                    "confirmation_phrase": {"type": "string"},
                },
                "required": ["epic", "direction", "size", "confirmation_phrase"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dashboard",
            "description": "Get agent mode, recent tickets, and recent audit events.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_action_audit",
            "description": "Get a unified timeline of ticket state and audit events, optionally filtered by ticket id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50},
                    "ticket_id": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_mode",
            "description": "Set operating mode: observe, analyze, prepare, confirm, or execute.",
            "parameters": {
                "type": "object",
                "properties": {"mode": {"type": "string"}},
                "required": ["mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_trade_tickets",
            "description": "List trade tickets, optionally filtered by status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 25},
                    "status": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_trade_ticket",
            "description": "Create a structured proposed trade ticket. Does not execute.",
            "parameters": {
                "type": "object",
                "properties": {
                    "epic": {"type": "string"},
                    "direction": {"type": "string", "enum": ["BUY", "SELL"]},
                    "size": {"type": "number"},
                    "order_type": {"type": "string", "enum": ["MARKET", "LIMIT", "STOP"]},
                    "level": {"type": "number"},
                    "stop_loss": {"type": "number"},
                    "take_profit": {"type": "number"},
                    "limit_distance": {"type": "number"},
                    "stop_distance": {"type": "number"},
                    "reason": {"type": "string"},
                    "invalidated_if": {"type": "string"},
                    "confidence": {"type": "string"},
                },
                "required": ["epic", "direction", "size", "reason", "invalidated_if"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_ticket",
            "description": "Approve a pending trade ticket using its exact confirmation phrase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "confirmation_phrase": {"type": "string"},
                },
                "required": ["ticket_id", "confirmation_phrase"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_ticket",
            "description": "Execute an approved ticket after fresh broker reconciliation and risk checks.",
            "parameters": {
                "type": "object",
                "properties": {"ticket_id": {"type": "string"}},
                "required": ["ticket_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_close_ticket",
            "description": "Create a structured close-position ticket after Capital Trader close preview. Does not close the position.",
            "parameters": {
                "type": "object",
                "properties": {
                    "deal_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "invalidated_if": {"type": "string"},
                    "confidence": {"type": "string"},
                },
                "required": ["deal_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_close_ticket",
            "description": "Approve a pending close-position ticket using its exact confirmation phrase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "confirmation_phrase": {"type": "string"},
                },
                "required": ["ticket_id", "confirmation_phrase"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_close_ticket",
            "description": "Execute an approved close-position ticket after a fresh close preview and write guard checks.",
            "parameters": {
                "type": "object",
                "properties": {"ticket_id": {"type": "string"}},
                "required": ["ticket_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_agent_memories",
            "description": "List active durable memories about Faraj, trading preferences, strategy notes, and operations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 25},
                    "memory_type": {"type": "string"},
                    "scope": {"type": "string"},
                    "active_only": {"type": "boolean", "default": True},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_agent_memories",
            "description": "Search durable agent memories. Use for preferences, lessons, strategy notes, and operational facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                    "active_only": {"type": "boolean", "default": True},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trading_profile",
            "description": "Return active memory relevant to Faraj's trading preferences, risk behavior, strategy notes, and local operations.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_trading_preference",
            "description": "Persist a durable trading or risk preference. Do not use for live broker facts like current balance or open positions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "memory_type": {"type": "string", "default": "trading_preference"},
                    "scope": {"type": "string", "default": "trading"},
                    "source": {"type": "string", "default": "user"},
                    "confidence": {"type": "number", "default": 1},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_strategy_note",
            "description": "Persist a durable research or strategy note. Do not treat it as a live trading signal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "source": {"type": "string", "default": "user"},
                    "confidence": {"type": "number", "default": 1},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_operational_note",
            "description": "Persist a durable operational fact about the local TradingCore stack.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "source": {"type": "string", "default": "user"},
                    "confidence": {"type": "number", "default": 1},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deactivate_memory",
            "description": "Deactivate one durable memory by id without deleting history.",
            "parameters": {
                "type": "object",
                "properties": {"memory_id": {"type": "integer"}},
                "required": ["memory_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_price_alert",
            "description": "Create a Telegram alert when a market price is above or below a threshold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "epic": {"type": "string"},
                    "condition": {"type": "string", "enum": ["above", "below"]},
                    "threshold": {"type": "number"},
                    "message": {"type": "string"},
                    "cooldown_seconds": {"type": "integer", "default": 900},
                    "notify_recovery": {"type": "boolean", "default": True},
                },
                "required": ["epic", "condition", "threshold"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_market_open_alert",
            "description": "Create a Telegram alert when a market becomes tradeable/open.",
            "parameters": {
                "type": "object",
                "properties": {
                    "epic": {"type": "string"},
                    "message": {"type": "string"},
                    "cooldown_seconds": {"type": "integer", "default": 3600},
                    "notify_recovery": {"type": "boolean", "default": True},
                },
                "required": ["epic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_position_pl_alert",
            "description": "Create a Telegram alert when aggregate open P/L for one epic crosses a threshold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "epic": {"type": "string"},
                    "condition": {"type": "string", "enum": ["above", "below"]},
                    "threshold": {"type": "number"},
                    "message": {"type": "string"},
                    "cooldown_seconds": {"type": "integer", "default": 900},
                    "notify_recovery": {"type": "boolean", "default": True},
                },
                "required": ["epic", "condition", "threshold"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_health_alert",
            "description": "Create a Telegram alert when Capital Trader deep health is degraded.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "cooldown_seconds": {"type": "integer", "default": 900},
                    "notify_recovery": {"type": "boolean", "default": True},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_notification_rules",
            "description": "List Telegram notification rules.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 25},
                    "enabled": {"type": "boolean"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "disable_notification_rule",
            "description": "Disable one Telegram notification rule by id.",
            "parameters": {
                "type": "object",
                "properties": {"rule_id": {"type": "integer"}},
                "required": ["rule_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_test_notification",
            "description": "Send a Telegram test notification and record the result.",
            "parameters": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_canvas_status",
            "description": "Check whether the BI Canvas account is connected.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_canvas_courses",
            "description": "List active courses from the connected BI Canvas account.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_canvas_events",
            "description": "List upcoming calendar events from BI Canvas.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_canvas_todo",
            "description": "List upcoming Canvas to-do and assignment reminders.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_browser_context",
            "description": "Read recent BI Canvas or student-portal pages explicitly imported from the local browser.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 5}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_research_backtest",
            "description": "Run a read-only moving-average backtest on broker candles. Never executes a trade.",
            "parameters": {
                "type": "object",
                "properties": {
                    "epic": {"type": "string"},
                    "resolution": {"type": "string", "default": "HOUR"},
                    "max_points": {"type": "integer", "default": 300},
                    "fast_window": {"type": "integer", "default": 10},
                    "slow_window": {"type": "integer", "default": 30},
                    "initial_cash": {"type": "number", "default": 10000},
                    "fee_bps": {"type": "number", "default": 1},
                    "slippage_bps": {"type": "number", "default": 2},
                },
                "required": ["epic"],
            },
        },
    },
]
