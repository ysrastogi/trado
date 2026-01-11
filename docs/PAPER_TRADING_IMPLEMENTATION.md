# Paper Trading Implementation Guide

## Overview
This document details the implementation of the Paper Trading system for Trado, enabling strategy testing without real capital.

## Components Implemented

### 1. Order Execution Service Architecture
- **`IOrderExecutionService`**: Interface defining standard execution methods (`execute_order`, `get_active_positions`, etc.).
- **`PaperTradingService`**: In-memory simulation of order execution.
  - Simulates fills based on current market price.
  - Persists state (balance, positions, orders) to `data_cache/paper_trading_state.json`.
- **`LiveExecutionService`**: Wrapper for the real `TradingClient` (Deriv API).
- **`ExecutionServiceFactory`**: Factory to instantiate the correct service based on configuration.

### 2. Broker Adapter
- **`IBrokerAdapter`**: Interface to decouple strategy logic from specific broker APIs.
- **`DerivBrokerAdapter`**: Implementation for Deriv.

### 3. Data Layer Enhancements
- **`DerivMarketStream`**: Updated to expose public methods (`get_next_request_id`, `send_message`) for use by the `TradingClient`.
- **`DerivMessageHandler`**: Added a `latest_ticks` cache to allow the Paper Service to look up the current price when executing market orders.

### 4. Runner Script
- **`run_paper_momentum.py`**: A dedicated script to run the `MomentumStrategy` on `cryBTCUSD` in paper trading mode.

## How to Run

1. **Ensure Configuration**:
   - Check `config/tradding_config.yaml` (or the script defaults).
   - Ensure `.env` has valid Deriv credentials (even for paper trading, we need a live data stream).

2. **Execute the Script**:
   ```bash
   python run_paper_momentum.py
   ```

3. **Monitor**:
   - The script logs to the console.
   - Watch for `Paper executing order` and `Execution result` logs.
   - Check `data_cache/paper_trading_state.json` for account state.

## Verification
- The system successfully connects to Deriv WebSocket.
- Authenticates using the provided token.
- Subscribes to `cryBTCUSD` ticks and candles.
- The `PaperTradingService` is active and ready to process signals from the `MomentumStrategy`.

## Future Improvements
- **Signal Metadata**: Update `SignalEvent` to carry trade parameters like `duration` and `stake` so `LiveTradingEngine` doesn't need to hardcode them.
- **Advanced Order Types**: Implement Limit/Stop orders in `PaperTradingService` (currently only Market execution is simulated).
