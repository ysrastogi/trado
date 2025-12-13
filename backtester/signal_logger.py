"""
Comprehensive signal logging system with JSON, CSV, and console output
"""

import logging
import json
import csv
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import defaultdict
import sys

from src.playback.models import SignalEvent, TrendPhase

logger = logging.getLogger(__name__)


# ANSI color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


class SignalLogger:
    """
    Comprehensive logging system for trading signals
    Logs to JSON, CSV, and console with rich formatting
    """
    
    def __init__(
        self,
        log_dir: str,
        console_output: bool = True,
        json_output: bool = True,
        csv_output: bool = True
    ):
        """
        Initialize signal logger
        
        Args:
            log_dir: Directory to store log files
            console_output: Enable colored console output
            json_output: Enable JSON logging
            csv_output: Enable CSV logging
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.console_output = console_output
        self.json_output = json_output
        self.csv_output = csv_output
        
        # Storage
        self.signals: List[SignalEvent] = []
        self.trend_phases: Dict[str, List[TrendPhase]] = defaultdict(list)
        
        # Statistics
        self.stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'total_signals': 0,
            'signal_counts': defaultdict(int),
            'total_confidence': 0.0,
            'trend_changes': 0
        })
        
        # File handles
        self.json_file: Optional[Any] = None
        self.csv_file: Optional[Any] = None
        self.csv_writer: Optional[Any] = None
        
        # Setup output files
        self._setup_files()
        
        logger.info(f"SignalLogger initialized (dir: {log_dir})")
    
    def _setup_files(self) -> None:
        """Setup output files"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # JSON Lines file
        if self.json_output:
            json_path = self.log_dir / f'signals_{timestamp}.jsonl'
            self.json_file = open(json_path, 'w')
            logger.info(f"JSON log: {json_path}")
        
        # CSV file
        if self.csv_output:
            csv_path = self.log_dir / f'signals_{timestamp}.csv'
            self.csv_file = open(csv_path, 'w', newline='')
            
            # CSV headers (will be written on first signal)
            self.csv_writer = None
            logger.info(f"CSV log: {csv_path}")
    
    def log_signal(self, signal: SignalEvent) -> None:
        """
        Log a signal event to all enabled outputs
        
        Args:
            signal: SignalEvent to log
        """
        # Store signal
        self.signals.append(signal)
        
        # Update statistics
        self._update_stats(signal)
        
        # Output to different formats
        if self.json_output:
            self._write_json(signal)
        
        if self.csv_output:
            self._write_csv(signal)
        
        if self.console_output:
            self._print_console(signal)
    
    def _update_stats(self, signal: SignalEvent) -> None:
        """Update statistics for a signal"""
        key = f"{signal.symbol}_{signal.algorithm}"
        stats = self.stats[key]
        
        stats['total_signals'] += 1
        stats['signal_counts'][signal.signal_type] += 1
        stats['total_confidence'] += signal.confidence
        
        if signal.signal_change:
            stats['trend_changes'] += 1
    
    def _write_json(self, signal: SignalEvent) -> None:
        """Write signal to JSON Lines file"""
        if self.json_file:
            try:
                json_line = json.dumps(signal.to_dict())
                self.json_file.write(json_line + '\n')
                self.json_file.flush()
            except Exception as e:
                logger.error(f"Error writing JSON: {e}")
    
    def _write_csv(self, signal: SignalEvent) -> None:
        """Write signal to CSV file"""
        if self.csv_file:
            try:
                row = signal.to_csv_row()
                
                # Initialize writer with headers on first write
                if self.csv_writer is None:
                    self.csv_writer = csv.DictWriter(
                        self.csv_file,
                        fieldnames=list(row.keys())
                    )
                    self.csv_writer.writeheader()
                
                self.csv_writer.writerow(row)
                self.csv_file.flush()
            except Exception as e:
                logger.error(f"Error writing CSV: {e}")
    
    def _print_console(self, signal: SignalEvent) -> None:
        """Print signal to console with color formatting"""
        try:
            # Choose color based on signal type
            if 'bullish' in signal.signal_type.lower():
                color = Colors.GREEN
                symbol = '▲'
            elif 'bearish' in signal.signal_type.lower():
                color = Colors.RED
                symbol = '▼'
            else:
                color = Colors.YELLOW
                symbol = '●'
            
            # Format timestamp
            ts = signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            
            # Build output line
            parts = [
                f"{Colors.BOLD}[{ts}]{Colors.RESET}",
                f"{Colors.CYAN}{signal.algorithm}{Colors.RESET}",
                f"{Colors.BLUE}{signal.symbol}{Colors.RESET}",
                f"{color}{symbol} {signal.signal_type.upper()}{Colors.RESET}",
                f"{Colors.MAGENTA}Conf: {signal.confidence:.2f}{Colors.RESET}"
            ]
            
            # Add reason if available
            if signal.reason:
                parts.append(f"- {signal.reason}")
            
            # Add key indicators
            if signal.indicators:
                indicator_strs = []
                for key, value in list(signal.indicators.items())[:3]:  # Show top 3
                    indicator_strs.append(f"{key}={value:.4f}")
                if indicator_strs:
                    parts.append(f"[{', '.join(indicator_strs)}]")
            
            # Print
            print(' '.join(parts), file=sys.stdout)
            sys.stdout.flush()
            
        except Exception as e:
            logger.error(f"Error printing to console: {e}")
    
    def get_statistics(self, symbol: Optional[str] = None,
                      algorithm: Optional[str] = None) -> Dict[str, Any]:
        """
        Get signal statistics
        
        Args:
            symbol: Filter by symbol (optional)
            algorithm: Filter by algorithm (optional)
        
        Returns:
            Statistics dictionary
        """
        # Filter signals
        filtered_signals = self.signals
        
        if symbol:
            filtered_signals = [s for s in filtered_signals if s.symbol == symbol]
        
        if algorithm:
            filtered_signals = [s for s in filtered_signals 
                              if s.algorithm == algorithm]
        
        if not filtered_signals:
            return {}
        
        # Calculate statistics
        total = len(filtered_signals)
        signal_types = defaultdict(int)
        total_confidence = 0.0
        trend_changes = 0
        
        for signal in filtered_signals:
            signal_types[signal.signal_type] += 1
            total_confidence += signal.confidence
            if signal.signal_change:
                trend_changes += 1
        
        avg_confidence = total_confidence / total if total > 0 else 0
        
        return {
            'total_signals': total,
            'signal_types': dict(signal_types),
            'avg_confidence': avg_confidence,
            'trend_changes': trend_changes,
            'signals_per_type': {
                k: (v / total * 100) for k, v in signal_types.items()
            }
        }
    
    def compute_trend_phases(self, symbol: str, algorithm: str) -> List[TrendPhase]:
        """
        Compute continuous trend phases from signals
        
        Args:
            symbol: Symbol to analyze
            algorithm: Algorithm to analyze
        
        Returns:
            List of TrendPhase objects
        """
        # Filter signals for this symbol/algorithm
        signals = [
            s for s in self.signals
            if s.symbol == symbol and s.algorithm == algorithm
        ]
        
        if not signals:
            return []
        
        # Sort by timestamp
        signals.sort(key=lambda s: s.timestamp)
        
        phases = []
        current_phase = None
        
        for i, signal in enumerate(signals):
            if current_phase is None:
                # Start first phase
                current_phase = {
                    'start_time': signal.timestamp,
                    'trend_type': signal.signal_type,
                    'confidences': [signal.confidence],
                    'signal_count': 1,
                    'price_start': signal.candle['close'] if signal.candle else 0
                }
            
            elif signal.signal_change:
                # End current phase and start new one
                end_time = signal.timestamp
                price_end = signals[i-1].candle['close'] if signals[i-1].candle else 0
                
                # Calculate phase metrics
                avg_confidence = sum(current_phase['confidences']) / len(current_phase['confidences'])
                duration = (end_time - current_phase['start_time']).total_seconds()
                price_change = 0
                if current_phase['price_start'] != 0:
                    price_change = ((price_end - current_phase['price_start']) / 
                                  current_phase['price_start'] * 100)
                
                # Create phase
                phase = TrendPhase(
                    start_time=current_phase['start_time'],
                    end_time=end_time,
                    trend_type=current_phase['trend_type'],
                    avg_confidence=avg_confidence,
                    signal_count=current_phase['signal_count'],
                    price_start=current_phase['price_start'],
                    price_end=price_end,
                    price_change_pct=price_change,
                    duration_seconds=duration,
                    algorithm=algorithm
                )
                phases.append(phase)
                
                # Start new phase
                current_phase = {
                    'start_time': signal.timestamp,
                    'trend_type': signal.signal_type,
                    'confidences': [signal.confidence],
                    'signal_count': 1,
                    'price_start': signal.candle['close'] if signal.candle else 0
                }
            else:
                # Continue current phase
                current_phase['confidences'].append(signal.confidence)
                current_phase['signal_count'] += 1
        
        # Close final phase
        if current_phase:
            end_time = signals[-1].timestamp
            price_end = signals[-1].candle['close'] if signals[-1].candle else 0
            
            avg_confidence = sum(current_phase['confidences']) / len(current_phase['confidences'])
            duration = (end_time - current_phase['start_time']).total_seconds()
            price_change = 0
            if current_phase['price_start'] != 0:
                price_change = ((price_end - current_phase['price_start']) / 
                              current_phase['price_start'] * 100)
            
            phase = TrendPhase(
                start_time=current_phase['start_time'],
                end_time=end_time,
                trend_type=current_phase['trend_type'],
                avg_confidence=avg_confidence,
                signal_count=current_phase['signal_count'],
                price_start=current_phase['price_start'],
                price_end=price_end,
                price_change_pct=price_change,
                duration_seconds=duration,
                algorithm=algorithm
            )
            phases.append(phase)
        
        # Store and return
        key = f"{symbol}_{algorithm}"
        self.trend_phases[key] = phases
        
        return phases
    
    def export_summary(self, filepath: Optional[str] = None) -> str:
        """
        Export summary statistics to JSON file
        
        Args:
            filepath: Output file path (optional)
        
        Returns:
            Path to exported file
        """
        if filepath is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = str(self.log_dir / f'summary_{timestamp}.json')
        
        summary = {
            'total_signals': len(self.signals),
            'statistics_by_symbol_algo': {},
            'trend_phases': {}
        }
        
        # Get unique symbol-algorithm combinations
        combinations = set(
            (s.symbol, s.algorithm) for s in self.signals
        )
        
        for symbol, algorithm in combinations:
            key = f"{symbol}_{algorithm}"
            
            # Get statistics
            stats = self.get_statistics(symbol=symbol, algorithm=algorithm)
            summary['statistics_by_symbol_algo'][key] = stats
            
            # Compute trend phases
            phases = self.compute_trend_phases(symbol, algorithm)
            summary['trend_phases'][key] = [p.to_dict() for p in phases]
        
        # Write to file
        with open(filepath, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Exported summary to {filepath}")
        return filepath
    
    def close(self) -> None:
        """Close all file handles"""
        if self.json_file:
            self.json_file.close()
        
        if self.csv_file:
            self.csv_file.close()
        
        logger.info("SignalLogger closed")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
