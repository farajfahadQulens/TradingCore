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
