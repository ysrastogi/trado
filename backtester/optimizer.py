import logging
import itertools
from typing import Dict, List, Any, Type
from datetime import datetime
import pandas as pd
import numpy as np
from datetime import timedelta

from backtester.backtest_engine import BacktestEngine
from backtester.engine import PlaybackEngine
from backtester.execution_simulator import ExecutionSimulator
from backtester.reporter import BacktestReporter
from strategy_engine.base_strategy import BaseStrategy
from data_layer.historical_data_provider import YFinanceDataProvider

logger = logging.getLogger(__name__)

class ParameterOptimizer:
    """
    Handles parameter sweeps and walk-forward optimization
    """
    
    def __init__(
        self,
        strategy_class: Type[BaseStrategy],
        data_provider: YFinanceDataProvider,
        symbols: List[str],
        base_config: Dict[str, Any],
        param_grid: Dict[str, List[Any]]
    ):
        self.strategy_class = strategy_class
        self.data_provider = data_provider
        self.symbols = symbols
        self.base_config = base_config
        self.param_grid = param_grid
        self.results = []
        
    def run_grid_search(
        self,
        start_date: datetime,
        end_date: datetime,
        interval: str = '1h',
        signal_timeframe: str = None
    ) -> pd.DataFrame:
        """Run grid search over parameter space"""
        
        # Generate all combinations
        keys, values = zip(*self.param_grid.items())
        combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
        
        logger.info(f"Starting grid search with {len(combinations)} combinations...")
        
        for i, params in enumerate(combinations):
            logger.info(f"Testing combination {i+1}/{len(combinations)}: {params}")
            
            # Merge params into config
            config = self.base_config.copy()
            config.update(params)
            
            # Run Backtest
            metrics = self._run_single_backtest(
                config, start_date, end_date, interval, signal_timeframe
            )
            
            # Store result
            result = params.copy()
            result.update(metrics)
            self.results.append(result)
            
        return pd.DataFrame(self.results)

    def _run_single_backtest(
        self,
        config: Dict[str, Any],
        start_date: datetime,
        end_date: datetime,
        interval: str,
        signal_timeframe: str
    ) -> Dict[str, float]:
        """Run a single backtest iteration"""
        
        # Setup Engines
        playback = PlaybackEngine(
            data_provider=self.data_provider,
            symbols=self.symbols,
            start_date=start_date,
            end_date=end_date,
            interval=interval
        )
        
        execution = ExecutionSimulator()
        
        engine = BacktestEngine(
            playback_engine=playback,
            execution_simulator=execution,
            strategy_class=self.strategy_class,
            strategy_config=config,
            signal_timeframe=signal_timeframe
        )
        
        # Run
        engine.start()
        
        # Calculate Metrics (using Reporter logic)
        reporter = BacktestReporter()
        stats = {
            'equity_curve': engine.equity_curve,
            'executions': execution.execution_history,
            'total_orders': len(execution.execution_history),
            # Add other stats needed by reporter
        }
        
        metrics = reporter._calculate_metrics(stats)
        
        # Return key metrics
        return {
            'cagr': metrics.get('cagr', 0),
            'sharpe': metrics.get('sharpe', 0),
            'max_drawdown': metrics.get('max_drawdown', 0),
            'win_rate': metrics.get('win_rate', 0),
            'profit_factor': metrics.get('profit_factor', 0)
        }

    def run_walk_forward(
        self,
        total_start: datetime,
        total_end: datetime,
        train_period_days: int,
        test_period_days: int,
        interval: str = '1h'
    ):
        """
        Run Walk-Forward Optimization
        1. Train (Optimize) on [t, t+train]
        2. Test (Validate) best params on [t+train, t+train+test]
        3. Slide window forward
        """
        current_start = total_start
        
        walk_forward_results = []
        
        while current_start + timedelta(days=train_period_days + test_period_days) <= total_end:
            train_end = current_start + timedelta(days=train_period_days)
            test_end = train_end + timedelta(days=test_period_days)
            
            logger.info(f"Walk-Forward Window: Train[{current_start.date()} - {train_end.date()}] Test[{train_end.date()} - {test_end.date()}]")
            
            # 1. Optimize on Train
            self.results = [] # Clear previous results
            train_df = self.run_grid_search(current_start, train_end, interval)
            
            # Pick best param (e.g. by Sharpe)
            if train_df.empty:
                logger.warning("No results for training window")
                current_start += timedelta(days=test_period_days)
                continue
                
            best_params = train_df.sort_values('sharpe', ascending=False).iloc[0].to_dict()
            # Filter out metrics from params
            param_keys = self.param_grid.keys()
            best_config = {k: v for k, v in best_params.items() if k in param_keys}
            
            logger.info(f"Best Params for window: {best_config}")
            
            # 2. Validate on Test
            config = self.base_config.copy()
            config.update(best_config)
            
            test_metrics = self._run_single_backtest(
                config, train_end, test_end, interval, None
            )
            
            walk_forward_results.append({
                'window_start': current_start,
                'window_end': test_end,
                'params': best_config,
                'train_sharpe': best_params.get('sharpe'),
                'test_sharpe': test_metrics.get('sharpe'),
                'test_cagr': test_metrics.get('cagr'),
                'test_dd': test_metrics.get('max_drawdown')
            })
            
            # Slide window
            current_start += timedelta(days=test_period_days)
            
        return pd.DataFrame(walk_forward_results)
