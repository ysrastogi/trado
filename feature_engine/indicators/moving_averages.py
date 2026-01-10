"""
Simple Moving Average indicator
"""

import pandas as pd
from .base import PriceBasedIndicator


class SMAIndicator(PriceBasedIndicator):
    """Simple Moving Average"""

    def __init__(self, params: dict = None):
        super().__init__("sma", params)
        self.length = self.params.get('length', 20)
        self.input_column = self.params.get('input_column', 'close')

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate SMA"""
        if self.input_column not in df.columns:
            raise ValueError(f"Input column '{self.input_column}' not found in DataFrame")
            
        series = df[self.input_column]
        result = series.rolling(window=self.length).mean()
        result.name = self.get_output_columns()[0]
        return result.to_frame()

    def get_output_columns(self) -> list:
        suffix = f"_{self.input_column}" if self.input_column != 'close' else ""
        return [f"SMA_{self.length}{suffix}"]

    def validate_params(self) -> bool:
        return 'length' in self.params and self.params['length'] > 0


class EMAIndicator(PriceBasedIndicator):
    """Exponential Moving Average"""

    def __init__(self, params: dict = None):
        super().__init__("ema", params)
        self.length = self.params.get('length', 20)

    def _calculate_from_close(self, close: pd.Series) -> pd.Series:
        """Calculate EMA from close prices"""
        return close.ewm(span=self.length, adjust=False).mean()

    def get_output_columns(self) -> list:
        return [f"EMA_{self.length}"]

    def validate_params(self) -> bool:
        return 'length' in self.params and self.params['length'] > 0


class WMAIndicator(PriceBasedIndicator):
    """Weighted Moving Average"""

    def __init__(self, params: dict = None):
        super().__init__("wma", params)
        self.length = self.params.get('length', 20)

    def _calculate_from_close(self, close: pd.Series) -> pd.Series:
        """Calculate WMA from close prices"""
        weights = pd.Series(range(1, self.length + 1))
        return close.rolling(window=self.length).apply(
            lambda x: (x * weights).sum() / weights.sum(), raw=False
        )

    def get_output_columns(self) -> list:
        return [f"WMA_{self.length}"]

    def validate_params(self) -> bool:
        return 'length' in self.params and self.params['length'] > 0


class HMAIndicator(PriceBasedIndicator):
    """Hull Moving Average"""

    def __init__(self, params: dict = None):
        super().__init__("hma", params)
        self.length = self.params.get('length', 20)

    def _calculate_from_close(self, close: pd.Series) -> pd.Series:
        """Calculate HMA from close prices"""
        # HMA = WMA(2*WMA(n/2) - WMA(n)), sqrt(n)
        half_length = int(self.length / 2)
        sqrt_length = int(self.length ** 0.5)

        wma_half = close.rolling(window=half_length).apply(
            lambda x: (x * pd.Series(range(1, half_length + 1))).sum() / sum(range(1, half_length + 1)), raw=False
        )
        wma_full = close.rolling(window=self.length).apply(
            lambda x: (x * pd.Series(range(1, self.length + 1))).sum() / sum(range(1, self.length + 1)), raw=False
        )

        diff = 2 * wma_half - wma_full
        return diff.rolling(window=sqrt_length).apply(
            lambda x: (x * pd.Series(range(1, sqrt_length + 1))).sum() / sum(range(1, sqrt_length + 1)), raw=False
        )

    def get_output_columns(self) -> list:
        return [f"HMA_{self.length}"]

    def validate_params(self) -> bool:
        return 'length' in self.params and self.params['length'] > 0


class TEMAIndicator(PriceBasedIndicator):
    """Triple Exponential Moving Average"""

    def __init__(self, params: dict = None):
        super().__init__("tema", params)
        self.length = self.params.get('length', 20)

    def _calculate_from_close(self, close: pd.Series) -> pd.Series:
        """Calculate TEMA from close prices"""
        ema1 = close.ewm(span=self.length, adjust=False).mean()
        ema2 = ema1.ewm(span=self.length, adjust=False).mean()
        ema3 = ema2.ewm(span=self.length, adjust=False).mean()
        return 3 * ema1 - 3 * ema2 + ema3

    def get_output_columns(self) -> list:
        return [f"TEMA_{self.length}"]

    def validate_params(self) -> bool:
        return 'length' in self.params and self.params['length'] > 0