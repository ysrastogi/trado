import logging
import yaml
from datetime import datetime, timedelta
from pathlib import Path

from backtester.optimizer import ParameterOptimizer
from data_layer.historical_data_provider import YFinanceDataProvider
from strategy_engine.momentum_strategy import MomentumStrategy

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config(path: str):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def main():
    # Configuration
    symbols = ['AAPL', 'MSFT', 'GOOGL'] # Example symbols
    start_date = datetime.now() - timedelta(days=60)
    end_date = datetime.now()
    
    # Base Strategy Config
    base_config = {
        'risk_per_trade': 0.01,
        'features': {
            # Base feature config if needed
        }
    }
    
    # Parameter Grid for Sweep
    param_grid = {
        'roc_period': [8, 12, 16],
        'donchian_period': [14, 20, 30],
        'volume_ma_period': [10, 20, 50]
    }
    
    # Initialize Data Provider
    data_provider = YFinanceDataProvider()
    
    # Initialize Optimizer
    optimizer = ParameterOptimizer(
        strategy_class=MomentumStrategy,
        data_provider=data_provider,
        symbols=symbols,
        base_config=base_config,
        param_grid=param_grid
    )
    
    # 1. Run Grid Search (In-Sample)
    logger.info("Running Grid Search...")
    results = optimizer.run_grid_search(
        start_date=start_date,
        end_date=end_date,
        interval='1h' # Using 1h for speed in this example
    )
    
    print("\nGrid Search Results (Top 5 by Sharpe):")
    print(results.sort_values('sharpe', ascending=False).head(5))
    
    # Save results
    results.to_csv('optimization_results.csv')
    
    # 2. Run Walk-Forward Optimization
    logger.info("\nRunning Walk-Forward Optimization...")
    wf_results = optimizer.run_walk_forward(
        total_start=start_date,
        total_end=end_date,
        train_period_days=30,
        test_period_days=7,
        interval='1h'
    )
    
    print("\nWalk-Forward Results:")
    print(wf_results)
    
    wf_results.to_csv('walk_forward_results.csv')

if __name__ == "__main__":
    main()
