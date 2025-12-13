#!/usr/bin/env python3
"""
Stress Test Engine for Trading Algorithms

Tests algorithm robustness against edge cases:
- Flat markets
- Spike anomalies  
- Missing data
- Minimal data
- Extreme ATR

Measures: crashes, error handling, signal quality, performance
"""

import logging
import traceback
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from .stress_test_data import StressTestScenario, StressTestDataGenerator
from .engine import PlaybackEngine
from .algorithm_adapter import PlaybackAlgorithmAdapter
from .signal_logger import SignalLogger
from .models import SignalEvent, PlaybackState
from src.data_layer.market_stream.models import TickData

logger = logging.getLogger(__name__)


class TestResult(Enum):
    """Test outcome"""
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class StressTestMetrics:
    """Metrics collected during stress test"""
    scenario_name: str
    algorithm_name: str
    edge_case_type: str
    
    # Execution metrics
    completed: bool = False
    crashed: bool = False
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    execution_time_seconds: float = 0.0
    
    # Data metrics
    total_candles: int = 0
    candles_processed: int = 0
    nan_candles_encountered: int = 0
    
    # Signal metrics
    total_signals: int = 0
    signal_types: Dict[str, int] = field(default_factory=dict)
    avg_confidence: float = 0.0
    signals_per_candle: float = 0.0
    
    # Error handling
    exceptions_caught: List[str] = field(default_factory=list)
    warnings_generated: List[str] = field(default_factory=list)
    
    # Test verdict
    result: TestResult = TestResult.PASS
    score: float = 100.0  # 0-100
    issues: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'scenario_name': self.scenario_name,
            'algorithm_name': self.algorithm_name,
            'edge_case_type': self.edge_case_type,
            'completed': self.completed,
            'crashed': self.crashed,
            'error_message': self.error_message,
            'execution_time_seconds': self.execution_time_seconds,
            'total_candles': self.total_candles,
            'candles_processed': self.candles_processed,
            'nan_candles_encountered': self.nan_candles_encountered,
            'total_signals': self.total_signals,
            'signal_types': self.signal_types,
            'avg_confidence': self.avg_confidence,
            'signals_per_candle': self.signals_per_candle,
            'exceptions_caught': self.exceptions_caught,
            'warnings_generated': self.warnings_generated,
            'result': self.result.value,
            'score': self.score,
            'issues': self.issues
        }


