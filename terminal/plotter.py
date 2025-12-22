"""
Terminal Plotter using plotext
Renders candlestick charts and technical indicators in the terminal
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd

try:
    import plotext as plt
except ImportError:
    plt = None

from common.models import CandleData, SignalEvent

logger = logging.getLogger(__name__)

class TerminalPlotter:
    """
    Handles plotting of market data and indicators using plotext
    """
    
    def __init__(self):
        if plt is None:
            logger.warning("plotext not installed. Charting will be disabled.")

    @staticmethod
    def is_overlay(name: str) -> bool:
        """Check if indicator should be overlaid on price chart"""
        name_upper = name.upper()
        
        # Exclude specific types that might match keywords but have different scales
        if 'VOL' in name_upper: return False
        if 'BBB' in name_upper: return False # Bollinger Band Width
        if '%B' in name_upper: return False
        
        overlay_keywords = ['SMA', 'EMA', 'WMA', 'VWAP', 'BB_', 'BOLLINGER']
        return any(k in name_upper for k in overlay_keywords)
            
    def render(self, symbol: str, candles: List[CandleData], 
               indicators: Dict[str, List[float]], 
               interval: str = "1m", width: int = 100, height: int = 30,
               active_secondary_indicator: Optional[str] = None,
               signals: Optional[List[SignalEvent]] = None) -> str:
        """
        Render the chart with candles and indicators
        """
        if plt is None:
            return "Error: 'plotext' library not installed. Please install it via pip."
            
        if not candles:
            return "No data available to plot."

        # Prepare data
        dates = [self._format_date(c.timestamp) for c in candles]
        opens = [c.open for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        volumes = [c.volume if c.volume else 0 for c in candles]
        
        # Identify Overlays
        overlays = {}
        for name, values in indicators.items():
            if self.is_overlay(name):
                overlays[name] = values
        
        output_parts = []
        
        # --- 1. Price Chart (with Overlays) ---
        plt.clear_figure()
        plt.theme('dark')
        plt.title(f"{symbol} - Price ({interval})")
        plt.date_form('H:M')
        
        plt.candlestick(dates, data={
            'Open': opens, 'High': highs, 'Low': lows, 'Close': closes
        }, colors=['green', 'red'])
        
        # Plot Overlays
        for name, values in overlays.items():
            # Filter None values for plotting
            clean_values = [v if (v is not None and v != 0) else None for v in values]
            # Simple color rotation or logic
            color = 'yellow' if 'EMA' in name else 'blue'
            if 'BB' in name: color = 'white'
            # Only plot if we have valid data
            if any(v is not None for v in clean_values):
                plt.plot(dates, clean_values, label=name, color=color)
        
        # Plot Signals
        if signals:
            # Map signals to current dates
            # We need to find which signals correspond to the visible candles
            # This is approximate as signals have timestamps
            
            buy_dates = []
            buy_prices = []
            sell_dates = []
            sell_prices = []
            
            # Create a lookup for candle timestamps
            candle_ts_map = {c.timestamp: c for c in candles}
            
            for signal in signals:
                # Find closest candle or exact match
                # For simplicity, we check if signal timestamp is in our visible range
                if not candles: continue
                
                if candles[0].timestamp <= signal.timestamp <= candles[-1].timestamp:
                    # Find the corresponding candle (or closest)
                    # Since we formatted dates as H:M, we need to match that
                    formatted_date = self._format_date(signal.timestamp)
                    
                    # Check if this date is in our x-axis
                    if formatted_date in dates:
                        # Use the candle's close or the signal's price if available
                        # SignalEvent doesn't strictly have price, but usually it's close
                        price = 0
                        if signal.candle and 'close' in signal.candle:
                            price = signal.candle['close']
                        else:
                            # Fallback to finding the candle in our list
                            # This is O(N), could be optimized
                            idx = dates.index(formatted_date)
                            price = closes[idx]
                        
                        if 'buy' in signal.signal_type.lower() or 'bullish' in signal.signal_type.lower():
                            buy_dates.append(formatted_date)
                            buy_prices.append(price * 0.995) # Slightly below
                        elif 'sell' in signal.signal_type.lower() or 'bearish' in signal.signal_type.lower():
                            sell_dates.append(formatted_date)
                            sell_prices.append(price * 1.005) # Slightly above

            if buy_dates:
                plt.scatter(buy_dates, buy_prices, marker="triangle", color="green", label="Buy Signal")
            if sell_dates:
                plt.scatter(sell_dates, sell_prices, marker="inverted_triangle", color="red", label="Sell Signal")

        plt.plot_size(width, 20) # Give price more space
        try:
            output_parts.append(plt.build())
        except IndexError:
            output_parts.append("Error building price chart")
        
        # --- 2. Volume Chart ---
        plt.clear_figure()
        plt.theme('dark')
        plt.title("Volume")
        plt.date_form('H:M')
        
        plt.bar(dates, volumes, color='blue')
        plt.plot_size(width, 8)
        output_parts.append(plt.build())
        
        # --- 3. Active Secondary Indicator ---
        if active_secondary_indicator and active_secondary_indicator in indicators:
            values = indicators[active_secondary_indicator]
            
            plt.clear_figure()
            plt.theme('dark')
            plt.title(f"Indicator: {active_secondary_indicator}")
            plt.date_form('H:M')
            
            # Handle None/0
            plot_values = [v if (v is not None and v != 0) else None for v in values]
            
            # Color logic
            color = 'magenta'
            if 'RSI' in active_secondary_indicator.upper(): color = 'cyan'
            elif 'MACD' in active_secondary_indicator.upper(): color = 'yellow'
            
            plt.plot(dates, plot_values, color=color)
            
            # RSI Reference lines
            if 'RSI' in active_secondary_indicator.upper():
                plt.ylim(0, 100)
                plt.plot(dates, [70]*len(dates), color='red')
                plt.plot(dates, [30]*len(dates), color='green')

            plt.plot_size(width, 10)
            output_parts.append(plt.build())
            
        return "\n".join(output_parts)
            
        return "\n".join(output_parts)

    def _format_date(self, dt: datetime) -> str:
        """Format datetime for x-axis"""
        return dt.strftime('%H:%M')
