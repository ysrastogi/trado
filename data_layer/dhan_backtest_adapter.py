import logging
import os
import pandas as pd
from typing import List, Dict
from datetime import datetime, timedelta
from common.models import CandleData
from data_layer.dhan_data_provider import DhanDataProvider
from data_layer.market_stream.models import TickData

logger = logging.getLogger(__name__)

class DhanBacktestAdapter:
    """
    Adapts DhanDataProvider to the interface expected by PlaybackEngine.
    Handles Symbol -> SecurityID mapping for Backtesting.
    """
    
    # Mapping for NSE Indices (Segment: INDICES / IDX)
    # IDs derived from Dhan Scrip Master or Documentation
    INDEX_MAP = {
        "NIFTY": "13",
        "BANKNIFTY": "25",
        "FINNIFTY": "27",
        "INDIA VIX": "21",
        "NIFTY 100": "17",
        "NIFTY 500": "19"
    }

    STOCK_MAP = {
        "NATIONALUM": "6364",
        "HINDZINC": "1424",
        "ASHOKLEY": "212",
        "VEDL": "3045",
        "TATASTEEL": "3499",
        "JINDALSTEL": "1727",
        "HINDALCO": "1363",
        "SAIL": "2963",
        "NMDC": "15377"
    }

    def __init__(self, data_provider: DhanDataProvider):
        self.dhan = data_provider
        self.dynamic_map = {}
        self._load_symbol_map()
        
    def _load_symbol_map(self):
        """Loads NSE Equity symbols from the master CSV config."""
        try:
            # Construct path to config/api-scrip-master-detailed.csv
            # Assuming this file is in data_layer/..., going up to root
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            csv_path = os.path.join(base_dir, "config", "api-scrip-master-detailed.csv")
            
            if os.path.exists(csv_path):
                logger.info(f"Loading symbol map from {csv_path}...")
                # Read only necessary columns to save memory
                # Columns verified from file: EXCH_ID, SEGMENT, SECURITY_ID, UNDERLYING_SYMBOL, SERIES
                # We switch to UNDERLYING_SYMBOL as it contains the ticker (e.g. "RELIANCE") 
                # whereas SYMBOL_NAME contains "RELIANCE INDUSTRIES LTD"
                df = pd.read_csv(csv_path, usecols=["EXCH_ID", "SERIES", "SECURITY_ID", "UNDERLYING_SYMBOL"], low_memory=False)
                
                # Check available columns
                cols = df.columns.tolist()
                
                # Standard Dhan Open API Scrip Master columns
                # We need EXCH_ID == 'NSE' and SERIES == 'EQ' 
                # Mapping Symbol (UNDERLYING_SYMBOL) -> Security ID (SECURITY_ID)
                
                if 'EXCH_ID' in cols and 'SERIES' in cols and 'UNDERLYING_SYMBOL' in cols and 'SECURITY_ID' in cols:
                    mask = (df['EXCH_ID'] == 'NSE') & (df['SERIES'] == 'EQ')
                    filtered = df[mask].copy() # Copy to avoid SettingWithCopyWarning
                    
                    # Clean up
                    filtered['UNDERLYING_SYMBOL'] = filtered['UNDERLYING_SYMBOL'].astype(str).str.strip()
                    filtered['SECURITY_ID'] = filtered['SECURITY_ID'].astype(str).str.strip()
                    
                    # Create dict: Ticker -> SecurityID
                    self.dynamic_map = pd.Series(filtered.SECURITY_ID.values, index=filtered.UNDERLYING_SYMBOL).to_dict()
                    logger.info(f"Loaded {len(self.dynamic_map)} NSE Equity symbols.")
                    print(f"DEBUG: Loaded {len(self.dynamic_map)} symbols (Example: RELIANCE -> {self.dynamic_map.get('RELIANCE')})")
                else:
                    logger.warning(f"CSV columns mismatch. Available: {cols}")
                    print(f"DEBUG: CSV columns mismatch: {cols}")
            else:
                logger.warning(f"Scrip master CSV not found at {csv_path}")
                print(f"DEBUG: CSV not found at {csv_path}")
        except Exception as e:
            logger.error(f"Failed to load symbol map: {e}")
            print(f"DEBUG: Failed to load symbol map: {e}")
        
    def candle_to_ticks(self, candle: CandleData) -> List[TickData]:
        """
        Convert a candle to a sequence of tick data points
        Generates 4 ticks: open, high, low, close with small time offsets
        """
        base_ts = candle.timestamp.timestamp()
        
        # Create 4 ticks per candle
        ticks = [
            TickData(symbol=candle.symbol, price=candle.open, volume=0, timestamp=base_ts),
            TickData(symbol=candle.symbol, price=candle.high, volume=0, timestamp=base_ts + 0.1),
            TickData(symbol=candle.symbol, price=candle.low, volume=0, timestamp=base_ts + 0.2),
            TickData(symbol=candle.symbol, price=candle.close, volume=candle.volume, timestamp=base_ts + 0.3)
        ]
        return ticks

    def get_ticker(self, symbol: str):
        """Mock ticker object for compatibility if needed by engine"""
        # Return a simple object or None as BacktestEngine might rely on it for symbol info
        return type('obj', (object,), {'info': {'symbol': symbol}})

    def get_candles(self, symbol: str, start: datetime, end: datetime, interval: str) -> List[CandleData]:
        """
        Interface method required by PlaybackEngine
        """
        symbol_upper = symbol.upper()
        
        # Determine segment and instrument based on symbol type
        if symbol_upper in self.dynamic_map:
            security_id = str(self.dynamic_map[symbol_upper])
            segment = "NSE_EQ"
            instrument_type = "EQUITY"
        elif symbol_upper in self.STOCK_MAP:
            security_id = self.STOCK_MAP[symbol_upper]
            segment = "NSE_EQ"
            instrument_type = "EQUITY"
        elif symbol_upper in self.INDEX_MAP:
            security_id = self.INDEX_MAP[symbol_upper]
            segment = "IDX_I"
            instrument_type = "INDEX"
        else:
            logger.error(f"Unknown Symbol for Backtesting: {symbol}")
            return []

        # Convert interval "5m" -> "5"
        dhan_interval = interval.lower().replace('m', '')
        
        # Convert dates to string format yyyy-MM-dd
        from_date = start.strftime("%Y-%m-%d")
        to_date = end.strftime("%Y-%m-%d")

        try:
            candles = self.dhan.fetch_intraday_data(
                security_id=security_id,
                exchange_segment=segment, 
                instrument_type=instrument_type,
                from_date=from_date,
                to_date=to_date,
                interval=dhan_interval
            )
            
            # Critical Fix: Override symbol in candle objects to match the requested ticker
            # Dhan API returns candles stamped with SecurityID (e.g. "212") but the rest of the 
            # system expects the Ticker Symbol (e.g. "ASHOKLEY").
            # This mismatch causes ExecutionSimulator market_state lookups to fail.
            for candle in candles:
                candle.symbol = symbol_upper
                
            return candles
        except Exception as e:
            logger.error(f"Failed to fetch backtest data for {symbol}: {e}")
            return []

    def candle_to_ticks(self, candle: CandleData) -> List[TickData]:
        """
        Convert a candle to a sequence of tick data points
        Generates 4 ticks: open, high, low, close.
        Uses small second offsets to order them O->H->L->C within the candle timestamp.
        """
        epoch = int(candle.timestamp.timestamp())
        
        ticks = [
            # Open tick
            TickData(
                symbol=candle.symbol,
                quote=candle.open,
                epoch=epoch,
                timestamp=candle.timestamp
            ),
            # High tick
            TickData(
                symbol=candle.symbol,
                quote=candle.high,
                epoch=epoch + 1,
                timestamp=candle.timestamp + timedelta(seconds=1)
            ),
            # Low tick
            TickData(
                symbol=candle.symbol,
                quote=candle.low,
                epoch=epoch + 2,
                timestamp=candle.timestamp + timedelta(seconds=2)
            ),
            # Close tick
            TickData(
                symbol=candle.symbol,
                quote=candle.close,
                epoch=epoch + 3,
                timestamp=candle.timestamp + timedelta(seconds=3)
            )
        ]
        return ticks
