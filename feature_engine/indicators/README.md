# Feature Engine - Modular Indicator System

This package provides a modular, configurable system for calculating technical indicators.

## Architecture

- **Base Classes**: Abstract base classes for different indicator types
- **Indicator Classes**: Individual implementations for each indicator
- **Registry**: Central registry for managing all available indicators
- **Calculator**: Main calculator that orchestrates indicator computation

## Supported Indicators

### Moving Averages
- `sma`: Simple Moving Average
- `ema`: Exponential Moving Average
- `wma`: Weighted Moving Average
- `hma`: Hull Moving Average
- `tema`: Triple Exponential Moving Average

### Momentum/Oscillators
- `rsi`: Relative Strength Index
- `macd`: Moving Average Convergence Divergence
- `stoch`: Stochastic Oscillator
- `willr`: Williams %R
- `roc`: Rate of Change
- `cci`: Commodity Channel Index

### Volatility/Trend
- `atr`: Average True Range
- `adx`: Average Directional Index
- `bbands`: Bollinger Bands
- `supertrend`: SuperTrend

### Volume
- `obv`: On Balance Volume

## Usage

### Basic Usage

```python
from feature_engine.indicator_calculator import IndicatorCalculator

# Use default configuration
calculator = IndicatorCalculator()
indicators = calculator.calculate_indicators(candles)
```

### Custom Configuration

```python
from feature_engine.models import FeatureConfig, IndicatorConfig

config = FeatureConfig(
    indicators=[
        IndicatorConfig(name="sma", params={"length": 20}),
        IndicatorConfig(name="rsi", params={"length": 14})
    ],
    timeframes=["4h"]  # Multi-timeframe support
)

calculator = IndicatorCalculator(config=config)
indicators = calculator.calculate_indicators(candles)
```

### Multi-Timeframe Calculation

The system supports calculating indicators on multiple timeframes automatically:

```python
config = FeatureConfig(
    indicators=[IndicatorConfig(name="sma", params={"length": 20})],
    timeframes=["1h", "4h", "1d"]  # Base + additional timeframes
)
```

### Adding Custom Indicators

```python
from feature_engine.indicators.base import PriceBasedIndicator
from feature_engine.indicators import IndicatorRegistry

class MyCustomIndicator(PriceBasedIndicator):
    def __init__(self, params=None):
        super().__init__("my_indicator", params)

    def _calculate_from_close(self, close):
        return close.rolling(window=10).mean()  # Your logic

# Register the indicator
registry = IndicatorRegistry()
registry.register_indicator("my_indicator", MyCustomIndicator)
```

## Configuration File

You can also configure indicators via YAML:

```yaml
indicators:
  - name: sma
    params:
      length: 20
  - name: rsi
    params:
      length: 14

timeframes:
  - "1h"
  - "4h"
```

## Extending the System

### Creating New Indicator Types

1. Choose the appropriate base class:
   - `PriceBasedIndicator`: For indicators using only close price
   - `OHLCBasedIndicator`: For indicators using Open, High, Low, Close
   - `OHLCVBasedIndicator`: For indicators using OHLC + Volume

2. Implement the calculation method:
   - `_calculate_from_close()` for price-based
   - `_calculate_from_ohlc()` for OHLC-based
   - `_calculate_from_ohlcv()` for OHLCV-based

3. Register your indicator in the registry

### Indicator Parameters

All indicators accept a `params` dictionary. Required parameters should be validated in `validate_params()`.

## Benefits

- **Modular**: Each indicator is self-contained
- **Extensible**: Easy to add new indicators
- **Configurable**: Runtime configuration of indicators and parameters
- **Multi-timeframe**: Automatic calculation across timeframes
- **Type-safe**: Proper base classes for different data requirements