"""SQLAlchemy ORM model for an order.
"""
from sqlalchemy import Column, String, Numeric, DateTime
from app.db.models.base import Base
from datetime import datetime , timezone




class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    epic = Column(String, index=True)
    order_type = Column(String)              # LIMIT, STOP
    state = Column(String, default="PENDING")  # PENDING, FILLED, PARTIALLY_FILLED, CANCELLED, REJECTED, CLOSED
    size = Column(Numeric(10, 2))
    limit_price = Column(Numeric(10, 2), nullable=True)
    broker_order_id = Column(String, nullable=True)
    client_order_id = Column(String, unique=True)   # idempotency key
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    filled_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))