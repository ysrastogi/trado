import logging
import time
import sys
from dotenv import load_dotenv

# Load env before imports
load_dotenv()

from strategy_engine.momentum_strategy import MomentumStrategy
from strategy_engine.live_engine import LiveTradingEngine
from broker.trading_client import TradingClient
from feature_engine.models import FeatureConfig, IndicatorConfig
from config.settings import settings

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MomentumRunner")

def main():
    symbol = "R_100" # Volatility 100 Index (Deriv standard)
    
    # 1. Configure Features
    feature_config = FeatureConfig(
        indicators=[
            IndicatorConfig(name="donchian", params={"length": 20}),
            IndicatorConfig(name="roc", params={"length": 12}),
            IndicatorConfig(name="sma", params={"length": 20, "input_column": "volume"}),
            IndicatorConfig(name="atr", params={"length": 14}),
            IndicatorConfig(name="ema", params={"length": 20}),
            IndicatorConfig(name="sma", params={"length": 1}),
        ],
        timeframes=["15m"]
    )
    
    # 2. Initialize Components
    try:
        broker = TradingClient()
        strategy = MomentumStrategy()
        
        engine = LiveTradingEngine(
            strategy=strategy,
            broker=broker,
            symbol=symbol,
            timeframe="5m",
            feature_config=feature_config,
            buffer_size=100
        )
        
        # 3. Start
        logger.info("Starting Momentum Strategy Runner...")
        engine.start()
        
        # Keep alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Stopping...")
        engine.stop()
    except Exception as e:
        logger.error(f"Fatal Error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
