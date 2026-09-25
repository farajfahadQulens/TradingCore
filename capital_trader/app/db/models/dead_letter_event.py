"""SQLAlchemy ORM model for dead letter events.
"""
from sqlalchemy import Column, String, DateTime, JSON
from app.db.models.base import Base
from datetime import datetime, timezone


class DeadLetterEvent(Base):
    __tablename__ = "dead_letter_events"

    id = Column(String, primary_key=True)
    event_type = Column(String, index=True)
    raw_payload = Column(JSON)
    failure_reason = Column(String)
    retry_count = Column(String, default="0")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime(timezone=True), nullable=True)