"""Repository layer for Order model.
"""
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.order import Order


class OrderRepo:
    @staticmethod
    async def create(session: AsyncSession, order: Order) -> Order:
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order

    @staticmethod
    async def get_by_id(session: AsyncSession, order_id: str) -> Order | None:
        result = await session.execute(select(Order).where(Order.id == order_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_client_order_id(session: AsyncSession, client_order_id: str) -> Order | None:
        result = await session.execute(select(Order).where(Order.client_order_id == client_order_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_pending(session: AsyncSession) -> list:
        result = await session.execute(select(Order).where(Order.state == "PENDING"))
        return result.scalars().all()

    @staticmethod
    async def update_state(session: AsyncSession, order_id: str, state: str) -> Order:
        await session.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(state=state, updated_at=datetime.now(timezone.utc))
        )
        await session.commit()
        return await OrderRepo.get_by_id(session, order_id)

    @staticmethod
    async def update_fields(session: AsyncSession, order_id: str, **fields) -> Order:
        fields.setdefault("updated_at", datetime.now(timezone.utc))
        await session.execute(update(Order).where(Order.id == order_id).values(**fields))
        await session.commit()
        return await OrderRepo.get_by_id(session, order_id)

    @staticmethod
    async def get_by_broker_id(session: AsyncSession, broker_order_id: str) -> Order | None:
        result = await session.execute(select(Order).where(Order.broker_order_id == broker_order_id))
        return result.scalar_one_or_none()
