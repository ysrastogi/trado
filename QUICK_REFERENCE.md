# Quick Reference: Detailed Trades Report API

## Core Classes

### TradeRecord
```python
from common.models import TradeRecord

# Access trade details
trade.entry_price       # Entry execution price
trade.exit_price        # Exit execution price
trade.entry_quantity    # Quantity entered
trade.net_pnl           # Profit/loss after costs
trade.pnl_pct           # Return percentage
trade.duration_seconds  # Trade duration in seconds
trade.holding_period    # Human-readable duration (e.g., "2h 15m")

# Check trade status
trade.is_winner()       # True if profitable
trade.is_loser()        # True if loss
trade.is_breakeven()    # True if near-zero P&L
trade.is_open()         # True if still open

# Access risk metrics
trade.max_adverse_excursion_pct    # Worst price movement against position
trade.max_favorable_excursion_pct  # Best price movement in favor
trade.max_price                     # Highest price during trade
trade.min_price                     # Lowest price during trade

# Access execution details
trade.entry_slippage_bps       # Entry slippage in basis points
trade.exit_slippage_bps        # Exit slippage in basis points
trade.total_costs              # Total cost = slippage + commission + impact
trade.entry_reason             # Why trade was entered
trade.exit_reason              # Why trade was exited (ExitReason enum)

# Access signals
trade.entry_signal       # SignalEvent that triggered entry
trade.exit_signal        # SignalEvent that triggered exit
trade.entry_confidence   # Confidence level (0-1)
```

### TradeTracker
```python
from backtester.trade_tracker import TradeTracker

tracker = TradeTracker()

# Entry phase
trade_id = tracker.on_entry_signal(signal)
tracker.on_entry_execution(trade_id, execution, is_long=True)

# Monitoring phase (call each candle for open position)
tracker.on_price_update(trade_id, candle.close)

# Exit phase
tracker.on_exit_signal(signal, trade_id)
tracker.on_exit_execution(trade_id, execution, ExitReason.SIGNAL_REVERSAL)

# Retrieval
all_trades = tracker.get_all_trades()
open_trades = tracker.get_open_trades()
stats = tracker.get_trade_statistics()
```

### BacktestReporter
```python
from backtester.reporter import BacktestReporter

reporter = BacktestReporter(output_dir="./backtest_reports")

# Generate reports
markdown_path = reporter.generate_detailed_trades_report(trades, "MyStrategy")
csv_path = reporter.export_trades_to_csv(trades, "MyStrategy")
json_path = reporter.export_trades_to_json(trades, "MyStrategy")
```

## Exit Reasons

```python
from common.models import ExitReason

ExitReason.STOP_LOSS       # Stop loss triggered
ExitReason.TAKE_PROFIT     # Take profit hit
ExitReason.SIGNAL_REVERSAL # Strategy signal changed
ExitReason.MANUAL_EXIT     # Operator closed
ExitReason.TIMEOUT         # Held too long
ExitReason.LIQUIDATION     # Forced closure
```

## Strategy Integration

```python
from strategy_engine.base_strategy import BaseStrategy
from common.models import ExitReason

class MyStrategy(BaseStrategy):
    
    def on_candle(self, candle, features):
        # ... your logic ...
        
        # When exiting due to stop loss
        if self.position.pl_pct <= -self.stop_loss_pct:
            self.record_exit_reason(
                ExitReason.STOP_LOSS,
                f"SL at {self.position.pl_pct:.2%}"
            )
            self.on_stop_loss_hit(candle.close)
            return exit_signal
        
        # When exiting due to signal reversal
        if signal_reversal_detected:
            self.record_exit_reason(
                ExitReason.SIGNAL_REVERSAL,
                "RSI crossed below 50"
            )
            self.on_signal_reversal(candle.close, "SELL")
            return exit_signal
```

## Analysis Examples

### Winners vs Losers
```python
winners = [t for t in trades if t.is_winner()]
losers = [t for t in trades if t.is_loser()]

print(f"Win Rate: {len(winners)/len(trades)*100:.1f}%")
print(f"Avg Winner: ${sum(t.net_pnl for t in winners)/len(winners):.2f}")
print(f"Avg Loser: ${sum(t.net_pnl for t in losers)/len(losers):.2f}")
```

### By Symbol
```python
by_symbol = {}
for trade in trades:
    if trade.symbol not in by_symbol:
        by_symbol[trade.symbol] = []
    by_symbol[trade.symbol].append(trade)

for symbol, trades_list in by_symbol.items():
    pnl = sum(t.net_pnl for t in trades_list)
    win_rate = len([t for t in trades_list if t.is_winner()]) / len(trades_list)
    print(f"{symbol}: {pnl:.2f} ({win_rate*100:.1f}%)")
```

### By Exit Reason
```python
from common.models import ExitReason

by_reason = {}
for trade in trades:
    reason = trade.exit_reason.value if trade.exit_reason else "Unknown"
    if reason not in by_reason:
        by_reason[reason] = []
    by_reason[reason].append(trade)

for reason, trades_list in by_reason.items():
    win_rate = len([t for t in trades_list if t.is_winner()]) / len(trades_list)
    print(f"{reason}: {win_rate*100:.1f}% win rate")
```

