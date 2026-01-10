import logging
import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Add current directory to path
sys.path.append(os.getcwd())

from backtester.engine import PlaybackEngine
from backtester.execution_simulator import ExecutionSimulator
from backtester.backtest_engine import BacktestEngine
from backtester.reporter import BacktestReporter
from data_layer.dhan_data_provider import DhanDataProvider
from data_layer.dhan_backtest_adapter import DhanBacktestAdapter
from strategy_engine.momentum_strategy import MomentumStrategy

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DhanBacktest")

def run_multi_index_backtest():
    # 1. Setup
    indexes = ["EMIL", "GLAXO", "MPSLTD", "EXCELINDUS", "DREAMFOLKS", "LALPATHLAB","RKFORGE"] 
    start_date = datetime.now() - timedelta(days=90) 
    end_date = datetime.now()
    timeframe = "5m"
    
    dhan_provider = DhanDataProvider()
    adapter = DhanBacktestAdapter(dhan_provider)

    results_summary = []

    print(f"\n{'='*60}")
    print(f"Starting Multi-Index Backtest on: {indexes}")
    print(f"Period: {start_date.date()} to {end_date.date()}")
    print(f"{'='*60}\n")

    for symbol in indexes:
        logger.info(f"--- Running Backtest for {symbol} ---")
        
        # 2. Strategy Config
        strategy_config = {
            "risk_per_trade": 0.01,
            "asset_type": "index",
            "features": {
                "indicators": [
                    {"name": "donchian", "params": {"length": 20}},
                    {"name": "roc", "params": {"length": 12}},
                    {"name": "sma", "params": {"length": 10, "input_column": "close"}}, 
                    {"name": "atr", "params": {"length": 14}},
                    {"name": "ema", "params": {"length": 20}}, 
                    {"name": "sma", "params": {"length": 1, "input_column": "close"}} 
                ],
                "timeframes": ["15m"] # HTF
            }
        }

        # 3. Playback Engine
        playback = PlaybackEngine(
            data_provider=adapter, 
            symbols=[symbol],
            start_date=start_date,
            end_date=end_date,
            interval=timeframe,
            initial_speed=0
        )
        
        # Load Data
        logger.info(f"Loading data for {symbol}...")
        try:
            playback.load_data()
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            continue
        
        if not playback._candles.get(symbol):
            logger.warning(f"Skipping {symbol} - No data found.")
            continue
            
        logger.info(f"Loaded {len(playback._candles[symbol])} candles for {symbol}")

        # 4. Run Engine
        execution = ExecutionSimulator()
        engine = BacktestEngine(
            playback_engine=playback,
            execution_simulator=execution,
            strategy_class=MomentumStrategy,
            strategy_config=strategy_config
        )
        
        logger.info("Starting simulation...")
        engine.start()
        
        # Wait for completion
        import time
        while playback.get_state().value == "playing":
            time.sleep(0.01)

        # 5. Collect Results
        stats = execution.get_execution_statistics()
        
        # Inject equity curve into stats for reporter (which needs it for CAGR/DD calculation)
        stats['equity_curve'] = engine.equity_curve
        stats['executions'] = execution.execution_history
        
        # Use filled_orders as proxy for activity if total_trades missing
        # (each trade usually has at least 2 filled orders: entry & exit)
        if stats.get('filled_orders', 0) > 0:
            reporter = BacktestReporter()
            report_path = reporter.generate_report(stats, f"Momentum_{symbol}_Dhan")
            
            # Simple trade count estimate if not provided
            trade_count = stats.get('total_trades', stats.get('filled_orders', 0) // 2)
            
            # Try to extract metrics if reporter modified stats or return
            # Using basic returns from stats if available, else derive
            
            # Re-read reports or calculate basic return here for summary
            initial_equity = engine.initial_capital
            final_equity = engine.current_capital
            total_return_pct = ((final_equity - initial_equity) / initial_equity) * 100
            
            results_summary.append({
                "Symbol": symbol,
                "Total Return %": f"{total_return_pct:.2f}",
                "Win Rate %": f"{stats.get('fill_rate_pct', 0):.2f}", # Placeholder, real win rate needs trade matching
                "Sharpe": "N/A", # Needs advanced calculation
                "Max DD %": "N/A", 
                "Trades": trade_count,
                "Report": report_path
            })
            logger.info(f"Finished {symbol}. Return: {total_return_pct:.2f}%")
        else:
            logger.warning(f"No trades generated for {symbol}")
            results_summary.append({
                "Symbol": symbol,
                "Total Return %": "0.00",
                "Win Rate %": "0.00",
                "Sharpe": "0.00",
                "Max DD %": "0.00",
                "Trades": 0,
                "Report": "N/A"
            })

    # 6. Final Summary
    print("\n" + "="*80)
    print("MULTI-INDEX BACKTEST SUMMARY (DHAN DATA)")
    print("="*80)
    if results_summary:
        df = pd.DataFrame(results_summary)
        print(df.to_string(index=False))
    else:
        print("No results generated.")
    print("="*80 + "\n")

if __name__ == "__main__":
    run_multi_index_backtest()
