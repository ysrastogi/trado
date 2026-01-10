import logging
import json
from typing import Dict, List, Callable, Optional, Any

from data_layer.market_stream.interfaces import ISubscriptionManager
from data_layer.market_stream.dhan.symbol_mapper import SymbolMapper

logger = logging.getLogger(__name__)

class DhanSubscriptionManager(ISubscriptionManager):
    def __init__(self, send_message_func: Callable[[Any], None], symbol_mapper: Optional[SymbolMapper] = None):
        self.logger = logger.getChild("DhanSubscriptionManager")
        self.send_message = send_message_func
        self.symbol_mapper = symbol_mapper
        self.subscriptions: Dict[str, Dict] = {}
        self.callbacks: Dict[str, Callable] = {} # Map symbol -> callback

    def subscribe_ticks(self, symbol: str, callback: Optional[Callable] = None) -> bool:
        # Try to resolve symbol using mapper first
        segment = None
        security_id = None
        
        if self.symbol_mapper:
            mapping = self.symbol_mapper.get_security_id(symbol)
            if mapping:
                segment, security_id = mapping
        
        # Fallback to parsing "SEGMENT:ID" if not found in mapper
        if not segment or not security_id:
            try:
                segment, security_id = symbol.split(':')
            except ValueError:
                self.logger.error(f"Invalid symbol format for Dhan: {symbol}. Expected 'SEGMENT:SECURITY_ID' or valid mapped symbol")
                return False

        request = {
            "RequestCode": 15, 
            "InstrumentCount": 1,
            "InstrumentList": [
                {
                    "ExchangeSegment": segment,
                    "SecurityId": security_id
                }
            ]
        }
        
        if callback:
            self.callbacks[symbol] = callback
            
        self.subscriptions[symbol] = request
        self.send_message(request)
        self.logger.info(f"Subscribed to {symbol} ({segment}:{security_id})")
        return True

    def unsubscribe_ticks(self, symbol: str) -> bool:
        if symbol in self.callbacks:
            del self.callbacks[symbol]
        if symbol in self.subscriptions:
            del self.subscriptions[symbol]
        return True

    def subscribe_candles(self, symbol: str, interval: str = "1m", callback: Optional[Callable] = None) -> bool:
        self.logger.warning("Dhan WebSocket does not support historical candles via WS. Use REST API.")
        return False

    def subscribe_ohlc(self, symbol: str, interval: str = "1m", callback: Optional[Callable] = None) -> bool:
        self.logger.warning("Dhan WebSocket does not support OHLC via WS. Use REST API.")
        return False

    def unsubscribe_ohlc(self, symbol: str, interval: str = "1m") -> bool:
        return False

    def get_active_subscriptions(self) -> List[str]:
        return list(self.subscriptions.keys())
