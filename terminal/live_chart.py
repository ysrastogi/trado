"""
Live Auto-Refreshing Chart for LumosTrade Terminal
Displays real-time candlestick charts with automatic updates
"""

import time
import sys
import os
import select
import tty
import termios
import yaml
from typing import Optional, Any
from datetime import datetime
import threading
import logging

from terminal.plotter import TerminalPlotter
from feature_engine.indicator_calculator import IndicatorCalculator
from feature_engine.models import FeatureConfig
from terminal.chart_consumer import ChartDataConsumer
from common.models import CandleData
from data_layer.market_stream.stream import MarketStream

logger = logging.getLogger(__name__)


class Colors:
    """ANSI color codes for terminal styling"""
    AQUA = '\033[38;2;15;240;252m'
    MAGENTA = '\033[38;2;255;0;128m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    CLEAR_SCREEN = '\033[2J'
    MOVE_CURSOR_HOME = '\033[H'


class LiveChart:
    """
    Live auto-refreshing candlestick chart with indicators
    """
    
    def __init__(self, symbol: str, interval: int = 60, refresh_rate: float = 1.0, 
                market_stream: Optional[Any] = None, window_size: int = 60,
                consumer: Optional[Any] = None):
        """
        Initialize live chart
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSD')
            interval: Time interval in seconds
            refresh_rate: Refresh rate in seconds
            market_stream: Ignored (kept for compatibility)
            window_size: Number of candles to display
        """
        self.symbol = symbol
        self.interval = interval
        self.refresh_rate = refresh_rate
        self.window_size = window_size
        self.is_running = False
        self.update_count = 0
        self.start_time = None
        self.last_update_time = None
        
        # Indicator Navigation State
        self.active_indicator_index = 0
        self.secondary_indicators = []
        
        # Interval display mapping
        self.interval_map = {
            60: '1m',
            120: '2m',
            300: '5m',
            900: '15m',
            3600: '1h'
        }
        self.interval_str = self.interval_map.get(interval, f"{interval}s")
        
        # Initialize components
        self.plotter = TerminalPlotter()
        
        # Load feature config
        try:
            with open("config/feature_config.yaml", "r") as f:
                config_dict = yaml.safe_load(f)
                feature_config = FeatureConfig.from_dict(config_dict)
                self.calculator = IndicatorCalculator(config=feature_config)
        except Exception as e:
            logger.warning(f"Failed to load feature config, using defaults: {e}")
            self.calculator = IndicatorCalculator()
        
        # Suppress logs from feature_engine to prevent terminal clutter
        logging.getLogger('feature_engine.indicator_calculator').setLevel(logging.WARNING)
        
        # Data Consumer
        if consumer:
            self.consumer = consumer
        else:
            self.consumer = ChartDataConsumer(self.symbol, self.interval, self.window_size)
        
    def start(self):
        """Start the live chart display"""
        self.is_running = True
        self.start_time = datetime.now()
        
        print(f"{Colors.CLEAR_SCREEN}{Colors.MOVE_CURSOR_HOME}")
        print(f"{Colors.AQUA}{'═' * 80}{Colors.RESET}")
        print(f"{Colors.AQUA}{Colors.BOLD}📊 LIVE CHART MODE (Redis Stream){Colors.RESET}")
        print(f"{Colors.AQUA}{'═' * 80}{Colors.RESET}")
        print(f"{Colors.WHITE}Symbol: {Colors.MAGENTA}{self.symbol}{Colors.RESET}")
        print(f"{Colors.WHITE}Interval: {Colors.AQUA}{self.interval_str}{Colors.RESET}")
        print(f"{Colors.GRAY}Connecting to Redis stream...{Colors.RESET}")
        
        # Start Consumer
        try:
            self.consumer.start()
        except Exception as e:
            print(f"{Colors.RED}Failed to connect to Redis: {e}{Colors.RESET}")
            return
        
        print(f"{Colors.GRAY}Press Ctrl+C to exit...{Colors.RESET}")
        
        # Save terminal settings
        old_settings = termios.tcgetattr(sys.stdin)
        try:
            # Set to cbreak mode (read char by char, no echo)
            tty.setcbreak(sys.stdin.fileno())
            
            while self.is_running:
                self._update_display()
                
                # Responsive sleep loop
                end_time = time.time() + self.refresh_rate
                while time.time() < end_time and self.is_running:
                    if self._is_key_pressed():
                        key = sys.stdin.read(1)
                        if key:
                            if key.lower() == 'n': # Next
                                self.active_indicator_index += 1
                                break # Trigger immediate update
                            elif key.lower() == 'p': # Previous
                                self.active_indicator_index -= 1
                                break # Trigger immediate update
                            elif key.lower() == 'q': # Quit
                                self.stop()
                                return
                    
                    time.sleep(0.05) # Short sleep for responsiveness
                
        except KeyboardInterrupt:
            self._handle_exit()
        except Exception as e:
            logger.error(f"Live chart error: {e}", exc_info=True)
            self._handle_exit()
        finally:
            # Restore settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    
    def stop(self):
        """Stop the live chart"""
        self.is_running = False
        self.consumer.stop()

    def _is_key_pressed(self):
        return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])
            
    def _update_display(self):
        """Update the chart display"""
        try:
            # Get candles from consumer
            current_candles = self.consumer.get_candles()
            
            if not current_candles:
                print(f"{Colors.YELLOW}Waiting for data...{Colors.RESET}")
                return

            # Calculate indicators
            indicators = self.calculator.calculate_indicators(current_candles)
            
            # Filter Secondary Indicators
            all_keys = sorted(indicators.keys())
            self.secondary_indicators = [k for k in all_keys if not self.plotter.is_overlay(k)]
            
            active_secondary = None
            if self.secondary_indicators:
                # Wrap index
                self.active_indicator_index = self.active_indicator_index % len(self.secondary_indicators)
                active_secondary = self.secondary_indicators[self.active_indicator_index]
            
            # Get signals if available
            signals = []
            if hasattr(self.consumer, 'get_signals'):
                signals = self.consumer.get_signals()

            # Render chart
            chart_output = self.plotter.render(
                self.symbol, 
                current_candles[-self.window_size:], # Show last n candles
                {k: v[-self.window_size:] for k, v in indicators.items()},
                self.interval_str,
                active_secondary_indicator=active_secondary,
                signals=signals
            )
            
            # Clear screen and display
            # Use a more robust clear sequence
            sys.stdout.write(f"{Colors.CLEAR_SCREEN}{Colors.MOVE_CURSOR_HOME}")
            sys.stdout.write(chart_output)
            sys.stdout.flush()
            
            # Display stats
            self._display_stats(current_candles[-1])
            
            self.update_count += 1
            self.last_update_time = datetime.now()
            
        except Exception as e:
            logger.error(f"Error updating live chart: {e}", exc_info=True)
            # Don't crash, just print error
            print(f"{Colors.RED}Error: {str(e)}{Colors.RESET}")
    
    def _display_stats(self, last_candle: CandleData):
        """Display live chart statistics"""
        if not self.start_time:
            return
        
        uptime = datetime.now() - self.start_time
        uptime_str = str(uptime).split('.')[0]
        last_update = datetime.now().strftime("%H:%M:%S")
        
        print(f"\n{Colors.AQUA}{'─' * 80}{Colors.RESET}")
        print(f"{Colors.BOLD} Price: {Colors.GREEN}{last_candle.close:.2f}{Colors.RESET} | "
              f"Vol: {Colors.YELLOW}{last_candle.volume}{Colors.RESET}")
        print(f"{Colors.GRAY} Last Update: {last_update} | Uptime: {uptime_str}{Colors.RESET}")
        print(f"{Colors.WHITE} Controls: [N]ext Indicator | [P]rev Indicator | [Q]uit{Colors.RESET}")
        print(f"{Colors.AQUA}{'─' * 80}{Colors.RESET}")

    def _handle_exit(self):
        """Handle graceful exit"""
        print(f"\n{Colors.YELLOW}Exiting Live Chart...{Colors.RESET}\n")

def start_live_chart(symbol: str, interval: int = 60, refresh_rate: float = 1.0, market_stream: Optional[MarketStream] = None, window_size: int = 60):
    """
    Convenience function to start a live chart
    """
    chart = LiveChart(symbol, interval, refresh_rate, market_stream, window_size)
    chart.start()

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python live_chart.py <SYMBOL> [interval_seconds] [window_size]")
        sys.exit(1)
    
    symbol = sys.argv[1]
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    window_size = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    start_live_chart(symbol, interval, window_size=window_size)
