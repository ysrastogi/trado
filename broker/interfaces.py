from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    # Binary Options / Deriv specific
    CALL = "CALL"
    PUT = "PUT"
    DIGITDIFF = "DIGITDIFF"
    DIGITEVEN = "DIGITEVEN"
    DIGITODD = "DIGITODD"
    DIGITOVER = "DIGITOVER"
    DIGITUNDER = "DIGITUNDER"
    UPORDOWN = "UPORDOWN"

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    NEW = "NEW"

@dataclass
class OrderRequest:
    symbol: str
    order_type: OrderType
    side: OrderSide
    quantity: float # Stake for options
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    # For Deriv/Options
    duration: Optional[int] = None
    duration_unit: Optional[str] = None # 't', 'm', 'h', 'd'
    barrier: Optional[str] = None
    strategy_name: Optional[str] = None
    
@dataclass
class OrderResult:
    order_id: str
    status: OrderStatus
    filled_quantity: float
    average_price: float
    timestamp: datetime
    error_message: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None

@dataclass
class Position:
    symbol: str
    side: OrderSide
    quantity: float
    average_entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    position_id: Optional[str] = None
    open_time: Optional[datetime] = None

class IBrokerAdapter(ABC):
    """Interface for broker-specific implementations"""
    
    @abstractmethod
    def connect(self) -> bool:
        pass
        
    @abstractmethod
    def disconnect(self):
        pass
        
    @abstractmethod
    def place_order(self, order: OrderRequest) -> OrderResult:
        pass
        
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        pass
        
    @abstractmethod
    def get_positions(self) -> List[Position]:
        pass
        
    @abstractmethod
    def get_balance(self) -> float:
        pass

class IOrderExecutionService(ABC):
    """Interface for the high-level execution service"""
    
    @abstractmethod
    def start(self):
        pass
        
    @abstractmethod
    def stop(self):
        pass
        
    @abstractmethod
    def execute_order(self, order: OrderRequest) -> OrderResult:
        pass
        
    @abstractmethod
    def get_active_positions(self) -> List[Position]:
        pass
        
    @abstractmethod
    def get_account_balance(self) -> float:
        pass
