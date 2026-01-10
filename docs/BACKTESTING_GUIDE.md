# Backtesting Guide

This guide details how to configure and run backtests in **Trado**, switch data sources, and manage symbol mappings.

## 1. Backtesting Architecture

The backtesting system is composed of three main components:
1.  **Playback Engine**: Simulates the passage of time by feeding historical data (Candles/Ticks) to the system.
2.  **Backtest Engine**: The conductor. It receives data from Playback, passes it to the Strategy, and handles Signals.
3.  **Execution Simulator**: Acts as a virtual broker. It fills orders based on simulated market conditions (latency, slippage).

## 2. Configuration & Running

Backtests are typically run via dedicated scripts (e.g., `run_backtest_nifty200.py`).

### Basic Setup
```python
# run_backtest_example.py

# 1. Select Data Provider
from data_layer.dhan_data_provider import DhanDataProvider
# or YFinanceDataProvider, etc.

# 2. Configure Period and Symbols
start_date = datetime(2023, 1, 1)
end_date = datetime(2023, 12, 31)
symbols = ["RELIANCE", "TCS"]

# 3. Initialize Engines
provider = DhanDataProvider() # or adapter logic
playback = PlaybackEngine(provider, symbols, start_date, end_date, interval="5m")
analytics = AnalyticsEngine(event_bus)

engine = BacktestEngine(
    playback_engine=playback,
    execution_simulator=ExecutionSimulator(),
    strategy_class=MyStrategy,
    strategy_config=config,
    event_bus=event_bus
)

engine.start()
```

## 3. Switching Data Sources

Trado supports pluggable data sources. The `PlaybackEngine` expects an adapter that can fetch historical data.

### A. Using YFinance (Default)
Best for US/Global stocks or general testing.
```python
from data_layer.historical_data_provider import YFinanceDataProvider

provider = YFinanceDataProvider()
# PlaybackEngine will use this to call yfinance API
```

### B. Using Dhan (Indian Equities)
The `DhanBacktestAdapter` bridges the Playback Engine with Dhan's API (or local CSV dumps).
```python
from data_layer.dhan_data_provider import DhanDataProvider
from data_layer.dhan_backtest_adapter import DhanBacktestAdapter

dhan_client = DhanDataProvider()
adapter = DhanBacktestAdapter(dhan_client)
```

**Note:** The adapter logic typically handles:
*   Fetching historical DataFrames.
*   Normalizing columns to standard `CallData` format (`timestamp`, `open`, `high`, `low`, `close`, `volume`).

### C. Custom CSV Source
To use your own data, implement a simple adapter:

```python
class CSVDataProvider:
    def get_historical_candles(self, symbol, start, end, interval):
        df = pd.read_csv(f"data/{symbol}.csv")
        # Ensure 'timestamp' column is datetime
        return [CandleData(...) for row in df]
```

## 4. Symbol Mapping

Different providers use different symbol formats (e.g., `NSE:RELIANCE-EQ` vs `RELIANCE.NS` vs `RELIANCE`).

### Handling Mappings
It is best to maintain a `config/symbol_map.json` or handling mapping in your adapter.

**Example: Dhan Adapter Logic**
The `DhanBacktestAdapter` often needs to resolve a generic symbol name ("RELIANCE") to a specific Security ID for the API.

*   **Config File**: `config/api-scrip-master.csv` (provided by Dhan).
*   **Resolution Strategy**:
    1.  User requests `RELIANCE`.
    2.  Adapter scans CSV for `RELIANCE` in `NSE` `EQ` segment.
    3.  Finds `security_id: 13332`.
    4.  Fetches data for `13332`.

### Manual Mapping (Optional)
If automatic resolution fails, you can pass explicit mapping:
```python
symbol_map = {
    "NIFTY": "13",       # Index ID
    "BANKNIFTY": "25"
}
```

## 5. Execution Simulation Settings

You can tune the realism of the backtest by configuring the `ExecutionSimulator`.

```python
from backtester.execution_simulator import ExecutionConfig

exec_config = ExecutionConfig(
    slippage_bps=5.0,        # 5 basis points slippage
    commission_bps=2.0,      # Brokerage
    latency_ms=200,          # Network delay simulation
    min_fill_rate=0.95       # 95% fill probability on limit orders
)

simulator = ExecutionSimulator(config=exec_config)
```

## 6. Reports & Analytics

Backtest results are automatically:
1.  **Stored in Memory**: Access via `analytics.get_metrics()`.
2.  **Exported to Markdown**: `BacktestReporter` generates detailed files in `backtest_reports/`.

**Metrics Explained:**
*   **CAGR**: Compound Annual Growth Rate.
*   **Sharpe**: Risk-adjusted return. Is the return worth the volatility?
*   **Max Drawdown**: Deepest peak-to-valley decline.
*   **Win Rate**: Percentage of profitable trades.
*   **Profit Factor**: Gross Profit / Gross Loss.

## 7. Troubleshooting

*   **No Data Loaded**: Check if the start/end dates cover trading days (weekends/holidays). Check Symbol mapping.
*   **Zero Trades**: Check strategy logic `on_candle`. Verify if `indicators` are being calculated (config match).
*   **Lookahead Bias**: The `PlaybackEngine` feeds candles sequentially. Ensure your strategy doesn't calculate indicators on the *entire* dataframe at once improperly (Trado's `IndicatorCalculator` handles this safely for standard indicators).
