"""Trade-ticket creation, confirmation, execution, and reconciliation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.config import settings
from app.risk import evaluate_ticket
from app.store import store
from app.trader import normalize_epic, trader_client


def _ticket_id() -> str:
    """Generate a readable ticket id."""

    return f"T-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:4].upper()}"


def _confirmation_phrase(ticket: dict[str, Any]) -> str:
    """Build a ticket-specific phrase for explicit human approval."""

    if ticket.get("ticket_type") == "close_position":
        return f"CONFIRM CLOSE {ticket['id']} {ticket['epic']} {ticket['deal_id']}"
    return f"CONFIRM {ticket['id']} {ticket['epic']} {ticket['direction']} {ticket['size']}"


def _broker_order_payload(ticket: dict[str, Any]) -> dict[str, Any]:
    """Build the exact payload sent to Capital Trader, omitting empty values."""

    payload = {
        "epic": ticket["epic"],
        "direction": ticket["direction"],
        "size": ticket["size"],
        "order_type": ticket["order_type"],
    }
    for key in ("level", "limit_distance", "stop_distance"):
        value = ticket.get(key)
        if value is not None:
            payload[key] = value
    return payload


async def broker_snapshot() -> dict[str, Any]:
    """Collect current Capital Trader state with errors captured as data."""

    snapshot: dict[str, Any] = {}

    async def capture(key: str, fn) -> None:
        try:
            snapshot[key] = await asyncio.wait_for(fn(), timeout=settings.broker_snapshot_timeout_seconds)
        except TimeoutError:
            snapshot[f"{key}_error"] = (
                f"{key} check exceeded {settings.broker_snapshot_timeout_seconds}s"
            )
        except Exception as exc:
            snapshot[f"{key}_error"] = str(exc)

    tasks = [
        capture(key, fn)
        for key, fn in (
            ("health", trader_client.health),
            ("balance", trader_client.balance),
            ("positions", trader_client.positions),
            ("orders", trader_client.orders),
        )
    ]
    await asyncio.gather(*tasks)
    return snapshot


async def create_trade_ticket(args: dict[str, Any]) -> dict[str, Any]:
    """Create and persist a structured trade ticket."""

    raw_ticket = {
        "id": _ticket_id(),
        "ticket_type": "open_position",
        "deal_id": None,
        "status": "draft",
        "epic": normalize_epic(str(args["epic"])),
        "direction": str(args["direction"]).upper(),
        "size": float(args["size"]),
        "order_type": str(args.get("order_type", "LIMIT")).upper(),
        "level": args.get("level"),
        "stop_loss": args.get("stop_loss"),
        "take_profit": args.get("take_profit"),
        "limit_distance": args.get("limit_distance"),
        "stop_distance": args.get("stop_distance"),
        "reason": str(args.get("reason", "")).strip() or "No reason provided.",
        "invalidated_if": str(args.get("invalidated_if", "")).strip() or "No invalidation provided.",
        "confidence": str(args.get("confidence", "medium")).lower(),
    }

    snapshot = await broker_snapshot()
    try:
        snapshot["market"] = await asyncio.wait_for(
            trader_client.market(raw_ticket["epic"]),
            timeout=settings.broker_snapshot_timeout_seconds,
        )
    except TimeoutError:
        snapshot["market_error"] = (
            f"market check exceeded {settings.broker_snapshot_timeout_seconds}s"
        )
    except Exception as exc:
        snapshot["market_error"] = str(exc)

    risk = evaluate_ticket(raw_ticket, snapshot)
    raw_ticket["risk"] = risk
    raw_ticket["status"] = "blocked" if risk["status"] == "blocked" else "pending_confirmation"
    raw_ticket["confirmation_phrase"] = _confirmation_phrase(raw_ticket)

    ticket = store.create_ticket(raw_ticket)
    return {"ticket": ticket, "broker_snapshot": snapshot}


def _close_ticket_risk(preview: dict[str, Any]) -> dict[str, Any]:
    """Convert Capital Trader close preview into local ticket risk shape."""

    warnings: list[str] = []
    errors: list[str] = []
    if not preview.get("approved", False):
        errors.append(preview.get("reason") or "close preview rejected")
    broker_position = preview.get("broker_position", {})
    if broker_position.get("market_status") != "TRADEABLE":
        warnings.append(f"market status is {broker_position.get('market_status')}")
    return {
        "status": "blocked" if errors else "approved",
        "errors": errors,
        "warnings": warnings,
    }


async def create_close_ticket(args: dict[str, Any]) -> dict[str, Any]:
    """Create and persist a close-position ticket from Capital Trader preview."""

    deal_id = str(args["deal_id"])
    reason = str(args.get("reason", "")).strip() or "Close existing broker position."
    invalidated_if = str(args.get("invalidated_if", "")).strip() or (
        "Broker position changes, disappears, or close preview becomes rejected."
    )
    preview = await trader_client.close_preview(deal_id)
    local_position = preview.get("local_position", {})
    broker_position = preview.get("broker_position", {})
    risk = _close_ticket_risk(preview)

    raw_ticket = {
        "id": _ticket_id(),
        "ticket_type": "close_position",
        "deal_id": deal_id,
        "status": "blocked" if risk["status"] == "blocked" else "pending_confirmation",
        "epic": str(local_position.get("epic") or broker_position.get("epic") or "UNKNOWN").upper(),
        "direction": str(broker_position.get("direction") or "CLOSE").upper(),
        "size": float(local_position.get("size") or broker_position.get("size") or 0),
        "order_type": "CLOSE",
        "level": broker_position.get("estimated_close_price"),
        "stop_loss": None,
        "take_profit": None,
        "limit_distance": None,
        "stop_distance": None,
        "reason": reason,
        "invalidated_if": invalidated_if,
        "confidence": str(args.get("confidence", "medium")).lower(),
        "risk": risk,
    }
    raw_ticket["confirmation_phrase"] = _confirmation_phrase(raw_ticket)

    ticket = store.create_ticket(raw_ticket)
    store.update_ticket(ticket["id"], reconciliation_before={"close_preview": preview})
    ticket = store.get_ticket(ticket["id"]) or ticket
    return {"ticket": ticket, "close_preview": preview}


async def approve_ticket(args: dict[str, Any]) -> dict[str, Any]:
    """Mark a ticket approved when the exact phrase is supplied."""

    ticket_id = str(args["ticket_id"])
    supplied_phrase = str(args.get("confirmation_phrase", ""))
    ticket = store.get_ticket(ticket_id)
    if not ticket:
        return {"approved": False, "reason": "ticket not found"}

    if ticket["status"] != "pending_confirmation":
        return {"approved": False, "reason": f"ticket status is {ticket['status']}"}

    if supplied_phrase != ticket["confirmation_phrase"]:
        store.audit("ticket_approval_rejected", {"ticket_id": ticket_id, "reason": "phrase mismatch"})
        return {"approved": False, "reason": "confirmation phrase mismatch"}

    updated = store.update_ticket(ticket_id, status="approved")
    store.audit("ticket_approved", {"ticket_id": ticket_id})
    return {"approved": True, "ticket": updated}


async def approve_close_ticket(args: dict[str, Any]) -> dict[str, Any]:
    """Approve a close-position ticket with the same exact phrase guard."""

    ticket = store.get_ticket(str(args["ticket_id"]))
    if not ticket:
        return {"approved": False, "reason": "ticket not found"}
    if ticket.get("ticket_type") != "close_position":
        return {"approved": False, "reason": f"ticket type is {ticket.get('ticket_type')}"}
    return await approve_ticket(args)


async def execute_ticket(args: dict[str, Any]) -> dict[str, Any]:
    """Execute an approved ticket after fresh risk and state checks."""

    ticket_id = str(args["ticket_id"])
    ticket = store.get_ticket(ticket_id)
    if not ticket:
        return {"executed": False, "reason": "ticket not found"}

    if not settings.allow_trading_writes:
        return {"executed": False, "reason": "trading writes are disabled"}

    if ticket["status"] != "approved":
        return {"executed": False, "reason": f"ticket status is {ticket['status']}"}

    if ticket.get("ticket_type") == "close_position":
        return await _execute_close_ticket(ticket)

    before = await broker_snapshot()
    fresh_risk = evaluate_ticket(ticket, before)
    if fresh_risk["status"] == "blocked":
        store.update_ticket(
            ticket_id,
            status="blocked",
            reconciliation_before=before,
        )
        store.audit("ticket_execution_blocked", {"ticket_id": ticket_id, "risk": fresh_risk})
        return {"executed": False, "reason": "fresh risk check blocked execution", "risk": fresh_risk}

    payload = _broker_order_payload(ticket)
    try:
        broker_response = await trader_client.submit_order(payload)
    except Exception as exc:
        store.update_ticket(
            ticket_id,
            status="blocked",
            reconciliation_before=before,
            broker_response={"error": str(exc), "payload": payload},
        )
        store.audit("ticket_execution_failed", {"ticket_id": ticket_id, "error": str(exc)})
        return {"executed": False, "reason": f"Capital Trader order failed: {exc}"}

    after = await broker_snapshot()
    updated = store.update_ticket(
        ticket_id,
        status="executed",
        broker_response=broker_response,
        reconciliation_before=before,
        reconciliation_after=after,
    )
    store.audit("ticket_executed", {"ticket_id": ticket_id, "broker_response": broker_response})
    return {"executed": True, "ticket": updated}


async def execute_close_ticket(args: dict[str, Any]) -> dict[str, Any]:
    """Execute an approved close-position ticket only."""

    ticket = store.get_ticket(str(args["ticket_id"]))
    if not ticket:
        return {"executed": False, "reason": "ticket not found"}
    if ticket.get("ticket_type") != "close_position":
        return {"executed": False, "reason": f"ticket type is {ticket.get('ticket_type')}"}
    return await execute_ticket(args)


async def _execute_close_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    """Execute an approved close ticket after a fresh close preview."""

    ticket_id = ticket["id"]
    deal_id = ticket.get("deal_id")
    if not deal_id:
        return {"executed": False, "reason": "close ticket is missing deal_id"}

    try:
        preview = await trader_client.close_preview(deal_id)
    except Exception as exc:
        store.update_ticket(
            ticket_id,
            status="blocked",
            reconciliation_before={"close_preview_error": str(exc)},
        )
        store.audit("close_ticket_preview_failed", {"ticket_id": ticket_id, "error": str(exc)})
        return {"executed": False, "reason": f"Capital Trader close preview failed: {exc}"}

    close_risk = _close_ticket_risk(preview)
    if close_risk["status"] == "blocked":
        store.update_ticket(
            ticket_id,
            status="blocked",
            reconciliation_before={"close_preview": preview},
        )
        store.audit("close_ticket_execution_blocked", {"ticket_id": ticket_id, "risk": close_risk})
        return {"executed": False, "reason": "fresh close preview blocked execution", "risk": close_risk}

    try:
        broker_response = await trader_client.close_position(deal_id)
    except Exception as exc:
        store.update_ticket(
            ticket_id,
            status="blocked",
            reconciliation_before={"close_preview": preview},
            broker_response={"error": str(exc), "deal_id": deal_id},
        )
        store.audit("close_ticket_execution_failed", {"ticket_id": ticket_id, "error": str(exc)})
        return {"executed": False, "reason": f"Capital Trader close failed: {exc}"}

    after = await broker_snapshot()
    updated = store.update_ticket(
        ticket_id,
        status="executed",
        broker_response=broker_response,
        reconciliation_before={"close_preview": preview},
        reconciliation_after=after,
    )
    store.audit("close_ticket_executed", {"ticket_id": ticket_id, "broker_response": broker_response})
    return {"executed": True, "ticket": updated}
