"""
Indicator Registry - Central configuration for all indicators
"""

from typing import Dict, Type, Any, Optional
from .base import BaseIndicator
from .moving_averages import SMAIndicator, EMAIndicator, WMAIndicator, HMAIndicator, TEMAIndicator
from .momentum import RSIIndicator, MACDIndicator, StochasticIndicator, WilliamsRIndicator, ROCIndicator, CCIIndicator
from .volatility import ATRIndicator, ADXIndicator, BollingerBandsIndicator, SuperTrendIndicator
from .volume import OBVIndicator, VWAPIndicator, VolumeSMAIndicator
import logging

logger = logging.getLogger(__name__)


class IndicatorRegistry:
    """Registry for all available indicators"""

    # Registry mapping indicator names to their classes
    _indicators: Dict[str, Type[BaseIndicator]] = {
        # Moving Averages
        'sma': SMAIndicator,
        'ema': EMAIndicator,
        'wma': WMAIndicator,
        'hma': HMAIndicator,
        'tema': TEMAIndicator,

        # Momentum/Oscillators
        'rsi': RSIIndicator,
        'macd': MACDIndicator,
        'stoch': StochasticIndicator,
        'willr': WilliamsRIndicator,
        'roc': ROCIndicator,
        'cci': CCIIndicator,

        # Volatility/Trend
        'atr': ATRIndicator,
        'adx': ADXIndicator,
        'bbands': BollingerBandsIndicator,
        'supertrend': SuperTrendIndicator,

        # Volume
        'obv': OBVIndicator,
        'vwap': VWAPIndicator,
        'vol_sma': VolumeSMAIndicator,
    }

    @classmethod
    def get_indicator_class(cls, name: str) -> Optional[Type[BaseIndicator]]:
        """Get indicator class by name"""
        return cls._indicators.get(name.lower())

    @classmethod
    def create_indicator(cls, name: str, params: Optional[Dict[str, Any]] = None) -> Optional[BaseIndicator]:
        """Create an indicator instance"""
        indicator_class = cls.get_indicator_class(name)
        if indicator_class:
            try:
                indicator = indicator_class(params)
                if indicator.validate_params():
                    return indicator
                else:
                    logger.error(f"Invalid parameters for indicator {name}: {params}")
                    return None
            except Exception as e:
                logger.error(f"Error creating indicator {name}: {e}")
                return None
        else:
            logger.warning(f"Unknown indicator: {name}")
            return None

    @classmethod
    def get_available_indicators(cls) -> list:
        """Get list of all available indicator names"""
        return list(cls._indicators.keys())

    @classmethod
    def register_indicator(cls, name: str, indicator_class: Type[BaseIndicator]) -> None:
        """Register a new indicator"""
        cls._indicators[name.lower()] = indicator_class
        logger.info(f"Registered new indicator: {name}")

    @classmethod
    def get_indicator_info(cls, name: str) -> Optional[Dict[str, Any]]:
        """Get information about an indicator"""
        indicator_class = cls.get_indicator_class(name)
        if indicator_class:
            # Create a dummy instance to get default params
            dummy = indicator_class()
            return {
                'name': name,
                'class': indicator_class.__name__,
                'default_params': dummy.params,
                'output_columns': dummy.get_output_columns()
            }
        return None