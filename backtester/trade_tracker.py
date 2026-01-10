"""
Trade Tracker
Monitors intra-trade price movements (MAE/MFE) and captures trade lifecycle events.
Integrates with BacktestEngine to track trades from entry to exit.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from collections import defaultdict

from common.models import (
    TradeRecord,
    OrderExecution,
    SignalEvent,
    ExitReason,
    CandleData
)

logger = logging.getLogger(__name__)


class IntraTradeMetrics:
    """Tracks intra-trade metrics like MAE/MFE"""
    
    def __init__(self, entry_price: float):
        self.entry_price = entry_price
        self.max_price = entry_price
        self.min_price = entry_price
        self.high_water_mark = entry_price  # Highest price reached
        self.low_water_mark = entry_price   # Lowest price reached
    
    def update(self, price: float):
        """Update with new candle price"""
        self.max_price = max(self.max_price, price)
        self.min_price = min(self.min_price, price)
        self.high_water_mark = max(self.high_water_mark, price)
        self.low_water_mark = min(self.low_water_mark, price)
    
    def get_mae_mfe(self, is_long: bool) -> tuple:
        """
        Calculate Maximum Adverse Excursion and Maximum Favorable Excursion.
        
        For LONG:
            - MAE = how much price went down from entry (adverse)
            - MFE = how much price went up from entry (favorable)
        
        For SHORT:
            - MAE = how much price went up from entry (adverse)
            - MFE = how much price went down from entry (favorable)
        
        Returns: (MAE_pct, MFE_pct)
        """
        if is_long:
            mae_pct = (self.min_price - self.entry_price) / self.entry_price
            mfe_pct = (self.max_price - self.entry_price) / self.entry_price
        else:
            mae_pct = (self.entry_price - self.max_price) / self.entry_price
            mfe_pct = (self.entry_price - self.min_price) / self.entry_price
        
        return (mae_pct, mfe_pct)


class TradeTracker:
    """
    Tracks trades from entry signal through exit.
    Maintains open trades and links them with execution details.
    """
    
    def __init__(self):
        self.open_trades: Dict[str, TradeRecord] = {}  # {trade_id: TradeRecord}
        self.closed_trades: List[TradeRecord] = []
        self.intra_metrics: Dict[str, IntraTradeMetrics] = {}  # {trade_id: metrics}
        self.trade_counter = 0
        self.signal_cache: Dict[str, SignalEvent] = {}  # Cache last signal per symbol
    
    def on_entry_signal(self, signal: SignalEvent) -> Optional[str]:
        """
        Register entry signal. Called when a BUY/SELL signal is generated.
        
        Returns: trade_id for tracking
        """
        self.trade_counter += 1
        trade_id = f"TRADE-{signal.timestamp.strftime('%Y%m%d-%H%M%S')}-{self.trade_counter}"
        
        # Cache the signal
        self.signal_cache[signal.symbol] = signal
        
        # Create trade record (will be populated with execution details later)
        trade = TradeRecord(
            trade_id=trade_id,
            symbol=signal.symbol,
            trade_number=self.trade_counter,
            entry_time=signal.timestamp,
            entry_price=signal.indicators.get('price', 0.0),  # Price from signal
            entry_quantity=signal.indicators.get('quantity', 0.0),
            entry_signal=signal,
            entry_confidence=signal.confidence,
            entry_reason=signal.reason,
            entry_trigger_conditions=signal.trigger_conditions,
            entry_indicators=signal.indicators.copy(),
            entry_candle=signal.candle.copy() if signal.candle else None
        )
        
        self.open_trades[trade_id] = trade
        self.intra_metrics[trade_id] = IntraTradeMetrics(trade.entry_price)
        
        logger.debug(f"Entry signal registered: {trade_id} for {signal.symbol} at {trade.entry_price}")
        return trade_id
    
    def on_entry_execution(self, trade_id: str, execution: OrderExecution, 
                           is_long: bool = True):
        """
        Update trade with entry execution details.
        Called when the entry order is filled.
        """
        if trade_id not in self.open_trades:
            logger.warning(f"Trade {trade_id} not found in open trades")
            return
        
        trade = self.open_trades[trade_id]
        trade.entry_execution = execution
        trade.entry_price = execution.average_fill_price
        trade.entry_quantity = execution.filled_quantity
        trade.entry_slippage_bps = execution.slippage_bps
        trade.entry_commission = execution.commission
        trade.entry_market_impact = execution.market_impact
        
        # Reset intra-metrics with actual entry price
        self.intra_metrics[trade_id] = IntraTradeMetrics(execution.average_fill_price)
        
        logger.debug(f"Entry execution recorded for {trade_id}: "
                    f"{execution.filled_quantity} @ {execution.average_fill_price}")
    
    def on_price_update(self, trade_id: str, price: float):
        """
        Update intra-trade metrics with new price.
        Called on each candle/bar during trade.
        """
        if trade_id not in self.intra_metrics:
            logger.warning(f"Trade {trade_id} not found for price update")
            return
        
        self.intra_metrics[trade_id].update(price)
    
    def on_exit_signal(self, signal: SignalEvent, trade_id: str) -> bool:
        """
        Register exit signal for a trade.
        Called when an exit condition is detected.
        
        Returns: True if exit was valid, False otherwise
        """
        if trade_id not in self.open_trades:
            logger.warning(f"Trade {trade_id} not found for exit signal")
            return False
        
        trade = self.open_trades[trade_id]
        trade.exit_signal = signal
        trade.exit_time = signal.timestamp
        trade.exit_reason_text = signal.reason
        trade.exit_trigger_conditions = signal.trigger_conditions
        trade.exit_indicators = signal.indicators.copy()
        
        return True
    
    def on_exit_execution(self, trade_id: str, execution: OrderExecution,
                         exit_reason: ExitReason = ExitReason.SIGNAL_REVERSAL):
        """
        Update trade with exit execution details and finalize.
        Called when the exit order is filled.
        """
        if trade_id not in self.open_trades:
            logger.warning(f"Trade {trade_id} not found for exit execution")
            return
        
        trade = self.open_trades[trade_id]
        
        # Set exit execution details
        trade.exit_execution = execution
        trade.exit_price = execution.average_fill_price
        trade.exit_quantity = execution.filled_quantity
        trade.exit_time = execution.timestamp
        trade.exit_slippage_bps = execution.slippage_bps
        trade.exit_commission = execution.commission
        trade.exit_market_impact = execution.market_impact
        trade.exit_reason = exit_reason
        
        # Calculate P&L metrics
        self._calculate_trade_metrics(trade_id)
        
        # Move to closed trades
        self.closed_trades.append(trade)
        del self.open_trades[trade_id]
        
        logger.debug(f"Trade closed: {trade_id} with P&L: {trade.net_pnl:.2f}")
    
    def on_trade_exit_reason(self, trade_id: str, exit_reason: ExitReason, 
                            reason_text: str = ""):
        """
        Record why a trade was exited.
        """
        if trade_id in self.open_trades:
            self.open_trades[trade_id].exit_reason = exit_reason
            self.open_trades[trade_id].exit_reason_text = reason_text
        elif trade_id in [t.trade_id for t in self.closed_trades]:
            for trade in self.closed_trades:
                if trade.trade_id == trade_id:
                    trade.exit_reason = exit_reason
                    trade.exit_reason_text = reason_text
                    break
    
    def _calculate_trade_metrics(self, trade_id: str):
        """
        Calculate all derived metrics for a closed trade.
        """
        if trade_id not in self.open_trades:
            return
        
        trade = self.open_trades[trade_id]
        
        if not trade.exit_price:
            return
        
        # Determine if long or short
        is_long = trade.entry_execution.side == 'buy' if trade.entry_execution else True
        
        # Calculate gross P&L
        if is_long:
            trade.gross_pnl = (trade.exit_price - trade.entry_price) * trade.entry_quantity
        else:
            trade.gross_pnl = (trade.entry_price - trade.exit_price) * trade.entry_quantity
        
        # Calculate costs
        trade.total_costs = (
            trade.entry_slippage_bps + trade.exit_slippage_bps +
            trade.entry_commission + trade.exit_commission +
            trade.entry_market_impact + trade.exit_market_impact
        )
        
        # Net P&L
        trade.net_pnl = trade.gross_pnl - trade.total_costs
        
        # P&L percentage
        capital_at_risk = trade.entry_price * trade.entry_quantity
        if capital_at_risk > 0:
            trade.pnl_pct = (trade.net_pnl / capital_at_risk) * 100
        
        # Duration
        if trade.exit_time and trade.entry_time:
            delta = trade.exit_time - trade.entry_time
            trade.duration_seconds = delta.total_seconds()
            
            # Format holding period
            hours = int(delta.total_seconds() // 3600)
            minutes = int((delta.total_seconds() % 3600) // 60)
            if hours > 0:
                trade.holding_period = f"{hours}h {minutes}m"
            else:
                trade.holding_period = f"{minutes}m"
        
        # MAE/MFE
        mae_pct, mfe_pct = self.intra_metrics[trade_id].get_mae_mfe(is_long)
        trade.max_adverse_excursion_pct = mae_pct * 100
        trade.max_favorable_excursion_pct = mfe_pct * 100
        trade.max_adverse_excursion = mae_pct * capital_at_risk
        trade.max_favorable_excursion = mfe_pct * capital_at_risk
        
        # Min/Max prices
        trade.max_price = self.intra_metrics[trade_id].max_price
        trade.min_price = self.intra_metrics[trade_id].min_price
    
    def get_open_trade(self, trade_id: str) -> Optional[TradeRecord]:
        """Get an open trade"""
        return self.open_trades.get(trade_id)
    
    def get_all_trades(self) -> List[TradeRecord]:
        """Get all closed trades"""
        return self.closed_trades.copy()
    
    def get_open_trades(self) -> List[TradeRecord]:
        """Get all open trades"""
        return list(self.open_trades.values())
    
    def get_trade_statistics(self) -> Dict[str, any]:
        """Calculate aggregate statistics from all trades"""
        if not self.closed_trades:
            return {}
        
        winning_trades = [t for t in self.closed_trades if t.is_winner()]
        losing_trades = [t for t in self.closed_trades if t.is_loser()]
        breakeven_trades = [t for t in self.closed_trades if t.is_breakeven()]
        
        stats = {
            'total_trades': len(self.closed_trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'breakeven_trades': len(breakeven_trades),
            'win_rate': (len(winning_trades) / len(self.closed_trades) * 100) if self.closed_trades else 0,
            'total_pnl': sum(t.net_pnl for t in self.closed_trades),
            'avg_pnl': sum(t.net_pnl for t in self.closed_trades) / len(self.closed_trades) if self.closed_trades else 0,
            'avg_winner': sum(t.net_pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0,
            'avg_loser': sum(t.net_pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0,
            'max_pnl': max((t.net_pnl for t in self.closed_trades), default=0),
            'min_pnl': min((t.net_pnl for t in self.closed_trades), default=0),
            'avg_mae_pct': sum((t.max_adverse_excursion_pct or 0) for t in self.closed_trades) / len(self.closed_trades) if self.closed_trades else 0,
            'avg_mfe_pct': sum((t.max_favorable_excursion_pct or 0) for t in self.closed_trades) / len(self.closed_trades) if self.closed_trades else 0,
        }
        
        return stats
