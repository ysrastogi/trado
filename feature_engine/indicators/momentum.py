"""
Momentum and Oscillator indicators
"""

import pandas as pd
import numpy as np
from .base import PriceBasedIndicator, OHLCBasedIndicator


class RSIIndicator(PriceBasedIndicator):
    """Relative Strength Index"""

    def __init__(self, params: dict = None):
        super().__init__("rsi", params)
        self.length = self.params.get('length', 14)

    def _calculate_from_close(self, close: pd.Series) -> pd.Series:
        """Calculate RSI from close prices"""
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.length).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.length).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def get_output_columns(self) -> list:
        return [f"RSI_{self.length}"]

    def validate_params(self) -> bool:
        return 'length' in self.params and self.params['length'] > 0


class MACDIndicator(PriceBasedIndicator):
    """Moving Average Convergence Divergence"""

    def __init__(self, params: dict = None):
        super().__init__("macd", params)
        self.fast = self.params.get('fast', 12)
        self.slow = self.params.get('slow', 26)
        self.signal = self.params.get('signal', 9)

    def _calculate_from_close(self, close: pd.Series) -> pd.DataFrame:
        """Calculate MACD from close prices"""
        fast_ema = close.ewm(span=self.fast, adjust=False).mean()
        slow_ema = close.ewm(span=self.slow, adjust=False).mean()
        macd_line = fast_ema - slow_ema
        signal_line = macd_line.ewm(span=self.signal, adjust=False).mean()
        histogram = macd_line - signal_line

        result = pd.DataFrame({
            f'MACD_{self.fast}_{self.slow}_{self.signal}': macd_line,
            f'MACDs_{self.fast}_{self.slow}_{self.signal}': signal_line,
            f'MACDh_{self.fast}_{self.slow}_{self.signal}': histogram
        })
        return result

    def get_output_columns(self) -> list:
        return [
            f'MACD_{self.fast}_{self.slow}_{self.signal}',
            f'MACDs_{self.fast}_{self.slow}_{self.signal}',
            f'MACDh_{self.fast}_{self.slow}_{self.signal}'
        ]

    def validate_params(self) -> bool:
        return all(k in self.params for k in ['fast', 'slow', 'signal'])


class StochasticIndicator(OHLCBasedIndicator):
    """Stochastic Oscillator"""

    def __init__(self, params: dict = None):
        super().__init__("stoch", params)
        self.k_length = self.params.get('k', 14)
        self.d_length = self.params.get('d', 3)

    def _calculate_from_ohlc(self, open_p, high, low, close) -> pd.DataFrame:
        """Calculate Stochastic from OHLC"""
        lowest_low = low.rolling(window=self.k_length).min()
        highest_high = high.rolling(window=self.k_length).max()

        k_percent = 100 * (close - lowest_low) / (highest_high - lowest_low)
        d_percent = k_percent.rolling(window=self.d_length).mean()

        result = pd.DataFrame({
            f'STOCHk_{self.k_length}_{self.d_length}': k_percent,
            f'STOCHd_{self.k_length}_{self.d_length}': d_percent
        })
        return result

    def get_output_columns(self) -> list:
        return [
            f'STOCHk_{self.k_length}_{self.d_length}',
            f'STOCHd_{self.k_length}_{self.d_length}'
        ]

    def validate_params(self) -> bool:
        return 'k' in self.params and 'd' in self.params


class WilliamsRIndicator(OHLCBasedIndicator):
    """Williams %R"""

    def __init__(self, params: dict = None):
        super().__init__("willr", params)
        self.length = self.params.get('length', 14)

    def _calculate_from_ohlc(self, open_p, high, low, close) -> pd.Series:
        """Calculate Williams %R from OHLC"""
        highest_high = high.rolling(window=self.length).max()
        lowest_low = low.rolling(window=self.length).min()
        return -100 * (highest_high - close) / (highest_high - lowest_low)

    def get_output_columns(self) -> list:
        return [f"WILLR_{self.length}"]

    def validate_params(self) -> bool:
        return 'length' in self.params and self.params['length'] > 0


class ROCIndicator(PriceBasedIndicator):
    """Rate of Change"""

    def __init__(self, params: dict = None):
        super().__init__("roc", params)
        self.length = self.params.get('length', 20)

    def _calculate_from_close(self, close: pd.Series) -> pd.Series:
        """Calculate ROC from close prices"""
        return 100 * (close - close.shift(self.length)) / close.shift(self.length)

    def get_output_columns(self) -> list:
        return [f"ROC_{self.length}"]

    def validate_params(self) -> bool:
        return 'length' in self.params and self.params['length'] > 0


class CCIIndicator(OHLCBasedIndicator):
    """Commodity Channel Index"""

    def __init__(self, params: dict = None):
        super().__init__("cci", params)
        self.length = self.params.get('length', 20)

    def _calculate_from_ohlc(self, open_p, high, low, close) -> pd.Series:
        """Calculate CCI from OHLC"""
        typical_price = (high + low + close) / 3
        sma = typical_price.rolling(window=self.length).mean()
        mad = typical_price.rolling(window=self.length).apply(
            lambda x: np.mean(np.abs(x - x.mean())), raw=False
        )
        return (typical_price - sma) / (0.015 * mad)

    def get_output_columns(self) -> list:
        return [f"CCI_{self.length}"]

    def validate_params(self) -> bool:
        return 'length' in self.params and self.params['length'] > 0