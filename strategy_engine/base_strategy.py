from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from common.models import CandleData, SignalEvent

@dataclass
class Position:
    """Represents a current trading position"""
    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    pl: float = 0.0
    pl_pct: float = 0.0
    
    def update(self, current_price: float):
        """Update position P&L based on current price"""
        self.current_price = current_price
        if self.quantity > 0:  # Long
            self.pl = (self.current_price - self.entry_price) * self.quantity
            self.pl_pct = (self.current_price - self.entry_price) / self.entry_price
        elif self.quantity < 0:  # Short
            self.pl = (self.entry_price - self.current_price) * abs(self.quantity)
            self.pl_pct = (self.entry_price - self.current_price) / self.entry_price

class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    """
    def __init__(self, config: Dict[str, Any], risk_params: Optional[Dict[str, Any]] = None):
        self.config = config
        self.risk_params = risk_params or {}
        self.position: Optional[Position] = None
        self.setup_indicators()

    @abstractmethod
    def setup_indicators(self):
        """Initialize strategy indicators"""
        pass

    @abstractmethod
    def on_tick(self, tick_data: Dict[str, Any]) -> Optional[SignalEvent]:
        """
        Called when a new tick is received.
        """
        pass
    
    @abstractmethod
    def on_bar(self, bar_data: Dict[str, Any]) -> Optional[SignalEvent]:
        """
        Called when a new bar (not necessarily a closed candle) is received.
        """
        pass

    @abstractmethod
    def on_candle(self, candle: CandleData) -> Optional[SignalEvent]:
        """
        Called when a new candle is closed.
        """
        # Base implementation checks risk management
        if self.position:
            self.position.update(candle.close)
            risk_signal = self.check_risk_management(candle.close)
            if risk_signal:
                return risk_signal
        return None

    def update_position(self, symbol: str, quantity: float, price: float, side: str):
        """
        Update position after an execution.
        """
        if not self.position:
            if side == 'buy':
                self.position = Position(symbol, quantity, price, price)
            elif side == 'sell':
                self.position = Position(symbol, -quantity, price, price)
        else:
            # Simplified position update logic
            if side == 'buy':
                new_qty = self.position.quantity + quantity
                # Weighted average price calculation could be added here
                self.position.quantity = new_qty
            elif side == 'sell':
                new_qty = self.position.quantity - quantity
                self.position.quantity = new_qty
            
            if self.position.quantity == 0:
                self.position = None

    def check_risk_management(self, current_price: float) -> Optional[SignalEvent]:
        """
        Check if risk management rules (SL/TP) are triggered.
        """
        if not self.position:
            return None
            
        stop_loss_pct = self.risk_params.get('stop_loss_pct', 0.02)
        take_profit_pct = self.risk_params.get('take_profit_pct', 0.04)
        
        # Check Stop Loss
        if self.position.pl_pct <= -stop_loss_pct:
            return SignalEvent(
                timestamp=datetime.utcnow(),
                symbol=self.position.symbol,
                algorithm="RiskManager",
                signal_type="EXIT_LONG" if self.position.quantity > 0 else "EXIT_SHORT",
                confidence=1.0,
                reason=f"Stop Loss triggered at {self.position.pl_pct:.2%}",
                trigger_conditions=["stop_loss"],
                indicators={"pl_pct": self.position.pl_pct}
            )
            
        # Check Take Profit
        if self.position.pl_pct >= take_profit_pct:
            return SignalEvent(
                timestamp=datetime.utcnow(),
                symbol=self.position.symbol,
                algorithm="RiskManager",
                signal_type="EXIT_LONG" if self.position.quantity > 0 else "EXIT_SHORT",
                confidence=1.0,
                reason=f"Take Profit triggered at {self.position.pl_pct:.2%}",
                trigger_conditions=["take_profit"],
                indicators={"pl_pct": self.position.pl_pct}
            )
            
        return None
