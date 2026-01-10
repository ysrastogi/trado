import logging
import threading
import time
import yaml
from typing import Dict, List, Optional, Callable, Any, Union
from datetime import datetime

from data_layer.market_stream.interfaces import IMarketStream, IConnectionManager, ISubscriptionManager, IMessageHandler
from data_layer.market_stream.callback_manager import CallbackManager
from data_layer.market_stream.redis_stream_consumer import RedisStreamConsumer
from data_layer.market_stream.redis_stream_config import RedisStreamConfig, redis_stream_config
from data_layer.market_stream.models import TickData, OHLCData
from common.models import CandleData

logger = logging.getLogger(__name__)

class RedisTickConsumer(RedisStreamConsumer):
    def __init__(self, consumer_name: str, symbols: List[str], callback: Callable[[TickData], None], config: RedisStreamConfig):
        super().__init__(consumer_name, symbols, config)
        self.callback = callback

    def process_tick(self, tick: TickData, message_id: str) -> bool:
        try:
            self.callback(tick)
            return True
        except Exception as e:
            self.logger.error(f"Error processing tick: {e}")
            return False

class RedisOHLCConsumer(RedisStreamConsumer):
    def __init__(self, consumer_name: str, symbols: List[str], callback: Callable[[OHLCData], None], config: RedisStreamConfig):
        # We need to trick the base class to use OHLC stream keys.
        # We can do this by subclassing Config or just overriding _initialize_consumer_groups and _consume_messages logic?
        # Or better, we pass a config that has get_stream_key pointing to OHLC.
        
        # Create a proxy config that redirects get_stream_key to get_ohlc_stream_key
        class OHLCConfigProxy:
            def __init__(self, original_config):
                self._config = original_config
            
            def __getattr__(self, name):
                return getattr(self._config, name)
            
            @property
            def stream_prefix(self):
                return self._config.ohlc_stream_prefix

            def get_stream_key(self, symbol: str) -> str:
                return self._config.get_ohlc_stream_key(symbol)
                
            def get_consumer_group(self, algo_name: str) -> str:
                return self._config.get_consumer_group(algo_name)

        ohlc_config = OHLCConfigProxy(config)
        super().__init__(consumer_name, symbols, ohlc_config)
        self.callback = callback

    def _deserialize_tick(self, data: Dict[bytes, bytes]) -> OHLCData:
        # Override to deserialize OHLC
        decoded = {k.decode('utf-8'): v.decode('utf-8') for k, v in data.items()}
        
        from datetime import datetime
        timestamp_str = decoded.get('timestamp', '')
        try:
            timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now()
        except ValueError:
            timestamp = datetime.now()
            
        return OHLCData(
            symbol=decoded.get('symbol', ''),
            open=float(decoded.get('open', 0)),
            high=float(decoded.get('high', 0)),
            low=float(decoded.get('low', 0)),
            close=float(decoded.get('close', 0)),
            epoch=int(decoded.get('epoch', 0)),
            timestamp=timestamp
        )

    def process_tick(self, ohlc: OHLCData, message_id: str) -> bool:
        try:
            self.callback(ohlc)
            return True
        except Exception as e:
            self.logger.error(f"Error processing OHLC: {e}")
            return False

class RedisConnectionManager(IConnectionManager):
    def __init__(self, market_stream):
        self.market_stream = market_stream
        self._is_connected = False

    def connect(self) -> bool:
        self.market_stream.start_consumers()
        self._is_connected = True
        return True

    def disconnect(self) -> None:
        self.market_stream.stop_consumers()
        self._is_connected = False

    def is_ready(self) -> bool:
        return self._is_connected

    def send_message(self, message: Any) -> None:
        # Redis stream is read-only for us (consumer). 
        # If TradingClient tries to send orders, it might use this?
        # No, TradingClient uses TradingService/ExecutionService for orders usually?
        # But TradingClient.connect() calls market_stream.connect().
        # If TradingClient sends 'authorize', we can ignore it or mock success.
        # For paper trading, we don't need real auth.
        pass

    def get_next_request_id(self) -> int:
        return int(time.time() * 1000)
    
    def set_authenticated(self, authenticated: bool):
        pass

class RedisSubscriptionManager(ISubscriptionManager):
    def __init__(self, market_stream):
        self.market_stream = market_stream
        self.active_subscriptions = set()

    def subscribe_ticks(self, symbol: str, callback: Optional[Callable] = None) -> bool:
        if callback:
            self.market_stream.callback_manager.add_callback(f"tick_{symbol}", callback)
        self.market_stream.add_symbol(symbol)
        self.active_subscriptions.add(f"tick_{symbol}")
        return True

    def unsubscribe_ticks(self, symbol: str) -> bool:
        return True

    def subscribe_candles(self, symbol: str, interval: str = "1m", callback: Optional[Callable] = None) -> bool:
        if callback:
            # Register for OHLC updates
            # Note: Redis stream might not differentiate intervals easily unless we have separate streams.
            # For now, we assume the OHLC stream matches the requested interval or we filter?
            # The current implementation of publish_ohlc uses one stream per symbol.
            # We assume it's the base interval (e.g. 1m).
            self.market_stream.callback_manager.add_callback(f"ohlc_{symbol}", callback)
        self.market_stream.add_symbol(symbol)
        self.active_subscriptions.add(f"ohlc_{symbol}")
        return True

    def subscribe_ohlc(self, symbol: str, interval: str = "1m", callback: Optional[Callable] = None) -> bool:
        return self.subscribe_candles(symbol, interval, callback)

    def unsubscribe_ohlc(self, symbol: str, interval: str = "1m") -> bool:
        return True

    def get_active_subscriptions(self) -> List[str]:
        return list(self.active_subscriptions)
    
    def register_callback(self, key: str, callback: Callable):
        self.market_stream.callback_manager.add_callback(key, callback)
        
    def get_callback(self, key: str) -> Optional[Callable]:
        # CallbackManager doesn't expose get_callback easily, but we can access .callbacks
        callbacks = self.market_stream.callback_manager.callbacks.get(key, [])
        return callbacks[0] if callbacks else None