### Duration Analysis
```python
import numpy as np

short_term = [t for t in trades if (t.duration_seconds or 0) < 3600]
medium_term = [t for t in trades if 3600 <= (t.duration_seconds or 0) < 86400]
long_term = [t for t in trades if (t.duration_seconds or 0) >= 86400]

print(f"Short (<1h): {len(short_term)} trades, "
      f"${np.mean([t.net_pnl for t in short_term]):.2f} avg")
print(f"Medium (1-24h): {len(medium_term)} trades, "
      f"${np.mean([t.net_pnl for t in medium_term]):.2f} avg")
print(f"Long (>24h): {len(long_term)} trades, "
      f"${np.mean([t.net_pnl for t in long_term]):.2f} avg")
```

### MAE/MFE Analysis
```python
import numpy as np

maes = [abs(t.max_adverse_excursion_pct or 0) for t in trades]
mfes = [t.max_favorable_excursion_pct or 0 for t in trades]

print(f"Avg MAE: {np.mean(maes):.2f}%")
print(f"Avg MFE: {np.mean(mfes):.2f}%")
print(f"MFE/MAE Ratio: {np.mean(mfes)/np.mean(maes):.2f}")
```

### Slippage Impact
```python
total_gross = sum(t.gross_pnl for t in trades)
total_slippage = sum(t.entry_slippage_bps + t.exit_slippage_bps for t in trades)

print(f"Gross P&L: ${total_gross:.2f}")
print(f"Total Slippage (bps): {total_slippage:.2f}")
print(f"Impact: {(total_slippage / total_gross) * 100:.1f}% of profit" if total_gross > 0 else "N/A")
```

## Data Export

### CSV Format
```python
reporter.export_trades_to_csv(trades, "MyStrategy")
# Creates: trades_MyStrategy_20241215_143000.csv
# Columns: trade_id, symbol, entry_time, exit_time, entry_price, exit_price,
#          quantity, duration_hours, net_pnl, pnl_pct, exit_reason, etc.
```

### JSON Format
```python
reporter.export_trades_to_json(trades, "MyStrategy")
# Creates: trades_MyStrategy_20241215_143000.json
# Full nested structure with all trade details
```

### Markdown Format
```python
reporter.generate_detailed_trades_report(trades, "MyStrategy")
# Creates: detailed_trades_report_MyStrategy_20241215_143000.md
# Contains: summary, tables, analysis sections
```

## Common Queries

### "Which trades had the worst MAE?"
```python
worst_mae = sorted(trades, key=lambda t: abs(t.max_adverse_excursion_pct or 0), reverse=True)
for trade in worst_mae[:5]:
    print(f"{trade.symbol}: {trade.max_adverse_excursion_pct:.2f}%, won: {trade.is_winner()}")
```

### "What's our recovery from MAE?"
```python
import numpy as np

recovery_rates = []
for trade in trades:
    mae = abs(trade.max_adverse_excursion_pct or 0)
    exit_pct = trade.pnl_pct
    if mae > 0:
        recovery = (exit_pct + mae) / mae  # How much we recovered from worst point
        recovery_rates.append(recovery)

print(f"Avg Recovery from MAE: {np.mean(recovery_rates):.2f}x")
```

### "Best stop-loss exit vs worst signal reversal exit?"
```python
sl_exits = [t for t in trades if t.exit_reason == ExitReason.STOP_LOSS]
sr_exits = [t for t in trades if t.exit_reason == ExitReason.SIGNAL_REVERSAL]

sl_avg = np.mean([t.net_pnl for t in sl_exits]) if sl_exits else 0
sr_avg = np.mean([t.net_pnl for t in sr_exits]) if sr_exits else 0

print(f"Stop-Loss avg: ${sl_avg:.2f}")
print(f"Signal-Reversal avg: ${sr_avg:.2f}")
```

## Performance Metrics

```python
# Build comprehensive stats
def get_trade_stats(trades):
    winners = [t for t in trades if t.is_winner()]
    losers = [t for t in trades if t.is_loser()]
    
    return {
        'total_trades': len(trades),
        'win_rate': len(winners) / len(trades) * 100 if trades else 0,
        'total_pnl': sum(t.net_pnl for t in trades),
        'avg_win': sum(t.net_pnl for t in winners) / len(winners) if winners else 0,
        'avg_loss': sum(t.net_pnl for t in losers) / len(losers) if losers else 0,
        'profit_factor': sum(t.net_pnl for t in winners) / abs(sum(t.net_pnl for t in losers)) if losers else float('inf'),
        'avg_mae': np.mean([abs(t.max_adverse_excursion_pct or 0) for t in trades]),
        'avg_mfe': np.mean([t.max_favorable_excursion_pct or 0 for t in trades]),
    }

stats = get_trade_stats(trades)
for key, value in stats.items():
    print(f"{key}: {value:.2f}")
```
