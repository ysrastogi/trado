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
from terminal.live_chart import start_live_chart
from broker.trading_client import TradingClient
from risk_manager.risk_manager import RiskManager

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
            self.broker = TradingClient(config_path="config/tradding_config.yaml")
            self.risk_manager = self.broker.risk_manager
            print(self.formatter.format_alert("SUCCESS", "Components initialized successfully"))
        except Exception as e:
            print(self.formatter.format_alert("ERROR", f"Failed to initialize components: {e}"))
            sys.exit(1)
    
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
            # Pass the existing market stream from the broker
            start_live_chart(symbol, interval, market_stream=self.broker.market_stream, window_size=window_size)
        except Exception as e:
            print(self.formatter.format_alert("ERROR", f"Failed to start chart: {e}"))

    def _show_status(self):
        """Show system status"""
        # Mock status for now
        print("\n" + self.formatter.format_status("Broker", "Active", {
            "Connected": "Yes",
            "Balance": "$10,000.00",
            "Open Positions": "0"
        }))
        print(self.formatter.format_status("Risk Manager", "Active", {
            "Daily Loss": "$0.00",
            "Trades Today": "0"
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

        # 2. Execute (Mock for now, hook up to broker.place_trade later)
        # self.broker.place_trade(...)
        print(self.formatter.format_alert("SUCCESS", f"Order placed: {action} {amount} {symbol}"))

def main():
    terminal = TradoTerminal()
    terminal.start()

if __name__ == "__main__":
    main()
