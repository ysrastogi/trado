import logging
import yaml
from typing import Dict, List, Optional, Callable, Any
from dotenv import load_dotenv

from config.settings import settings
from data_layer.market_stream.callback_manager import CallbackManager
from data_layer.market_stream.models import MarketConfig
from data_layer.market_stream.interfaces import IMarketDataSource
from data_layer.market_stream.deriv.deriv_connection_manager import DerivConnectionManager
from data_layer.market_stream.deriv.deriv_subscription_manager import DerivSubscriptionManager
from data_layer.market_stream.deriv.deriv_message_handler import DerivMessageHandler

load_dotenv()
logger = logging.getLogger(__name__)


class DerivMarketStream(IMarketDataSource):
    
    def __init__(self, config_path: str = "config/tradding_config.yaml", auth_token: str = None, enable_redis_stream: bool = True):

        self.logger = logger.getChild("DerivMarketStream")
        self.config = self._load_config(config_path)
        self.auth_token = auth_token or settings.deriv_auth_token
        self.enable_redis_stream = enable_redis_stream
        self.logger.info(f"Using Deriv auth token: {self.auth_token[:5]}...")
        self.logger.info(f"Redis Stream publishing: {'enabled' if enable_redis_stream else 'disabled'}")
        
        self.ws_url = f"{self.config['websocket']['url']}?app_id={self.config['websocket']['app_id']}"
        
        # CallbackManager is still needed by MessageHandler internally, even if we don't expose it
        self.callback_manager = CallbackManager()
    
        self.market_config = self._create_market_config()
    
        self._initialize_components()
    
    def _load_config(self, config_path: str) -> Dict:
        
        try:
            with open(config_path, 'r') as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            self.logger.error(f"Configuration file not found: {config_path}")
            raise
        except yaml.YAMLError as e:
            self.logger.error(f"Error parsing configuration file: {e}")
            raise
    
    def _create_market_config(self) -> MarketConfig:
    
        websocket_config = self.config['websocket']
        market_data_config = self.config.get('market_data', {})
        
        symbols = market_data_config.get('symbols', [])
        if not symbols:
            logger.warning("No symbols specified in configuration; using default symbols")
        
        return MarketConfig(
            websocket_url=websocket_config['url'],
            app_id=websocket_config['app_id'],
            reconnect_attempts=websocket_config['reconnect_attempts'],
            reconnect_delay=websocket_config['reconnect_delay'],
            heartbeat_interval=websocket_config['heartbeat_interval'],
            symbols=symbols,
            stream_types=market_data_config.get('stream_types', ['tick']),
            candle_intervals=market_data_config.get('candle_intervals', ['1m'])
        )
    
    def _initialize_components(self) -> None:
       
        self.connection_manager = DerivConnectionManager(
            ws_url=self.ws_url,
            auth_token=self.auth_token,
            reconnect_attempts=self.market_config.reconnect_attempts,
            reconnect_delay=self.market_config.reconnect_delay,
            heartbeat_interval=self.market_config.heartbeat_interval,
            message_handler=self._handle_message
        )
        
        self.subscription_manager = DerivSubscriptionManager(
            send_message_func=self.connection_manager.send_message,
            get_request_id_func=self.connection_manager.get_next_request_id
        )
        
        self.message_handler = DerivMessageHandler(
            auth_token=self.auth_token,
            callback_manager=self.callback_manager,
            subscription_manager=self.subscription_manager,
            connection_manager=self.connection_manager,
            subscribe_configured_symbols_func=self._subscribe_to_configured_symbols,
            enable_redis_stream=self.enable_redis_stream
        )
    
    def _handle_message(self, data: Any) -> None:
        self.message_handler.handle_message(data)
    
    def _subscribe_to_configured_symbols(self) -> None:
        try:
            self.logger.info("Subscribing to configured symbols")
            self.subscribe_symbols(self.market_config.symbols)
        except Exception as e:
            self.logger.error(f"Error subscribing to symbols: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
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

    @property
    def is_connected(self) -> bool:
        return self.connection_manager.is_ready()

