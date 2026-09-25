"""Deterministic risk checks for proposed trade tickets.

The model may explain a setup, but this module owns the hard checks. Any error
blocks execution. Warnings do not block by themselves but are shown on tickets.
"""

from __future__ import annotations

from typing import Any

from app.config import settings


def _count_open_positions(positions_response: dict[str, Any] | None) -> int:
    """Extract an open-position count from Capital Trader's response."""

    if not positions_response:
        return 0
    positions = positions_response.get("positions")
    if isinstance(positions, list):
        return len(positions)
    return 0


def _optional_float(value: Any) -> float | None:
    """Return a float for present numeric values and None for absent values."""

    if value is None or value == "":
        return None
    return float(value)


def evaluate_ticket(ticket: dict[str, Any], broker_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate a ticket against local risk rules."""

    errors: list[str] = []
    warnings: list[str] = []
    broker_state = broker_state or {}

    try:
        size = float(ticket.get("size", 0))
    except (TypeError, ValueError):
        size = 0
    order_type = str(ticket.get("order_type", "")).upper()
    direction = str(ticket.get("direction", "")).upper()
    try:
        level = _optional_float(ticket.get("level"))
        stop_loss = _optional_float(ticket.get("stop_loss"))
        take_profit = _optional_float(ticket.get("take_profit"))
        stop_distance = _optional_float(ticket.get("stop_distance"))
        limit_distance = _optional_float(ticket.get("limit_distance"))
    except (TypeError, ValueError):
        level = None
        stop_loss = None
        take_profit = None
        stop_distance = None
        limit_distance = None
        errors.append("price, stop, take-profit, and distance fields must be numeric when provided")

    if direction not in {"BUY", "SELL"}:
        errors.append("direction must be BUY or SELL")

    if order_type not in {"MARKET", "LIMIT", "STOP"}:
        errors.append("order_type must be MARKET, LIMIT, or STOP")

    if size <= 0:
        errors.append("size must be greater than zero")

    if size > settings.max_ticket_size:
        errors.append(f"size {size} exceeds MAX_TICKET_SIZE {settings.max_ticket_size}")

    if settings.require_stop_loss and stop_loss is None and stop_distance is None:
        errors.append("stop loss or stop distance is required")

    if stop_distance is not None and stop_distance <= 0:
        errors.append("stop distance must be greater than zero")

    if limit_distance is not None and limit_distance <= 0:
        errors.append("limit distance must be greater than zero")

    if take_profit is None:
        warnings.append("take profit is missing")

    if level is not None and stop_loss is not None:
        if direction == "BUY" and stop_loss >= level:
            errors.append("BUY stop loss must be below entry level")
        if direction == "SELL" and stop_loss <= level:
            errors.append("SELL stop loss must be above entry level")

    if level is not None and take_profit is not None:
        if direction == "BUY" and take_profit <= level:
            errors.append("BUY take profit must be above entry level")
        if direction == "SELL" and take_profit >= level:
            errors.append("SELL take profit must be below entry level")

    if order_type in {"LIMIT", "STOP"} and ticket.get("level") is None:
        errors.append(f"{order_type} orders require level")

    positions_count = _count_open_positions(broker_state.get("positions"))
    if positions_count >= settings.max_open_positions:
        errors.append(f"open positions {positions_count} reached MAX_OPEN_POSITIONS {settings.max_open_positions}")

    if broker_state.get("health_error"):
        errors.append(f"trader health unavailable: {broker_state['health_error']}")

    if broker_state.get("positions_error"):
        errors.append(f"positions unavailable: {broker_state['positions_error']}")

    if broker_state.get("orders_error"):
        errors.append(f"orders unavailable: {broker_state['orders_error']}")

    if broker_state.get("market_error"):
        errors.append(f"market unavailable: {broker_state['market_error']}")

    status = "blocked" if errors else "approved"
    return {"status": status, "errors": errors, "warnings": warnings}
