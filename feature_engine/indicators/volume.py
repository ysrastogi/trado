"""
Volume-based indicators
"""

import pandas as pd
from .base import OHLCVBasedIndicator


class OBVIndicator(OHLCVBasedIndicator):
    """On Balance Volume"""

    def __init__(self, params: dict = None):
        super().__init__("obv", params)
        # OBV typically doesn't need parameters, but we can add smoothing if needed
        self.length = self.params.get('length', None)

    def _calculate_from_ohlcv(self, open_p, high, low, close, volume) -> pd.Series:
        """Calculate OBV from OHLCV"""
        obv = pd.Series(0.0, index=close.index)

        for i in range(1, len(close)):
            if close.iloc[i] > close.iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
            elif close.iloc[i] < close.iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]

        # Apply smoothing if length is specified
        if self.length:
            obv = obv.rolling(window=self.length).mean()

        return obv

    def get_output_columns(self) -> list:
        suffix = f"_{self.length}" if self.length else ""
        return [f"OBV{suffix}"]

    def validate_params(self) -> bool:
        # Length is optional for OBV
        return True