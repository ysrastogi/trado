import logging
import time
import yaml
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from broker.factory import ExecutionServiceFactory
from broker.trading_client import TradingClient
# from data_layer.market_stream.stream import MarketStream
from data_layer.market_stream.redis_market_stream import RedisMarketStream
from strategy_engine.momentum_strategy import MomentumStrategy
from strategy_engine.live_engine import LiveTradingEngine
from feature_engine.models import FeatureConfig, IndicatorConfig

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("paper_trading.log")
    ]
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting Paper Trading Session for Momentum Strategy")

    # 1. Load Configuration
    try:
        with open("config/tradding_config.yaml", 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("Config file not found!")
        return

    # Force Paper Mode in Config for this session
    config['trading']['execution_mode'] = 'paper'
    
    # Symbol to trade
    symbol = "cryBTCUSD"
    timeframe = "5m"

    # 2. Initialize Market Stream
    # Ensure symbol is in config
    if symbol not in config['market_data']['symbols']:
        config['market_data']['symbols'].append(symbol)
        
    # market_stream = MarketStream(config_path="config/tradding_config.yaml")
    logger.info(f"Initializing RedisMarketStream for {symbol}")
    market_stream = RedisMarketStream(config_path="config/tradding_config.yaml", symbols=[symbol])
    
    # 3. Initialize Execution Service (Paper)
    execution_service = ExecutionServiceFactory.create_service(config, market_stream)
    execution_service.start()
    broker_client = TradingClient(market_stream)

    # 5. Configure Strategy
    strategy_config = {
        'risk_per_trade': 0.01,
        'roc_period': 12,
        'donchian_period': 20,
        'atr_period': 14,
        'asset_type': 'index' # Crypto is like index/commodity for this strategy
    }
    strategy = MomentumStrategy(strategy_config)

    # 6. Configure Features (Indicators)
    # The strategy expects: ROC_12, DonchianHigh_20, DonchianLow_20, ATRr_14, SMA_20_volume
    # And HTF: 15m_SMA_1, 15m_EMA_20
    
    feature_config = FeatureConfig(
        indicators=[
            IndicatorConfig(name="roc", params={"length": 12}),
            IndicatorConfig(name="donchian", params={"length": 20}),
            IndicatorConfig(name="atr", params={"length": 14}),
            # Volume SMA
            IndicatorConfig(name="sma", params={"length": 20, "input_column": "volume"}),
            # HTF Indicators (15m)
            IndicatorConfig(name="ema", params={"length": 20}), 
            IndicatorConfig(name="sma", params={"length": 1}),  # For HTF Close check
        ],
        timeframes=[timeframe, "15m"] # Request 1m and 15m data
    )

    # 7. Initialize Live Trading Engine
    engine = LiveTradingEngine(
        strategy=strategy,
        broker=broker_client,
        execution_service=execution_service,
        symbol=symbol,
        timeframe=timeframe,
        feature_config=feature_config,
        buffer_size=1000
    )

    # 8. Start
    try:
        engine.start()
        
        # Keep main thread alive
        while True:
            time.sleep(1)
            
            # Optional: Print status periodically
            if int(time.time()) % 60 == 0:
                balance = execution_service.get_account_balance()
                positions = execution_service.get_active_positions()
                logger.info(f"STATUS: Balance=${balance:.2f} | Positions={len(positions)}")

    except KeyboardInterrupt:
        logger.info("Stopping...")
    except Exception as e:
        logger.error(f"Runtime error: {e}", exc_info=True)
    finally:
        engine.stop()
        execution_service.stop()
        market_stream.disconnect()

if __name__ == "__main__":
    main()
