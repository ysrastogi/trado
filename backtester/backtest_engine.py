"""
Backtest Engine
Coordinates data playback, strategy execution, and order simulation
"""

import logging
from typing import Dict, List, Any, Optional, Type
from datetime import datetime

from backtester.engine import PlaybackEngine
from backtester.execution_simulator import ExecutionSimulator
from strategy_engine.base_strategy import BaseStrategy
from common.models import (
    SignalEvent, 
    OrderType, 
    MarketConditions,
    PlaybackState,
    CandleData
)
from data_layer.market_stream.models import TickData

logger = logging.getLogger(__name__)

class BacktestEngine:
    """
    Orchestrates the backtesting process by connecting:
    1. PlaybackEngine (Data Source)
    2. Strategy (Logic)
    3. ExecutionSimulator (Order Execution)
    """
    
    def __init__(
        self,
        playback_engine: PlaybackEngine,
        execution_simulator: ExecutionSimulator,
        strategy_class: Type[BaseStrategy],
        strategy_config: Dict[str, Any],
        initial_capital: float = 100000.0
    ):
        self.playback = playback_engine
        self.execution = execution_simulator
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        
        # Initialize strategy
        self.strategy = strategy_class(config=strategy_config)
        
        # Register callbacks
        self.playback.register_tick_callback(self._on_tick)
        # We might need a candle callback if PlaybackEngine supports it, 
        # otherwise we might need to aggregate ticks or rely on PlaybackEngine feeding candles if it does that.
        # Looking at PlaybackEngine, it seems to feed candles via _process_next_candles -> _emit_tick (converting candle to ticks).
        # But BaseStrategy has on_candle. We might need to adapt this.
        
        # For now, let's assume we trigger strategy on ticks, or we need to modify PlaybackEngine to emit candles too.
        # Actually PlaybackEngine reads candles. It converts them to ticks to simulate real-time feed.
        # But for backtesting strategies often work on closed candles.
        
        # Let's check if PlaybackEngine has a candle callback.
        # It has _tick_callbacks, _signal_callbacks, _state_callbacks.
        # It does NOT seem to have a candle callback exposed publicly in the interface I read.
        # However, it has `_candles` storage.
        
        # If the strategy needs candles, we might need to reconstruct them or modify PlaybackEngine.
        # But wait, PlaybackEngine.load_data loads candles.
        
        # Let's assume for now we drive the strategy via ticks, and the strategy aggregates them or we add a candle callback to PlaybackEngine later.
        # Or better, let's add a candle callback to PlaybackEngine if it's missing, or check if I missed it.
        # I read `backtester/engine.py` lines 1-100 and 101-452.
        # It has `_emit_tick`.
        
        # Let's implement `_on_tick` to pass data to strategy.
        
    def start(self):
        """Start the backtest"""
        logger.info("Starting backtest...")
        self.playback.play()
        
    def stop(self):
        """Stop the backtest"""
        self.playback.stop()
        logger.info("Backtest stopped.")
        
    def _on_tick(self, tick: TickData, symbol: str):
        """Handle incoming tick"""
        # Update market conditions in execution simulator
        self.execution.update_market_conditions(symbol, MarketConditions(
            symbol=symbol,
            current_price=tick.quote,
            bid_price=tick.bid if tick.bid else tick.quote,
            ask_price=tick.ask if tick.ask else tick.quote,
            spread_bps=0,
            average_daily_volume=0, # Need to get this from somewhere
            current_volume=0, # TickData doesn't have volume
            volatility=0.2, # Placeholder
            liquidity_score=1.0
        ))
        
        # Pass to strategy
        # Note: BaseStrategy.on_tick expects Dict[str, Any]
        tick_dict = {
            'symbol': symbol,
            'price': tick.quote,
            'volume': 0,
            'timestamp': tick.timestamp
        }
        signal = self.strategy.on_tick(tick_dict)
        
        if signal:
            self._handle_signal(signal)
            
    def _handle_signal(self, signal: SignalEvent):
        """Process signal from strategy"""
        logger.info(f"Received signal: {signal.signal_type} for {signal.symbol}")
        
        # Convert signal to order
        quantity = 0
        side = None
        
        if "BUY" in signal.signal_type or "LONG" in signal.signal_type:
            side = "buy"
            # Simple position sizing: 10% of capital
            price = signal.indicators.get('price', 100.0) # Should come from signal or market
            quantity = (self.current_capital * 0.1) / price
        elif "SELL" in signal.signal_type or "SHORT" in signal.signal_type:
            side = "sell"
            # Logic to close position or go short
            quantity = 100 # Placeholder
            
        if side and quantity > 0:
            execution = self.execution.simulate_order(
                symbol=signal.symbol,
                side=side,
                quantity=quantity,
                order_type=OrderType.MARKET
            )
            
            if execution.status == "filled":
                logger.info(f"Executed {side} {quantity} {signal.symbol} @ {execution.average_fill_price}")
                # Update capital (simplified)
                cost = execution.get_total_cost()
                if side == 'buy':
                    self.current_capital -= (execution.filled_quantity * execution.average_fill_price + cost)
                else:
                    self.current_capital += (execution.filled_quantity * execution.average_fill_price - cost)

