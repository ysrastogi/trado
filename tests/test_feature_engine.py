
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from feature_engine.indicator_calculator import IndicatorCalculator
from feature_engine.models import FeatureConfig, IndicatorConfig
from common.models import CandleData

class TestIndicatorCalculator(unittest.TestCase):
    def setUp(self):
        # Create sample candles
        self.candles = []
        base_time = datetime(2023, 1, 1)
        price = 100.0
        for i in range(200):
            self.candles.append(CandleData(
                timestamp=base_time + timedelta(hours=i),
                symbol="TEST",
                open=price,
                high=price + 2.0,
                low=price - 2.0,
                close=price + 1.0,
                volume=1000
            ))
            price += 0.5 if i % 2 == 0 else -0.3

    def test_default_config(self):
        calculator = IndicatorCalculator()
        indicators = calculator.calculate_indicators(self.candles)
        
        # Check if default indicators are present
        self.assertTrue(len(indicators) > 0)
        # Default config has sma, rsi, macd, etc.
        # Check for some keys (case insensitive)
        keys = [k.lower() for k in indicators.keys()]
        print(f"Default keys: {keys}")
        self.assertTrue(any('sma' in k for k in keys))
        self.assertTrue(any('rsi' in k for k in keys))

    def test_custom_config(self):
        config = FeatureConfig(
            indicators=[
                IndicatorConfig(name="sma", params={"length": 10}),
                IndicatorConfig(name="ema", params={"length": 20})
            ]
        )
        calculator = IndicatorCalculator(config=config)
        indicators = calculator.calculate_indicators(self.candles)
        
        keys = list(indicators.keys())
        print(f"Custom keys: {keys}")
        self.assertIn('SMA_10', keys)
        self.assertIn('EMA_20', keys)
        self.assertNotIn('rsi', keys)

    def test_multi_timeframe(self):
        # Config with 1h (base) and 2h
        config = FeatureConfig(
            indicators=[
                IndicatorConfig(name="sma", params={"length": 10})
            ],
            timeframes=["2h"]
        )
        calculator = IndicatorCalculator(config=config)
        indicators = calculator.calculate_indicators(self.candles)
        
        keys = list(indicators.keys())
        print(f"Multi-timeframe keys: {keys}")
        
        # Should have base SMA_10
        self.assertIn('SMA_10', keys)
        # Should have 2h_SMA_10
        self.assertIn('2h_SMA_10', keys)
        
        # Check lengths
        self.assertEqual(len(indicators['SMA_10']), 200)
        self.assertEqual(len(indicators['2h_SMA_10']), 200)

if __name__ == '__main__':
    unittest.main()
