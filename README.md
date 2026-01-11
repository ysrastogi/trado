# Trado 📈

**Trado** is a modular algorithmic trading engine designed for high-performance backtesting, paper trading, and live execution.

Key architectural highlights include:
*   **Event-Driven & Vectorized Hybrid**: Combines the speed of vectorized backtesting with the realism of event-driven live execution.
*   **Centralized Analytics**: A dedicated analytics engine that observes trades across all environments (Backtest/Paper/Live) to provide real-time performance metrics like Sharpe Ratio, Drawdown, and MAE/MFE.
*   **Asset Agnostic**: Seamlessly switches between Synthetic Indices (Deriv) and Equities/F&O (Dhan, NSE/BSE).

<img width="6378" height="3218" alt="image" src="https://github.com/user-attachments/assets/04b1faa9-dc0d-4e88-a756-a18ac4481a49" />

## 🚀 Key Features

- **Interactive Terminal**: A rich CLI interface for manual trading, system monitoring, and real-time control.
- **Modular Feature Engine**: 
  - **Registry Pattern**: Easily extendable indicator system.
  - **Multi-Timeframe Support**: Calculate indicators across various timeframes automatically.
  - **Zero-Dependency Calculations**: Custom implementations of technical indicators (SMA, EMA, RSI, MACD, etc.) without heavy external TA libraries.
- **Deriv API Integration**: Full support for trading contracts (Call/Put, Digits, etc.) via WebSocket.
- **Strategy Engine**: Abstract base classes for implementing custom strategies with `on_tick`, `on_bar`, and `on_candle` hooks.
- **Backtesting**: Simulation engine to validate strategies against historical data before live deployment.
- **Risk Management**: Integrated risk checks for position sizing, stop-loss, and take-profit.
- **Data Layer**: Efficient market data streaming with optional Redis integration for high-throughput setups.

## � Documentation
- [Architecture Overview](docs/ARCHITECTURE_OVERVIEW.md): High-level design and component interactions.
- [Strategy Engine Guide](docs/STRATEGY_GUIDE.md): How to build strategies, use indicators, and integrate analytics.
- [Feature Engine Guide](docs/FEATURE_ENGINE_GUIDE.md): Architecture of indicators, creating new ones, and multi-timeframe logic.
- [Backtesting Guide](docs/BACKTESTING_GUIDE.md): Configuration, running simulations, and using different data sources.
- [Paper Trading Guide](docs/PAPER_TRADING_IMPLEMENTATION.md): Details on the paper trading system.
- [Quick Reference](docs/QUICK_REFERENCE.md): Cheat sheet for common tasks.

## 📂 Project Structure

```
trado/
├── terminal/           # Interactive CLI entry point and UI logic
├── broker/             # Deriv API client and trade execution
├── data_layer/         # Market data streaming (WebSocket/Redis)
├── feature_engine/     # Technical indicators and calculation logic
│   ├── indicators/     # Modular indicator implementations
│   └── calculator.py   # Main orchestration
├── strategy_engine/    # Base strategy classes and implementations
├── backtester/         # Historical simulation engine
├── config/             # Configuration files and settings
└── common/             # Shared data models (CandleData, SignalEvent)
```

## 🛠️ Getting Started

### Prerequisites

- **Python 3.12+**
- **Redis** (Optional, for advanced data streaming)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/ysrastogi/trado.git
    cd trado
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: If `requirements.txt` is missing, ensure you have `pandas`, `numpy`, `pydantic`, `pydantic-settings`, `websockets`, `pyyaml`, `python-dotenv` installed)*

4.  **Configuration:**
    Create a `.env` file in the root directory:
    ```env
    DERIV_AUTH_TOKEN=your_deriv_api_token
    REDIS_URL=redis://localhost:6379/0
    ```


## 🖥️ Usage

### 1. Interactive Terminal
The core terminal for manual trading and system monitoring:
```bash
python main.py
```
**Commands:** `/help`, `/status`, `/buy`, `/sell`, `/strategy`, `/risk`

### 2. Backtesting
Run simulations against historical data.

**Momentum Strategy on Nifty 200:**
```bash
python run_backtest_nifty200.py
```

**Single Stock (Interactive/Specific):**
```bash
python run_backtest_momentum.py
```
*Check `backtest_reports/` for generated Markdown reports.*

### 3. Paper Trading (Forward Testing)
Run strategies in live markets with simulated execution:
```bash
python run_paper_momentum.py
```
*Set `DERIV_AUTH_TOKEN` or `DHAN_ACCESS_TOKEN` in `.env` before running.*

### 4. Optimization
Run parameter optimization (Grid/Random Search):
```bash
python run_optimization.py
```


### Adding New Indicators

Trado uses a **Registry Pattern** for indicators. To add a new one:

1.  Create a new class in `feature_engine/indicators/` inheriting from `BaseIndicator`.
2.  Implement the `calculate()` method.
3.  Register it using the decorator:
    ```python
    @IndicatorRegistry.register("my_indicator")
    class MyIndicator(BaseIndicator):
        ...
    ```
4.  It will automatically be available in the `IndicatorCalculator`.
