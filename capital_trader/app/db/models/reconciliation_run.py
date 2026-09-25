"""SQLAlchemy ORM model for reconciliation run summaries."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, JSON, String

from app.db.models.base import Base


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id = Column(String, primary_key=True)
    status = Column(String, index=True)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(String, nullable=True)
    summary = Column(JSON, nullable=True)