class StressTestEngine:
    """
    Runs stress tests on trading algorithms.
    
    Tests algorithm behavior under edge case conditions
    and scores robustness, error handling, and signal quality.
    """
    
    def __init__(self, verbose: bool = True):
        """
        Initialize stress test engine
        
        Args:
            verbose: Print detailed progress
        """
        self.verbose = verbose
        self.results: List[StressTestMetrics] = []
    
    def run_scenario(
        self,
        scenario: StressTestScenario,
        algorithm: Any,
        algorithm_name: str,
        timeout_seconds: float = 300.0
    ) -> StressTestMetrics:
        """
        Run a single stress test scenario
        
        Args:
            scenario: Test scenario with synthetic data
            algorithm: Algorithm instance to test
            algorithm_name: Name for reporting
            timeout_seconds: Max execution time
            
        Returns:
            StressTestMetrics with results
        """
        if self.verbose:
            print(f"\n{'─'*70}")
            print(f"Testing: {algorithm_name}")
            print(f"Scenario: {scenario.name}")
            print(f"Edge Case: {scenario.edge_case_type}")
            print(f"Candles: {len(scenario.candles)}")
            print(f"{'─'*70}")
        
        metrics = StressTestMetrics(
            scenario_name=scenario.name,
            algorithm_name=algorithm_name,
            edge_case_type=scenario.edge_case_type,
            total_candles=len(scenario.candles)
        )
        
        start_time = datetime.now()
        
        try:
            import pandas as pd  # For NaN checking
            
            # Track signals by monitoring algorithm state
            signals_captured = []
            processed_count = 0
            nan_count = 0
            
            # Track previous signal state for change detection
            previous_signal = {}
            for symbol in getattr(algorithm, 'symbols', ['TEST-USD']):
                previous_signal[symbol] = None
            
            # Feed candles as ticks directly to algorithm
            for i, candle in enumerate(scenario.candles):
                try:
                    # Check for NaN
                    if (pd.isna(candle.open) or pd.isna(candle.high) or 
                        pd.isna(candle.low) or pd.isna(candle.close)):
                        nan_count += 1
                        # Try to feed NaN to test error handling
                        try:
                            # Create tick with NaN
                            tick = TickData(
                                symbol=candle.symbol,
                                quote=candle.close,
                                epoch=int(candle.timestamp.timestamp()),
                                timestamp=candle.timestamp
                            )
                            algorithm.process_tick(tick, message_id=f"stress_test_{i}")
                        except Exception as e:
                            metrics.warnings_generated.append(
                                f"Candle {i}: Rejected NaN - {str(e)}"
                            )
                        continue
                    
                    # Feed valid candle as OHLC ticks
                    symbol = candle.symbol
                    
                    # Create 4 ticks: open, high, low, close
                    for price in [candle.open, candle.high, candle.low, candle.close]:
                        tick = TickData(
                            symbol=symbol,
                            quote=price,
                            epoch=int(candle.timestamp.timestamp()),
                            timestamp=candle.timestamp
                        )
                        algorithm.process_tick(tick, message_id=f"stress_test_{i}")
                    
                    processed_count += 1
                    
                    # Check if signal changed
                    current_signal = getattr(algorithm, 'previous_signals', {}).get(symbol)
                    if current_signal and current_signal != previous_signal.get(symbol):
                        # Signal changed - capture it
                        signal_event = SignalEvent(
                            timestamp=candle.timestamp,
                            symbol=symbol,
                            algorithm=algorithm_name,
                            signal_type=str(current_signal),
                            confidence=getattr(algorithm, 'previous_confidences', {}).get(symbol, 0.5),
                            reason=f"Signal: {current_signal}",
                            trigger_conditions=[],
                            indicators={},
                            candle=candle,
                            previous_signal=previous_signal.get(symbol),
                            signal_change=True
                        )
                        signals_captured.append(signal_event)
                        previous_signal[symbol] = current_signal
                    
                except Exception as e:
                    error_msg = f"Candle {i}: {type(e).__name__} - {str(e)}"
                    metrics.exceptions_caught.append(error_msg)
                    if self.verbose:
                        print(f"  ⚠️  {error_msg}")
            
            metrics.candles_processed = processed_count
            metrics.nan_candles_encountered = nan_count
            metrics.completed = True
            
            # Analyze signals
            metrics.total_signals = len(signals_captured)
            
            if signals_captured:
                # Count signal types
                for signal in signals_captured:
                    signal_type = signal.signal_type
                    metrics.signal_types[signal_type] = metrics.signal_types.get(signal_type, 0) + 1
                
                # Average confidence
                confidences = [s.confidence for s in signals_captured if s.confidence is not None]
                if confidences:
                    metrics.avg_confidence = sum(confidences) / len(confidences)
                
                # Signals per candle
                if processed_count > 0:
                    metrics.signals_per_candle = len(signals_captured) / processed_count
            
        except Exception as e:
            metrics.crashed = True
            metrics.error_message = str(e)
            metrics.error_traceback = traceback.format_exc()
            
            if self.verbose:
                print(f"  ❌ CRASH: {e}")
                print(f"  {traceback.format_exc()}")
        
        finally:
            end_time = datetime.now()
            metrics.execution_time_seconds = (end_time - start_time).total_seconds()
        
        # Score the test
        self._score_test(scenario, metrics)
        
        if self.verbose:
            self._print_metrics(metrics)
        
        self.results.append(metrics)
        return metrics
    
    def _score_test(self, scenario: StressTestScenario, metrics: StressTestMetrics):
        """
        Score the test based on behavior
        
        Scoring criteria:
        - Crashes: -100 (instant fail)
        - Errors: -10 per error
        - Warnings: -5 per warning
        - Completion: +20
        - Signal quality: edge-case specific
        """
        score = 100.0
        issues = []
        
        # Critical: Crash
        if metrics.crashed:
            score = 0.0
            metrics.result = TestResult.ERROR
            issues.append(f"CRASH: {metrics.error_message}")
            metrics.issues = issues
            metrics.score = score
            return
        
        # Major: Did not complete
        if not metrics.completed:
            score -= 50
            issues.append("Failed to complete scenario")
            metrics.result = TestResult.FAIL
        
        # Exceptions during processing
        if metrics.exceptions_caught:
            penalty = min(len(metrics.exceptions_caught) * 10, 40)
            score -= penalty
            issues.append(f"{len(metrics.exceptions_caught)} exceptions caught during processing")
        
        # Warnings
        if metrics.warnings_generated:
            penalty = min(len(metrics.warnings_generated) * 5, 20)
            score -= penalty
        
        # Edge case specific scoring
        edge_case = scenario.edge_case_type
        
        if edge_case == "flat_market":
            # Should not generate excessive signals in flat market
            if metrics.signals_per_candle > 0.05:  # More than 5%
                score -= 20
                issues.append(f"Too many signals in flat market: {metrics.signals_per_candle:.2%}")
        
        elif edge_case == "spike_anomaly":
            # Should not overreact to single spike
            spike_position = scenario.metadata.get('spike_position', 0)
            recovery = scenario.metadata.get('recovery_candles', 1)
            
            # Check if signals clustered around spike
            # (In real implementation, would check signal timestamps)
            if metrics.total_signals > 3:
                score -= 15
                issues.append("Excessive signals around anomaly spike")
        
        elif edge_case == "missing_data":
            # Should handle NaN gracefully
            if metrics.crashed:
                score = 0
                issues.append("Crashed on NaN data")
            elif metrics.exceptions_caught:
                # Some exceptions ok if handled
                pass
        
        elif edge_case == "minimal_data":
            # Should initialize without crashing on limited data
            if not metrics.completed:
                score -= 40
                issues.append("Failed with minimal data")
            
            # May not generate signals (ok)
            if metrics.total_signals == 0:
                issues.append("No signals (expected with limited data)")
        
        elif edge_case == "extreme_atr":
            # Should adapt to high volatility
            if metrics.signals_per_candle > 0.15:  # >15% of candles
                score -= 15
                issues.append("Too many signals in high volatility")
        
        # Final result
        score = max(0.0, min(100.0, score))
        metrics.score = score
        
        if score >= 80:
            metrics.result = TestResult.PASS
        elif score >= 60:
            metrics.result = TestResult.WARNING
        else:
            metrics.result = TestResult.FAIL
        
        metrics.issues = issues
    
    def _print_metrics(self, metrics: StressTestMetrics):
        """Print test metrics"""
        print(f"\n  Result: {metrics.result.value.upper()} (Score: {metrics.score:.1f}/100)")
        
        if metrics.crashed:
            print(f"  ❌ Crashed: {metrics.error_message}")
        elif metrics.completed:
            print(f"  ✓ Completed in {metrics.execution_time_seconds:.2f}s")
        else:
            print(f"  ✗ Did not complete")
        
        print(f"  Candles: {metrics.candles_processed}/{metrics.total_candles} processed")
        
        if metrics.nan_candles_encountered > 0:
            print(f"  NaN candles: {metrics.nan_candles_encountered}")
        
        print(f"  Signals: {metrics.total_signals} (avg conf: {metrics.avg_confidence:.2f})")
        
        if metrics.signal_types:
            print(f"  Signal types: {metrics.signal_types}")
        
        if metrics.exceptions_caught:
            print(f"  ⚠️  Exceptions: {len(metrics.exceptions_caught)}")
        
        if metrics.issues:
            print(f"  Issues:")
            for issue in metrics.issues:
                print(f"    • {issue}")
    
    def run_all_scenarios(
        self,
        algorithm: Any,
        algorithm_name: str,
        scenarios: Optional[List[StressTestScenario]] = None
    ) -> List[StressTestMetrics]:
        """
        Run all stress test scenarios on an algorithm
        
        Args:
            algorithm: Algorithm instance
            algorithm_name: Name for reporting
            scenarios: List of scenarios (generates default if None)
            
        Returns:
            List of test metrics
        """
        if scenarios is None:
            generator = StressTestDataGenerator()
            scenarios = generator.generate_all_scenarios()
        
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"STRESS TEST: {algorithm_name}")
            print(f"Running {len(scenarios)} edge case scenarios")
            print(f"{'='*70}")
        
        results = []
        for scenario in scenarios:
            result = self.run_scenario(scenario, algorithm, algorithm_name)
            results.append(result)
        
        # Summary
        if self.verbose:
            self._print_summary(algorithm_name, results)
        
        return results
    
    def _print_summary(self, algorithm_name: str, results: List[StressTestMetrics]):
        """Print test summary"""
        print(f"\n{'='*70}")
        print(f"STRESS TEST SUMMARY: {algorithm_name}")
        print(f"{'='*70}\n")
        
        total_tests = len(results)
        passed = sum(1 for r in results if r.result == TestResult.PASS)
        warnings = sum(1 for r in results if r.result == TestResult.WARNING)
        failed = sum(1 for r in results if r.result == TestResult.FAIL)
        errors = sum(1 for r in results if r.result == TestResult.ERROR)
        
        avg_score = sum(r.score for r in results) / total_tests if total_tests > 0 else 0
        
        print(f"Total Tests: {total_tests}")
        print(f"  ✓ Passed:   {passed}")
        print(f"  ⚠ Warnings: {warnings}")
        print(f"  ✗ Failed:   {failed}")
        print(f"  ❌ Errors:   {errors}")
        print(f"\nAverage Score: {avg_score:.1f}/100")
        
        if avg_score >= 80:
            grade = "A"
        elif avg_score >= 70:
            grade = "B"
        elif avg_score >= 60:
            grade = "C"
        elif avg_score >= 50:
            grade = "D"
        else:
            grade = "F"
        
        print(f"Overall Grade: {grade}")
        
        # Show failures
        failures = [r for r in results if r.result in [TestResult.FAIL, TestResult.ERROR]]
        if failures:
            print(f"\nFailed Scenarios:")
            for r in failures:
                print(f"  • {r.scenario_name}: {r.result.value.upper()} ({r.score:.0f}/100)")
                for issue in r.issues:
                    print(f"      - {issue}")


if __name__ == "__main__":
    # Demo
    print("Stress Test Engine Demo")
    print("="*70)
    print("\nThis module requires an algorithm instance to test.")
    print("Use: python -m src.playback.stress_test_runner")
