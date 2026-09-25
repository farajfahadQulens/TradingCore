"""SQLAlchemy ORM model for a trading position.
"""
from sqlalchemy import Column, String, Numeric, DateTime
from app.db.models.base import Base
from datetime import datetime , timezone

class Position(Base):
    __tablename__ = "positions"

    id = Column(String, primary_key=True)  # broker‑provided UUID
    epic = Column(String, index=True)
    size = Column(Numeric(10, 2))
    entry_price = Column(Numeric(10, 2))
    stop_loss = Column(Numeric(10, 2), nullable=True)
    take_profit = Column(Numeric(10, 2), nullable=True)
    opened_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    deal_reference = Column(String, nullable=True)   # broker's deal ID
    close_price = Column(Numeric(10, 2), nullable=True)        # filled when closed
    closed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, default="OPEN")           # OPEN, CLOSED
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))    