class RedisMarketStream(IMarketStream):
    def __init__(self, config_path: str = "config/tradding_config.yaml", symbols: List[str] = None):
        self.logger = logger.getChild("RedisMarketStream")
        
        # Load general config for TradingClient compatibility
        try:
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            self.logger.error(f"Failed to load config from {config_path}: {e}")
            self.config = {}

        self.redis_config = redis_stream_config 
        self.symbols = symbols or []
        
        self.callback_manager = CallbackManager()
        self.connection_manager = RedisConnectionManager(self)
        self.subscription_manager = RedisSubscriptionManager(self)
        
        self.tick_consumer: Optional[RedisTickConsumer] = None
        self.ohlc_consumer: Optional[RedisOHLCConsumer] = None
        
        self.latest_ticks: Dict[str, TickData] = {}
        self.latest_candles: Dict[str, OHLCData] = {}
        
    def connect(self) -> bool:
        return self.connection_manager.connect()

    def disconnect(self) -> None:
        self.connection_manager.disconnect()

    @property
    def is_connected(self) -> bool:
        return self.connection_manager.is_ready()

    def is_ready(self) -> bool:
        return self.connection_manager.is_ready()

    def send_message(self, message: Any) -> None:
        self.connection_manager.send_message(message)

    def get_next_request_id(self) -> int:
        return self.connection_manager.get_next_request_id()

    def subscribe_ticks(self, symbol: str, callback: Optional[Callable] = None) -> bool:
        return self.subscription_manager.subscribe_ticks(symbol, callback)

    def unsubscribe_ticks(self, symbol: str) -> bool:
        return self.subscription_manager.unsubscribe_ticks(symbol)

    def subscribe_candles(self, symbol: str, interval: str = "1m", callback: Optional[Callable] = None) -> bool:
        return self.subscription_manager.subscribe_candles(symbol, interval, callback)

    def subscribe_ohlc(self, symbol: str, interval: str = "1m", callback: Optional[Callable] = None) -> bool:
        return self.subscription_manager.subscribe_ohlc(symbol, interval, callback)

    def unsubscribe_ohlc(self, symbol: str, interval: str = "1m") -> bool:
        return self.subscription_manager.unsubscribe_ohlc(symbol, interval)

    def add_callback(self, event_type: str, callback: Callable) -> None:
        self.callback_manager.add_callback(event_type, callback)

    def remove_callback(self, event_type: str, callback: Callable) -> bool:
        return self.callback_manager.remove_callback(event_type, callback)

    def get_active_subscriptions(self) -> List[str]:
        return self.subscription_manager.get_active_subscriptions()

    def start_consumers(self):
        if not self.symbols:
            self.logger.warning("No symbols to consume")
            return

        # Start Tick Consumer
        self.tick_consumer = RedisTickConsumer(
            consumer_name=f"paper_tick_{int(time.time())}",
            symbols=self.symbols,
            callback=self._on_tick,
            config=self.redis_config
        )
        self.tick_consumer.start()

        # Start OHLC Consumer
        self.ohlc_consumer = RedisOHLCConsumer(
            consumer_name=f"paper_ohlc_{int(time.time())}",
            symbols=self.symbols,
            callback=self._on_ohlc,
            config=self.redis_config
        )
        self.ohlc_consumer.start()
        
        self.logger.info(f"Redis consumers started for {self.symbols}")

    def stop_consumers(self):
        if self.tick_consumer:
            self.tick_consumer.stop()
        if self.ohlc_consumer:
            self.ohlc_consumer.stop()

    def add_symbol(self, symbol: str):
        if symbol not in self.symbols:
            self.symbols.append(symbol)
            # Restart consumers to include new symbol?
            # RedisStreamConsumer takes symbols in __init__.
            # We might need to restart or dynamic add.
            # For now, assume symbols are known at start or we restart.
            if self.is_connected:
                self.logger.info(f"Restarting consumers to add {symbol}")
                self.stop_consumers()
                self.start_consumers()

    def _on_tick(self, tick: TickData):
        self.latest_ticks[tick.symbol] = tick
        # Trigger callbacks
        self.callback_manager.trigger_callbacks(f"tick_{tick.symbol}", tick.to_dict() if hasattr(tick, 'to_dict') else tick)
        # Also trigger generic 'tick'
        self.callback_manager.trigger_callbacks("tick", tick)

    def _on_ohlc(self, ohlc: OHLCData):
        self.latest_candles[ohlc.symbol] = ohlc
        
        # Convert to CandleData for LiveTradingEngine
        candle = CandleData(
            timestamp=ohlc.timestamp,
            symbol=ohlc.symbol,
            open=ohlc.open,
            high=ohlc.high,
            low=ohlc.low,
            close=ohlc.close,
            volume=0 # Redis stream might not have volume
        )
        
        # Trigger callbacks
        self.callback_manager.trigger_callbacks(f"ohlc_{ohlc.symbol}", candle)
        self.callback_manager.trigger_callbacks("candles", {'candles': [ohlc]}) # Keep this for compatibility if needed

    def get_latest_tick(self, symbol: str) -> Optional[Dict]:
        tick = self.latest_ticks.get(symbol)
        if tick:
            # Return dict as expected by PaperTradingService
            return {
                'quote': tick.quote,
                'epoch': tick.epoch,
                'symbol': tick.symbol
            }
        return None
    
    @property
    def auth_token(self):
        return "DUMMY_TOKEN"

