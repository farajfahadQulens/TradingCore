"""Account endpoints — public API v1.
"""
from fastapi import APIRouter, HTTPException
from app.broker.client import BrokerClient
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/accounts")
async def get_accounts():
    try:
        async with BrokerClient() as client:
            data = await client.get_accounts()
            logger.info("accounts_retrieved", count=len(data.get("accounts", [])))
            return data
    except Exception as e:
        logger.error("get_accounts_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accounts/balance")
async def get_balance():
    try:
        async with BrokerClient() as client:
            balance = await client.get_balance()
            logger.info("balance_retrieved", balance=balance)
            return {"balance": balance}
    except Exception as e:
        logger.error("get_balance_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/accounts/positions")
async def get_positions():
    try:
        async with BrokerClient() as client:
            data = await client.get_positions()
            logger.info("positions_retrieved", count=len(data.get("positions", [])))
            return data
    except Exception as e:
        logger.error("get_positions_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/accounts/working-orders")
async def get_working_orders():
    try:
        async with BrokerClient() as client:
            data = await client.get_working_orders()
            logger.info("working_orders_retrieved", count=len(data.get("workingOrders", [])))
            return data
    except Exception as e:
        logger.error("get_working_orders_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/accounts/client-sentiment")
async def get_client_sentiment(epic: str):
    try:
        async with BrokerClient() as client:
            data = await client.get_client_sentiment(epic)
            logger.info("client_sentiment_retrieved", epic=epic)
            return data
    except Exception as e:
        logger.error("get_client_sentiment_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))