import yaml
from typing import Optional
from data_layer.market_stream.interfaces import IMarketStream, IMarketDataSource
from data_layer.market_stream.deriv.deriv_market_stream import DerivMarketStream
from data_layer.market_stream.dhan.dhan_market_stream import DhanMarketStream
from data_layer.market_stream.redis_market_stream import RedisMarketStream

class MarketStreamFactory:
    @staticmethod
    def create_data_source(config_path: str = "config/tradding_config.yaml", auth_token: str = None, enable_redis_stream: bool = True) -> IMarketDataSource:
        """
        Creates a data source (Producer) that connects to the exchange and publishes to Redis.
        Used by the Stream Worker.
        """
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
                provider = config.get('websocket', {}).get('provider', 'deriv')
                
                if provider == 'dhan':
                    return DhanMarketStream(config_path, enable_redis_stream)
                else:
                    return DerivMarketStream(config_path, auth_token, enable_redis_stream)
        except Exception as e:
            # Default to Deriv if config fails or provider not specified
            return DerivMarketStream(config_path, auth_token, enable_redis_stream)

    @staticmethod
    def create_market_stream(config_path: str = "config/tradding_config.yaml", auth_token: str = None, enable_redis_stream: bool = True) -> IMarketStream:
        """
        Creates a market stream (Consumer) that reads from Redis.
        Used by the Application (TradingClient, StrategyEngine).
        
        Note: auth_token and enable_redis_stream are kept for signature compatibility but ignored
        as the consumer doesn't need them (it just reads from Redis).
        """
        return RedisMarketStream(config_path=config_path)
