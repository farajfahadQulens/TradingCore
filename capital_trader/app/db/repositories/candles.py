"""Repository layer for Candle model.
"""
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from app.db.models.candle import Candle
from datetime import datetime


class CandleRepo:
    @staticmethod
    async def batch_insert(session: AsyncSession, candles: list[Candle]) -> None:
        for candle in candles:
            stmt = insert(Candle).values(
                id=candle.id,
                epic=candle.epic,
                timeframe=candle.timeframe,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                bid_close=candle.bid_close,
                ask_close=candle.ask_close,
                candle_time=candle.candle_time,
                created_at=candle.created_at,
            ).on_conflict_do_nothing(index_elements=["id"])
            await session.execute(stmt)
        await session.commit()

    @staticmethod
    async def get_latest(session: AsyncSession, epic: str, timeframe: str) -> Candle | None:
        result = await session.execute(
            select(Candle)
            .where(Candle.epic == epic, Candle.timeframe == timeframe)
            .order_by(Candle.candle_time.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_range(session: AsyncSession, epic: str, timeframe: str, from_time: datetime, to_time: datetime) -> list:
        result = await session.execute(
            select(Candle)
            .where(
                Candle.epic == epic,
                Candle.timeframe == timeframe,
                Candle.candle_time >= from_time,
                Candle.candle_time <= to_time
            )
            .order_by(Candle.candle_time.asc())
        )
        return result.scalars().all()

    @staticmethod
    async def cleanup_old(session: AsyncSession, epic: str, timeframe: str, before: datetime) -> None:
        await session.execute(
            delete(Candle).where(
                Candle.epic == epic,
                Candle.timeframe == timeframe,
                Candle.candle_time < before
            )
        )
        await session.commit()