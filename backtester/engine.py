"""
Core Playback Engine for feeding historical data to algorithms
"""

import logging
import threading
import time
from datetime import datetime
from typing import Optional, List, Callable, Dict, Any
from collections import deque

from common.models import (
    PlaybackState,
    CandleData,
    PlaybackMetrics,
    SignalEvent
)
from data_layer.historical_data_provider import YFinanceDataProvider
from data_layer.market_stream.models import TickData

logger = logging.getLogger(__name__)


class PlaybackEngine:
    """
    Core playback engine that feeds candle-by-candle data to algorithms
    Supports pause, step, speed control, and seeking
    """
    
    def __init__(
        self,
        data_provider: YFinanceDataProvider,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        interval: str = '1h',
        initial_speed: float = 1.0
    ):
        """
        Initialize playback engine
        
        Args:
            data_provider: YFinanceDataProvider instance
            symbols: List of symbols to play back
            start_date: Start datetime
            end_date: End datetime
            interval: Data interval (1m, 5m, 1h, etc.)
            initial_speed: Initial playback speed multiplier
        """
        self.data_provider = data_provider
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.interval = interval
        
        # State management
        self._state = PlaybackState.STOPPED
        self._speed = initial_speed
        self._lock = threading.RLock()
        
        # Data storage
        self._candles: Dict[str, List[CandleData]] = {}
        self._current_index: Dict[str, int] = {}
        
        # Metrics
        self.metrics = PlaybackMetrics()
        
        # Event callbacks
        self._tick_callbacks: List[Callable[[TickData, str], None]] = []
        self._signal_callbacks: List[Callable[[SignalEvent], None]] = []
        self._state_callbacks: List[Callable[[PlaybackState], None]] = []
        
        # Playback thread
        self._playback_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        logger.info(
            f"PlaybackEngine initialized: {symbols} from {start_date.date()} "
            f"to {end_date.date()} ({interval})"
        )
    
    def load_data(self) -> None:
        """Load historical data for all symbols"""
        logger.info("Loading historical data...")
        
        for symbol in self.symbols:
            candles = self.data_provider.get_candles(
                symbol=symbol,
                start=self.start_date,
                end=self.end_date,
                interval=self.interval
            )
            
            if not candles:
                logger.warning(f"No data loaded for {symbol}")
                continue
            
            self._candles[symbol] = candles
            self._current_index[symbol] = 0
            
            logger.info(f"Loaded {len(candles)} candles for {symbol}")
        
        # Update metrics
        self.metrics.total_candles = sum(len(c) for c in self._candles.values())
        self.metrics.start_time = self.start_date
        self.metrics.end_time = self.end_date
        
        logger.info(f"Total candles loaded: {self.metrics.total_candles}")
    
    def register_tick_callback(
        self,
        callback: Callable[[TickData, str], None]
    ) -> None:
        """
        Register a callback to receive tick data
        
        Args:
            callback: Function(tick, symbol) to call for each tick
        """
        self._tick_callbacks.append(callback)
    
    def register_signal_callback(
        self,
        callback: Callable[[SignalEvent], None]
    ) -> None:
        """
        Register a callback to receive signal events
        
        Args:
            callback: Function(signal) to call for each signal
        """
        self._signal_callbacks.append(callback)
    
    def register_state_callback(
        self,
        callback: Callable[[PlaybackState], None]
    ) -> None:
        """
        Register a callback for state changes
        
        Args:
            callback: Function(state) to call on state change
        """
        self._state_callbacks.append(callback)
    
    def _emit_tick(self, tick: TickData, symbol: str) -> None:
        """Emit tick to all registered callbacks"""
        for callback in self._tick_callbacks:
            try:
                callback(tick, symbol)
            except Exception as e:
                logger.error(f"Error in tick callback: {e}")
    
    def emit_signal(self, signal: SignalEvent) -> None:
        """
        Emit a signal event (called by algorithm adapters)
        
        Args:
            signal: SignalEvent to emit
        """
        self.metrics.signals_emitted += 1
        
        for callback in self._signal_callbacks:
            try:
                callback(signal)
            except Exception as e:
                logger.error(f"Error in signal callback: {e}")
    
    def _set_state(self, new_state: PlaybackState) -> None:
        """Change playback state and notify callbacks"""
        with self._lock:
            old_state = self._state
            self._state = new_state
            
            if old_state != new_state:
                logger.info(f"State: {old_state.value} -> {new_state.value}")
                
                for callback in self._state_callbacks:
                    try:
                        callback(new_state)
                    except Exception as e:
                        logger.error(f"Error in state callback: {e}")
    
    def get_state(self) -> PlaybackState:
        """Get current playback state"""
        with self._lock:
            return self._state
    
    def set_speed(self, speed: float) -> None:
        """
        Set playback speed
        
        Args:
            speed: Speed multiplier (1.0 = real-time, 0 = max speed)
        """
        with self._lock:
            if speed < 0:
                raise ValueError("Speed must be >= 0")
            self._speed = speed
            self.metrics.playback_speed = speed
            logger.info(f"Playback speed set to {speed}x")
    
    def get_speed(self) -> float:
        """Get current playback speed"""
        with self._lock:
            return self._speed
    
    def play(self) -> None:
        """Start or resume playback"""
        with self._lock:
            if self._state == PlaybackState.PLAYING:
                logger.warning("Already playing")
                return
            
            if self._state == PlaybackState.STOPPED:
                # Start from beginning
                for symbol in self.symbols:
                    self._current_index[symbol] = 0
                self.metrics.candles_processed = 0
            
            self._set_state(PlaybackState.PLAYING)
            
            # Start playback thread
            self._stop_event.clear()
            self._playback_thread = threading.Thread(
                target=self._playback_loop,
                daemon=True
            )
            self._playback_thread.start()
    
    def pause(self) -> None:
        """Pause playback"""
        with self._lock:
            if self._state != PlaybackState.PLAYING:
                logger.warning("Not playing")
                return
            
            self._set_state(PlaybackState.PAUSED)
            self._stop_event.set()
            
            if self._playback_thread:
                self._playback_thread.join(timeout=5)
    
    def stop(self) -> None:
        """Stop playback and reset to beginning"""
        with self._lock:
            self._set_state(PlaybackState.STOPPED)
            self._stop_event.set()
            
            if self._playback_thread:
                self._playback_thread.join(timeout=5)
            
            # Reset position
            for symbol in self.symbols:
                self._current_index[symbol] = 0
            self.metrics.candles_processed = 0
    
    def step_forward(self, steps: int = 1) -> int:
        """
        Step forward by N candles
        
        Args:
            steps: Number of candles to step
        
        Returns:
            Number of candles actually stepped
        """
        with self._lock:
            if self._state == PlaybackState.PLAYING:
                logger.warning("Cannot step while playing")
                return 0
            
            self._set_state(PlaybackState.STEPPING)
            
            stepped = 0
            for _ in range(steps):
                if not self._process_next_candles():
                    break
                stepped += 1
            
            self._set_state(PlaybackState.PAUSED)
            return stepped
    
    def step_backward(self, steps: int = 1) -> int:
        """
        Step backward by N candles
        
        Args:
            steps: Number of candles to step back
        
        Returns:
            Number of candles actually stepped back
        """
        with self._lock:
            if self._state == PlaybackState.PLAYING:
                logger.warning("Cannot step while playing")
                return 0
            
            stepped = 0
            for symbol in self.symbols:
                current = self._current_index[symbol]
                new_index = max(0, current - steps)
                actual_steps = current - new_index
                self._current_index[symbol] = new_index
                stepped = max(stepped, actual_steps)
            
            self.metrics.candles_processed = max(
                0,
                self.metrics.candles_processed - stepped
            )
            
            logger.info(f"Stepped back {stepped} candles")
            return stepped
    
    def seek_to_timestamp(self, timestamp: datetime) -> bool:
        """
        Seek to a specific timestamp
        
        Args:
            timestamp: Target timestamp
        
        Returns:
            True if successful
        """
        with self._lock:
            if self._state == PlaybackState.PLAYING:
                self.pause()
            
            self._set_state(PlaybackState.SEEKING)
            
            success = True
            for symbol in self.symbols:
                candles = self._candles.get(symbol, [])
                
                # Find closest candle
                target_index = 0
                for i, candle in enumerate(candles):
                    if candle.timestamp >= timestamp:
                        target_index = i
                        break
                    target_index = i
                
                self._current_index[symbol] = target_index
            
            # Recalculate processed count
            self.metrics.candles_processed = sum(
                self._current_index.get(s, 0) for s in self.symbols
            )
            
            self._set_state(PlaybackState.PAUSED)
            logger.info(f"Seeked to {timestamp}")
            
            return success
    
    def get_current_position(self) -> Dict[str, Any]:
        """Get current playback position"""
        with self._lock:
            positions = {}
            
            for symbol in self.symbols:
                idx = self._current_index.get(symbol, 0)
                candles = self._candles.get(symbol, [])
                
                if candles and idx < len(candles):
                    current_candle = candles[idx]
                    positions[symbol] = {
                        'index': idx,
                        'timestamp': current_candle.timestamp.isoformat(),
                        'price': current_candle.close
                    }
                else:
                    positions[symbol] = {
                        'index': idx,
                        'timestamp': None,
                        'price': None
                    }
            
            return positions
    
    def get_progress(self) -> float:
        """Get playback progress (0-100%)"""
        return self.metrics.progress_pct
    
    def _process_next_candles(self) -> bool:
        """
        Process next candle for all symbols
        
        Returns:
            True if more candles available
        """
        has_more = False
        
        for symbol in self.symbols:
            candles = self._candles.get(symbol, [])
            idx = self._current_index.get(symbol, 0)
            
            if idx >= len(candles):
                continue
            
            has_more = True
            candle = candles[idx]
            
            # Convert candle to ticks
            ticks = self.data_provider.candle_to_ticks(candle)
            
            # Emit ticks
            for tick in ticks:
                self._emit_tick(tick, symbol)
            
            # Advance index
            self._current_index[symbol] += 1
        
        self.metrics.candles_processed += 1
        
        return has_more
    
    def _playback_loop(self) -> None:
        """Main playback loop (runs in thread)"""
        logger.info("Playback loop started")
        
        try:
            while not self._stop_event.is_set():
                # Check state
                if self.get_state() != PlaybackState.PLAYING:
                    break
                
                # Process next candles
                has_more = self._process_next_candles()
                
                if not has_more:
                    logger.info("Playback complete")
                    self._set_state(PlaybackState.STOPPED)
                    break
                
                # Speed control (if speed > 0, add delay)
                if self._speed > 0:
                    # Calculate delay based on speed
                    # 1.0x = real-time, higher = slower, lower = faster
                    delay = 1.0 / self._speed if self._speed > 0 else 0
                    time.sleep(delay)
        
        except Exception as e:
            logger.error(f"Error in playback loop: {e}", exc_info=True)
            self._set_state(PlaybackState.STOPPED)
        
        finally:
            logger.info("Playback loop ended")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get playback metrics"""
        return self.metrics.to_dict()
