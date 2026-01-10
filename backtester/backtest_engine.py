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
from feature_engine.indicator_calculator import IndicatorCalculator
from feature_engine.models import FeatureConfig
from common.models import (
    SignalEvent, 
    OrderType, 
    OrderStatus,
    MarketConditions,
    PlaybackState,
    CandleData
)
from common.events import (
    EventBus, EventType, Event,
    OrderCreatedEventData, OrderFilledEventData,
    EquityUpdateEventData
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
        initial_capital: float = 100000.0,
        signal_timeframe: Optional[str] = None,
        event_bus: Optional[EventBus] = None
    ):
        self.playback = playback_engine
        self.execution = execution_simulator
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.signal_timeframe = signal_timeframe
        self.event_bus = event_bus
        
        # Position Tracker {symbol: {'quantity': float, 'avg_price': float}}
        self.positions: Dict[str, Dict[str, Any]] = {}
        
        # Equity Curve Tracking
        self.equity_curve: List[Dict[str, Any]] = []
        
        # Candle Aggregation State
        self.current_aggregated_candle: Dict[str, CandleData] = {} # {symbol: candle}
        self.aggregation_start_time: Dict[str, datetime] = {}
        self.aggregated_history: Dict[str, List[CandleData]] = {} # {symbol: [candles]}
        
        # Initialize strategy
        self.strategy = strategy_class(config=strategy_config)
        
        # Initialize Calculator
        self.feature_config = FeatureConfig.from_dict(strategy_config.get('features', {}))
        self.calculator = IndicatorCalculator(self.feature_config)
        
        # Pre-calculate Indicators
        self.precalculated_features = {} # {symbol: {indicator_name: [values]}}
        # Only pre-calculate if we are NOT aggregating on the fly
        if not self.signal_timeframe or self.signal_timeframe == self.playback.interval:
            self._precalculate_features()
        
        # Register callbacks
        self.playback.register_tick_callback(self._on_tick)
        self.playback.register_candle_callback(self._on_candle)

    def _precalculate_features(self):
        """Run indicators on all historical data before backtest starts"""
        # Ensure data is loaded
        if not self.playback._candles:
            self.playback.load_data()
            
        for symbol in self.playback.symbols:
            candles = self.playback._candles.get(symbol, [])
            if candles:
                self.precalculated_features[symbol] = self.calculator.calculate_indicators(candles)
                logger.info(f"Pre-calculated features for {symbol}: {list(self.precalculated_features[symbol].keys())}")

    def _on_candle(self, candle: CandleData, symbol: str):
        """Handle candle close"""
        # logger.info(f"Received candle: {candle.timestamp}")
        
        # 1. Update Execution Simulator with latest price
        self.execution.update_market_conditions(symbol, MarketConditions(
            symbol=symbol,
            current_price=candle.close,
            bid_price=candle.close, # Simplified
            ask_price=candle.close, # Simplified
            spread_bps=0.0,
            average_daily_volume=candle.volume, # Approximation
            current_volume=candle.volume,
            volatility=0.2, # Placeholder
            liquidity_score=1.0
        ))
        
        # 2. Track Equity
        # Note: This is a simplification. Ideally we mark-to-market all open positions.
        # For now we just track cash + unrealized PnL if we had access to positions.
        # Since ExecutionSimulator doesn't expose open positions easily, we might need to rely on realized PnL.
        # But let's just track timestamp for now.
        self.equity_curve.append({
            'timestamp': candle.timestamp,
            'equity': self.current_capital # This needs to be updated with PnL
        })
        
        # Publish Equity Update Event
        if self.event_bus:
            self.event_bus.publish(Event(
                EventType.EQUITY_UPDATE,
                candle.timestamp,
                EquityUpdateEventData(
                    timestamp=candle.timestamp,
                    equity=self.current_capital,
                    cash=self.current_capital, # Assuming 100% cash for now as positions simplistically managed
                    margin_used=0.0
                )
            ))

        # 3. Handle Aggregation or Direct Pass-through
        if self.signal_timeframe and self.signal_timeframe != self.playback.interval:
            self._handle_aggregated_candle(candle, symbol)
        else:
            self._handle_direct_candle(candle, symbol)

    def _handle_direct_candle(self, candle: CandleData, symbol: str):
        # Get current index from playback engine
        current_idx = self.playback._current_index.get(symbol, 0)
        
        # Extract features for this specific candle index
        current_features = {}
        if symbol in self.precalculated_features:
            for name, values in self.precalculated_features[symbol].items():
                if current_idx < len(values):
                    current_features[name] = values[current_idx]
        
        # Pass to strategy
        signal = self.strategy.on_candle(candle, features=current_features)
        
        if signal:
            self._handle_signal(signal)

    def _handle_aggregated_candle(self, candle: CandleData, symbol: str):
        """Aggregate high-frequency candles into signal timeframe"""
        # Parse timeframes (assuming '1m', '5m' format)
        try:
            tf_min = int(self.signal_timeframe[:-1])
        except ValueError:
            logger.error(f"Invalid signal timeframe: {self.signal_timeframe}")
            return
        
        # Initialize if needed
        if symbol not in self.current_aggregated_candle:
            self.aggregation_start_time[symbol] = candle.timestamp
            self.current_aggregated_candle[symbol] = candle
            return

        # Update current aggregated candle
        curr = self.current_aggregated_candle[symbol]
        curr.high = max(curr.high, candle.high)
        curr.low = min(curr.low, candle.low)
        curr.close = candle.close
        curr.volume += candle.volume
        
        # Check if aggregation period is complete
        # Simple check: if time difference >= timeframe
        time_diff = candle.timestamp - self.aggregation_start_time[symbol]
        if time_diff.total_seconds() >= (tf_min * 60) - 60: # -60 because we are at the END of the minute
             
             # Add to history
             if symbol not in self.aggregated_history:
                 self.aggregated_history[symbol] = []
             self.aggregated_history[symbol].append(curr)
             
             # Calculate indicators on the fly
             # We need enough history for indicators
             # Optimization: Only calculate for the last candle, but Calculator might need full series
             # For now, we recalculate on the growing list. This is slow but correct.
             features = self.calculator.calculate_indicators(self.aggregated_history[symbol])
             
             # Extract latest features
             current_features = {k: v[-1] for k, v in features.items() if len(v) > 0}
             
             # Pass to strategy
             signal = self.strategy.on_candle(curr, features=current_features)
             
             if signal:
                 self._handle_signal(signal)
             
             # Reset
             del self.current_aggregated_candle[symbol]


    def start(self):
        """Start the backtest"""
        logger.info("Starting backtest...")
        self.playback.play()
        
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Calculate and return performance metrics including:
        - Total Return %
        - Sharpe Ratio
        - Max Drawdown
        - Win Rate
        """
        from backtester.reporter import BacktestReporter
        
        # 1. Gather stats from execution simulator
        stats = self.execution.get_execution_statistics()
        
        # 2. Add equity curve and executions for metric calculation
        stats['equity_curve'] = self.equity_curve
        stats['executions'] = self.execution.execution_history
        
        # 3. Calculate advanced metrics using Reporter logic
        reporter = BacktestReporter()
        metrics = reporter.calculate_metrics(stats)
        
        # Merge metrics back into stats to include all execution stats
        stats.update(metrics)
        
        # 4. Add simple Total Return % if not present
        if self.equity_curve:
            start_equity = self.initial_capital
            end_equity = self.current_capital # OR self.equity_curve[-1]['equity']
            total_return = (end_equity - start_equity) / start_equity
            stats['total_return_pct'] = total_return * 100
            stats['final_equity'] = end_equity
            stats['initial_capital'] = self.initial_capital
            
        # 5. Map keys to expected names
        if 'sharpe' in stats:
            stats['sharpe_ratio'] = stats['sharpe']
            
        return stats

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
        
        # Publish Signal Event
        if self.event_bus:
            self.event_bus.publish(Event(EventType.SIGNAL, signal.timestamp, signal))
        
        symbol = signal.symbol
        # Get current position
        current_pos = self.positions.get(symbol, {'quantity': 0.0, 'avg_price': 0.0})
        existing_qty = current_pos['quantity']
        
        # Convert signal to order
        quantity = 0.0
        side = None
        
        # Determine price for sizing
        price = signal.indicators.get('price', 0.0)
        if price <= 0:
             # Fallback to execution state if price missing in signal
             market = self.execution.market_state.get(symbol)
             price = market.current_price if market else 100.0
        
        if "BUY" in signal.signal_type or "LONG" in signal.signal_type:
            side = "buy"
            # Simple position sizing: 10% of capital
            if self.current_capital > 0 and price > 0:
                quantity = (self.current_capital * 0.1) / price
                
        elif "SELL" in signal.signal_type or "SHORT" in signal.signal_type:
            side = "sell"
            # Logic to close ENTIRE position
            quantity = existing_qty
            
        if side and quantity > 0:
            # Publish Order Created
            if self.event_bus:
                self.event_bus.publish(Event(
                    EventType.ORDER_CREATED, 
                    signal.timestamp, 
                    OrderCreatedEventData(
                        order_id=f"ORD-{signal.timestamp.timestamp()}",
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        price=price,
                        order_type="MARKET",
                        timestamp=signal.timestamp
                    )
                ))

            # Capture state before execution for validation
            prev_capital = self.current_capital

            execution = self.execution.simulate_order(
                symbol=signal.symbol,
                side=side,
                quantity=quantity,
                order_type=OrderType.MARKET,
                current_price=price  # Pass invalidates fallback
            )
            
            if execution.status == OrderStatus.FILLED:
                logger.info(f"Executed {side} {quantity:.2f} {signal.symbol} @ {execution.average_fill_price:.2f}")
                
                # Publish Order Filled
                if self.event_bus:
                    self.event_bus.publish(Event(
                        EventType.ORDER_FILLED,
                        signal.timestamp,
                        OrderFilledEventData(
                            order_id=execution.order_id,
                            symbol=symbol,
                            side=side,
                            filled_quantity=execution.filled_quantity,
                            price=execution.average_fill_price,
                            timestamp=execution.timestamp,
                            commission=execution.commission,
                            slippage=execution.slippage
                        )
                    ))

                fill_val = execution.filled_quantity * execution.average_fill_price
                commission = execution.commission
                
                if side == 'buy':
                    # Cash Outflow: Price + Commission
                    self.current_capital -= (fill_val + commission)
                    
                    # Update Position Logic (Weighted Average Price)
                    old_cost = existing_qty * current_pos['avg_price']
                    new_qty = existing_qty + execution.filled_quantity
                    new_avg = (old_cost + fill_val) / new_qty if new_qty > 0 else 0.0
                    
                    self.positions[symbol] = {
                        'quantity': new_qty,
                        'avg_price': new_avg
                    }
                    
                else: # sell
                    # Cash Inflow: Price - Commission
                    self.current_capital += (fill_val - commission)
                    
                    # Calculate Realized PnL
                    avg_entry = current_pos['avg_price']
                    realized_pnl = ((execution.average_fill_price - avg_entry) * execution.filled_quantity) - commission
                    
                    print(f"Trade Closed: {symbol} | PnL: {realized_pnl:.2f} | Capital: {self.current_capital:.2f}")                    
                    # VALIDATION: Equity MUST change
                    assert self.current_capital != prev_capital, "CRITICAL: Equity did not change after trade! Check PnL logic."                    
                    # Close Position
                    remaining_qty = existing_qty - execution.filled_quantity
                    if remaining_qty < 0.0001:
                        self.positions[symbol] = {'quantity': 0.0, 'avg_price': 0.0}
                    else:
                        self.positions[symbol]['quantity'] = remaining_qty

