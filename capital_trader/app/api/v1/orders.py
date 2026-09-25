"""Order endpoints — public API v1.
"""
from fastapi import APIRouter, HTTPException
from app.broker.client import BrokerClient
from app.core.logging import get_logger
from app.services.order_workflow_service import order_workflow_service
from pydantic import BaseModel
logger = get_logger(__name__)

router = APIRouter()

class OrderRequest(BaseModel):
    epic: str
    direction: str  # BUY or SELL
    size: float
    order_type: str = "MARKET"
    level: float | None = None
    limit_distance: float | None = None
    stop_distance: float | None = None

@router.post("/orders")
async def create_order(order: OrderRequest):
    raise HTTPException(
        status_code=403,
        detail="Direct broker order placement is disabled. Use POST /api/v1/workflow/orders.",
    )


@router.post("/workflow/orders")
async def create_workflow_order(order: OrderRequest):
    try:
        data = await order_workflow_service.submit_and_place(
            epic=order.epic,
            direction=order.direction,
            size=order.size,
            order_type=order.order_type,
            level=order.level,
            limit_distance=order.limit_distance,
            stop_distance=order.stop_distance,
        )
        logger.info("workflow_order_created", epic=order.epic, direction=order.direction)
        return data
    except PermissionError as e:
        logger.warning("workflow_order_risk_rejected", epic=order.epic, reason=str(e))
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        logger.warning("workflow_order_invalid", epic=order.epic, reason=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("create_workflow_order_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflow/risk-preview")
async def preview_workflow_risk(order: OrderRequest):
    try:
        data = await order_workflow_service.preview_risk(
            epic=order.epic,
            direction=order.direction,
            size=order.size,
            order_type=order.order_type,
        )
        logger.info(
            "workflow_risk_previewed",
            epic=order.epic,
            direction=order.direction,
            approved=data["approved"],
        )
        return data
    except ValueError as e:
        logger.warning("workflow_risk_preview_invalid", epic=order.epic, reason=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("preview_workflow_risk_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders")
async def get_working_orders():
    try:
        async with BrokerClient() as client:
            data = await client.get_working_orders()
            logger.info("orders_retrieved", count=len(data.get("workingOrders", [])))
            return data
    except Exception as e:
        logger.error("get_orders_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/orders/history")
async def get_order_history(from_date: str, to_date: str):
    try:
        async with BrokerClient() as client:
            data = await client.get_history(from_date, to_date)
            logger.info("order_history_retrieved", count=len(data.get("activities", [])))
            return data
    except Exception as e:
        logger.error("get_order_history_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/orders/{order_id}")
async def cancel_order(order_id: str):
    try:
        async with BrokerClient() as client:
            data = await client.cancel_order(order_id)
            logger.info("order_cancelled", order_id=order_id)
            return data
    except Exception as e:
        logger.error("cancel_order_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
