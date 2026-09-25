"""Repository layer for Alert model.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.alert import Alert


class AlertRepo:
    @staticmethod
    async def get_active_rules(session: AsyncSession) -> list:
        result = await session.execute(
            select(Alert).where(Alert.active == "true")
        )
        return result.scalars().all()

    @staticmethod
    async def create_rule(session: AsyncSession, alert: Alert) -> Alert:
        session.add(alert)
        await session.commit()
        await session.refresh(alert)
        return alert

    @staticmethod
    async def get_by_id(session: AsyncSession, alert_id: str) -> Alert | None:
        result = await session.execute(
            select(Alert).where(Alert.id == alert_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def deactivate(session: AsyncSession, alert_id: str) -> None:
        from sqlalchemy import update
        await session.execute(
            update(Alert).where(Alert.id == alert_id).values(active="false")
        )
        await session.commit()