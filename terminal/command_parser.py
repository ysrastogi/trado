"""
Command Parser for Trado Terminal
Handles trader commands and user input parsing
"""

from typing import Tuple, Optional, Dict, Any
from enum import Enum


class Colors:
    """ANSI color codes for terminal styling"""
    AQUA = '\033[38;2;15;240;252m'      # #0FF0FC
    MAGENTA = '\033[38;2;255;0;128m'    # #FF0080
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    RED = '\033[91m'


class CommandType(Enum):
    """Types of commands supported by the terminal"""
    EXIT = "exit"
    HELP = "help"
    STATUS = "status"
    CHART = "chart"
    BUY = "buy"
    SELL = "sell"
    STRATEGY = "strategy"
    RISK = "risk"
    LIVE_CHART = "live_chart"
    UNKNOWN = "unknown"


class CommandParser:
    """Parse user commands and determine routing"""
    
    def __init__(self):
        self.commands = {
            '/exit': CommandType.EXIT,
            '/quit': CommandType.EXIT,
            '/help': CommandType.HELP,
            '/h': CommandType.HELP,
            '/status': CommandType.STATUS,
            '/s': CommandType.STATUS,
            '/chart': CommandType.CHART,
            '/live': CommandType.LIVE_CHART,
            '/buy': CommandType.BUY,
            '/sell': CommandType.SELL,
            '/strategy': CommandType.STRATEGY,
            '/risk': CommandType.RISK,
        }
    
    def parse(self, user_input: str) -> Tuple[CommandType, Dict[str, Any]]:
        """
        Parse user input and return command type and metadata
        
        Args:
            user_input: Raw user input string
            
        Returns:
            Tuple of (CommandType, metadata dict)
        """
        if not user_input or not user_input.strip():
            return CommandType.UNKNOWN, {'error': 'Empty input'}
        
        parts = user_input.strip().split()
        command = parts[0].lower()
        args = parts[1:]
        
        if command in self.commands:
            return self.commands[command], {'args': args, 'raw': user_input}
            
        return CommandType.UNKNOWN, {'raw': user_input}
