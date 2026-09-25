"""

Base event definitions used throughout the platform.

"""
from __future__ import annotations
from dataclasses import dataclass
from uuid import UUID, uuid4
from datetime import datetime , timezone
from typing import  Self

@dataclass(kw_only=True)
class BaseEvent:
    event_id: UUID
    sequence_id: int
    created_at: datetime
    correlation_id: UUID
    causation_id: UUID | None = None

    @classmethod
    def new(
        cls,
        sequence_id: int,
        correlation_id: UUID,
        causation_id: UUID | None = None,
        **payload,
    ) -> Self:
        return cls(
            event_id=uuid4(),
            sequence_id=sequence_id,
            created_at=datetime.now(timezone.utc),
            correlation_id=correlation_id,
            causation_id=causation_id,
            **payload,
        )

@dataclass
class PriceUpdated(BaseEvent):
    epic: str
    bid: float
    ask: float
    broker_timestamp: datetime
    @classmethod
    def new(cls, sequence_id: int, correlation_id, epic: str,
            bid: float, ask: float, broker_timestamp: datetime,
            causation_id=None):
        return cls(
            event_id=uuid4(),
            sequence_id=sequence_id,
            created_at=datetime.now(timezone.utc),
            correlation_id=correlation_id,
            causation_id=causation_id,
            epic=epic,
            bid=bid,
            ask=ask,
            broker_timestamp=broker_timestamp,
        )

@dataclass
class CandleClosed(BaseEvent):
    epic: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    candle_time: datetime

@dataclass
class MarketDisconnected(BaseEvent):
    reason: str

@dataclass
class MarketReconnected(BaseEvent):
    pass

@dataclass
class SignalDetected(BaseEvent):
    epic: str
    direction: str  # "BUY" or "SELL"
    price: float

@dataclass
class RiskApproved(BaseEvent):
    epic: str
    size: float

@dataclass
class RiskRejected(BaseEvent):
    epic: str
    reason: str

@dataclass
class OrderSubmitted(BaseEvent):
    epic: str
    client_order_id: str
    size: float

@dataclass
class OrderFilled(BaseEvent):
    epic: str
    client_order_id: str
    fill_price: float

@dataclass
class OrderRejected(BaseEvent):
    epic: str
    client_order_id: str
    reason: str

@dataclass
class PositionOpened(BaseEvent):
    epic: str
    deal_reference: str
    size: float
    entry_price: float

@dataclass
class PositionClosed(BaseEvent):
    epic: str
    deal_reference: str
    close_price: float

@dataclass
class PartialFillDetected(BaseEvent):
    epic: str
    client_order_id: str
    filled: float
    total: float

@dataclass
class WebSocketDisconnected(BaseEvent):
    reason: str

@dataclass
class SessionExpired(BaseEvent):
    pass

@dataclass
class CircuitBreakerOpened(BaseEvent):
    reason: str

@dataclass
class TradingDisabled(BaseEvent):
    reason: str

@dataclass
class DeadLetterCreated(BaseEvent):
    original_event_type: str
    failure_reason: str
