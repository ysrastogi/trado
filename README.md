# Trado 📈

**Trado** is a sophisticated, modular algorithmic trading engine built for the **Deriv API**. It features a professional interactive terminal, a robust strategy execution engine, and a flexible backtesting framework. Designed for developers and quants, Trado emphasizes modularity, type safety, and extensibility.

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

### Launching the Terminal

Start the interactive trading environment:

```bash
python main.py
```

### Terminal Commands

Once inside the terminal, use the following commands:

- **/help**: Show available commands.
- **/status**: Display connection status and account balance.
- **/buy [symbol] [amount]**: Execute a buy order.
- **/sell [symbol] [amount]**: Execute a sell order.
- **/chart**: View real-time market data.
- **/strategy**: Manage active strategies.
- **/risk**: View or configure risk parameters.
- **/exit**: Close the application.

## 🧪 Development

### Running Tests

Trado uses `pytest` for testing. Run the full suite:

```bash
python -m pytest tests/ -v
```

To run specific tests for the feature engine:

```bash
python -m pytest tests/test_feature_engine.py -v
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

## ⚠️ Disclaimer

**Trading involves significant risk.** This software is for educational and development purposes only. The authors are not responsible for any financial losses incurred while using this software. Always test strategies thoroughly in a demo environment before trading with real capital.
