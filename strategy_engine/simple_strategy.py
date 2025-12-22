from typing import Dict, Any, Optional
from strategy_engine.base_strategy import BaseStrategy
from common.models import SignalEvent, CandleData
from datetime import datetime

class SimpleStrategy(BaseStrategy):
    """A simple strategy that buys on every 3rd tick/candle for testing"""
    
    def setup_indicators(self):
        self.count = 0
        
    def on_tick(self, tick_data: Dict[str, Any]) -> Optional[SignalEvent]:
        self.count += 1
        if self.count % 3 == 0:
            return SignalEvent(
                timestamp=tick_data['timestamp'],
                symbol=tick_data['symbol'],
                algorithm="SimpleStrategy",
                signal_type="BUY",
                confidence=1.0,
                reason="Test Buy",
                indicators={'price': tick_data['price']}
            )
        return None

    def on_bar(self, bar_data: Dict[str, Any]) -> Optional[SignalEvent]:
        return None
        
    def on_candle(self, candle: CandleData, features: Optional[Dict[str, float]] = None) -> Optional[SignalEvent]:
        return super().on_candle(candle, features)
