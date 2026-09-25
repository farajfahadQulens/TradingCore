"""SQLAlchemy ORM model for a trade log.
"""
from sqlalchemy import Column, String, DateTime , JSON
from app.db.models.base import Base
from datetime import datetime , timezone




class TradeLog(Base):
    __tablename__ = "trade_logs"

    id = Column(String, primary_key=True)
    event_type = Column(String, index=True)  # OrderFilled, RiskRejected, etc.
    payload = Column(JSON)                   # full event data
    correlation_id = Column(String, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))