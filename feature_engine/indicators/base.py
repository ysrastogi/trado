"""
Base classes and interfaces for technical indicators
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class BaseIndicator(ABC):
    """Abstract base class for all technical indicators"""

    def __init__(self, name: str, params: Optional[Dict[str, Any]] = None):
        self.name = name
        self.params = params or {}

    @abstractmethod
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate the indicator from OHLCV data

        Args:
            df: DataFrame with columns: open, high, low, close, volume

        Returns:
            DataFrame with indicator values (can have multiple columns)
        """
        pass

    def get_output_columns(self) -> List[str]:
        """Return the names of output columns this indicator produces"""
        return [self.name]

    def validate_params(self) -> bool:
        """Validate that required parameters are present"""
        return True


class PriceBasedIndicator(BaseIndicator):
    """Base class for indicators that primarily use close price"""

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Default implementation using close price"""
        try:
            result = self._calculate_from_close(df['close'])
            if isinstance(result, pd.Series):
                result.name = self.get_output_columns()[0]
                return result.to_frame()
            elif isinstance(result, pd.DataFrame):
                return result
            else:
                return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error calculating {self.name}: {e}")
            return pd.DataFrame()


class OHLCBasedIndicator(BaseIndicator):
    """Base class for indicators that use open, high, low, close"""

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Default implementation using OHLC"""
        try:
            result = self._calculate_from_ohlc(df['open'], df['high'], df['low'], df['close'])
            if isinstance(result, pd.Series):
                result.name = self.get_output_columns()[0]
                return result.to_frame()
            elif isinstance(result, pd.DataFrame):
                return result
            else:
                return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error calculating {self.name}: {e}")
            return pd.DataFrame()


class OHLCVBasedIndicator(BaseIndicator):
    """Base class for indicators that use open, high, low, close, volume"""

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Default implementation using OHLCV"""
        try:
            result = self._calculate_from_ohlcv(df['open'], df['high'], df['low'], df['close'], df['volume'])
            if isinstance(result, pd.Series):
                result.name = self.get_output_columns()[0]
                return result.to_frame()
            elif isinstance(result, pd.DataFrame):
                return result
            else:
                return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error calculating {self.name}: {e}")
            return pd.DataFrame()