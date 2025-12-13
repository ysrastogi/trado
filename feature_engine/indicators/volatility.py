"""
Volatility and Trend indicators
"""

import pandas as pd
import numpy as np
from .base import OHLCBasedIndicator, PriceBasedIndicator


class ATRIndicator(OHLCBasedIndicator):
    """Average True Range"""

    def __init__(self, params: dict = None):
        super().__init__("atr", params)
        self.length = self.params.get('length', 14)

    def _calculate_from_ohlc(self, open_p, high, low, close) -> pd.Series:
        """Calculate ATR from OHLC"""
        high_low = high - low
        high_close = np.abs(high - close.shift(1))
        low_close = np.abs(low - close.shift(1))

        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return true_range.rolling(window=self.length).mean()

    def get_output_columns(self) -> list:
        return [f"ATRr_{self.length}"]

    def validate_params(self) -> bool:
        return 'length' in self.params and self.params['length'] > 0


class ADXIndicator(OHLCBasedIndicator):
    """Average Directional Index"""

    def __init__(self, params: dict = None):
        super().__init__("adx", params)
        self.length = self.params.get('length', 14)

    def _calculate_from_ohlc(self, open_p, high, low, close) -> pd.DataFrame:
        """Calculate ADX from OHLC"""
        # True Range
        tr1 = high - low
        tr2 = np.abs(high - close.shift(1))
        tr3 = np.abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=self.length).mean()

        # Directional Movement
        high_diff = high.diff()
        low_diff = -low.diff()

        plus_dm = pd.Series(np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0))
        minus_dm = pd.Series(np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0))

        plus_di = 100 * plus_dm.rolling(window=self.length).mean() / atr
        minus_di = 100 * minus_dm.rolling(window=self.length).mean() / atr

        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=self.length).mean()

        result = pd.DataFrame({
            f'ADX_{self.length}': adx,
            f'DMP_{self.length}': plus_di,
            f'DMN_{self.length}': minus_di
        })
        return result

    def get_output_columns(self) -> list:
        return [
            f'ADX_{self.length}',
            f'DMP_{self.length}',
            f'DMN_{self.length}'
        ]

    def validate_params(self) -> bool:
        return 'length' in self.params and self.params['length'] > 0


class BollingerBandsIndicator(PriceBasedIndicator):
    """Bollinger Bands"""

    def __init__(self, params: dict = None):
        super().__init__("bbands", params)
        self.length = self.params.get('length', 20)
        self.std = self.params.get('std', 2.0)

    def _calculate_from_close(self, close: pd.Series) -> pd.DataFrame:
        """Calculate Bollinger Bands from close prices"""
        sma = close.rolling(window=self.length).mean()
        std = close.rolling(window=self.length).std()

        upper = sma + self.std * std
        lower = sma - self.std * std

        result = pd.DataFrame({
            f'BBU_{self.length}_{self.std}_{self.std}': upper,
            f'BBM_{self.length}_{self.std}_{self.std}': sma,
            f'BBL_{self.length}_{self.std}_{self.std}': lower,
            f'BBB_{self.length}_{self.std}_{self.std}': (upper - lower) / sma * 100,
            f'BBP_{self.length}_{self.std}_{self.std}': (close - lower) / (upper - lower)
        })
        return result

    def get_output_columns(self) -> list:
        return [
            f'BBU_{self.length}_{self.std}_{self.std}',
            f'BBM_{self.length}_{self.std}_{self.std}',
            f'BBL_{self.length}_{self.std}_{self.std}',
            f'BBB_{self.length}_{self.std}_{self.std}',
            f'BBP_{self.length}_{self.std}_{self.std}'
        ]

    def validate_params(self) -> bool:
        return 'length' in self.params and 'std' in self.params


class SuperTrendIndicator(OHLCBasedIndicator):
    """SuperTrend"""

    def __init__(self, params: dict = None):
        super().__init__("supertrend", params)
        self.length = self.params.get('length', 10)
        self.multiplier = self.params.get('multiplier', 3.0)

    def _calculate_from_ohlc(self, open_p, high, low, close) -> pd.DataFrame:
        """Calculate SuperTrend from OHLC"""
        # ATR calculation
        tr1 = high - low
        tr2 = np.abs(high - close.shift(1))
        tr3 = np.abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=self.length).mean()

        # Basic bands
        hl2 = (high + low) / 2
        upper_band = hl2 + self.multiplier * atr
        lower_band = hl2 - self.multiplier * atr

        # Final bands
        final_upper = pd.Series(index=upper_band.index, dtype=float)
        final_lower = pd.Series(index=lower_band.index, dtype=float)
        trend = pd.Series(index=upper_band.index, dtype=int)

        for i in range(len(upper_band)):
            if i == 0:
                final_upper.iloc[i] = upper_band.iloc[i]
                final_lower.iloc[i] = lower_band.iloc[i]
                trend.iloc[i] = 1 if close.iloc[i] > final_upper.iloc[i] else -1
            else:
                # Upper band
                if upper_band.iloc[i] < final_upper.iloc[i-1] or close.iloc[i-1] > final_upper.iloc[i-1]:
                    final_upper.iloc[i] = upper_band.iloc[i]
                else:
                    final_upper.iloc[i] = final_upper.iloc[i-1]

                # Lower band
                if lower_band.iloc[i] > final_lower.iloc[i-1] or close.iloc[i-1] < final_lower.iloc[i-1]:
                    final_lower.iloc[i] = lower_band.iloc[i]
                else:
                    final_lower.iloc[i] = final_lower.iloc[i-1]

                # Trend
                if close.iloc[i] > final_upper.iloc[i]:
                    trend.iloc[i] = 1
                elif close.iloc[i] < final_lower.iloc[i]:
                    trend.iloc[i] = -1
                else:
                    trend.iloc[i] = trend.iloc[i-1]

        supertrend = pd.Series(np.where(trend == 1, final_lower, final_upper))

        result = pd.DataFrame({
            f'SUPERT_{self.length}_{self.multiplier}': supertrend,
            f'SUPERTd_{self.length}_{self.multiplier}': trend
        })
        return result

    def get_output_columns(self) -> list:
        return [
            f'SUPERT_{self.length}_{self.multiplier}',
            f'SUPERTd_{self.length}_{self.multiplier}'
        ]

    def validate_params(self) -> bool:
        return 'length' in self.params and 'multiplier' in self.params