"""Audit endpoints for persisted Capital Trader trade logs."""
from fastapi import APIRouter

from app.db.repositories.trades import TradeRepo
from app.db.session import get_session
from app.services.trade_log_service import trade_log_to_dict

router = APIRouter()


@router.get("/audit/trade-log")
async def list_trade_logs(
    limit: int = 50,
    event_type: str | None = None,
    correlation_id: str | None = None,
) -> dict:
    """List persisted trade log entries newest first."""

    async with get_session() as session:
        logs = await TradeRepo.list_logs(
            session,
            limit=limit,
            event_type=event_type,
            correlation_id=correlation_id,
        )
    return {"logs": [trade_log_to_dict(log) for log in logs]}
