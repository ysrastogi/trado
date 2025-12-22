import logging
from typing import Dict, Any, Optional, List, Deque
from collections import deque
from datetime import datetime

from strategy_engine.base_strategy import BaseStrategy
from feature_engine.indicator_calculator import IndicatorCalculator
from feature_engine.models import FeatureConfig
from broker.trading_client import TradingClient
from broker.interfaces import IOrderExecutionService, OrderRequest, OrderSide, OrderType
from common.models import CandleData, SignalEvent

logger = logging.getLogger(__name__)

class LiveTradingEngine:
    """
    Orchestrates live trading by connecting:
    1. TradingClient (Data Source)
    2. ExecutionService (Order Execution)
    3. IndicatorCalculator (Feature Engineering)
    4. Strategy (Logic)
    """
    
    def __init__(
        self,
        strategy: BaseStrategy,
        broker: TradingClient,
        execution_service: IOrderExecutionService,
        symbol: str,
        timeframe: str = "1m",
        feature_config: Optional[FeatureConfig] = None,
        buffer_size: int = 500
    ):
        self.strategy = strategy
        self.broker = broker
        self.execution_service = execution_service
        self.symbol = symbol
        self.timeframe = timeframe
        self.buffer_size = buffer_size
        
        # Initialize Calculator
        self.feature_config = feature_config or FeatureConfig(indicators=[])
        self.calculator = IndicatorCalculator(self.feature_config)
        
        # Candle Buffer
        self.candles: Deque[CandleData] = deque(maxlen=buffer_size)
        
        # State
        self.is_running = False
        
    def start(self):
        """Start the live trading engine"""
        if self.is_running:
            logger.warning("Live engine already running")
            return
            
        logger.info(f"Starting live trading engine for {self.symbol} ({self.timeframe})")
        self.is_running = True
        
        # Ensure connection
        if not self.broker.market_stream.is_connected:
            self.broker.connect()
            
        # Subscribe to candles
        success = self.broker.market_stream.subscription_manager.subscribe_candles(
            symbol=self.symbol,
            interval=self.timeframe,
            callback=self._on_candle_update
        )
        
        if not success:
            logger.error(f"Failed to subscribe to candles for {self.symbol}")
            self.is_running = False
            
    def stop(self):
        """Stop the live trading engine"""
        if not self.is_running:
            return
            
        logger.info("Stopping live trading engine")
        self.is_running = False
        # Unsubscribe logic would go here
        
    def _on_candle_update(self, candle_data: Any):
        """
        Handle incoming candle update.
        Detects candle closure to trigger strategy.
        """
        try:
            candle = self._parse_candle(candle_data)
            if not candle:
                return

            if not self.candles:
                self.candles.append(candle)
                return
                
            last_candle = self.candles[-1]
            
            if candle.timestamp > last_candle.timestamp:
                # New candle started! The previous one is closed.
                self._on_candle_closed(last_candle)
                self.candles.append(candle)
                
            elif candle.timestamp == last_candle.timestamp:
                # Update current candle
                self.candles[-1] = candle
                
        except Exception as e:
            logger.error(f"Error processing candle update: {e}", exc_info=True)

    def _on_candle_closed(self, candle: CandleData):
        """Called when a candle is fully formed and closed"""
        logger.debug(f"Candle closed: {candle.timestamp}")
        
        # 1. Calculate Indicators
        # Pass the full buffer (history + just closed candle)
        features_dict = self.calculator.calculate_indicators(list(self.candles))
        
        # Extract latest features (for the closed candle)
        current_features = {}
        for name, values in features_dict.items():
            if values:
                current_features[name] = values[-1]
                
        # 2. Run Strategy
        signal = self.strategy.on_candle(candle, features=current_features)
        
        # 3. Execute Signal
        if signal:
            self._execute_signal(signal)

    def _execute_signal(self, signal: SignalEvent):
        """Execute the signal via execution service"""
        logger.info(f"Executing signal: {signal.signal_type} for {signal.symbol}")
        
        # Determine Order Type
        # Basic mapping for Deriv Options
        order_type = None
        if "bullish" in signal.signal_type.lower() or "call" in signal.signal_type.lower():
            order_type = OrderType.CALL
        elif "bearish" in signal.signal_type.lower() or "put" in signal.signal_type.lower():
            order_type = OrderType.PUT
            
        if not order_type:
            logger.warning(f"Unknown signal type for execution: {signal.signal_type}")
            return

        # Get stake from config if possible, else default
        stake = 10.0
        if hasattr(self.broker, 'config'):
             stake = self.broker.config.get('trading', {}).get('default_stake', 10.0)

        # Create Order Request
        # TODO: Duration should ideally come from Strategy/Signal
        order = OrderRequest(
            symbol=signal.symbol,
            order_type=order_type,
            side=OrderSide.BUY, # Always BUY for options (opening position)
            quantity=stake,
            duration=5, 
            duration_unit='t'
        )
        
        try:
            result = self.execution_service.execute_order(order)
            logger.info(f"Execution result: {result}")
        except Exception as e:
            logger.error(f"Failed to execute order: {e}")

    def _parse_candle(self, data: Any) -> Optional[CandleData]:
        """Helper to parse incoming data to CandleData"""
        if isinstance(data, CandleData):
            return data
        # If data is a dict, try to convert
        if isinstance(data, dict):
            try:
                return CandleData(
                    timestamp=datetime.fromtimestamp(data.get('epoch', 0)),
                    open=float(data.get('open', 0)),
                    high=float(data.get('high', 0)),
                    low=float(data.get('low', 0)),
                    close=float(data.get('close', 0)),
                    volume=float(data.get('volume', 0))
                )
            except Exception:
                pass
        return None
