import logging
from data_layer.market_stream.factory import MarketStreamFactory

logger = logging.getLogger(__name__)

class MarketStream:
    """
    Facade class that delegates to the appropriate MarketStream implementation
    based on configuration.
    """
    def __new__(cls, config_path: str = "config/tradding_config.yaml", auth_token: str = None, enable_redis_stream: bool = True):
        logger.info(f"Initializing MarketStream with config: {config_path}")
        return MarketStreamFactory.create_market_stream(config_path, auth_token, enable_redis_stream)

