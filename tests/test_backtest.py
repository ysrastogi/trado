import logging
from datetime import datetime, timedelta
import sys
import os
import random

# Add current directory to path so imports work
sys.path.append(os.getcwd())

from backtester.engine import PlaybackEngine
from backtester.execution_simulator import ExecutionSimulator
from backtester.backtest_engine import BacktestEngine
# from data_layer.historical_data_provider import YFinanceDataProvider
from strategy_engine.simple_strategy import SimpleStrategy
from backtester.reporter import BacktestReporter
from common.models import CandleData

# Setup logging
logging.basicConfig(level=logging.INFO)

class MockDataProvider:
    def __init__(self):
        pass
        
    def get_candles(self, symbol, start, end, interval):
        candles = []
        current = start
        price = 100.0
        while current <= end:
            price = price * (1 + random.uniform(-0.01, 0.01))
            candles.append(CandleData(
                timestamp=current,
                symbol=symbol,
                open=price,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=1000
            ))
            current += timedelta(hours=1)
        return candles
        
    def candle_to_ticks(self, candle):
        from data_layer.market_stream.models import TickData
        # Simple conversion: 1 tick per candle for testing
        return [TickData(
            symbol=candle.symbol,
            quote=candle.close,
            epoch=int(candle.timestamp.timestamp()),
            timestamp=candle.timestamp,
            ask=candle.close * 1.0001,
            bid=candle.close * 0.9999
        )]

def run_test():
    # 1. Data Provider
    data_provider = MockDataProvider()
    
    # 2. Playback Engine
    end_date = datetime.now() - timedelta(days=1)
    start_date = end_date - timedelta(days=5)
    symbols = ['AAPL']
    
    playback = PlaybackEngine(
        data_provider=data_provider,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        interval='1h',
        initial_speed=0 # Max speed
    )
    
    # Load data
    playback.load_data()
    
    # 3. Execution Simulator
    execution = ExecutionSimulator()
    
    # 4. Backtest Engine
    engine = BacktestEngine(
        playback_engine=playback,
        execution_simulator=execution,
        strategy_class=SimpleStrategy,
        strategy_config={},
        initial_capital=10000.0
    )
    
    # 5. Run
    engine.start()
    
    # Wait for completion (PlaybackEngine runs in a thread)
    import time
    while playback.get_state().value == "playing":
        time.sleep(0.1)
        
    # 6. Results
    stats = execution.get_execution_statistics()
    print("\nExecution Statistics:")
    print(stats)
    
    # 7. Report
    reporter = BacktestReporter()
    report_path = reporter.generate_report(stats, "SimpleStrategy")
    print(f"\nReport generated at: {report_path}")

if __name__ == "__main__":
    run_test()
