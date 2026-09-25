"""Repository layer for TradeLog and DeadLetterEvent models.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.trade_log import TradeLog
from app.db.models.dead_letter_event import DeadLetterEvent


class TradeRepo:
    @staticmethod
    async def append_log(session: AsyncSession, log: TradeLog) -> TradeLog:
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log

    @staticmethod
    async def get_by_correlation_id(session: AsyncSession, correlation_id: str) -> list:
        result = await session.execute(
            select(TradeLog).where(TradeLog.correlation_id == correlation_id)
            .order_by(TradeLog.created_at.asc())
        )
        return result.scalars().all()

    @staticmethod
    async def list_logs(
        session: AsyncSession,
        *,
        limit: int = 50,
        event_type: str | None = None,
        correlation_id: str | None = None,
    ) -> list[TradeLog]:
        query = select(TradeLog)
        if event_type:
            query = query.where(TradeLog.event_type == event_type)
        if correlation_id:
            query = query.where(TradeLog.correlation_id == correlation_id)
        query = query.order_by(TradeLog.created_at.desc()).limit(max(1, min(int(limit), 200)))
        result = await session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def create_dead_letter(session: AsyncSession, event: DeadLetterEvent) -> DeadLetterEvent:
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event

    @staticmethod
    async def get_unresolved(session: AsyncSession) -> list:
        result = await session.execute(
            select(DeadLetterEvent).where(DeadLetterEvent.resolved_at == None)
        )
        return result.scalars().all()

    @staticmethod
    async def resolve_dead_letter(session: AsyncSession, event_id: str) -> None:
        from sqlalchemy import update
        from datetime import datetime, timezone
        await session.execute(
            update(DeadLetterEvent)
            .where(DeadLetterEvent.id == event_id)
            .values(resolved_at=datetime.now(timezone.utc))
        )
        await session.commit()
