import logging
import sys
import os
from datetime import datetime, timedelta

# Add current directory to path
sys.path.append(os.getcwd())

from backtester.engine import PlaybackEngine
from backtester.execution_simulator import ExecutionSimulator
from backtester.backtest_engine import BacktestEngine
from backtester.reporter import BacktestReporter
from data_layer.historical_data_provider import YFinanceDataProvider
from strategy_engine.momentum_strategy import MomentumStrategy

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MomentumBacktest")

def run_backtest():
    # 1. Configuration
    symbol = "AAPL"
    start_date = datetime.now() - timedelta(days=30) # Last 30 days
    end_date = datetime.now() - timedelta(days=1)
    timeframe = "5m"
    
    strategy_config = {
        "risk_per_trade": 0.01,
        "features": {
            "indicators": [
                {"name": "donchian", "params": {"length": 20}},
                {"name": "roc", "params": {"length": 12}},
                {"name": "sma", "params": {"length": 20, "input_column": "volume"}},
                {"name": "atr", "params": {"length": 14}},
                {"name": "ema", "params": {"length": 20}},
                {"name": "sma", "params": {"length": 1}}, # Price proxy for HTF
            ],
            "timeframes": ["15m"]
        }
    }

    # 2. Data Provider
    logger.info(f"Fetching data for {symbol}...")
    data_provider = YFinanceDataProvider(cache_dir="data_cache")
    
    # 3. Playback Engine
    playback = PlaybackEngine(
        data_provider=data_provider,
        symbols=[symbol],
        start_date=start_date,
        end_date=end_date,
        interval=timeframe,
        initial_speed=0 # Max speed
    )
    
    # Load data explicitly to ensure we have it before starting
    playback.load_data()
    
    if not playback._candles.get(symbol):
        logger.error("No data found. Exiting.")
        return

    # 4. Execution Simulator
    execution = ExecutionSimulator()
    
    # 5. Backtest Engine
    engine = BacktestEngine(
        playback_engine=playback,
        execution_simulator=execution,
        strategy_class=MomentumStrategy,
        strategy_config=strategy_config,
        initial_capital=100000.0
    )
    
    # 6. Run Backtest
    logger.info("Starting Backtest...")
    engine.start()
    
    # Wait for completion
    import time
    while playback.get_state().value == "playing":
        time.sleep(0.1)
        
    logger.info("Backtest Completed.")
    
    # 7. Generate Report
    stats = execution.get_execution_statistics()
    reporter = BacktestReporter()
    report_path = reporter.generate_report(
        stats=stats,
        strategy_name="MomentumStrategy"
    )
    logger.info(f"Report generated at: {report_path}")
    
    # Print Summary
    print("\n" + "="*50)
    print("BACKTEST RESULTS")
    print("="*50)
    print(f"Total Orders: {stats.get('total_orders', 0)}")
    print(f"Filled Orders: {stats.get('filled_orders', 0)}")
    print(f"Total Cost: ${stats.get('total_cost', 0):.2f}")
    print("="*50 + "\n")

if __name__ == "__main__":
    run_backtest()
