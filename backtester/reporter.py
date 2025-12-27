import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
from collections import deque
import csv
import logging

from common.models import TradeRecord, ExitReason

logger = logging.getLogger(__name__)


class BacktestReporter:
    """Generate reports from backtest execution statistics"""
    
    def __init__(self, output_dir: str = "./backtest_reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def generate_report(self, stats: Dict[str, Any], strategy_name: str):
        """Generate markdown report"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backtest_report_{strategy_name}_{timestamp}.md"
        filepath = self.output_dir / filename
        
        # Calculate Advanced Metrics
        metrics = self._calculate_metrics(stats)
        
        with open(filepath, 'w') as f:
            f.write(f"# Backtest Report: {strategy_name}\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            f.write("## Performance Metrics\n\n")
            f.write(f"- **CAGR:** {metrics.get('cagr', 0):.2f}%\n")
            f.write(f"- **Sharpe Ratio:** {metrics.get('sharpe', 0):.2f}\n")
            f.write(f"- **Max Drawdown:** {metrics.get('max_drawdown', 0):.2f}%\n")
            f.write(f"- **Win Rate:** {metrics.get('win_rate', 0):.2f}%\n")
            f.write(f"- **Profit Factor:** {metrics.get('profit_factor', 0):.2f}\n")
            f.write(f"- **Avg Win:** ${metrics.get('avg_win', 0):.2f}\n")
            f.write(f"- **Avg Loss:** ${metrics.get('avg_loss', 0):.2f}\n")
            f.write(f"- **Avg Trade Duration:** {metrics.get('avg_duration', 'N/A')}\n\n")

            f.write("## Execution Summary\n\n")
            f.write(f"- **Total Orders:** {stats.get('total_orders', 0)}\n")
            f.write(f"- **Filled Orders:** {stats.get('filled_orders', 0)}\n")
            f.write(f"- **Fill Rate:** {stats.get('fill_rate_pct', 0):.2f}%\n")
            f.write(f"- **Total Cost:** ${stats.get('total_cost', 0):.2f}\n")
            f.write(f"- **Avg Slippage:** {stats.get('avg_slippage_bps', 0):.2f} bps\n")
            f.write(f"- **Avg Latency:** {stats.get('avg_latency_ms', 0):.2f} ms\n\n")
            
            f.write("## Symbol Performance\n\n")
            f.write("| Symbol | Orders | Volume | Avg Slippage (bps) | Realized PnL |\n")
            f.write("|--------|--------|--------|-------------------|--------------|\n")
            
            for symbol, sym_stats in stats.get('by_symbol', {}).items():
                pnl = metrics.get('symbol_pnl', {}).get(symbol, 0.0)
                f.write(f"| {symbol} | {sym_stats['count']} | {sym_stats['total_volume']:.2f} | {sym_stats['avg_slippage_bps']:.2f} | ${pnl:.2f} |\n")
                
        return filepath

    def _calculate_metrics(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate advanced financial metrics"""
        equity_curve = stats.get('equity_curve', [])
        executions = stats.get('executions', [])
        
        if not equity_curve:
            return {}
            
        # Convert to DataFrame
        df = pd.DataFrame(equity_curve)
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
        
        # 1. CAGR
        start_val = df['equity'].iloc[0]
        end_val = df['equity'].iloc[-1]
        days = (df.index[-1] - df.index[0]).days
        if days > 0:
            cagr = (end_val / start_val) ** (365 / days) - 1
        else:
            cagr = 0
            
        # 2. Max Drawdown
        df['peak'] = df['equity'].cummax()
        df['drawdown'] = (df['equity'] - df['peak']) / df['peak']
        max_drawdown = df['drawdown'].min() * 100
        
        # 3. Sharpe Ratio
        df['returns'] = df['equity'].pct_change()
        sharpe = 0
        if df['returns'].std() > 0:
            sharpe = (df['returns'].mean() / df['returns'].std()) * np.sqrt(252) # Annualized
            
        # 4. Trade Analysis (FIFO)
        trades = self._match_trades(executions)
        wins = [t['pnl'] for t in trades if t['pnl'] > 0]
        losses = [t['pnl'] for t in trades if t['pnl'] <= 0]
        
        win_rate = len(wins) / len(trades) * 100 if trades else 0
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        profit_factor = sum(wins) / abs(sum(losses)) if losses else float('inf')
        
        durations = [t['duration'] for t in trades]
        avg_duration = np.mean(durations) if durations else timedelta(0)
        
        # Symbol PnL
        symbol_pnl = {}
        for t in trades:
            symbol_pnl[t['symbol']] = symbol_pnl.get(t['symbol'], 0) + t['pnl']

        return {
            'cagr': cagr * 100,
            'sharpe': sharpe,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'avg_duration': str(avg_duration),
            'symbol_pnl': symbol_pnl
        }

    def _match_trades(self, executions: List[Any]) -> List[Dict]:
        """Match buy/sell executions into trades using FIFO"""
        trades = []
        positions = {} # {symbol: deque([{'price':, 'qty':, 'time':, 'side':}])}
        
        # Helper to get attribute or dict item
        def get_val(obj, key):
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)
            
        sorted_execs = sorted(executions, key=lambda x: get_val(x, 'timestamp'))
        
        for exc in sorted_execs:
            symbol = get_val(exc, 'symbol')
            side = get_val(exc, 'side')
            qty = get_val(exc, 'filled_quantity') # Use filled_quantity instead of quantity
            if qty is None: # Fallback for dicts that might use 'quantity'
                 qty = get_val(exc, 'quantity')
            
            price = get_val(exc, 'average_fill_price') # Use average_fill_price
            if price is None:
                price = get_val(exc, 'price')
                
            time = get_val(exc, 'timestamp')
            
            if not qty or qty == 0:
                continue
            
            if symbol not in positions:
                positions[symbol] = deque()
                
            # If flat or same side, add to position
            if not positions[symbol] or positions[symbol][0]['side'] == side:
                positions[symbol].append({
                    'price': price,
                    'qty': qty,
                    'time': time,
                    'side': side
                })
            else:
                # Closing position
                remaining_qty = qty
                while remaining_qty > 0 and positions[symbol]:
                    open_pos = positions[symbol][0]
                    match_qty = min(remaining_qty, open_pos['qty'])
                    
                    # Calculate PnL
                    if side == 'sell': # Closing Long
                        pnl = (price - open_pos['price']) * match_qty
                    else: # Closing Short
                        pnl = (open_pos['price'] - price) * match_qty
                        
                    duration = time - open_pos['time']
                    
                    trades.append({
                        'symbol': symbol,
                        'pnl': pnl,
                        'duration': duration,
                        'entry_time': open_pos['time'],
                        'exit_time': time
                    })
                    
                    # Update remaining
                    remaining_qty -= match_qty
                    open_pos['qty'] -= match_qty
                    
                    if open_pos['qty'] <= 0:
                        positions[symbol].popleft()
                        
                # If we flipped position, add remainder
                if remaining_qty > 0:
                    positions[symbol].append({
                        'price': price,
                        'qty': remaining_qty,
                        'time': time,
                        'side': side
                    })
                    
        return trades
    
    def generate_detailed_trades_report(self, trades: List[TradeRecord], 
                                       strategy_name: str, 
                                       stats: Optional[Dict[str, Any]] = None) -> Path:
        """
        Generate a comprehensive detailed trades report with per-trade analysis.
        
        Args:
            trades: List of TradeRecord objects
            strategy_name: Name of strategy for report title
            stats: Optional dictionary with additional statistics
        
        Returns:
            Path to generated report file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"detailed_trades_report_{strategy_name}_{timestamp}.md"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w') as f:
            # Header
            f.write(f"# Detailed Trades Report: {strategy_name}\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Total Trades Analyzed:** {len(trades)}\n\n")
            
            # Summary Statistics
            f.write(self._format_trades_summary(trades))
            
            # Per-Trade Analysis Table
            f.write(self._format_trades_table(trades))
            
            # Execution Quality Analysis
            f.write(self._format_execution_analysis(trades))
            
            # Risk Analysis
            f.write(self._format_risk_analysis(trades))
            
            # Trade Groupings
            f.write(self._format_trade_groupings(trades))
            
            # Statistical Analysis
            f.write(self._format_statistical_analysis(trades))
            
            # Detailed Trade Records (optional, for debugging)
            if len(trades) <= 50:  # Only if reasonable number of trades
                f.write(self._format_detailed_trade_records(trades))
        
        logger.info(f"Detailed trades report generated: {filepath}")
        return filepath
    
    def _format_trades_summary(self, trades: List[TradeRecord]) -> str:
        """Format trade summary statistics"""
        if not trades:
            return "## Summary\n\nNo trades to analyze.\n\n"
        
        winners = [t for t in trades if t.is_winner()]
        losers = [t for t in trades if t.is_loser()]
        breakevens = [t for t in trades if t.is_breakeven()]
        
        summary = "## Summary\n\n"
        summary += f"| Metric | Value |\n"
        summary += f"|--------|-------|\n"
        summary += f"| Total Trades | {len(trades)} |\n"
        summary += f"| Winning Trades | {len(winners)} ({len(winners)/len(trades)*100:.1f}%) |\n"
        summary += f"| Losing Trades | {len(losers)} ({len(losers)/len(trades)*100:.1f}%) |\n"
        summary += f"| Breakeven Trades | {len(breakevens)} ({len(breakevens)/len(trades)*100:.1f}%) |\n"
        
        total_pnl = sum(t.net_pnl for t in trades)
        summary += f"| **Total P&L** | **${total_pnl:.2f}** |\n"
        
        if winners:
            avg_win = sum(t.net_pnl for t in winners) / len(winners)
            summary += f"| Avg Win | ${avg_win:.2f} |\n"
        
        if losers:
            avg_loss = sum(t.net_pnl for t in losers) / len(losers)
            summary += f"| Avg Loss | ${avg_loss:.2f} |\n"
        
        if winners and losers:
            profit_factor = sum(t.net_pnl for t in winners) / abs(sum(t.net_pnl for t in losers))
            summary += f"| Profit Factor | {profit_factor:.2f} |\n"
        
        # Duration stats
        durations = [t.duration_seconds for t in trades if t.duration_seconds]
        if durations:
            avg_hours = sum(durations) / len(durations) / 3600
            summary += f"| Avg Trade Duration | {avg_hours:.1f} hours |\n"
        
        # Slippage stats
        entry_slippages = [t.entry_slippage_bps for t in trades if t.entry_slippage_bps]
        exit_slippages = [t.exit_slippage_bps for t in trades if t.exit_slippage_bps]
        
        if entry_slippages:
            summary += f"| Avg Entry Slippage | {np.mean(entry_slippages):.2f} bps |\n"
        if exit_slippages:
            summary += f"| Avg Exit Slippage | {np.mean(exit_slippages):.2f} bps |\n"
        
        # MAE/MFE stats
        maes = [abs(t.max_adverse_excursion_pct or 0) for t in trades]
        mfes = [t.max_favorable_excursion_pct or 0 for t in trades]
        
        if maes:
            summary += f"| Avg Max Adverse Excursion | {np.mean(maes):.2f}% |\n"
        if mfes:
            summary += f"| Avg Max Favorable Excursion | {np.mean(mfes):.2f}% |\n"
        
        summary += "\n"
        return summary
    
    def _format_trades_table(self, trades: List[TradeRecord]) -> str:
        """Format detailed per-trade table"""
        table = "## Per-Trade Analysis\n\n"
        table += "| # | Symbol | Entry Time | Exit Time | Duration | Entry Price | Exit Price | Qty | P&L | P&L % | Reason | MAE% | MFE% |\n"
        table += "|---|--------|-----------|----------|----------|------------|-----------|-----|-----|-------|--------|------|------|\n"
        
        for i, trade in enumerate(trades, 1):
            entry_time = trade.entry_time.strftime("%Y-%m-%d %H:%M")
            exit_time = trade.exit_time.strftime("%Y-%m-%d %H:%M") if trade.exit_time else "OPEN"
            duration = trade.holding_period or "N/A"
            pnl_color = "+" if trade.net_pnl >= 0 else "-"
            exit_reason = trade.exit_reason.value if trade.exit_reason else "N/A"
            mae = trade.max_adverse_excursion_pct or 0
            mfe = trade.max_favorable_excursion_pct or 0
            
            table += f"| {i} | {trade.symbol} | {entry_time} | {exit_time} | {duration} | "
            table += f"${trade.entry_price:.2f} | ${trade.exit_price or 0:.2f} | {trade.entry_quantity:.2f} | "
            table += f"${trade.net_pnl:.2f} | {trade.pnl_pct:.2f}% | {exit_reason} | {mae:.2f}% | {mfe:.2f}% |\n"
        
        table += "\n"
        return table
    
    def _format_execution_analysis(self, trades: List[TradeRecord]) -> str:
        """Format execution quality analysis"""
        analysis = "## Execution Quality Analysis\n\n"
        
        # Entry execution
        analysis += "### Entry Execution\n\n"
        analysis += "| Metric | Value |\n"
        analysis += "|--------|-------|\n"
        
        entry_slippages = [t.entry_slippage_bps for t in trades if t.entry_execution]
        if entry_slippages:
            analysis += f"| Min Slippage | {min(entry_slippages):.2f} bps |\n"
            analysis += f"| Max Slippage | {max(entry_slippages):.2f} bps |\n"
            analysis += f"| Avg Slippage | {np.mean(entry_slippages):.2f} bps |\n"
            analysis += f"| Std Dev | {np.std(entry_slippages):.2f} bps |\n"
        
        # Exit execution
        analysis += "\n### Exit Execution\n\n"
        analysis += "| Metric | Value |\n"
        analysis += "|--------|-------|\n"
        
        exit_slippages = [t.exit_slippage_bps for t in trades if t.exit_execution]
        if exit_slippages:
            analysis += f"| Min Slippage | {min(exit_slippages):.2f} bps |\n"
            analysis += f"| Max Slippage | {max(exit_slippages):.2f} bps |\n"
            analysis += f"| Avg Slippage | {np.mean(exit_slippages):.2f} bps |\n"
            analysis += f"| Std Dev | {np.std(exit_slippages):.2f} bps |\n"
        
        # Total costs impact
        analysis += "\n### Cost Impact\n\n"
        total_costs = sum(t.total_costs for t in trades)
        total_gross_pnl = sum(t.gross_pnl for t in trades)
        total_net_pnl = sum(t.net_pnl for t in trades)
        
        analysis += "| Metric | Value |\n"
        analysis += "|--------|-------|\n"
        analysis += f"| Total Gross P&L | ${total_gross_pnl:.2f} |\n"
        analysis += f"| Total Costs | ${total_costs:.2f} |\n"
        analysis += f"| Total Net P&L | ${total_net_pnl:.2f} |\n"
        
        if total_gross_pnl != 0:
            cost_pct = (total_costs / abs(total_gross_pnl)) * 100
            analysis += f"| Costs as % of Gross P&L | {cost_pct:.2f}% |\n"
        
        analysis += "\n"
        return analysis
    
    def _format_risk_analysis(self, trades: List[TradeRecord]) -> str:
        """Format risk metrics analysis"""
        analysis = "## Risk Analysis\n\n"
        
        # MAE/MFE analysis
        analysis += "### Intra-Trade Excursions\n\n"
        analysis += "| Metric | Avg | Min | Max |\n"
        analysis += "|--------|-----|-----|-----|\n"
        
        maes = [abs(t.max_adverse_excursion_pct or 0) for t in trades]
        mfes = [t.max_favorable_excursion_pct or 0 for t in trades]
        
        if maes:
            analysis += f"| Max Adverse Excursion | {np.mean(maes):.2f}% | {min(maes):.2f}% | {max(maes):.2f}% |\n"
        if mfes:
            analysis += f"| Max Favorable Excursion | {np.mean(mfes):.2f}% | {min(mfes):.2f}% | {max(mfes):.2f}% |\n"
        
        # Exit reason distribution
        analysis += "\n### Exit Reason Distribution\n\n"
        analysis += "| Exit Reason | Count | Avg P&L | Win Rate |\n"
        analysis += "|-------------|-------|---------|----------|\n"
        
        exit_reasons = {}
        for trade in trades:
            reason = trade.exit_reason.value if trade.exit_reason else "Unknown"
            if reason not in exit_reasons:
                exit_reasons[reason] = []
            exit_reasons[reason].append(trade)
        
        for reason, reason_trades in sorted(exit_reasons.items()):
            count = len(reason_trades)
            avg_pnl = np.mean([t.net_pnl for t in reason_trades])
            win_pct = len([t for t in reason_trades if t.is_winner()]) / count * 100
            analysis += f"| {reason} | {count} | ${avg_pnl:.2f} | {win_pct:.1f}% |\n"
        
        analysis += "\n"
        return analysis
    
    def _format_trade_groupings(self, trades: List[TradeRecord]) -> str:
        """Format trades grouped by various dimensions"""
        grouping = "## Trade Groupings\n\n"
        
        # By Symbol
        grouping += "### By Symbol\n\n"
        grouping += "| Symbol | Count | Avg P&L | Win Rate | Total P&L |\n"
        grouping += "|--------|-------|---------|----------|----------|\n"
        
        by_symbol = {}
        for trade in trades:
            if trade.symbol not in by_symbol:
                by_symbol[trade.symbol] = []
            by_symbol[trade.symbol].append(trade)
        
        for symbol in sorted(by_symbol.keys()):
            sym_trades = by_symbol[symbol]
            count = len(sym_trades)
            avg_pnl = np.mean([t.net_pnl for t in sym_trades])
            win_pct = len([t for t in sym_trades if t.is_winner()]) / count * 100 if count > 0 else 0
            total_pnl = sum(t.net_pnl for t in sym_trades)
            grouping += f"| {symbol} | {count} | ${avg_pnl:.2f} | {win_pct:.1f}% | ${total_pnl:.2f} |\n"
        
        # By Duration
        grouping += "\n### By Trade Duration\n\n"
        grouping += "| Duration Range | Count | Avg P&L | Win Rate |\n"
        grouping += "|-----------------|-------|---------|----------|\n"
        
        duration_ranges = {
            "< 1 hour": [],
            "1-4 hours": [],
            "4-24 hours": [],
            "> 24 hours": []
        }
        
        for trade in trades:
            if not trade.duration_seconds:
                continue
            hours = trade.duration_seconds / 3600
            if hours < 1:
                duration_ranges["< 1 hour"].append(trade)
            elif hours < 4:
                duration_ranges["1-4 hours"].append(trade)
            elif hours < 24:
                duration_ranges["4-24 hours"].append(trade)
            else:
                duration_ranges["> 24 hours"].append(trade)
        
        for duration_range, range_trades in duration_ranges.items():
            if range_trades:
                count = len(range_trades)
                avg_pnl = np.mean([t.net_pnl for t in range_trades])
                win_pct = len([t for t in range_trades if t.is_winner()]) / count * 100
                grouping += f"| {duration_range} | {count} | ${avg_pnl:.2f} | {win_pct:.1f}% |\n"
        
        grouping += "\n"
        return grouping
    
    def _format_statistical_analysis(self, trades: List[TradeRecord]) -> str:
        """Format statistical analysis"""
        analysis = "## Statistical Analysis\n\n"
        
        pnls = [t.net_pnl for t in trades]
        pnl_pcts = [t.pnl_pct for t in trades]
        
        analysis += "| Statistic | Value |\n"
        analysis += "|-----------|-------|\n"
        analysis += f"| Mean P&L | ${np.mean(pnls):.2f} |\n"
        analysis += f"| Median P&L | ${np.median(pnls):.2f} |\n"
        analysis += f"| Std Dev P&L | ${np.std(pnls):.2f} |\n"
        analysis += f"| Skewness | {pd.Series(pnls).skew():.2f} |\n"
        analysis += f"| Kurtosis | {pd.Series(pnls).kurtosis():.2f} |\n"
        analysis += f"| Mean P&L % | {np.mean(pnl_pcts):.2f}% |\n"
        analysis += f"| Median P&L % | {np.median(pnl_pcts):.2f}% |\n"
        
        analysis += "\n"
        return analysis
    
    def _format_detailed_trade_records(self, trades: List[TradeRecord]) -> str:
        """Format detailed breakdown for each trade"""
        detailed = "## Detailed Trade Records\n\n"
        
        for i, trade in enumerate(trades, 1):
            detailed += f"### Trade #{i}: {trade.trade_id}\n\n"
            
            detailed += f"**Symbol:** {trade.symbol}  \n"
            detailed += f"**Entry Time:** {trade.entry_time.strftime('%Y-%m-%d %H:%M:%S')}  \n"
            detailed += f"**Exit Time:** {trade.exit_time.strftime('%Y-%m-%d %H:%M:%S') if trade.exit_time else 'OPEN'}  \n"
            detailed += f"**Duration:** {trade.holding_period or 'N/A'}  \n\n"
            
            detailed += "#### Entry\n"
            detailed += f"- **Price:** ${trade.entry_price:.2f}\n"
            detailed += f"- **Quantity:** {trade.entry_quantity:.2f}\n"
            detailed += f"- **Confidence:** {trade.entry_confidence:.2%}\n"
            detailed += f"- **Reason:** {trade.entry_reason}\n"
            detailed += f"- **Slippage:** {trade.entry_slippage_bps:.2f} bps\n"
            detailed += f"- **Commission:** ${trade.entry_commission:.2f}\n\n"
            
            detailed += "#### Exit\n"
            detailed += f"- **Price:** ${trade.exit_price or 0:.2f}\n"
            detailed += f"- **Quantity:** {trade.exit_quantity or 0:.2f}\n"
            detailed += f"- **Reason:** {trade.exit_reason.value if trade.exit_reason else 'N/A'}\n"
            detailed += f"- **Slippage:** {trade.exit_slippage_bps:.2f} bps\n"
            detailed += f"- **Commission:** ${trade.exit_commission:.2f}\n\n"
            
            detailed += "#### P&L\n"
            detailed += f"- **Gross P&L:** ${trade.gross_pnl:.2f}\n"
            detailed += f"- **Total Costs:** ${trade.total_costs:.2f}\n"
            detailed += f"- **Net P&L:** ${trade.net_pnl:.2f}\n"
            detailed += f"- **P&L %:** {trade.pnl_pct:.2f}%\n\n"
            
            detailed += "#### Intra-Trade Metrics\n"
            detailed += f"- **Max Price:** ${trade.max_price or 0:.2f}\n"
            detailed += f"- **Min Price:** ${trade.min_price or 0:.2f}\n"
            detailed += f"- **Max Adverse Excursion:** {trade.max_adverse_excursion_pct or 0:.2f}%\n"
            detailed += f"- **Max Favorable Excursion:** {trade.max_favorable_excursion_pct or 0:.2f}%\n\n"
        
        return detailed
    
    def export_trades_to_csv(self, trades: List[TradeRecord], 
                            strategy_name: str) -> Path:
        """
        Export trade records to CSV format for external analysis.
        
        Args:
            trades: List of TradeRecord objects
            strategy_name: Name for the CSV file
        
        Returns:
            Path to generated CSV file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"trades_{strategy_name}_{timestamp}.csv"
        filepath = self.output_dir / filename
        
        if not trades:
            logger.warning("No trades to export")
            return filepath
        
        rows = [trade.to_csv_row() for trade in trades]
        
        with open(filepath, 'w', newline='') as csvfile:
            fieldnames = rows[0].keys()
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        logger.info(f"Trades exported to CSV: {filepath}")
        return filepath
    
    def export_trades_to_json(self, trades: List[TradeRecord], 
                             strategy_name: str) -> Path:
        """
        Export trade records to JSON format for external analysis.
        
        Args:
            trades: List of TradeRecord objects
            strategy_name: Name for the JSON file
        
        Returns:
            Path to generated JSON file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"trades_{strategy_name}_{timestamp}.json"
        filepath = self.output_dir / filename
        
        data = {
            'exported_at': datetime.now().isoformat(),
            'strategy': strategy_name,
            'total_trades': len(trades),
            'trades': [trade.to_dict() for trade in trades]
        }
        
        with open(filepath, 'w') as jsonfile:
            json.dump(data, jsonfile, indent=2)
        
        logger.info(f"Trades exported to JSON: {filepath}")
        return filepath
