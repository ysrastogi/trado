import logging
import yaml
from datetime import datetime, timedelta
from pathlib import Path

from backtester.backtest_engine import BacktestEngine
from backtester.engine import PlaybackEngine
from backtester.execution_simulator import ExecutionSimulator
from backtester.reporter import BacktestReporter
from data_layer.historical_data_provider import YFinanceDataProvider
from strategy_engine.momentum_strategy import MomentumStrategy

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    # Configuration
    symbols = ['^NSEI']
    start_date = datetime.now() - timedelta(days=7) # Last 7 days for 1m data
    end_date = datetime.now()
    
    # Strategy Config
    strategy_config = {
        'risk_per_trade': 0.01,
        'roc_period': 12,
        'donchian_period': 20,
        'volume_ma_period': 20,
        'atr_period': 14,
        'htf_ema_period': 20,
        'features': {
            'indicators': [
                {'name': 'roc', 'params': {'length': 12}},
                {'name': 'donchian', 'params': {'length': 20}},
                {'name': 'sma', 'params': {'length': 20, 'input_column': 'volume'}},
                {'name': 'atr', 'params': {'length': 14}},
                {'name': 'sma', 'params': {'length': 1}}, # For HTF Close (15m_SMA_1)
                {'name': 'ema', 'params': {'length': 20}} # For HTF EMA (15m_EMA_20)
            ],
            'timeframes': ['15m']
        }
    }
    
    # Initialize Data Provider
    data_provider = YFinanceDataProvider()
    
    # 1. Setup Playback Engine with High-Frequency Data (1m)
    logger.info("Initializing Playback with 1m data...")
    playback = PlaybackEngine(
        data_provider=data_provider,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        interval='5m' # Execution Timeframe
    )
    playback.load_data() # Explicitly load data
    
    # 2. Setup Execution Simulator
    execution = ExecutionSimulator()
    
    # 3. Setup Backtest Engine with Signal Timeframe (5m)
    logger.info("Initializing Backtest Engine with 5m signal aggregation...")
    engine = BacktestEngine(
        playback_engine=playback,
        execution_simulator=execution,
        strategy_class=MomentumStrategy,
        strategy_config=strategy_config,
        signal_timeframe='5m' # Signal Timeframe
    )
    
    # 4. Run Backtest
    engine.start()
    
    # Wait for completion
    import time
    from common.models import PlaybackState
    
    while playback._state == PlaybackState.PLAYING or playback._state == PlaybackState.PAUSED:
        time.sleep(0.001)
        
    # 5. Generate Report
    logger.info("Generating Report...")
    reporter = BacktestReporter()
    
    # Helper to get status value
    def get_status(execution):
        return execution.status.value if hasattr(execution.status, 'value') else execution.status

    stats = {
        'equity_curve': engine.equity_curve,
        'executions': execution.execution_history,
        'total_orders': len(execution.execution_history),
        'filled_orders': len([x for x in execution.execution_history if get_status(x) == 'filled']),
        'fill_rate_pct': 100.0, # Simplified
        'total_cost': sum([x.get_total_cost() for x in execution.execution_history]),
        'avg_slippage_bps': 0.0, # Need to calculate
        'avg_latency_ms': 0.0, # Need to calculate
        'by_symbol': {s: {'count': 0, 'total_volume': 0, 'avg_slippage_bps': 0} for s in symbols} # Simplified
    }
    
    report_path = reporter.generate_report(stats, "MomentumStrategy_MultiFrame")
    logger.info(f"Report generated at: {report_path}")

if __name__ == "__main__":
    main()
