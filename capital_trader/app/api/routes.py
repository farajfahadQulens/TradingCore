"""FastAPI endpoints for health and simple read-only queries.
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from app.db.session import get_session
from app.db.models.position import Position
from app.db.repositories.positions import PositionRepo
from app.broker.client import BrokerClient
from app.core.config import settings
from app.core.logging import get_logger
from app.services.health_service import health_service

logger = get_logger(__name__)

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "healthy"}


@router.get("/health/deep")
async def deep_health():
    return await health_service.deep_health()




@router.get("/debug/settings")
async def debug_settings():
    logger.info("debug_settings",
        environment=settings.environment,
        broker_base_url=settings.broker_base_url,
        broker_ws_url=settings.broker_ws_url,
    )
    return {
        "environment": settings.environment,
        "broker_base_url": settings.broker_base_url,
        "broker_ws_url": settings.broker_ws_url,
    }


@router.get("/debug/equity")
async def debug_equity():
    try:
        async with BrokerClient() as client:
            balance = await client.get_balance()
            logger.info("debug_equity", balance=balance)
            return {"equity": balance}
    except Exception as e:
        logger.error("debug_equity_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/positions")
async def debug_positions():
    try:
        async with BrokerClient() as client:
            data = await client.get_positions()
            logger.info("debug_positions", count=len(data.get("positions", [])))
            return data
    except Exception as e:
        logger.error("debug_positions_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/sync-positions")
async def sync_positions():
    try:
        async with BrokerClient() as client:
            data = await client.get_positions()
            logger.info("debug_positions", count=len(data.get("positions", [])))
            async with get_session() as session:
                saved = []

                for item in data.get("positions", []):
                    p = item["position"]
                    m = item["market"]
                    pos = Position(
                        id=p["dealId"],
                        epic=m["epic"],
                        size=p["size"],
                        entry_price=p["level"],
                        stop_loss=p.get("stopLevel"),
                        deal_reference=p["dealReference"],
                        status="OPEN",
                    )
                    result = await PositionRepo.create_position(session, pos)
                    saved.append(result.id)

            return {"synced": saved}
            
    except Exception as e:
        logger.error("debug_positions_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/debug/recent-positions")
async def debug_recent_positions():
    try:
        async with BrokerClient() as client:
            data = await client.get_history(from_date="2026-05-08T01:09:47", to_date="2026-05-08T20:10:05")
            logger.info("debug_recent_positions", count=len(data.get("activities", [])))
            return data
    except Exception as e:
        logger.error("debug_recent_positions_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/account")
async def account_info():
    try:
        async with BrokerClient() as client:
            data = await client.get_accounts()
            logger.info("account_info_retrieved", count=len(data.get("accounts", [])))
            return data
    except Exception as e:
        logger.error("account_info_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
