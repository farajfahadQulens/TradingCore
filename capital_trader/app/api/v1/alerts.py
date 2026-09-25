"""Alert endpoints — public API v1.
"""
from fastapi import APIRouter, HTTPException
from app.db.session import get_session
from app.db.repositories.alerts import AlertRepo
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/alerts")
async def get_alerts():
    try:
        async with get_session() as session:
            alerts = await AlertRepo.get_active_rules(session)
            logger.info("alerts_retrieved", count=len(alerts))
            return {"alerts": alerts}
    except Exception as e:
        logger.error("get_alerts_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))