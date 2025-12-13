"""
Redis Stream Consumer for Live Chart
Consumes tick data from Redis and aggregates it into candles for the live chart
"""

import logging
import threading
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta

from data_layer.market_stream.redis_stream_consumer import RedisStreamConsumer
from data_layer.market_stream.models import TickData
from common.models import CandleData

logger = logging.getLogger(__name__)

class ChartDataConsumer(RedisStreamConsumer):
    """
    Consumes ticks from Redis and maintains live candles for charting
    """
    
    def __init__(self, symbol: str, interval_seconds: int = 60, window_size: int = 60):
        """
        Initialize chart data consumer
        
        Args:
            symbol: Symbol to consume
            interval_seconds: Candle interval in seconds
            window_size: Number of historical candles to fetch
        """
        super().__init__(
            consumer_name=f"chart_consumer_{symbol}_{int(datetime.now().timestamp())}",
            symbols=[symbol],
            from_beginning=False # We will manually set the ID
        )
        self.symbol = symbol
        self.interval_seconds = interval_seconds
        self.current_candle: Optional[CandleData] = None
        self.candles: List[CandleData] = []
        self.data_lock = threading.Lock()
        
        # Reset consumer group to fetch historical data
        try:
            # Calculate timestamp for n candles ago (in milliseconds)
            # Add a small buffer (e.g. 2 extra candles) to ensure we have enough data
            lookback_seconds = (window_size + 2) * interval_seconds
            start_ts = int((datetime.now().timestamp() - lookback_seconds) * 1000)
            
            stream_key = self.config.get_stream_key(symbol)
            # Check if stream exists first
            if self._redis.exists(stream_key):
                self._redis.xgroup_setid(stream_key, self.consumer_group, str(start_ts))
                logger.info(f"Reset consumer group to {start_ts} (approx {window_size} candles history)")
            else:
                logger.warning(f"Stream {stream_key} does not exist yet. Waiting for data...")
                
        except Exception as e:
            logger.warning(f"Failed to reset consumer group position: {e}")
        
    def process_tick(self, tick: TickData, message_id: str) -> bool:
        """
        Process incoming tick and update current candle
        """
        try:
            with self.data_lock:
                self._update_candle(tick)
            return True
        except Exception as e:
            logger.error(f"Error processing tick for chart: {e}")
            return False
            
    def _update_candle(self, tick: TickData):
        """Update current candle with new tick data"""
        tick_time = tick.timestamp
        
        # Calculate candle start time (floor to nearest interval)
        timestamp_ts = tick_time.timestamp()
        candle_start_ts = (timestamp_ts // self.interval_seconds) * self.interval_seconds
        candle_start_time = datetime.fromtimestamp(candle_start_ts)
        
        if self.current_candle and self.current_candle.timestamp == candle_start_time:
            # Update existing candle
            self.current_candle.high = max(self.current_candle.high, tick.quote)
            self.current_candle.low = min(self.current_candle.low, tick.quote)
            self.current_candle.close = tick.quote
            self.current_candle.volume = (self.current_candle.volume or 0) + 1 # Count ticks as volume
        else:
            # Close previous candle if exists
            if self.current_candle:
                self.candles.append(self.current_candle)
                # Keep buffer size manageable
                if len(self.candles) > 1000:
                    self.candles.pop(0)
            
            # Start new candle
            self.current_candle = CandleData(
                timestamp=candle_start_time,
                symbol=self.symbol,
                open=tick.quote,
                high=tick.quote,
                low=tick.quote,
                close=tick.quote,
                volume=1
            )
            
    def get_candles(self) -> List[CandleData]:
        """Get all completed candles plus current partial candle"""
        with self.data_lock:
            result = list(self.candles)
            if self.current_candle:
                result.append(self.current_candle)
            return result
