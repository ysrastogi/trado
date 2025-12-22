"""
Trado Terminal CLI
Main command-line interface for the trading system
"""

import sys
import logging
import threading
import time
from typing import Optional

from terminal.command_parser import CommandParser, CommandType
from terminal.formatter import ResponseFormatter, Colors
from terminal.live_chart import start_live_chart, LiveChart
from broker.factory import ExecutionServiceFactory
from broker.interfaces import OrderRequest, OrderSide, OrderType, OrderStatus
from data_layer.market_stream.stream import MarketStream
from risk_manager.risk_manager import RiskManager
from data_layer.historical_data_provider import YFinanceDataProvider
from backtester.engine import PlaybackEngine
from terminal.playback_consumer import PlaybackChartConsumer
from datetime import datetime, timedelta
import yaml

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TradoTerminal:
    """Main terminal interface for Trado"""
    
    WELCOME_BANNER = f"""
{Colors.AQUA}╔══════════════════════════════════════════════════════════════╗
║                   TRADO TRADING ENGINE                       ║
║               Interactive Trader Interface                   ║
╚══════════════════════════════════════════════════════════════╝{Colors.RESET}
"""
    
    def __init__(self):
        """Initialize the terminal with all components"""
        self.parser = CommandParser()
        self.formatter = ResponseFormatter()
        self.running = False
        
        # Initialize Core Components
        print(f"{Colors.GRAY}Initializing components...{Colors.RESET}")
        try:
            # Load Config
            with open("config/tradding_config.yaml", 'r') as f:
                self.config = yaml.safe_load(f)

            # Initialize Market Stream
            self.market_stream = MarketStream(config_path="config/tradding_config.yaml")
            
            # Initialize Execution Service
            self.execution_service = ExecutionServiceFactory.create_service(self.config, self.market_stream)
            
            # Initialize Risk Manager
            self.risk_manager = RiskManager(self.config)
            
            print(self.formatter.format_alert("SUCCESS", "Components initialized successfully"))
        except Exception as e:
            print(self.formatter.format_alert("ERROR", f"Failed to initialize components: {e}"))
            # sys.exit(1) # Don't exit, let it fail gracefully or retry
    
    def start(self):
        """Start the terminal loop"""
        self.running = True
        
        # Display welcome banner
        print(self.WELCOME_BANNER)
        print(f"\nType '{Colors.BOLD}/help{Colors.RESET}' to see available commands.\n")
        
        # Main loop
        while self.running:
            try:
                # Get user input with colored prompt
                prompt = f"{Colors.AQUA}TRADER{Colors.RESET} ▶ "
                user_input = input(prompt)
                
                # Skip empty input
                if not user_input.strip():
                    continue
                
                # Parse command
                command_type, metadata = self.parser.parse(user_input)
                self._handle_command(command_type, metadata)
                
            except KeyboardInterrupt:
                print("\n")
                self._handle_exit()
                break
            except Exception as e:
                logger.error(f"Error in terminal loop: {e}")
                print(self.formatter.format_alert("ERROR", str(e)))

    def _handle_command(self, command_type: CommandType, metadata: dict):
        """Route commands to appropriate handlers"""
        
        if command_type == CommandType.EXIT:
            self._handle_exit()
            
        elif command_type == CommandType.HELP:
            self._show_help()
            
        elif command_type == CommandType.STATUS:
            self._show_status()
            
        elif command_type == CommandType.BUY:
            self._handle_trade(metadata, is_buy=True)
            
        elif command_type == CommandType.SELL:
            self._handle_trade(metadata, is_buy=False)
            
        elif command_type == CommandType.REPLAY:
            self._handle_replay(metadata)
            
        elif command_type == CommandType.RISK:
            self._show_risk_status()
            
        elif command_type == CommandType.LIVE_CHART:
            self._handle_live_chart(metadata)
            
        elif command_type == CommandType.UNKNOWN:
            print(self.formatter.format_alert("WARNING", f"Unknown command: {metadata.get('raw')}"))

    def _handle_exit(self):
        """Handle exit command"""
        print(f"\n{Colors.GRAY}Shutting down...{Colors.RESET}")
        self.running = False
        # self.broker.close() # If broker has a close method

    def _show_help(self):
        """Show help message"""
        help_text = [
            ["Command", "Description"],
            ["/status", "Show system and account status"],
            ["/buy <symbol> <amount>", "Place a buy order"],
            ["/sell <symbol> <amount>", "Place a sell order"],
            ["/risk", "Show risk management metrics"],
            ["/live <symbol> [interval] [window_size]", "Open live chart with indicators"],
            ["/exit", "Exit the terminal"]
        ]
        print("\n" + self.formatter.format_table(help_text[0], help_text[1:]))

    def _handle_live_chart(self, metadata: dict):
        """Handle live chart command"""
        args = metadata.get('args', [])
        if not args:
            print(self.formatter.format_alert("ERROR", "Usage: /live <symbol> [interval_seconds] [window_size]"))
            return
            
        symbol = args[0]
        interval = int(args[1]) if len(args) > 1 else 60
        window_size = int(args[2]) if len(args) > 2 else 60
        
        try:
            # Pass the existing market stream
            start_live_chart(symbol, interval, market_stream=self.market_stream, window_size=window_size)
        except Exception as e:
            print(self.formatter.format_alert("ERROR", f"Failed to start chart: {e}"))

    def _show_status(self):
        """Show system status"""
        balance = self.execution_service.get_account_balance()
        positions = self.execution_service.get_active_positions()
        
        print("\n" + self.formatter.format_status("Broker", "Active", {
            "Connected": "Yes" if self.market_stream.is_connected else "No",
            "Balance": f"${balance:.2f}",
            "Open Positions": str(len(positions))
        }))
        print(self.formatter.format_status("Risk Manager", "Active", {
            "Daily Loss": f"${self.risk_manager.daily_loss}",
            "Trades Today": f"{self.risk_manager.daily_trades_count}"
        }))

    def _show_risk_status(self):
        """Show detailed risk status"""
        print("\n" + self.formatter.format_status("Risk Metrics", "Active", {
            "Max Daily Loss": f"${self.risk_manager.max_daily_loss}",
            "Current Daily Loss": f"${self.risk_manager.daily_loss}",
            "Max Trades/Day": f"{self.risk_manager.max_trades_per_day}",
            "Trades Today": f"{self.risk_manager.daily_trades_count}"
        }))

    def _handle_trade(self, metadata: dict, is_buy: bool):
        """Handle buy/sell commands"""
        args = metadata.get('args', [])
        if len(args) < 2:
            print(self.formatter.format_alert("ERROR", "Usage: /buy|sell <symbol> <amount>"))
            return
            
        symbol = args[0]
        try:
            amount = float(args[1])
        except ValueError:
            print(self.formatter.format_alert("ERROR", "Amount must be a number"))
            return

        action = "BUY" if is_buy else "SELL"
        print(f"{Colors.GRAY}Processing {action} order for {symbol}...{Colors.RESET}")
        
        # 1. Check Risk
        if not self.risk_manager.check_trade_allowed(amount):
            print(self.formatter.format_alert("WARNING", "Trade rejected by Risk Manager"))
            return

        # 2. Execute
        # Mapping: BUY -> CALL, SELL -> PUT (for Binary Options context)
        order_type = OrderType.CALL if is_buy else OrderType.PUT
        
        order = OrderRequest(
            symbol=symbol,
            order_type=order_type,
            side=OrderSide.BUY, # Always BUY for options (opening position)
            quantity=amount,
            duration=5, # Default duration
            duration_unit='t'
        )
        
        try:
            result = self.execution_service.execute_order(order)
            
            if result.status == OrderStatus.FILLED:
                print(self.formatter.format_alert("SUCCESS", f"Order filled: {result.order_id} @ {result.average_price}"))
            else:
                print(self.formatter.format_alert("ERROR", f"Order failed: {result.error_message}"))
        except Exception as e:
            print(self.formatter.format_alert("ERROR", f"Execution error: {e}"))

    def _handle_replay(self, metadata: dict):
        """Handle visual backtest replay"""
        args = metadata.get('args', [])
        
        # Default values
        symbol = "BTC-USD"
        days = 60
        interval = "1h"
        
        # Parse args: /replay [symbol] [days] [interval]
        if len(args) >= 1: symbol = args[0]
        if len(args) >= 2: 
            try:
                days = int(args[1])
            except ValueError:
                print(self.formatter.format_alert("ERROR", "Days must be a number"))
                return
        if len(args) >= 3: interval = args[2]
        
        print(self.formatter.format_alert("INFO", f"Starting replay for {symbol} ({days} days, {interval})"))
        
        try:
            # Setup components
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            data_provider = YFinanceDataProvider(cache_dir="data_cache")
            
            playback_engine = PlaybackEngine(
                data_provider=data_provider,
                symbols=[symbol],
                start_date=start_date,
                end_date=end_date,
                interval=interval,
                initial_speed=3600.0
            )
            
            print(f"{Colors.GRAY}Loading historical data...{Colors.RESET}")
            playback_engine.load_data()
            
            consumer = PlaybackChartConsumer(playback_engine, symbol)
            
            # Map interval string to seconds for LiveChart
            interval_map = {'1m': 60, '5m': 300, '15m': 900, '1h': 3600, '1d': 86400}
            interval_seconds = interval_map.get(interval, 3600)
            
            chart = LiveChart(
                symbol=symbol,
                interval=interval_seconds,
                refresh_rate=0.05,
                consumer=consumer,
                window_size=100
            )
            
            # Start
            playback_engine.play()
            chart.start() # Blocks until exit
            playback_engine.stop()
            
        except Exception as e:
            print(self.formatter.format_alert("ERROR", f"Replay failed: {e}"))
            logger.error(f"Replay error: {e}", exc_info=True)

def main():
    terminal = TradoTerminal()
    terminal.start()

if __name__ == "__main__":
    main()
