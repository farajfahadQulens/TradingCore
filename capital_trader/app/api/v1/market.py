"""Market data endpoints — public API v1.
"""
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response

from app.broker.client import BrokerClient
from app.core.logging import get_logger
from app.services.gold_candle_store import (
    candle_summary,
    filter_candle_rows,
    load_candle_rows,
    render_csv,
)

logger = get_logger(__name__)
router = APIRouter()
GOLD_CSV_PATH = Path(os.getenv("GOLD_CSV_PATH", "/data/gold_candles.csv"))
GOLD_STATUS_PATH = Path(os.getenv("GOLD_STATUS_PATH", "/data/gold_recorder_status.json"))


@router.get("/market/prices/{epic}")
async def get_prices(
    epic: str,
    resolution: str = "MINUTE",
    max_points: int = 60,
    from_date: str = None,
    to_date: str = None,
):
    try:
        async with BrokerClient() as client:
            data = await client.get_prices(
                epic,
                resolution=resolution,
                max_points=max_points,
                from_date=from_date,
                to_date=to_date,
            )
            logger.info("prices_retrieved", epic=epic)
            return data
    except Exception as error:
        logger.error("get_prices_error", error=str(error))
        raise HTTPException(status_code=500, detail=str(error))


@router.get("/market/gold/candles.csv")
@router.get("/gold/candles.csv")
@router.get("/market/gold/candles")
@router.get("/gold/candles")
async def get_gold_candles_csv(
    start: str = None,
    end: str = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=10000),
):
    try:
        rows = filter_candle_rows(
            load_candle_rows(GOLD_CSV_PATH),
            start=start,
            end=end,
            offset=offset,
            limit=limit,
        )
        return Response(
            content=render_csv(rows),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=gold_candles.csv"},
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/market/gold/candles/status")
@router.get("/gold/candles/status")
async def get_gold_candles_status():
    rows = load_candle_rows(GOLD_CSV_PATH)
    result = candle_summary(rows, GOLD_CSV_PATH)
    if GOLD_STATUS_PATH.exists():
        try:
            result["recorder"] = json.loads(GOLD_STATUS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            result["recorder"] = {"status": "unavailable"}
    else:
        result["recorder"] = {"status": "starting"}
    return result


@router.get("/market/{epic}")
async def get_market(epic: str):
    try:
        async with BrokerClient() as client:
            data = await client.get_market(epic)
            logger.info("market_retrieved", epic=epic)
            return data
    except Exception as error:
        logger.error("get_market_error", error=str(error))
        raise HTTPException(status_code=500, detail=str(error))
