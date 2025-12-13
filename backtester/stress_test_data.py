#!/usr/bin/env python3
"""
Synthetic data generators for stress testing trading algorithms.

Generates edge case scenarios to test algorithm robustness:
- Flat markets (no volatility)
- Spike anomalies (sudden price jumps)
- Missing data (NaN sequences)
- Minimal data (bare minimum candles)
- Extreme ATR (high volatility for large caps)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from dataclasses import dataclass

from .models import CandleData


@dataclass
class StressTestScenario:
    """Describes a stress test scenario"""
    name: str
    description: str
    edge_case_type: str
    expected_behavior: str
    candles: List[CandleData]
    metadata: dict


class StressTestDataGenerator:
    """Generate synthetic data for stress testing algorithms"""
    
    def __init__(self, base_price: float = 45000.0, symbol: str = "BTC-USD"):
        """
        Initialize generator
        
        Args:
            base_price: Starting price for synthetic data
            symbol: Symbol name for generated candles
        """
        self.base_price = base_price
        self.symbol = symbol
    
    def generate_flat_market(
        self,
        num_candles: int = 200,
        price_variation: float = 0.001,  # 0.1% max variation
        start_time: Optional[datetime] = None
    ) -> StressTestScenario:
        """
        Generate flat market with minimal price movement.
        
        Tests algorithm behavior when:
        - No clear trend exists
        - Volatility is extremely low
        - Indicators may give false signals
        
        Args:
            num_candles: Number of candles to generate
            price_variation: Maximum price variation as fraction (0.001 = 0.1%)
            start_time: Starting timestamp
        """
        if start_time is None:
            start_time = datetime(2024, 1, 1)
        
        candles = []
        current_time = start_time
        
        for i in range(num_candles):
            # Very small random variations around base price
            variation = np.random.uniform(-price_variation, price_variation)
            price = self.base_price * (1 + variation)
            
            # Create extremely tight OHLC ranges
            high = price * (1 + price_variation/2)
            low = price * (1 - price_variation/2)
            open_price = price * (1 + np.random.uniform(-price_variation/3, price_variation/3))
            close = price * (1 + np.random.uniform(-price_variation/3, price_variation/3))
            
            candles.append(CandleData(
                timestamp=current_time,
                symbol=self.symbol,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=1000 + np.random.randint(-100, 100)
            ))
            
            current_time += timedelta(hours=1)
        
        return StressTestScenario(
            name="Flat Market",
            description=f"Sideways market with {price_variation*100:.2f}% max variation over {num_candles} candles",
            edge_case_type="flat_market",
            expected_behavior="Should avoid false signals, maintain neutral/sideways stance",
            candles=candles,
            metadata={
                "price_variation": price_variation,
                "num_candles": num_candles,
                "avg_price": self.base_price
            }
        )
    
    def generate_spike_anomaly(
        self,
        num_candles: int = 100,
        spike_position: int = 50,
        spike_magnitude: float = 0.15,  # 15% spike
        spike_type: str = "up",  # "up" or "down"
        recovery_candles: int = 1,  # How fast it recovers
        start_time: Optional[datetime] = None
    ) -> StressTestScenario:
        """
        Generate single-candle spike anomaly (flash crash/pump).
        
        Tests algorithm behavior when:
        - Sudden price anomaly occurs
        - Single candle deviates significantly
        - Price quickly reverts to normal
        
        Args:
            num_candles: Total candles
            spike_position: Where spike occurs (candle index)
            spike_magnitude: Size of spike as fraction (0.15 = 15%)
            spike_type: "up" or "down"
            recovery_candles: Number of candles to recover
        """
        if start_time is None:
            start_time = datetime(2024, 1, 1)
        
        candles = []
        current_time = start_time
        price = self.base_price
        
        for i in range(num_candles):
            if i == spike_position:
                # Anomaly candle
                if spike_type == "up":
                    spike_price = price * (1 + spike_magnitude)
                    candle = CandleData(
                        timestamp=current_time,
                        symbol=self.symbol,
                        open=price,
                        high=spike_price,
                        low=price * 0.999,
                        close=spike_price * 0.95,  # Closes lower than peak
                        volume=5000  # High volume spike
                    )
                else:  # down
                    spike_price = price * (1 - spike_magnitude)
                    candle = CandleData(
                        timestamp=current_time,
                        symbol=self.symbol,
                        open=price,
                        high=price * 1.001,
                        low=spike_price,
                        close=spike_price * 1.05,  # Closes higher than bottom
                        volume=5000
                    )
                candles.append(candle)
                price = candle.close
            
            elif i > spike_position and i <= spike_position + recovery_candles:
                # Recovery candles - revert to base
                recovery_progress = (i - spike_position) / recovery_candles
                target_price = self.base_price
                price = price + (target_price - price) * recovery_progress
                
                candles.append(CandleData(
                    timestamp=current_time,
                    symbol=self.symbol,
                    open=candles[-1].close,
                    high=max(candles[-1].close, price) * 1.002,
                    low=min(candles[-1].close, price) * 0.998,
                    close=price,
                    volume=2000
                ))
            
            else:
                # Normal candles with small variation
                variation = np.random.uniform(-0.005, 0.005)
                price = self.base_price * (1 + variation)
                
                candles.append(CandleData(
                    timestamp=current_time,
                    symbol=self.symbol,
                    open=price * 0.999,
                    high=price * 1.003,
                    low=price * 0.997,
                    close=price,
                    volume=1000
                ))
            
            current_time += timedelta(hours=1)
        
        return StressTestScenario(
            name=f"Spike Anomaly ({spike_type.upper()})",
            description=f"{spike_magnitude*100:.0f}% {spike_type} spike at candle {spike_position}, recovers in {recovery_candles} candles",
            edge_case_type="spike_anomaly",
            expected_behavior="Should not overreact to single candle anomaly, wait for confirmation",
            candles=candles,
            metadata={
                "spike_magnitude": spike_magnitude,
                "spike_type": spike_type,
                "spike_position": spike_position,
                "recovery_candles": recovery_candles
            }
        )
    
    def generate_missing_data(
        self,
        num_candles: int = 150,
        gap_starts: List[int] = [50, 100],
        gap_lengths: List[int] = [5, 10],
        start_time: Optional[datetime] = None
    ) -> StressTestScenario:
        """
        Generate data with NaN/missing sequences.
        
        Tests algorithm behavior when:
        - Data feeds are interrupted
        - NaN values appear in OHLCV
        - History has gaps
        
        Args:
            num_candles: Total candles (including gaps)
            gap_starts: List of positions where gaps start
            gap_lengths: List of gap durations (parallel to gap_starts)
        """
        if start_time is None:
            start_time = datetime(2024, 1, 1)
        
        candles = []
        current_time = start_time
        price = self.base_price
        
        # Create gap map
        gap_map = {}
        for gap_start, gap_len in zip(gap_starts, gap_lengths):
            for i in range(gap_start, gap_start + gap_len):
                gap_map[i] = True
        
        for i in range(num_candles):
            if i in gap_map:
                # Missing data candle - all NaN
                candles.append(CandleData(
                    timestamp=current_time,
                    symbol=self.symbol,
                    open=np.nan,
                    high=np.nan,
                    low=np.nan,
                    close=np.nan,
                    volume=np.nan
                ))
            else:
                # Normal candle
                variation = np.random.uniform(-0.01, 0.01)
                price = price * (1 + variation)
                
                candles.append(CandleData(
                    timestamp=current_time,
                    symbol=self.symbol,
                    open=price * 0.998,
                    high=price * 1.005,
                    low=price * 0.995,
                    close=price,
                    volume=1000 + np.random.randint(-200, 200)
                ))
            
            current_time += timedelta(hours=1)
        
        total_missing = sum(gap_lengths)
        return StressTestScenario(
            name="Missing Data",
            description=f"{len(gap_starts)} gaps with {total_missing} total missing candles out of {num_candles}",
            edge_case_type="missing_data",
            expected_behavior="Should handle NaN gracefully without crashes, skip or interpolate missing values",
            candles=candles,
            metadata={
                "gap_starts": gap_starts,
                "gap_lengths": gap_lengths,
                "total_missing": total_missing,
                "missing_percentage": (total_missing / num_candles) * 100
            }
        )
    
    def generate_minimal_data(
        self,
        num_candles: int = 15,  # Just enough for most indicators
        trend: str = "flat",  # "flat", "up", "down"
        start_time: Optional[datetime] = None
    ) -> StressTestScenario:
        """
        Generate minimal data (bare minimum for indicators).
        
        Tests algorithm behavior when:
        - Insufficient history for full indicator calculation
        - Cold start scenario
        - Limited data points
        
        Args:
            num_candles: Very small number of candles
            trend: "flat", "up", or "down"
        """
        if start_time is None:
            start_time = datetime(2024, 1, 1)
        
        candles = []
        current_time = start_time
        price = self.base_price
        
        if trend == "up":
            price_increment = 0.02  # 2% per candle
        elif trend == "down":
            price_increment = -0.02
        else:
            price_increment = 0
        
        for i in range(num_candles):
            if trend != "flat":
                price = price * (1 + price_increment)
            else:
                price = self.base_price * (1 + np.random.uniform(-0.002, 0.002))
            
            candles.append(CandleData(
                timestamp=current_time,
                symbol=self.symbol,
                open=price * 0.998,
                high=price * 1.004,
                low=price * 0.996,
                close=price,
                volume=1000
            ))
            
            current_time += timedelta(hours=1)
        
        return StressTestScenario(
            name=f"Minimal Data ({trend})",
            description=f"Only {num_candles} candles with {trend} trend - tests cold start",
            edge_case_type="minimal_data",
            expected_behavior="Should initialize without errors, may defer signals until enough data",
            candles=candles,
            metadata={
                "num_candles": num_candles,
                "trend": trend,
                "sufficient_for_periods": [5, 10, 12, 14]  # Common indicator periods
            }
        )
    
    def generate_extreme_atr(
        self,
        num_candles: int = 100,
        base_price: float = 150.0,  # Large cap stock price
        atr_percentage: float = 0.10,  # 10% ATR
        start_time: Optional[datetime] = None
    ) -> StressTestScenario:
        """
        Generate extreme ATR scenario for large cap stocks.
        
        Tests algorithm behavior when:
        - High volatility on normally stable assets
        - ATR is abnormally large relative to price
        - Whipsaw conditions
        
        Args:
            num_candles: Number of candles
            base_price: Price level (lower = large cap)
            atr_percentage: ATR as percentage of price (0.10 = 10%)
        """
        if start_time is None:
            start_time = datetime(2024, 1, 1)
        
        candles = []
        current_time = start_time
        price = base_price
        
        for i in range(num_candles):
            # Generate large swings
            swing = np.random.uniform(-atr_percentage, atr_percentage)
            price = price * (1 + swing)
            
            # Create wide OHLC ranges
            range_size = abs(swing) * 1.5
            high = price * (1 + range_size/2)
            low = price * (1 - range_size/2)
            
            open_price = low + (high - low) * np.random.uniform(0.2, 0.8)
            close = low + (high - low) * np.random.uniform(0.2, 0.8)
            
            candles.append(CandleData(
                timestamp=current_time,
                symbol=self.symbol,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=10000 + np.random.randint(-2000, 2000)
            ))
            
            current_time += timedelta(hours=1)
        
        # Calculate actual ATR for metadata
        atr_values = []
        for i in range(1, len(candles)):
            tr = max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - candles[i-1].close),
                abs(candles[i].low - candles[i-1].close)
            )
            atr_values.append(tr)
        
        avg_atr = np.mean(atr_values) if atr_values else 0
        
        return StressTestScenario(
            name="Extreme ATR",
            description=f"Large cap (${base_price:.0f}) with {atr_percentage*100:.0f}% ATR - extreme volatility",
            edge_case_type="extreme_atr",
            expected_behavior="Should adapt to high volatility, avoid excessive stop-outs",
            candles=candles,
            metadata={
                "base_price": base_price,
                "target_atr_percentage": atr_percentage * 100,
                "actual_avg_atr": avg_atr,
                "actual_atr_percentage": (avg_atr / base_price) * 100,
                "num_candles": num_candles
            }
        )
    
    def generate_all_scenarios(self) -> List[StressTestScenario]:
        """Generate all stress test scenarios"""
        scenarios = []
        
        # 1. Flat market
        scenarios.append(self.generate_flat_market(
            num_candles=200,
            price_variation=0.001
        ))
        
        # 2. Spike anomaly (up)
        scenarios.append(self.generate_spike_anomaly(
            num_candles=100,
            spike_position=50,
            spike_magnitude=0.20,
            spike_type="up",
            recovery_candles=2
        ))
        
        # 3. Spike anomaly (down)
        scenarios.append(self.generate_spike_anomaly(
            num_candles=100,
            spike_position=50,
            spike_magnitude=0.20,
            spike_type="down",
            recovery_candles=2
        ))
        
        # 4. Missing data
        scenarios.append(self.generate_missing_data(
            num_candles=150,
            gap_starts=[30, 80, 120],
            gap_lengths=[5, 10, 8]
        ))
        
        # 5. Minimal data (flat)
        scenarios.append(self.generate_minimal_data(
            num_candles=15,
            trend="flat"
        ))
        
        # 6. Minimal data (trending up)
        scenarios.append(self.generate_minimal_data(
            num_candles=20,
            trend="up"
        ))
        
        # 7. Minimal data (trending down)
        scenarios.append(self.generate_minimal_data(
            num_candles=20,
            trend="down"
        ))
        
        # 8. Extreme ATR
        scenarios.append(self.generate_extreme_atr(
            num_candles=100,
            base_price=150.0,
            atr_percentage=0.12
        ))
        
        return scenarios


if __name__ == "__main__":
    # Demo the generators
    generator = StressTestDataGenerator(base_price=45000.0, symbol="TEST-USD")
    
    print("Generating stress test scenarios...\n")
    scenarios = generator.generate_all_scenarios()
    
    for scenario in scenarios:
        print(f"{'='*70}")
        print(f"Scenario: {scenario.name}")
        print(f"Description: {scenario.description}")
        print(f"Edge Case: {scenario.edge_case_type}")
        print(f"Expected: {scenario.expected_behavior}")
        print(f"Candles: {len(scenario.candles)}")
        print(f"Metadata: {scenario.metadata}")
        print()
