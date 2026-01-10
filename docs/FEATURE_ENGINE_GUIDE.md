# Feature Engine Guide

The **Feature Engine** in Trado is a modular system designed to calculate technical indicators and features efficiently for both backtesting and live trading. 

It handles:
1.  **Calculation**: Computing indicators (SMA, RSI, MACD, etc.) from raw Candle data.
2.  **Multi-Timeframe Alignment**: Automatic resampling of data to higher timeframes (e.g., calculating Daily RSI on 5-minute data) and aligning it back to the base timeframe.
3.  **Standardization**: Providing a consistent API for all indicators.

## 🏗 Architecture

The system is built around three core components:

### 1. `IndicatorCalculator` (`feature_engine/indicator_calculator.py`)
This is the orchestration engine. It:
- Takes a list of `CandleData`.
- Converts them to a pandas DataFrame.
- Iterates through the config to calculate requested indicators.
- Handles resampling for multi-timeframe requests.
- Merges everything into a single dictionary of arrays.

### 2. `IndicatorRegistry` (`feature_engine/indicators/registry.py`)
A central registry that maps string names (e.g., `"rsi"`, `"sma"`) to their respective Python classes. This allows the system to be configuration-driven (you specify strings in JSON/YAML, and the registry finds the code).

### 3. `BaseIndicator` (`feature_engine/indicators/base.py`)
The abstract base class that all indicators must inherit. It ensures every indicator implements:
- `calculate(df)`: The logic.
- `validate_params()`: Parameter checking.
- `get_output_columns()`: Naming convention.

---

## ⚙️ Configuration

You typically configure the feature engine via a dictionary or JSON config passed to the `FeatureConfig` model.

### Structure
```python
{
    "indicators": [
        # Simple indicator with default params
        {"name": "rsi"},
        
        # Indicator with custom params and explicit name
        {
            "name": "sma", 
            "params": {"length": 50}, 
            "columns": ["SMA_50"] 
        },
        
        # Another instance of the same indicator
        {
            "name": "sma", 
            "params": {"length": 200}
        }
    ],
    "timeframes": ["15m", "1h"] # Higher timeframes to calculate concurrently
}
```

### Usage
```python
from feature_engine.models import FeatureConfig
from feature_engine.indicator_calculator import IndicatorCalculator

# 1. Define Config
config = FeatureConfig.from_dict({
    "indicators": [{"name": "rsi"}, {"name": "sma", "params": {"length": 20}}],
    "timeframes": ["1h"]
})

# 2. Initialize Calculator
calculator = IndicatorCalculator(config)

# 3. Calculate
# 'candles' is a list of CandleData objects
results = calculator.calculate_indicators(candles)

# results['rsi'] -> [30.1, 32.5, ...]
# results['1h_rsi'] -> [55.2, 55.2, ...] (Aligned Daily RSI)
```

---

## 🛠 Adding New Indicators

To add a new indicator, you need to create a class and register it.

### Step 1: Create the Indicator Class
Create a new file in `feature_engine/indicators/` (e.g., `my_indicator.py`) or add to an existing category file.

Inherit from `BaseIndicator` (or `PriceBasedIndicator` if you only need the 'close' price).

```python
import pandas as pd
from .base import PriceBasedIndicator

class MyCustomMA(PriceBasedIndicator):
    """My Custom Moving Average"""

    def __init__(self, params: dict = None):
        # "my_ma" is the default name
        super().__init__("my_ma", params)
        # 1. Parse Parameters
        self.length = self.params.get('length', 14)

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        # 2. Implement Logic
        # df contains: open, high, low, close, volume (indexed by timestamp)
        
        # Example logic
        result = df['close'].rolling(window=self.length).mean() + 10
        
        # 3. Format Result
        result.name = self.get_output_columns()[0]
        return result.to_frame()

    def get_output_columns(self) -> list:
        # Define the exact column name in the output
        return [f"MyMA_{self.length}"]

    def validate_params(self) -> bool:
        # Optional validation
        return self.params.get('length', 0) > 0
```

### Step 2: Register the Indicator
Two ways to register:

**Method A: Static Registration (Recommended)**
Add it to the `_indicators` dictionary in `feature_engine/indicators/registry.py`.
```python
# feature_engine/indicators/registry.py
from .my_indicator import MyCustomMA

class IndicatorRegistry:
    _indicators = {
        # ... existing ...
        'my_ma': MyCustomMA, 
    }
```

**Method B: Runtime Registration**
Use the `register_indicator` class method at startup.
```python
from feature_engine.indicators import IndicatorRegistry
from my_custom_indicator import MyCustomMA

IndicatorRegistry.register_indicator("my_ma", MyCustomMA)
```

---

## 🔄 Multi-Timeframe Logic

Trado automatically handles "HTF" (Higher Timeframe) indicators.

**How it works:**
1.  **Resampling**: The base candles (e.g., 1-minute) are resampled to the target timeframe (e.g., 1-hour) using standard OHLC aggregation.
2.  **Calculation**: The indicators are calculated on the 1-hour DataFrame.
3.  **Forward Fill**: The 1-hour results are re-indexed back to the 1-minute timestamps using `ffill`. This ensures no lookahead bias (you only see the 1H value once the hour has closed, or the latest available value).
4.  **Naming**: The columns are prefixed with the timeframe (e.g., `1h_rsi`, `1h_sma_20`).

**Example:**
If you request `rsi` and `timeframes=["1h"]`:
- You get `rsi` (calculated on base timeframe).
- You get `1h_rsi` (calculated on hourly candles, aligned to base).

---

## 📚 Available Indicators

| Category | Key | Class |
|qs|---|---|
| **Moving Averages** | `sma`, `ema`, `wma`, `hma`, `tema` | Standard, Exponential, Weighted, Hull, Triple EMA |
| **Momentum** | `rsi`, `macd`, `stoch`, `willr`, `roc`, `cci` | RSI, MACD, Stochastic, Williams %R, Rate of Change, CCI |
| **Vol/Trend** | `atr`, `adx`, `bbands`, `supertrend` | ATR, ADX, Bollinger Bands, SuperTrend |
| **Volume** | `obv`, `vwap`, `vol_sma` | On Balance Volume, VWAP, Volume SMA |
| **Channels** | `donchian` | Donchian Channels |
