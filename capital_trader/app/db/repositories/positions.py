"""Repository layer for Position model.
"""
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.position import Position

class PositionRepo:
    @staticmethod
    async def create_position(session: AsyncSession, position: Position) -> Position:
        session.add(position)
        await session.commit()
        await session.refresh(position)
        return position

    @staticmethod
    async def get_position_by_id(session: AsyncSession, position_id: str) -> Position:
        result = await session.execute(select(Position).where(Position.id == position_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def update_position(session: AsyncSession, position_id: str, **kwargs) -> Position:
        kwargs.setdefault("updated_at", datetime.now(timezone.utc))
        await session.execute(update(Position).where(Position.id == position_id).values(**kwargs))
        await session.commit()
        return await PositionRepo.get_position_by_id(session, position_id)
    
    @staticmethod
    async def get_open_positions(session: AsyncSession):
        result = await session.execute(select(Position).where(Position.status == "OPEN"))
        return result.scalars().all()
    
    @staticmethod
    async def update_position_status(session: AsyncSession, position_id: str, status: str) -> Position:
        await session.execute(
            update(Position)
            .where(Position.id == position_id)
            .values(status=status, updated_at=datetime.now(timezone.utc))
        )
        await session.commit()
        return await PositionRepo.get_position_by_id(session, position_id)
