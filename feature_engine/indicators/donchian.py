"""
Donchian Channels Indicator
"""

import pandas as pd
from .base import BaseIndicator

class DonchianChannelsIndicator(BaseIndicator):
    """
    Donchian Channels
    Upper Band: Max High over N periods
    Lower Band: Min Low over N periods
    Middle Band: Average of Upper and Lower
    """

    def __init__(self, params: dict = None):
        super().__init__("donchian", params)
        self.length = self.params.get('length', 20)

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Donchian Channels
        """
        high = df['high']
        low = df['low']

        # Donchian Channel calculation
        # Note: Usually Donchian is High of previous N bars to avoid look-ahead bias if including current bar for breakout
        # But standard definition often includes current bar in the window.
        # For breakout strategies, we often check if Close > DonchianHigh(shifted).
        # Here we calculate the raw channel values for the window ending at current bar.
        
        upper = high.rolling(window=self.length).max()
        lower = low.rolling(window=self.length).min()
        mid = (upper + lower) / 2

        result = pd.DataFrame({
            f"DonchianHigh_{self.length}": upper,
            f"DonchianLow_{self.length}": lower,
            f"DonchianMid_{self.length}": mid
        }, index=df.index)

        return result

    def get_output_columns(self) -> list:
        return [
            f"DonchianHigh_{self.length}",
            f"DonchianLow_{self.length}",
            f"DonchianMid_{self.length}"
        ]

    def validate_params(self) -> bool:
        return 'length' in self.params and self.params['length'] > 0
