"""SQLAlchemy ORM model for a candle.
"""
from sqlalchemy import Column, String, Numeric, DateTime
from app.db.models.base import Base
from datetime import datetime , timezone




class Candle(Base):
    __tablename__ = "candles"

    id = Column(String, primary_key=True)
    epic = Column(String, index=True)
    timeframe = Column(String)               # MINUTE, MINUTE_5, HOUR, DAY etc.
    open = Column(Numeric(10, 2))
    high = Column(Numeric(10, 2))
    low = Column(Numeric(10, 2))
    close = Column(Numeric(10, 2))
    bid_close = Column(Numeric(10, 2), nullable=True)
    ask_close = Column(Numeric(10, 2), nullable=True)
    candle_time = Column(DateTime(timezone=True), index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))