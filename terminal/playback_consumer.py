import logging
from typing import List, Optional, Dict
from common.models import CandleData, SignalEvent
from backtester.engine import PlaybackEngine

logger = logging.getLogger(__name__)

class PlaybackChartConsumer:
    """
    Consumer that bridges PlaybackEngine events to the LiveChart interface.
    Instead of reading from Redis, it receives candles directly from the playback engine.
    """
    
    def __init__(self, playback_engine: PlaybackEngine, symbol: str):
        self.playback_engine = playback_engine
        self.symbol = symbol
        self.candles: List[CandleData] = []
        self.signals: List[SignalEvent] = []
        
        # Register callback
        self.playback_engine.register_candle_callback(self._on_candle)
        # Assuming register_signal_callback exists in PlaybackEngine
        if hasattr(self.playback_engine, 'register_signal_callback'):
             self.playback_engine.register_signal_callback(self._on_signal)
        
    def _on_candle(self, candle: CandleData, symbol: str):
        """Callback for new candles from playback engine"""
        if symbol == self.symbol:
            self.candles.append(candle)
            # Keep a reasonable buffer, though LiveChart only asks for window_size
            # We keep more just in case, but prevent infinite growth
            if len(self.candles) > 2000:
                self.candles.pop(0)
    
    def _on_signal(self, signal: SignalEvent):
        """Callback for new signals"""
        if signal.symbol == self.symbol:
            self.signals.append(signal)
            if len(self.signals) > 500:
                self.signals.pop(0)
                
    def get_candles(self) -> List[CandleData]:
        """Return the current list of candles"""
        return list(self.candles)
    
    def get_signals(self) -> List[SignalEvent]:
        """Return the current list of signals"""
        return list(self.signals)
        
    def start(self):
        """
        Start the consumer. 
        For playback, the engine is usually started separately or we could trigger it here.
        We'll assume the runner script handles the engine thread.
        """
        pass
        
    def stop(self):
        """Stop the consumer"""
        self.playback_engine.stop()
