"""
Technical Indicator Calculator
Calculates technical indicators from candle data using modular indicator classes
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Any
import logging
from feature_engine.models import FeatureConfig, DEFAULT_FEATURE_CONFIG
from feature_engine.indicators import IndicatorRegistry

logger = logging.getLogger(__name__)


class IndicatorCalculator:
    """Calculate technical indicators from candle data"""
    
    def __init__(self, config: Optional[FeatureConfig] = None):
        """Initialize the calculator"""
        self.config = config or DEFAULT_FEATURE_CONFIG
        self.registry = IndicatorRegistry()
    
    def calculate_indicators(self, candles: list) -> Dict[str, list]:
        """
        Calculate configured technical indicators from candles
        Supports multi-timeframe calculation if configured
        
        Args:
            candles: List of CandleData objects
            
        Returns:
            Dictionary of indicator names to value lists (aligned to input candles)
        """
        if not candles or len(candles) < 2:
            logger.warning(f"Not enough candles for indicator calculation: {len(candles)}")
            return {}
        
        try:
            # Convert to DataFrame
            df = self._candles_to_dataframe(candles)
            
            # Base indicators
            base_indicators_df = self._calculate_with_modular_indicators(df)
            
            # Multi-timeframe indicators
            if self.config.timeframes:
                for tf in self.config.timeframes:
                    try:
                        # Resample
                        resampled_df = self._resample_dataframe(df, tf)
                        
                        # If resampled has fewer rows, it's a higher timeframe
                        if len(resampled_df) < len(df):
                            tf_indicators_df = self._calculate_with_modular_indicators(resampled_df)
                            
                            # Rename columns with prefix
                            tf_indicators_df.columns = [f"{tf}_{col}" for col in tf_indicators_df.columns]
                            
                            # Align back to base index (forward fill)
                            aligned_df = tf_indicators_df.reindex(df.index, method='ffill')
                            
                            # Join with base results
                            base_indicators_df = base_indicators_df.join(aligned_df)
                            
                    except Exception as tf_e:
                        logger.warning(f"Error calculating timeframe {tf}: {tf_e}")
            
            # Convert to dictionary
            indicators = {}
            for col in base_indicators_df.columns:
                indicators[col] = base_indicators_df[col].fillna(0).tolist()
                
            return indicators
                
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}", exc_info=True)
            return {}
    
    def _candles_to_dataframe(self, candles: list) -> pd.DataFrame:
        """Convert candle list to pandas DataFrame"""
        data = {
            'timestamp': [c.timestamp for c in candles],
            'open': [c.open for c in candles],
            'high': [c.high for c in candles],
            'low': [c.low for c in candles],
            'close': [c.close for c in candles],
            'volume': [c.volume if c.volume else 0 for c in candles]
        }
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        return df
        
    def _resample_dataframe(self, df: pd.DataFrame, interval: str) -> pd.DataFrame:
        """Resample dataframe to new interval"""
        # Map common intervals to pandas offset aliases
        rule = interval
        if interval.endswith('m'):
            rule = interval.replace('m', 'min')
        elif interval.endswith('h'):
            pass  # Pandas 2.2+ prefers lowercase 'h'
        elif interval.endswith('d'):
            rule = interval.replace('d', 'D')
            
        resampled = df.resample(rule).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        return resampled
    
    def _calculate_with_modular_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate indicators using modular indicator classes"""
        all_indicators_df = pd.DataFrame(index=df.index)
        
        try:
            for ind_config in self.config.indicators:
                name = ind_config.name.lower()
                params = ind_config.params
                
                # Create indicator instance using registry
                indicator = self.registry.create_indicator(name, params)
                
                if indicator:
                    try:
                        # Calculate the indicator
                        result_df = indicator.calculate(df)
                        
                        if not result_df.empty:
                            # Join with main dataframe
                            all_indicators_df = all_indicators_df.join(result_df)
                            logger.debug(f"Calculated {name} with {len(result_df.columns)} columns")
                        else:
                            logger.warning(f"Indicator {name} returned empty result")
                            
                    except Exception as ind_e:
                        logger.error(f"Failed to calculate {name}: {ind_e}")
                else:
                    logger.warning(f"Could not create indicator: {name}")
            
            logger.info(f"Calculated {len(all_indicators_df.columns)} indicator columns using modular indicators")
            
        except Exception as e:
            logger.error(f"Error in modular indicator calculation: {e}", exc_info=True)
        
        return all_indicators_df
    