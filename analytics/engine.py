import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd
import numpy as np
from collections import deque

from common.events import (
    EventBus, EventType, Event, 
    OrderFilledEventData, OrderCreatedEventData,
    TradeClosedEventData, EquityUpdateEventData, SignalEvent
)
from common.models import TradeRecord

logger = logging.getLogger(__name__)

class AnalyticsEngine:
    """
    Central Analytics Engine that observes the trading system events
    and maintains real-time performance metrics and trade history.
    """
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.trades: List[TradeRecord] = []
        self.equity_curve: List[Dict[str, Any]] = []
        self.active_orders: Dict[str, OrderCreatedEventData] = {}
        self.open_positions: Dict[str, Dict[str, Any]] = {}  # symbol -> details
        
        # Subscribe to events
        self.event_bus.subscribe(EventType.ORDER_CREATED, self.on_order_created)
        self.event_bus.subscribe(EventType.ORDER_FILLED, self.on_order_filled)
        self.event_bus.subscribe(EventType.TRADE_CLOSED, self.on_trade_closed)
        self.event_bus.subscribe(EventType.EQUITY_UPDATE, self.on_equity_update)
        
        logger.info("AnalyticsEngine initialized and listening to events.")

    def on_order_created(self, event: Event):
        if not isinstance(event.data, OrderCreatedEventData):
            return
        self.active_orders[event.data.order_id] = event.data

    def on_order_filled(self, event: Event):
        if not isinstance(event.data, OrderFilledEventData):
            return
        
        fill_data = event.data
        # logic to track open positions if needed, 
        # but primarily we rely on TRADE_CLOSED events for full trade records
        # However, for live updates we might want to track partials here.
        pass

    def on_trade_closed(self, event: Event):
        """
        Receive a fully formed TradeRecord from the Strategy logic or TradeTracker
        """
        if not isinstance(event.data, TradeClosedEventData):
            return
        self.trades.append(event.data.trade)
        logger.info(f"Recorded closed trade: {event.data.trade.trade_id} PnL: {event.data.trade.net_pnl}")

    def on_equity_update(self, event: Event):
        if not isinstance(event.data, EquityUpdateEventData):
            return
        self.equity_curve.append({
            'timestamp': event.data.timestamp,
            'equity': event.data.equity,
            'cash': event.data.cash,
            'margin_used': event.data.margin_used
        })

    def get_metrics(self) -> Dict[str, Any]:
        """Calculate and return current performance metrics"""
        if not self.equity_curve:
            return self._empty_metrics()

        df = pd.DataFrame(self.equity_curve)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        # Basic Metrics
        start_equity = df['equity'].iloc[0]
        end_equity = df['equity'].iloc[-1]
        
        # CAGR
        days = (df.index[-1] - df.index[0]).days
        if days > 0:
            cagr = (end_equity / start_equity) ** (365 / days) - 1
        else:
            cagr = 0

        # Max Drawdown
        df['peak'] = df['equity'].cummax()
        df['drawdown'] = (df['equity'] - df['peak']) / df['peak']
        max_drawdown = df['drawdown'].min() * 100

        # Sharpe
        df['returns'] = df['equity'].pct_change()
        sharpe = 0
        if df['returns'].std() > 0:
            sharpe = (df['returns'].mean() / df['returns'].std()) * np.sqrt(252 * 1440) # Approximately minutes? Adjust if data is not daily.
            # Assuming equity updates are frequent, standard Sharpe calculation requires periodic returns. 
            # We will approximate or assume daily data if we resample.
            # Let's resample to daily for standard Sharpe
            daily_returns = df['equity'].resample('D').last().dropna().pct_change()
            if daily_returns.std() > 0:
                sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)

        # Trade Stats from recorded trades
        wins = [t for t in self.trades if t.net_pnl > 0]
        losses = [t for t in self.trades if t.net_pnl <= 0]
        
        win_rate = len(wins) / len(self.trades) * 100 if self.trades else 0
        total_pnl = sum(t.net_pnl for t in self.trades)
        profit_factor = abs(sum(t.net_pnl for t in wins) / sum(t.net_pnl for t in losses)) if losses and sum(t.net_pnl for t in losses) != 0 else float('inf')

        return {
            "total_trades": len(self.trades),
            "win_rate": win_rate,
            "cagr_pct": cagr * 100,
            "max_drawdown_pct": max_drawdown,
            "sharpe_ratio": sharpe,
            "total_pnl": total_pnl,
            "profit_factor": profit_factor,
            "equity_current": end_equity
        }

    def _empty_metrics(self):
        return {
            "total_trades": 0,
            "win_rate": 0.0, 
            "cagr_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "total_pnl": 0.0,
            "equity_current": 0.0
        }
