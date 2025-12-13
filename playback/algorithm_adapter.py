"""
Algorithm adapter for connecting existing algorithms to playback engine
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from src.playback.models import SignalEvent, CandleData
from src.playback.engine import PlaybackEngine
from src.data_layer.market_stream.models import TickData

logger = logging.getLogger(__name__)


class PlaybackAlgorithmAdapter:
    """
    Adapter that wraps trading algorithms for offline playback mode
    Routes ticks from playback engine to algorithm's process_tick method
    Captures signals emitted by algorithms
    """
    
    def __init__(
        self,
        algorithm,
        playback_engine: PlaybackEngine,
        algorithm_name: Optional[str] = None
    ):
        """
        Initialize algorithm adapter
        
        Args:
            algorithm: Algorithm instance (must have process_tick method)
            playback_engine: PlaybackEngine instance
            algorithm_name: Optional name for the algorithm
        """
        self.algorithm = algorithm
        self.playback_engine = playback_engine
        self.algorithm_name = algorithm_name or algorithm.__class__.__name__
        
        # Track previous signals for change detection
        self._previous_signals: Dict[str, Optional[str]] = {}
        self._previous_confidences: Dict[str, float] = {}
        
        # Signal extraction state
        self._last_candle: Dict[str, Optional[CandleData]] = {}
        
        # Register as tick callback
        self.playback_engine.register_tick_callback(self._on_tick)
        
        # Hook into algorithm logging if possible
        self._setup_signal_capture()
        
        logger.info(f"Adapter created for {self.algorithm_name}")
    
    def _setup_signal_capture(self) -> None:
        """Setup signal capture mechanism"""
        # Try to hook into algorithm's signal emission
        # Many algorithms log signals, we'll intercept those
        
        # Store original logger
        if hasattr(self.algorithm, 'logger'):
            original_logger = self.algorithm.logger
            
            # Create wrapper logger that captures signals
            class SignalCapturingLogger:
                def __init__(self, original, adapter):
                    self._original = original
                    self._adapter = adapter
                
                def info(self, msg, *args, **kwargs):
                    # Try to parse signal from log message
                    self._adapter._parse_log_for_signal(msg)
                    return self._original.info(msg, *args, **kwargs)
                
                def __getattr__(self, name):
                    return getattr(self._original, name)
            
            # Replace logger
            self.algorithm.logger = SignalCapturingLogger(original_logger, self)
    
    def _on_tick(self, tick: TickData, symbol: str) -> None:
        """
        Handle tick from playback engine
        
        Args:
            tick: TickData object
            symbol: Symbol name
        """
        try:
            # Update last candle info (extract from tick)
            if symbol not in self._last_candle or self._last_candle[symbol] is None:
                self._last_candle[symbol] = CandleData(
                    timestamp=tick.timestamp,
                    symbol=symbol,
                    open=tick.quote,
                    high=tick.quote,
                    low=tick.quote,
                    close=tick.quote
                )
            else:
                # Update candle
                candle = self._last_candle[symbol]
                candle.high = max(candle.high, tick.quote)
                candle.low = min(candle.low, tick.quote)
                candle.close = tick.quote
            
            # Call algorithm's process_tick
            message_id = f"playback_{symbol}_{tick.timestamp.timestamp()}"
            result = self.algorithm.process_tick(tick, message_id)
            
            # Check if algorithm emitted a signal
            self._check_for_signal(symbol, tick.timestamp)
            
        except Exception as e:
            logger.error(f"Error processing tick in adapter: {e}", exc_info=True)
    
    def _check_for_signal(self, symbol: str, timestamp: datetime) -> None:
        """
        Check if algorithm has new signal and emit SignalEvent
        
        Args:
            symbol: Symbol name
            timestamp: Current timestamp
        """
        # Try to get current signal from algorithm
        current_signal = None
        confidence = 0.0
        indicators = {}
        reason = ""
        trigger_conditions = []
        
        # Different algorithms have different ways to expose signals
        # Try multiple approaches
        
        # Approach 1: Check if algorithm stores previous_signals
        if hasattr(self.algorithm, 'previous_signals'):
            current_signal = self.algorithm.previous_signals.get(symbol)
        
        # Approach 2: Check if algorithm has get_signal method
        if hasattr(self.algorithm, 'get_signal'):
            try:
                signal_info = self.algorithm.get_signal(symbol)
                if signal_info:
                    current_signal = signal_info.get('signal')
                    confidence = signal_info.get('confidence', 0.0)
            except:
                pass
        
        # Approach 3: Try to analyze algorithm state directly
        if current_signal is None:
            current_signal = self._extract_signal_from_state(symbol)
        
        # Get confidence
        if hasattr(self.algorithm, 'previous_confidences'):
            confidence = self.algorithm.previous_confidences.get(symbol, 0.0)
        
        # Get indicators
        indicators = self._extract_indicators(symbol)
        
        # Build reason string
        reason = self._build_reason(symbol, current_signal, indicators)
        
        # Build trigger conditions
        trigger_conditions = self._extract_trigger_conditions(symbol, indicators)
        
        # Check if signal changed
        previous_signal = self._previous_signals.get(symbol)
        signal_changed = previous_signal != current_signal
        
        # Only emit if we have a valid signal and it's different or first time
        if current_signal and (signal_changed or previous_signal is None):
            # Get candle data
            candle_dict = None
            if symbol in self._last_candle and self._last_candle[symbol]:
                candle = self._last_candle[symbol]
                candle_dict = {
                    'open': candle.open,
                    'high': candle.high,
                    'low': candle.low,
                    'close': candle.close,
                    'volume': candle.volume
                }
            
            # Create signal event
            signal_event = SignalEvent(
                timestamp=timestamp,
                symbol=symbol,
                algorithm=self.algorithm_name,
                signal_type=current_signal,
                confidence=confidence,
                reason=reason,
                trigger_conditions=trigger_conditions,
                indicators=indicators,
                candle=candle_dict,
                previous_signal=previous_signal,
                signal_change=signal_changed
            )
            
            # Emit to playback engine
            self.playback_engine.emit_signal(signal_event)
            
            # Update tracking
            self._previous_signals[symbol] = current_signal
            self._previous_confidences[symbol] = confidence
    
    def _extract_signal_from_state(self, symbol: str) -> Optional[str]:
        """Try to extract current signal from algorithm state"""
        # Check common attribute names
        for attr in ['current_signal', 'signal', 'last_signal']:
            if hasattr(self.algorithm, attr):
                signal_dict = getattr(self.algorithm, attr)
                if isinstance(signal_dict, dict):
                    return signal_dict.get(symbol)
        
        return None
    
    def _extract_indicators(self, symbol: str) -> Dict[str, float]:
        """Extract indicator values from algorithm state"""
        indicators = {}
        
        # Common indicator attributes to extract
        indicator_attrs = [
            'sma_value',
            'fast_ema',
            'slow_ema',
            'macd_line',
            'signal_ema',
            'price_data',
            'sma_slope_pct',
            'price_to_sma_ratio'
        ]
        
        for attr in indicator_attrs:
            if hasattr(self.algorithm, attr):
                value = getattr(self.algorithm, attr)
                
                if isinstance(value, dict):
                    # Extract for this symbol
                    val = value.get(symbol)
                    
                    if val is not None:
                        # Handle different types
                        if isinstance(val, (int, float)):
                            indicators[attr] = float(val)
                        elif hasattr(val, '__iter__') and len(val) > 0:
                            # Get last value from deque/list
                            try:
                                indicators[attr] = float(list(val)[-1])
                            except:
                                pass
        
        return indicators
    
    def _build_reason(
        self,
        symbol: str,
        signal: Optional[str],
        indicators: Dict[str, float]
    ) -> str:
        """Build human-readable reason for signal"""
        if not signal:
            return ""
        
        # Build reason based on signal type and indicators
        reason_parts = []
        
        if signal == "bullish_trend":
            reason_parts.append("Bullish trend detected:")
            
            if 'price_to_sma_ratio' in indicators:
                ratio = indicators['price_to_sma_ratio']
                if ratio > 1.02:
                    reason_parts.append(f"Price {(ratio-1)*100:.1f}% above SMA")
            
            if 'sma_slope_pct' in indicators:
                slope = indicators['sma_slope_pct']
                if slope > 0:
                    reason_parts.append(f"SMA trending up ({slope*100:.2f}%)")
        
        elif signal == "bearish_trend":
            reason_parts.append("Bearish trend detected:")
            
            if 'price_to_sma_ratio' in indicators:
                ratio = indicators['price_to_sma_ratio']
                if ratio < 0.98:
                    reason_parts.append(f"Price {(1-ratio)*100:.1f}% below SMA")
            
            if 'sma_slope_pct' in indicators:
                slope = indicators['sma_slope_pct']
                if slope < 0:
                    reason_parts.append(f"SMA trending down ({slope*100:.2f}%)")
        
        elif signal == "sideways":
            reason_parts.append("Sideways movement: Price near SMA")
        
        return " ".join(reason_parts) if reason_parts else signal
    
    def _extract_trigger_conditions(
        self,
        symbol: str,
        indicators: Dict[str, float]
    ) -> List[str]:
        """Extract specific trigger conditions"""
        conditions = []
        
        if 'price_to_sma_ratio' in indicators:
            ratio = indicators['price_to_sma_ratio']
            conditions.append(f"price_to_sma_ratio: {ratio:.4f}")
        
        if 'sma_slope_pct' in indicators:
            slope = indicators['sma_slope_pct']
            conditions.append(f"sma_slope_pct: {slope:.4f}")
        
        if 'sma_value' in indicators:
            sma = indicators['sma_value']
            conditions.append(f"sma_value: {sma:.4f}")
        
        return conditions
    
    def _parse_log_for_signal(self, log_message: str) -> None:
        """Parse algorithm log message for signal information"""
        # This is a backup method if direct state access fails
        # Parse log messages like:
        # "[SMA] BTCUSD - SIGNAL: bullish_trend | Conf: 0.78 ..."
        
        # For now, we rely on direct state access
        # Could implement log parsing if needed
        pass
    
    def get_algorithm_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get metrics from the wrapped algorithm"""
        if hasattr(self.algorithm, 'get_metrics'):
            try:
                return self.algorithm.get_metrics(symbol)
            except Exception as e:
                logger.warning(f"Failed to get metrics: {e}")
        
        return {}
