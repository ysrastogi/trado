from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
import logging

from common.models import SignalEvent, OrderExecution, TradeRecord, CandleData

class EventType(Enum):
    MARKET_DATA = "MARKET_DATA"
    SIGNAL = "SIGNAL"
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_FILLED = "ORDER_FILLED"
    TRADE_CLOSED = "TRADE_CLOSED"
    EQUITY_UPDATE = "EQUITY_UPDATE"
    SYSTEM = "SYSTEM"

@dataclass
class Event:
    type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    data: Any = None

@dataclass
class MarketEventData:
    symbol: str
    candle: CandleData

@dataclass
class OrderCreatedEventData:
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: Optional[float]
    order_type: str
    timestamp: datetime

@dataclass
class OrderFilledEventData:
    order_id: str
    symbol: str
    side: str
    filled_quantity: float
    price: float
    timestamp: datetime
    commission: float = 0.0
    slippage: float = 0.0

@dataclass
class TradeClosedEventData:
    trade: TradeRecord

@dataclass
class EquityUpdateEventData:
    timestamp: datetime
    equity: float
    cash: float
    margin_used: float

class EventBus:
    """
    Central event bus for the application.
    Implements a simple Pub-Sub pattern.
    """
    def __init__(self):
        self.subscribers = {}
        self.logger = logging.getLogger("EventBus")

    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)
        self.logger.debug(f"Subscribed to {event_type.value}: {callback.__name__}")

    def publish(self, event: Event):
        if event.type in self.subscribers:
            for callback in self.subscribers[event.type]:
                try:
                    callback(event)
                except Exception as e:
                    self.logger.error(f"Error in subscriber {callback.__name__}: {e}", exc_info=True)

    def clear(self):
        """Clear all subscribers (useful for testing)"""
        self.subscribers = {}
