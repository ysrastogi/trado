# Strategy Development Guide

This guide explains how to build, test, and integrate trading strategies in **Trado**.

## 1. Architecture Overview

Strategies in Trado are classes that inherit from `BaseStrategy`. They are environment-agnostic, meaning the same code runs in **Backtesting**, **Paper Trading**, and **Live Trading**.

The Strategy Engine works on an **Event-Driven** model:
1.  **Input**: Receives `on_candle` (or `on_tick`) events with market data and pre-calculated features.
2.  **Processing**: Updates internal state, history buffers, and checks logic rules.
3.  **Output**: Returns a `SignalEvent` (BUY/SELL) if a decision is made, or `None`.

## 2. Creating a Strategy

### Step 1: Subclass `BaseStrategy`

Create a new file in `strategy_engine/` (e.g., `my_strategy.py`).

```python
from typing import Dict, Optional, Deque
from collections import deque, defaultdict
from strategy_engine.base_strategy import BaseStrategy
from common.models import SignalEvent, CandleData

class MyStrategy(BaseStrategy):
    def __init__(self, config: Dict = None):
        super().__init__(config or {})
        
        # 1. Load Parameters
        self.fast_period = self.config.get('fast_period', 10)
        self.slow_period = self.config.get('slow_period', 20)
        
        # 2. State Management (History Buffers)
        # Use deque for efficient rolling windows
        self.history: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=50))
        
        # 3. Trading State
        self.in_position = False
        self.stop_loss = 0.0

    def setup_indicators(self):
        # Indicators are configured in FeatureConfig, not here.
        # This method is for internal initializations if needed.
        pass
```

### Step 2: Implement `on_candle`

This is the main logic loop.

```python
    def on_candle(self, candle: CandleData, features: Optional[Dict[str, float]] = None) -> Optional[SignalEvent]:
        if not features:
            return None
            
        # 1. Update History
        for k, v in features.items():
            self.history[k].append(v)
            
        # 2. Ensure enough data
        if len(self.history['SMA_fast']) < 1:
            return None
            
        # 3. Entry/Exit Logic
        if self.in_position:
            return self._check_exit(candle, features)
        else:
            return self._check_entry(candle, features)
```

## 3. Working with Indicators

Trado separates **Calculation** from **Decision**. You do *not* calculate indicators (like SMA/RSI) inside the strategy class usually. Instead:

1.  **Define Requirement**: You define what indicators you need in the configuration (e.g., in `run_backtest_*.py`).
    ```python
    # In configuration
    "features": {
        "indicators": [
            {"name": "sma", "params": {"length": 10}, "output_name": "SMA_fast"},
            {"name": "sma", "params": {"length": 20}, "output_name": "SMA_slow"}
        ],
        "timeframes": ["15m"] # Optional HTF
    }
    ```

2.  **Consume in Strategy**: The `features` dictionary in `on_candle` will strictly contain these keys/aliases.
    ```python
    # Inside Strategy
    fast_ma = features.get('SMA_fast', 0)
    slow_ma = features.get('SMA_slow', 0)
    ```

## 4. Integrating Analytics

The Analytics Engine tracks performance automatically, but strategies can enrich this data by providing context details in the `SignalEvent`.

### A. Tracking Metrics
Provide custom metrics in the `indicators` field of the `SignalEvent`. These are persisted to the `TradeRecord` and accessible by `AnalyticsEngine`.

**Example: Tracking MAE/MFE and Ignition Time**

```python
    def _check_entry(self, candle, features):
        # ... logic ...
        
        # Track specific state
        self.last_ignition_time = candle.timestamp
        self.entry_price = candle.close
        
        return SignalEvent(
            ...,
            indicators={
                'price': candle.close,
                'atr': features.get('atr'),
                'time_since_last_signal': (datetime.now() - self.last_event).seconds
            }
        )

    def _check_exit(self, candle, features):
        # Calculate MAE/MFE manually (or rely on TradeTracker if standard)
        # Usually, Strategy tracks "internal" view of MAE/MFE for logic
        mae = self.entry_price - self.lowest_price_seen
        
        return SignalEvent(
            ...,
            signal_type="SELL",
            indicators={
                'price': candle.close,
                'mae_observed': mae,
                'max_r_multiple': self.max_r_reached
            }
        )
```

### B. Signals vs. Trades
*   **Signal**: "I want to buy/sell now".
*   **Trade**: The execution result.
The Analytics Engine joins these. Your strategy focuses on generating high-quality signals with rich metadata (reasons, confidence, indicator snapshots).

## 5. Risk Management

You can implement risk logic directly or rely on global standard checks.

**Internal Risk (Recommended):**
Manage stops/targets within the strategy state to ensure logic consistency (e.g., Trailing Stops using `ATR`).

```python
    def _check_exit(self, candle, features):
        # Trailing Stop Example
        atr = features['ATR_14']
        new_stop = candle.close - (1.5 * atr)
        
        if new_stop > self.stop_loss:
            self.stop_loss = new_stop
            
        if candle.low <= self.stop_loss:
            return SignalEvent(..., reason="Trailing Stop", ...)
```

## 6. Full Example Checklist

When defining `MyStrategy.py`:
1.  [ ] Inherit `BaseStrategy`.
2.  [ ] Initialize `history` buffers in `__init__`.
3.  [ ] Implement `on_candle`.
4.  [ ] **Update History** at the start of `on_candle`.
5.  [ ] Separate `_check_entry` and `_check_exit`.
6.  [ ] Return `SignalEvent` with `indicators={}` populated for analytics.
7.  [ ] Add it to `strategy_engine/__init__.py` or simpler, just import it in your runner script.
