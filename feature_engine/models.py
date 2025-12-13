"""
Data models for the feature engine
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union

@dataclass
class IndicatorConfig:
    """Configuration for a single indicator"""
    name: str
    params: Dict[str, Any] = field(default_factory=dict)
    columns: Optional[List[str]] = None  # Custom output column names

@dataclass
class FeatureConfig:
    """Global configuration for feature calculation"""
    indicators: List[IndicatorConfig]
    timeframes: List[str] = field(default_factory=lambda: ["1h"])
    
    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'FeatureConfig':
        """Create config from dictionary"""
        indicators = []
        for ind in config.get('indicators', []):
            if isinstance(ind, str):
                indicators.append(IndicatorConfig(name=ind))
            elif isinstance(ind, dict):
                indicators.append(IndicatorConfig(
                    name=ind['name'],
                    params=ind.get('params', {}),
                    columns=ind.get('columns')
                ))
        
        return cls(
            indicators=indicators,
            timeframes=config.get('timeframes', ["1h"])
        )

# Default configuration
DEFAULT_FEATURE_CONFIG = FeatureConfig(
    indicators=[
        IndicatorConfig(name="sma", params={"length": 20}),
        IndicatorConfig(name="sma", params={"length": 50}),
        IndicatorConfig(name="rsi", params={"length": 14}),
        IndicatorConfig(name="macd", params={"fast": 12, "slow": 26, "signal": 9}),
        IndicatorConfig(name="atr", params={"length": 14}),
        IndicatorConfig(name="bbands", params={"length": 20, "std": 2.0})
    ]
)
