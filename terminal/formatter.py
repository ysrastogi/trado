"""
Response Formatter for Trado Terminal
Formats responses for clean terminal display
"""

from typing import Dict, Any, Optional, List
from datetime import datetime


class Colors:
    """ANSI color codes for terminal styling"""
    # Accent colors
    AQUA = '\033[38;2;15;240;252m'      # #0FF0FC
    MAGENTA = '\033[38;2;255;0;128m'    # #FF0080
    
    # Standard colors
    CYAN = '\033[96m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'
    
    # Styles
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'


class ResponseFormatter:
    """Format responses for terminal display"""
    
    def format_status(self, component: str, status: str, details: Dict[str, Any] = None) -> str:
        """Format component status"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = Colors.GREEN if status.lower() == 'active' else Colors.RED
        
        output = [
            f"{Colors.GRAY}[{timestamp}]{Colors.RESET} {Colors.BOLD}{component}{Colors.RESET}: {color}{status}{Colors.RESET}"
        ]
        
        if details:
            for key, value in details.items():
                output.append(f"  {Colors.CYAN}{key}{Colors.RESET}: {value}")
                
        return "\n".join(output)

    def format_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """Format data as a table"""
        if not headers or not rows:
            return "No data"
            
        # Calculate column widths
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))
        
        # Create format string
        fmt = "  ".join([f"{{:<{w}}}" for w in widths])
        
        output = []
        output.append(Colors.BOLD + fmt.format(*headers) + Colors.RESET)
        output.append(Colors.GRAY + "-" * (sum(widths) + 2 * (len(widths) - 1)) + Colors.RESET)
        
        for row in rows:
            output.append(fmt.format(*[str(c) for c in row]))
            
        return "\n".join(output)

    def format_alert(self, level: str, message: str) -> str:
        """Format alert message"""
        colors = {
            'INFO': Colors.CYAN,
            'WARNING': Colors.YELLOW,
            'ERROR': Colors.RED,
            'SUCCESS': Colors.GREEN
        }
        color = colors.get(level.upper(), Colors.WHITE)
        return f"{color}{Colors.BOLD}[{level.upper()}]{Colors.RESET} {message}"
