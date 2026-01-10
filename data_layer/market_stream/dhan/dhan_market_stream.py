import logging
import yaml
from typing import Dict, List, Optional, Callable, Any
from dotenv import load_dotenv

from config.settings import settings
from data_layer.market_stream.callback_manager import CallbackManager
from data_layer.market_stream.models import MarketConfig
from data_layer.market_stream.interfaces import IMarketDataSource
from data_layer.market_stream.dhan.dhan_connection_manager import DhanConnectionManager
from data_layer.market_stream.dhan.dhan_subscription_manager import DhanSubscriptionManager
from data_layer.market_stream.dhan.dhan_message_handler import DhanMessageHandler
from data_layer.market_stream.dhan.symbol_mapper import SymbolMapper

load_dotenv()
logger = logging.getLogger(__name__)

class DhanMarketStream(IMarketDataSource):
    def __init__(self, config_path: str = "config/tradding_config.yaml", enable_redis_stream: bool = True):
        self.logger = logger.getChild("DhanMarketStream")
        self.config = self._load_config(config_path)
        
        self.client_id = settings.dhan_client_id
        self.access_token = settings.dhan_access_token
        self.enable_redis_stream = enable_redis_stream
        
        if not self.client_id or not self.access_token:
            self.logger.error("Dhan Client ID or Access Token not found in settings")
            
        self.dhan_config = self.config.get('dhan', {})
        self.ws_url = self.dhan_config.get('url', "wss://api-feed.dhan.co")
        
        # CallbackManager is still needed by MessageHandler internally
        self.callback_manager = CallbackManager()
        self.market_config = self._create_market_config()
        
        # Initialize Symbol Mapper
        self.symbol_mapper = SymbolMapper()
        # Load mapping from CSV if available
        csv_path = "config/api-scrip-master-detailed.csv"
        self.symbol_mapper.load_from_csv(csv_path)
        
        self._initialize_components()

    def _load_config(self, config_path: str) -> Dict:
        try:
            with open(config_path, 'r') as file:
                return yaml.safe_load(file)
        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
            return {}

    def _create_market_config(self) -> MarketConfig:
        websocket_config = self.config.get('websocket', {})
        market_data_config = self.config.get('market_data', {})
        
        return MarketConfig(
            websocket_url=self.ws_url,
            app_id="", # Not used for Dhan
            reconnect_attempts=websocket_config.get('reconnect_attempts', 5),
            reconnect_delay=websocket_config.get('reconnect_delay', 5),
            heartbeat_interval=websocket_config.get('heartbeat_interval', 30),
            symbols=market_data_config.get('symbols', []),
            stream_types=market_data_config.get('stream_types', ['tick']),
            candle_intervals=market_data_config.get('candle_intervals', ['1m'])
        )

    def _initialize_components(self) -> None:
        self.connection_manager = DhanConnectionManager(
            ws_url=self.ws_url,
            client_id=self.client_id,
            access_token=self.access_token,
            reconnect_attempts=self.market_config.reconnect_attempts,
            reconnect_delay=self.market_config.reconnect_delay,
            message_handler=self._handle_message
        )
        
        self.subscription_manager = DhanSubscriptionManager(
            send_message_func=self.connection_manager.send_message,
            symbol_mapper=self.symbol_mapper
        )
        
        self.message_handler = DhanMessageHandler(
            callback_manager=self.callback_manager,
            subscription_manager=self.subscription_manager,
            enable_redis_stream=self.enable_redis_stream,
            symbol_mapper=self.symbol_mapper
        )

    def _handle_message(self, data: Any) -> None:
        self.message_handler.handle_message(data)

    def connect(self) -> bool:
        return self.connection_manager.connect()

    def disconnect(self) -> None:
        self.connection_manager.disconnect()

    def subscribe_symbols(self, symbols: List[str]) -> bool:
        self.logger.info(f"Subscribing to {len(symbols)} symbols: {symbols}")
        success = True
        for symbol in symbols:
            # Subscribe to ticks
            if not self.subscription_manager.subscribe_ticks(symbol):
                success = False
            # Subscribe to OHLC (1m default)
            if not self.subscription_manager.subscribe_ohlc(symbol, "1m"):
                success = False
        return success

    def unsubscribe_symbols(self, symbols: List[str]) -> bool:
        """Unsubscribe from symbols."""
        self.logger.info(f"Unsubscribing from {len(symbols)} symbols: {symbols}")
        success = True
        for symbol in symbols:
            if not self.subscription_manager.unsubscribe_ticks(symbol):
                success = False
            if not self.subscription_manager.unsubscribe_ohlc(symbol, "1m"):
                success = False
        return success

    def add_callback(self, event_type: str, callback: Callable) -> None:
        """Add callback for stream events."""
        self.callback_manager.add_callback(event_type, callback)

    def remove_callback(self, event_type: str, callback: Callable) -> bool:
        """Remove callback for stream events."""
        return self.callback_manager.remove_callback(event_type, callback)

    def get_active_subscriptions(self) -> List[str]:
        """Get list of active subscriptions."""
        return self.subscription_manager.get_active_subscriptions()

    def is_ready(self) -> bool:
        """Check if stream is ready."""
        return self.connection_manager.is_ready()

    @property
    def is_connected(self) -> bool:
        return self.connection_manager.is_ready()

