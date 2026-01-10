import logging
import requests
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import pandas as pd

from common.models import CandleData
from config.settings import settings

logger = logging.getLogger(__name__)

class DhanDataProvider:
    """
    Data provider for fetching historical/intraday data from Dhan API
    """
    
    def __init__(self):
        self.base_url = settings.dhan_api_url
        self.access_token = settings.dhan_access_token
        self.client_id = settings.dhan_client_id
        
    def fetch_intraday_data(
        self, 
        security_id: str, 
        exchange_segment: str, 
        instrument_type: str,
        from_date: str,
        to_date: str,
        interval: str = "1"
    ) -> List[CandleData]:
        """
        Fetch intraday OHLC data from Dhan API
        
        Args:
            security_id: Exchange standard identification for scrip
            exchange_segment: NSE_EQ, NSE_FNO, etc.
            instrument_type: INDEX, FUTIDX, EQUITY, etc.
            from_date: yyyy-MM-dd
            to_date: yyyy-MM-dd
            interval: time interval in minutes (1, 5, 15, 25, 60)
            
        Returns:
            List of CandleData objects
        """
        endpoint = f"{self.base_url}/charts/intraday"
        
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'access-token': self.access_token
        }
        
        payload = {
            "securityId": security_id,
            "exchangeSegment": exchange_segment,
            "instrument": instrument_type,
            "interval": interval,
            "fromDate": from_date,
            "toDate": to_date
        }
        
        logger.info(f"Fetching Dhan data for {security_id} ({from_date} to {to_date})")
        
        try:
            response = requests.post(endpoint, json=payload, headers=headers)
            if not response.ok:
                logger.error(f"Dhan API Error: {response.text}")
            response.raise_for_status()
            data = response.json()
            
            return self._parse_response(data, security_id)
            
        except Exception as e:
            logger.error(f"Error fetching data from Dhan: {e}")
            # If request fails, we might want to return empty list or re-raise
            # For now re-raising to make it visible
            raise

    def _parse_response(self, data: Dict[str, Any], symbol: str) -> List[CandleData]:
        """
        Parse Dhan chart response to CandleData objects
        Timestamp is seconds since 1980-01-01 00:00:00
        """
        candles = []
        
        # Dhan returns arrays of values or empty dict if no data
        if not data or 'timestamp' not in data or not data['timestamp']:
            logger.warning(f"No data received from Dhan for {symbol}")
            return []
            
        timestamps = data['timestamp']
        opens = data['open']
        highs = data['high']
        lows = data['low']
        closes = data['close']
        volumes = data['volume']
        
        # Although docs say 1980, empirical testing shows it's standard unix epoch (1970)
        # resulting in correct 2026 dates.
        # base_date = datetime(1980, 1, 1) 
        
        count = len(timestamps)
        for i in range(count):
            try:
                # Handle potential invalid values (sometimes API might return weird placeholders)
                # Validating if timestamp is a valid number
                ts_val = float(timestamps[i])
                
                # Check for the negative infinity placeholder seen in user example
                if ts_val < 0:
                    continue
                    
                # Use fromtimestamp as it seems to be standard unix epoch
                candle_time = datetime.fromtimestamp(ts_val)
                
                candle = CandleData(
                    timestamp=candle_time,
                    symbol=symbol,
                    open=float(opens[i]),
                    high=float(highs[i]),
                    low=float(lows[i]),
                    close=float(closes[i]),
                    volume=float(volumes[i]) if volumes else 0.0
                )
                candles.append(candle)
            except (ValueError, TypeError) as e:
                logger.debug(f"Skipping malformed candle index {i}: {e}")
                continue
            
        logger.info(f"Parsed {len(candles)} candles for {symbol}")
        return candles
