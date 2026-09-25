"""SQLAlchemy ORM model for an alert.
"""
from sqlalchemy import Column, String, Numeric, DateTime
from app.db.models.base import Base
from datetime import datetime , timezone




class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True)
    epic = Column(String, index=True)
    threshold = Column(Numeric(10, 2))
    direction = Column(String)               # ABOVE, BELOW
    notification_channel = Column(String)    # email, slack, log
    active = Column(String, default="true")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))