import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import numpy as np

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
        
        with open(filepath, 'w') as f:
            f.write(f"# Backtest Report: {strategy_name}\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            f.write("## Execution Summary\n\n")
            f.write(f"- **Total Orders:** {stats['total_orders']}\n")
            f.write(f"- **Filled Orders:** {stats['filled_orders']}\n")
            f.write(f"- **Fill Rate:** {stats['fill_rate_pct']:.2f}%\n")
            f.write(f"- **Total Cost:** ${stats['total_cost']:.2f}\n")
            f.write(f"- **Avg Slippage:** {stats['avg_slippage_bps']:.2f} bps\n")
            f.write(f"- **Avg Latency:** {stats['avg_latency_ms']:.2f} ms\n\n")
            
            f.write("## Symbol Performance\n\n")
            f.write("| Symbol | Orders | Volume | Avg Slippage (bps) |\n")
            f.write("|--------|--------|--------|-------------------|\n")
            
            for symbol, sym_stats in stats['by_symbol'].items():
                f.write(f"| {symbol} | {sym_stats['count']} | {sym_stats['total_volume']:.2f} | {sym_stats['avg_slippage_bps']:.2f} |\n")
                
        return filepath
