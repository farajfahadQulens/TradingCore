"""Repository layer for reconciliation run summaries."""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.reconciliation_run import ReconciliationRun


class ReconciliationRunRepo:
    @staticmethod
    async def create(session: AsyncSession, run: ReconciliationRun) -> ReconciliationRun:
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run

    @staticmethod
    async def update_fields(session: AsyncSession, run_id: str, **fields) -> ReconciliationRun | None:
        await session.execute(
            update(ReconciliationRun)
            .where(ReconciliationRun.id == run_id)
            .values(**fields)
        )
        await session.commit()
        return await ReconciliationRunRepo.get_by_id(session, run_id)

    @staticmethod
    async def get_by_id(session: AsyncSession, run_id: str) -> ReconciliationRun | None:
        result = await session.execute(select(ReconciliationRun).where(ReconciliationRun.id == run_id))
        return result.scalar_one_or_none()
