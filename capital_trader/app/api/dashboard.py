"""Dashboard-specific endpoints.
"""
from fastapi import APIRouter, HTTPException
from app.broker.client import BrokerClient
from app.core.logging import get_logger
import datetime

logger = get_logger(__name__)

router = APIRouter()


@router.get("/equity")
async def get_equity():
    try:
        async with BrokerClient() as client:
            balance = await client.get_balance()
            logger.info("equity_retrieved", balance=balance)
            return {"equity": balance}
    except Exception as e:
        logger.error("get_equity_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_positions():
    try:
        async with BrokerClient() as client:
            data = await client.get_positions()
            logger.info("dashboard_positions", count=len(data.get("positions", [])))
            return data
    except Exception as e:
        logger.error("dashboard_positions_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/activity")
async def get_activity():
    try:
        async with BrokerClient() as client:
            to_date = datetime.datetime.utcnow()
            from_date = to_date - datetime.timedelta(days=2)
            fmt = "%Y-%m-%dT%H:%M:%S"
            data = await client.get_transactions(
                            from_date=from_date.strftime(fmt),
                            to_date=to_date.strftime(fmt),
                        )     
            logger.info("activity_retrieved", count=len(data.get("transactions", [])))
            return data
    except Exception as e:
        logger.error("get_activity_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/transactions")
async def get_transactions():
    try:
        async with BrokerClient() as client:
            to_date = datetime.datetime.utcnow()
            from_date = to_date - datetime.timedelta(days=8)
            fmt = "%Y-%m-%dT%H:%M:%S"
            data = await client.get_transactions(
                from_date=from_date.strftime(fmt),
                to_date=to_date.strftime(fmt),
            )
            logger.info("transactions_retrieved", count=len(data.get("transactions", [])))
            return data
    except Exception as e:
        logger.error("get_transactions_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_stats():
    try:
        async with BrokerClient() as client:
            to_date = datetime.datetime.utcnow()
            from_date = to_date - datetime.timedelta(days=8)
            fmt = "%Y-%m-%dT%H:%M:%S"
            data = await client.get_transactions(from_date=from_date.strftime(fmt), to_date=to_date.strftime(fmt))
            logger.info("stats_retrieved", count=len(data.get("transactions", [])))
            trades = [t for t in data.get("transactions", []) if t.get("transactionType") == "TRADE"]
            total_trades = len(trades)
            profitable_trades = len([t for t in trades if float(t.get("size", 0)) > 0])
            win_rate = (profitable_trades / total_trades) * 100 if total_trades > 0 else 0
            return {
                "trades": trades,
                "total_trades": total_trades,
                "profitable_trades": profitable_trades,
                "win_rate": win_rate,
            }
    except Exception as e:
        logger.error("get_stats_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))