"""Position endpoints — public API v1.
"""
from fastapi import APIRouter, HTTPException
from app.broker.client import BrokerClient
from app.core.logging import get_logger
from app.services.position_workflow_service import position_workflow_service

logger = get_logger(__name__)

router = APIRouter()


@router.get("/positions")
async def get_positions():
    try:
        async with BrokerClient() as client:
            data = await client.get_positions()
            logger.info("positions_retrieved", count=len(data.get("positions", [])))
            return data
    except Exception as e:
        logger.error("get_positions_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflow/positions/{deal_id}/close-preview")
async def preview_close_position(deal_id: str):
    try:
        data = await position_workflow_service.preview_close(deal_id)
        logger.info("workflow_close_previewed", deal_id=deal_id, approved=data["approved"])
        return data
    except ValueError as e:
        logger.warning("workflow_close_preview_invalid", deal_id=deal_id, reason=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("workflow_close_preview_error", deal_id=deal_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflow/positions/{deal_id}/close")
async def close_position_workflow(deal_id: str):
    try:
        data = await position_workflow_service.close_position(deal_id)
        logger.info("workflow_position_closed", deal_id=deal_id)
        return data
    except PermissionError as e:
        logger.warning("workflow_close_rejected", deal_id=deal_id, reason=str(e))
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        logger.warning("workflow_close_invalid", deal_id=deal_id, reason=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("workflow_close_error", deal_id=deal_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
