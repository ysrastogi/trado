from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from common.models import CandleData, SignalEvent, ExitReason

@dataclass
class Position:
    """Represents a current trading position"""
    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    entry_time: datetime = field(default_factory=datetime.utcnow)
    pl: float = 0.0
    pl_pct: float = 0.0
    exit_reason: Optional[ExitReason] = None
    exit_reason_text: str = ""
    
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
    Tracks position lifecycle with exit reason callbacks.
    """
    def __init__(self, config: Dict[str, Any], risk_params: Optional[Dict[str, Any]] = None):
        self.config = config
        self.risk_params = risk_params or {}
        self.position: Optional[Position] = None
        self.features: Dict[str, float] = {}
        
        # Exit reason callbacks
        self._exit_callbacks: Dict[ExitReason, Callable] = {
            ExitReason.STOP_LOSS: self._default_on_stop_loss,
            ExitReason.TAKE_PROFIT: self._default_on_take_profit,
            ExitReason.SIGNAL_REVERSAL: self._default_on_signal_reversal,
            ExitReason.MANUAL_EXIT: self._default_on_manual_exit,
            ExitReason.TIMEOUT: self._default_on_timeout,
            ExitReason.LIQUIDATION: self._default_on_liquidation,
        }
        
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
    def on_candle(self, candle: CandleData, features: Optional[Dict[str, float]] = None) -> Optional[SignalEvent]:
        """
        Called when a new candle is closed.
        """
        if features:
            self.features = features

        # Base implementation checks risk management
        if self.position:
            self.position.update(candle.close)
            risk_signal = self.check_risk_management(candle.close)
            if risk_signal:
                return risk_signal
        return None

    def update_position(self, symbol: str, quantity: float, price: float, side: str, 
                       entry_time: Optional[datetime] = None):
        """
        Update position after an execution.
        """
        if not self.position:
            if side == 'buy':
                self.position = Position(symbol, quantity, price, price, 
                                       entry_time=entry_time or datetime.utcnow())
            elif side == 'sell':
                self.position = Position(symbol, -quantity, price, price,
                                       entry_time=entry_time or datetime.utcnow())
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
            self.on_stop_loss_hit(current_price)
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
            self.on_take_profit_hit(current_price)
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
    
    def on_stop_loss_hit(self, exit_price: float):
        """
        Called when stop loss is triggered.
        Override in subclass to add custom logic.
        """
        self._default_on_stop_loss(exit_price)
    
    def on_take_profit_hit(self, exit_price: float):
        """
        Called when take profit is triggered.
        Override in subclass to add custom logic.
        """
        self._default_on_take_profit(exit_price)
    
    def on_signal_reversal(self, exit_price: float, new_signal: str):
        """
        Called when signal reverses (e.g., from BUY to SELL).
        Override in subclass to add custom logic.
        """
        self._default_on_signal_reversal(exit_price, new_signal)
    
    def on_manual_exit(self, exit_price: float, reason: str = ""):
        """
        Called when position is manually closed.
        Override in subclass to add custom logic.
        """
        self._default_on_manual_exit(exit_price, reason)
    
    def on_timeout(self, exit_price: float, holding_duration: float):
        """
        Called when position exceeds max holding duration.
        Override in subclass to add custom logic.
        """
        self._default_on_timeout(exit_price, holding_duration)
    
    def on_liquidation(self, exit_price: float):
        """
        Called when position is forcefully closed (e.g., margin call).
        Override in subclass to add custom logic.
        """
        self._default_on_liquidation(exit_price)
    
    def record_exit_reason(self, exit_reason: ExitReason, reason_text: str = ""):
        """
        Record why a position is being exited.
        Should be called before closing position.
        """
        if self.position:
            self.position.exit_reason = exit_reason
            self.position.exit_reason_text = reason_text
            # Invoke callback if registered
            if exit_reason in self._exit_callbacks:
                self._exit_callbacks[exit_reason](reason_text)
    
    # Default callback implementations (no-op)
    def _default_on_stop_loss(self, exit_price: float):
        """Default stop loss handler"""
        pass
    
    def _default_on_take_profit(self, exit_price: float):
        """Default take profit handler"""
        pass
    
    def _default_on_signal_reversal(self, exit_price: float, new_signal: str):
        """Default signal reversal handler"""
        pass
    
    def _default_on_manual_exit(self, exit_price: float, reason: str):
        """Default manual exit handler"""
        pass
    
    def _default_on_timeout(self, exit_price: float, holding_duration: float):
        """Default timeout handler"""
        pass
    
    def _default_on_liquidation(self, exit_price: float):
        """Default liquidation handler"""
        pass
