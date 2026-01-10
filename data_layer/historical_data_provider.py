"""
Historical data provider using yfinance
"""

import logging
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
import pickle

from common.models import CandleData
from data_layer.market_stream.models import TickData

logger = logging.getLogger(__name__)


class YFinanceDataProvider:
    """
    Fetches historical OHLCV data from Yahoo Finance (via yfinance)
    with caching capabilities
    """
    
    # Mapping of timeframe strings to yfinance interval codes
    INTERVAL_MAP = {
        '1m': '1m',
        '2m': '2m',
        '5m': '5m',
        '15m': '15m',
        '30m': '30m',
        '60m': '60m',
        '1h': '1h',
        '90m': '90m',
        '1d': '1d',
        '5d': '5d',
        '1wk': '1wk',
        '1mo': '1mo',
        '3mo': '3mo'
    }
    
    def __init__(self, cache_dir: Optional[str] = None, enable_cache: bool = True):
        """
        Initialize data provider
        
        Args:
            cache_dir: Directory to store cached data
            enable_cache: Whether to use caching
        """
        self.enable_cache = enable_cache
        
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path.home() / '.lumostrade' / 'playback_cache'
        
        if self.enable_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"YFinanceDataProvider initialized (cache: {self.enable_cache})")
    
    def _get_cache_key(self, symbol: str, start: datetime, end: datetime, 
                       interval: str) -> str:
        """Generate cache key for a data request"""
        start_str = start.strftime('%Y%m%d')
        end_str = end.strftime('%Y%m%d')
        return f"{symbol}_{interval}_{start_str}_{end_str}"
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """Get cache file path"""
        return self.cache_dir / f"{cache_key}.pkl"
    
    def _load_from_cache(self, cache_key: str) -> Optional[pd.DataFrame]:
        """Load data from cache if available"""
        if not self.enable_cache:
            return None
        
        cache_path = self._get_cache_path(cache_key)
        
        if cache_path.exists():
            try:
                with open(cache_path, 'rb') as f:
                    data = pickle.load(f)
                logger.info(f"Loaded data from cache: {cache_key}")
                
                # Validate cache data has required columns
                # If not, invalidate cache and return None to fetch fresh
                if 'timestamp' not in data.columns:
                    logger.warning(f"Cache {cache_key} has old format, invalidating...")
                    cache_path.unlink()  # Delete old cache
                    return None
                    
                return data
            except Exception as e:
                logger.warning(f"Failed to load cache {cache_key}: {e}")
                return None
        
        return None
    
    def _save_to_cache(self, cache_key: str, data: pd.DataFrame) -> None:
        """Save data to cache"""
        if not self.enable_cache:
            return
        
        cache_path = self._get_cache_path(cache_key)
        
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
            logger.info(f"Saved data to cache: {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to save cache {cache_key}: {e}")
    
    def fetch_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = '1h'
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data
        
        Args:
            symbol: Trading symbol (e.g., 'BTC-USD', 'AAPL')
            start: Start datetime
            end: End datetime
            interval: Data interval (1m, 5m, 15m, 1h, 1d, etc.)
        
        Returns:
            DataFrame with OHLCV data
        """
        # Validate interval
        if interval not in self.INTERVAL_MAP:
            raise ValueError(
                f"Invalid interval: {interval}. "
                f"Valid options: {list(self.INTERVAL_MAP.keys())}"
            )
        
        yf_interval = self.INTERVAL_MAP[interval]
        
        # Check cache
        cache_key = self._get_cache_key(symbol, start, end, interval)
        cached_data = self._load_from_cache(cache_key)
        
        if cached_data is not None:
            return cached_data
        
        # Fetch from yfinance
        logger.info(
            f"Fetching {symbol} data from {start.date()} to {end.date()} "
            f"(interval: {interval})"
        )
        
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(
                start=start,
                end=end,
                interval=yf_interval,
                auto_adjust=True,  # Adjust for splits and dividends
                actions=False
            )
            
            if data.empty:
                logger.warning(f"No data returned for {symbol}")
                return pd.DataFrame()
            
            # Reset index to make timestamp a column BEFORE renaming
            data.reset_index(inplace=True)
            
            # Now rename ALL columns to lowercase (including the datetime column)
            data.columns = [col.lower() for col in data.columns]
            
            # The datetime index becomes 'datetime' column after lowercase
            # Rename it to 'timestamp' for consistency
            if 'datetime' in data.columns:
                data.rename(columns={'datetime': 'timestamp'}, inplace=True)
            elif 'date' in data.columns:
                data.rename(columns={'date': 'timestamp'}, inplace=True)
            
            # Ensure we have required columns
            required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            if not all(col in data.columns for col in required_cols):
                logger.error(f"Missing required columns in data for {symbol}. Got: {list(data.columns)}")
                return pd.DataFrame()
            
            # Save to cache
            self._save_to_cache(cache_key, data)
            
            logger.info(f"Fetched {len(data)} candles for {symbol}")
            return data
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            raise
    
    def get_candles(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = '1h'
    ) -> List[CandleData]:
        """
        Get data as list of CandleData objects
        
        Args:
            symbol: Trading symbol
            start: Start datetime
            end: End datetime
            interval: Data interval
        
        Returns:
            List of CandleData objects
        """
        df = self.fetch_data(symbol, start, end, interval)
        
        if df.empty:
            return []
        
        candles = []
        for _, row in df.iterrows():
            candle = CandleData(
                timestamp=row['timestamp'],
                symbol=symbol,
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row['volume']) if 'volume' in row else None
            )
            candles.append(candle)
        
        return candles
    
    def candle_to_ticks(self, candle: CandleData) -> List[TickData]:
        """
        Convert a candle to a sequence of tick data points
        Generates 4 ticks: open, high, low, close
        
        Args:
            candle: CandleData object
        
        Returns:
            List of TickData objects
        """
        epoch = int(candle.timestamp.timestamp())
        
        # Generate 4 ticks per candle (OHLC)
        ticks = [
            # Open tick
            TickData(
                symbol=candle.symbol,
                quote=candle.open,
                epoch=epoch,
                timestamp=candle.timestamp
            ),
            # High tick (offset by 1/4 of interval)
            TickData(
                symbol=candle.symbol,
                quote=candle.high,
                epoch=epoch + 900,  # +15 minutes for 1h candle
                timestamp=candle.timestamp + timedelta(seconds=900)
            ),
            # Low tick (offset by 1/2 of interval)
            TickData(
                symbol=candle.symbol,
                quote=candle.low,
                epoch=epoch + 1800,  # +30 minutes
                timestamp=candle.timestamp + timedelta(seconds=1800)
            ),
            # Close tick (at end of interval)
            TickData(
                symbol=candle.symbol,
                quote=candle.close,
                epoch=epoch + 3600,  # +1 hour
                timestamp=candle.timestamp + timedelta(seconds=3600)
            )
        ]
        
        return ticks
    
    def clear_cache(self, symbol: Optional[str] = None) -> int:
        """
        Clear cached data
        
        Args:
            symbol: If provided, only clear cache for this symbol
        
        Returns:
            Number of cache files deleted
        """
        if not self.enable_cache:
            return 0
        
        deleted = 0
        
        for cache_file in self.cache_dir.glob('*.pkl'):
            if symbol is None or cache_file.name.startswith(f"{symbol}_"):
                cache_file.unlink()
                deleted += 1
        
        logger.info(f"Cleared {deleted} cache files")
        return deleted
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about cached data"""
        if not self.enable_cache:
            return {'enabled': False}
        
        cache_files = list(self.cache_dir.glob('*.pkl'))
        total_size = sum(f.stat().st_size for f in cache_files)
        
        return {
            'enabled': True,
            'cache_dir': str(self.cache_dir),
            'num_files': len(cache_files),
            'total_size_mb': total_size / (1024 * 1024)
        }
