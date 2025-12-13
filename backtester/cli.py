"""
Command-line interface for playback control
"""

import cmd
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path

from src.playback.engine import PlaybackEngine, PlaybackState
from src.playback.data_provider import YFinanceDataProvider
from src.playback.algorithm_adapter import PlaybackAlgorithmAdapter
from src.playback.signal_logger import SignalLogger
from src.playback.visualizer import PlaybackVisualizer

logger = logging.getLogger(__name__)


class PlaybackCLI(cmd.Cmd):
    """Interactive CLI for playback control"""
    
    intro = """
╔══════════════════════════════════════════════════════════════╗
║          LumosTrade Data Playback Engine                    ║
║          Interactive Playback & Analysis                     ║
╚══════════════════════════════════════════════════════════════╝

Type 'help' to see available commands.
"""
    
    prompt = '(playback) > '
    
    def __init__(
        self,
        engine: PlaybackEngine,
        signal_logger: SignalLogger,
        visualizer: PlaybackVisualizer
    ):
        super().__init__()
        self.engine = engine
        self.signal_logger = signal_logger
        self.visualizer = visualizer
        self.candles = []
    
    def do_play(self, arg):
        """Start or resume playback"""
        try:
            self.engine.play()
            print("▶ Playback started")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_pause(self, arg):
        """Pause playback"""
        try:
            self.engine.pause()
            print("⏸ Playback paused")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_stop(self, arg):
        """Stop playback and reset to beginning"""
        try:
            self.engine.stop()
            print("⏹ Playback stopped")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_step(self, arg):
        """Step forward N candles (default: 1)
        Usage: step [N]
        """
        try:
            steps = int(arg) if arg else 1
            stepped = self.engine.step_forward(steps)
            print(f"⏭ Stepped forward {stepped} candles")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_back(self, arg):
        """Step backward N candles (default: 1)
        Usage: back [N]
        """
        try:
            steps = int(arg) if arg else 1
            stepped = self.engine.step_backward(steps)
            print(f"⏮ Stepped back {stepped} candles")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_speed(self, arg):
        """Set playback speed
        Usage: speed <multiplier>
        Examples: speed 1.0 (real-time), speed 5 (5x), speed 0 (max)
        """
        try:
            speed = float(arg)
            self.engine.set_speed(speed)
            print(f"⚡ Speed set to {speed}x")
        except ValueError:
            print("Error: Invalid speed value")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_seek(self, arg):
        """Seek to timestamp
        Usage: seek YYYY-MM-DD [HH:MM:SS]
        """
        try:
            # Parse timestamp
            if len(arg.split()) == 1:
                timestamp = datetime.strptime(arg, '%Y-%m-%d')
            else:
                timestamp = datetime.strptime(arg, '%Y-%m-%d %H:%M:%S')
            
            success = self.engine.seek_to_timestamp(timestamp)
            if success:
                print(f"⏩ Seeked to {timestamp}")
            else:
                print("Failed to seek")
        except ValueError:
            print("Error: Invalid timestamp format")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_status(self, arg):
        """Show current playback status"""
        try:
            state = self.engine.get_state()
            speed = self.engine.get_speed()
            progress = self.engine.get_progress()
            positions = self.engine.get_current_position()
            metrics = self.engine.get_metrics()
            
            print("\n" + "="*60)
            print(f"State:    {state.value.upper()}")
            print(f"Speed:    {speed}x")
            print(f"Progress: {progress:.1f}%")
            print(f"Candles:  {metrics['candles_processed']}/{metrics['total_candles']}")
            print(f"Signals:  {metrics['signals_emitted']}")
            print("\nPositions:")
            for symbol, pos in positions.items():
                print(f"  {symbol}: Index {pos['index']} | {pos['timestamp']} | Price: {pos['price']}")
            print("="*60 + "\n")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_stats(self, arg):
        """Show signal statistics
        Usage: stats [symbol] [algorithm]
        """
        try:
            parts = arg.split()
            symbol = parts[0] if len(parts) > 0 else None
            algorithm = parts[1] if len(parts) > 1 else None
            
            stats = self.signal_logger.get_statistics(symbol, algorithm)
            
            if not stats:
                print("No statistics available")
                return
            
            print("\n" + "="*60)
            print("Signal Statistics")
            print("="*60)
            print(f"Total Signals:   {stats['total_signals']}")
            print(f"Avg Confidence:  {stats['avg_confidence']:.2f}")
            print(f"Trend Changes:   {stats['trend_changes']}")
            print("\nSignal Types:")
            for sig_type, count in stats['signal_types'].items():
                pct = stats['signals_per_type'][sig_type]
                print(f"  {sig_type}: {count} ({pct:.1f}%)")
            print("="*60 + "\n")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_visualize(self, arg):
        """Generate visualizations
        Usage: 
            visualize dashboard [symbol] [algorithm]  - Technical analysis dashboard
            visualize interactive [symbol] [algorithm] - Interactive dashboard
            visualize comparison [symbol]              - Compare algorithms
            visualize heatmap [symbol]                 - Performance heatmap
            visualize price [symbol] [algorithm]       - Price with signals
            visualize timeline [symbol] [algorithm]    - Trend timeline
            visualize all [symbol]                     - Generate all charts
        """
        try:
            parts = arg.split()
            viz_type = parts[0].lower() if parts else 'all'
            symbol = parts[1] if len(parts) > 1 else None
            algorithm = parts[2] if len(parts) > 2 else None
            
            # Get available data
            if not self.signal_logger.signals:
                print("❌ No signals to visualize. Run playback first.")
                return
            
            # Get unique symbols and algorithms
            all_symbols = set(s.symbol for s in self.signal_logger.signals)
            all_algorithms = set(s.algorithm for s in self.signal_logger.signals)
            
            # Default to first symbol if not specified
            if not symbol and all_symbols:
                symbol = list(all_symbols)[0]
            
            # Get candles and indicators from engine (if available)
            candles = self._get_candles_for_symbol(symbol) if symbol else []
            
            if viz_type == 'dashboard':
                self._generate_dashboard(symbol, algorithm, candles)
            
            elif viz_type == 'interactive':
                self._generate_interactive(symbol, algorithm, candles)
            
            elif viz_type == 'comparison':
                self._generate_comparison(symbol, candles)
            
            elif viz_type == 'heatmap':
                self._generate_heatmap(symbol)
            
            elif viz_type == 'price':
                self._generate_price_chart(symbol, algorithm, candles)
            
            elif viz_type == 'timeline':
                self._generate_timeline(symbol, algorithm)
            
            elif viz_type == 'all':
                print(f"\n{'='*60}")
                print("Generating all visualizations...")
                print(f"{'='*60}\n")
                self._generate_all(symbol, candles)
            
            else:
                print(f"Unknown visualization type: {viz_type}")
                print("Use 'help visualize' to see available options")
        
        except Exception as e:
            logger.error(f"Error generating visualization: {e}", exc_info=True)
            print(f"❌ Error: {e}")
    
    def _get_candles_for_symbol(self, symbol: str):
        """Get candles for a symbol from engine or fetch from yfinance"""
        try:
            # First, try to get from engine's data provider
            if hasattr(self.engine, 'data') and symbol in self.engine.data:
                from src.playback.models import CandleData
                candles = []
                for _, row in self.engine.data[symbol].iterrows():
                    candles.append(CandleData(
                        timestamp=row.name,
                        symbol=symbol,
                        open=row['open'],
                        high=row['high'],
                        low=row['low'],
                        close=row['close'],
                        volume=row.get('volume', None)
                    ))
                if candles:
                    return candles
        except Exception as e:
            logger.warning(f"Could not get candles from engine: {e}")
        
        # If no candles from engine, fetch from yfinance
        try:
            logger.info(f"Fetching candles for {symbol} from yfinance...")
            return self._fetch_candles_from_yfinance(symbol)
        except Exception as e:
            logger.error(f"Could not fetch candles from yfinance: {e}")
            return []
    
    def _fetch_candles_from_yfinance(self, symbol: str, period: str = "3mo", interval: str = "1h"):
        """Fetch candles from yfinance"""
        try:
            import yfinance as yf
            from src.playback.models import CandleData
            import pandas as pd
            
            print(f"   📡 Fetching {period} of {interval} data from yfinance...")
            
            # Download data
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                logger.warning(f"No data returned from yfinance for {symbol}")
                return []
            
            # Convert to CandleData objects
            candles = []
            for timestamp, row in df.iterrows():
                candles.append(CandleData(
                    timestamp=timestamp.to_pydatetime(),
                    symbol=symbol,
                    open=row['Open'],
                    high=row['High'],
                    low=row['Low'],
                    close=row['Close'],
                    volume=row.get('Volume', None)
                ))
            
            print(f"   ✓ Fetched {len(candles)} candles from yfinance")
            return candles
            
        except ImportError:
            logger.error("yfinance not installed. Install with: pip install yfinance")
            return []
        except Exception as e:
            logger.error(f"Error fetching from yfinance: {e}", exc_info=True)
            return []
    
    def _get_indicators_for_algorithm(self, symbol: str, algorithm: str):
        """Get indicators from algorithm adapter if available"""
        # This would need algorithm adapters to expose their indicators
        # For now, return empty dict - algorithms need to implement this
        return {}
    
    def _generate_dashboard(self, symbol: str, algorithm: str, candles: list):
        """Generate technical analysis dashboard"""
        print(f"📊 Generating technical dashboard for {symbol}...")
        
        # Get candles if not provided
        fetched_from_yfinance = False
        if not candles:
            print(f"   ⚠ No candles in engine, fetching from yfinance...")
            candles = self._fetch_candles_from_yfinance(symbol)
            fetched_from_yfinance = True
            if not candles:
                print(f"   ❌ Could not get candle data for {symbol}")
                return
        
        signals = [s for s in self.signal_logger.signals if s.symbol == symbol]
        if algorithm:
            signals = [s for s in signals if s.algorithm == algorithm]
        
        # Get indicators - calculate if fetched from yfinance, otherwise from signals
        if fetched_from_yfinance:
            indicators = self._calculate_indicators_for_candles(candles)
        else:
            indicators = self._collect_indicators_from_signals(signals, len(candles))
        
        algo_name = algorithm or "All Algorithms"
        filepath = self.visualizer.create_technical_dashboard(
            candles=candles,
            indicators=indicators,
            signals=signals,
            algorithm_name=algo_name,
            symbol=symbol
        )
        
        if filepath:
            print(f"   ✓ Saved: {filepath}")
        else:
            print(f"   ❌ Failed to generate dashboard")
    
    def _generate_interactive(self, symbol: str, algorithm: str, candles: list):
        """Generate interactive dashboard"""
        print(f"🌐 Generating interactive dashboard for {symbol}...")
        
        # Get candles if not provided
        fetched_from_yfinance = False
        if not candles:
            print(f"   ⚠ No candles in engine, fetching from yfinance...")
            candles = self._fetch_candles_from_yfinance(symbol)
            fetched_from_yfinance = True
            if not candles:
                print(f"   ❌ Could not get candle data for {symbol}")
                return
        
        signals = [s for s in self.signal_logger.signals if s.symbol == symbol]
        if algorithm:
            signals = [s for s in signals if s.algorithm == algorithm]
        
        # Get indicators
        if fetched_from_yfinance:
            indicators = self._calculate_indicators_for_candles(candles)
        else:
            indicators = self._collect_indicators_from_signals(signals, len(candles))
        
        algo_name = algorithm or "All Algorithms"
        filepath = self.visualizer.create_interactive_dashboard(
            candles=candles,
            indicators=indicators,
            signals=signals,
            algorithm_name=algo_name,
            symbol=symbol
        )
        
        if filepath:
            print(f"   ✓ Saved: {filepath}")
            print(f"   💡 Open in browser to interact with the chart")
        else:
            print(f"   ❌ Failed to generate interactive dashboard")
    
    def _generate_comparison(self, symbol: str, candles: list):
        """Generate algorithm comparison"""
        print(f"🔄 Generating algorithm comparison for {symbol}...")
        
        # Get candles if not provided
        fetched_from_yfinance = False
        if not candles:
            print(f"   ⚠ No candles in engine, fetching from yfinance...")
            candles = self._fetch_candles_from_yfinance(symbol)
            fetched_from_yfinance = True
            if not candles:
                print(f"   ❌ Could not get candle data for {symbol}")
                return
        
        # Group signals by algorithm
        algorithms = {}
        for signal in self.signal_logger.signals:
            if signal.symbol == symbol:
                if signal.algorithm not in algorithms:
                    algorithms[signal.algorithm] = {'signals': [], 'indicators': {}}
                algorithms[signal.algorithm]['signals'].append(signal)
        
        # Collect indicators for each algorithm
        if fetched_from_yfinance:
            # Calculate indicators once for all algorithms
            calculated_indicators = self._calculate_indicators_for_candles(candles)
            for algo, data in algorithms.items():
                data['indicators'] = calculated_indicators
        else:
            for algo, data in algorithms.items():
                data['indicators'] = self._collect_indicators_from_signals(
                    data['signals'], len(candles)
                )
        
        filepath = self.visualizer.create_algorithm_comparison_dashboard(
            candles=candles,
            algorithms_data=algorithms,
            symbol=symbol
        )
        
        if filepath:
            print(f"   ✓ Saved: {filepath}")
        else:
            print(f"   ❌ Failed to generate comparison")
    
    def _generate_heatmap(self, symbol: str):
        """Generate performance heatmap"""
        print(f"🔥 Generating performance heatmap for {symbol}...")
        
        signals = [s for s in self.signal_logger.signals if s.symbol == symbol]
        candles = self._get_candles_for_symbol(symbol)
        
        filepath = self.visualizer.create_performance_heatmap(
            signals=signals,
            candles=candles,
            symbol=symbol
        )
        
        if filepath:
            print(f"   ✓ Saved: {filepath}")
        else:
            print(f"   ❌ Failed to generate heatmap")
    
    def _generate_price_chart(self, symbol: str, algorithm: str, candles: list):
        """Generate price chart with signals"""
        print(f"📈 Generating price chart for {symbol}...")
        
        # Get candles if not provided
        fetched_from_yfinance = False
        if not candles:
            print(f"   ⚠ No candles in engine, fetching from yfinance...")
            candles = self._fetch_candles_from_yfinance(symbol)
            fetched_from_yfinance = True
            if not candles:
                print(f"   ❌ Could not get candle data for {symbol}")
                return
        
        signals = [s for s in self.signal_logger.signals if s.symbol == symbol]
        if algorithm:
            signals = [s for s in signals if s.algorithm == algorithm]
        
        # Get indicators
        if fetched_from_yfinance:
            indicators = self._calculate_indicators_for_candles(candles)
        else:
            indicators = self._collect_indicators_from_signals(signals, len(candles))
        
        algo_name = algorithm or "All Algorithms"
        filepath = self.visualizer.plot_price_with_signals(
            candles=candles,
            signals=signals,
            indicators=indicators,
            title=f"{symbol} - {algo_name}"
        )
        
        if filepath:
            print(f"   ✓ Saved: {filepath}")
        else:
            print(f"   ❌ Failed to generate price chart")
    
    def _generate_timeline(self, symbol: str, algorithm: str):
        """Generate trend timeline"""
        print(f"⏱ Generating timeline for {symbol}...")
        
        phases = self.signal_logger.compute_trend_phases(symbol, algorithm)
        
        if not phases:
            print(f"   ⚠ No trend phases found")
            return
        
        algo_name = algorithm or "All Algorithms"
        filepath = self.visualizer.plot_trend_timeline(
            phases=phases,
            symbol=symbol,
            algorithm=algo_name
        )
        
        if filepath:
            print(f"   ✓ Saved: {filepath}")
        else:
            print(f"   ❌ Failed to generate timeline")
    
    def _generate_all(self, symbol: str, candles: list):
        """Generate all visualizations"""
        self._generate_dashboard(symbol, None, candles)
        self._generate_interactive(symbol, None, candles)
        self._generate_comparison(symbol, candles)
        self._generate_heatmap(symbol)
        self._generate_timeline(symbol, None)
        print(f"\n{'='*60}")
        print("✓ All visualizations generated successfully!")
        print(f"{'='*60}\n")
    
    def _calculate_indicators_for_candles(self, candles: list) -> dict:
        """Calculate technical indicators for candles using IndicatorCalculator"""
        try:
            from feature_engine.indicator_calculator import IndicatorCalculator
            
            calculator = IndicatorCalculator()
            indicators = calculator.calculate_indicators(candles)
            
            if indicators:
                print(f"   ✓ Calculated {len(indicators)} indicators")
            else:
                print(f"   ⚠ No indicators calculated")
            
            return indicators
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}", exc_info=True)
            print(f"   ⚠ Could not calculate indicators: {e}")
            return {}
    
    def _collect_indicators_from_signals(self, signals: list, num_candles: int) -> dict:
        """Collect indicators from signal metadata"""
        indicators = {}
        
        # Initialize indicator lists
        indicator_names = set()
        for signal in signals:
            if hasattr(signal, 'indicators') and signal.indicators:
                indicator_names.update(signal.indicators.keys())
        
        # Create lists for each indicator
        for name in indicator_names:
            indicators[name] = [None] * num_candles
        
        # Populate indicators from signals (approximate)
        # Note: This is a simplified approach - ideally algorithms would expose full history
        for signal in signals:
            if hasattr(signal, 'indicators') and signal.indicators:
                for name, value in signal.indicators.items():
                    if name in indicators:
                        # Store at approximate index (needs proper timestamp mapping)
                        indicators[name][-1] = value
        
        return indicators
    
    def do_export(self, arg):
        """Export summary and logs
        Usage: export [filename]
        """
        try:
            filename = arg if arg else None
            filepath = self.signal_logger.export_summary(filename)
            print(f"✓ Exported summary to: {filepath}")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_quit(self, arg):
        """Quit the application"""
        print("Stopping playback and closing...")
        try:
            self.engine.stop()
            self.signal_logger.close()
        except:
            pass
        return True
    
    def do_exit(self, arg):
        """Exit the application (alias for quit)"""
        return self.do_quit(arg)
    
    def do_EOF(self, arg):
        """Handle EOF (Ctrl+D)"""
        print()
        return self.do_quit(arg)
    
    def emptyline(self):
        """Do nothing on empty line"""
        pass
    
    def default(self, line):
        """Handle unknown commands"""
        print(f"Unknown command: {line}")
        print("Type 'help' for available commands")


def create_playback_session(
    symbols: list,
    start_date: datetime,
    end_date: datetime,
    interval: str = '1h',
    log_dir: str = './playback_logs',
    cache_dir: Optional[str] = None
) -> tuple:
    """
    Create a playback session with all components
    
    Args:
        symbols: List of symbols to play
        start_date: Start datetime
        end_date: End datetime
        interval: Data interval
        log_dir: Log directory
        cache_dir: Cache directory
    
    Returns:
        Tuple of (engine, signal_logger, visualizer)
    """
    # Create data provider
    data_provider = YFinanceDataProvider(cache_dir=cache_dir)
    
    # Create playback engine
    engine = PlaybackEngine(
        data_provider=data_provider,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        interval=interval
    )
    
    # Load data
    print("Loading historical data...")
    engine.load_data()
    print(f"✓ Loaded {engine.metrics.total_candles} candles")
    
    # Create signal logger
    signal_logger = SignalLogger(log_dir=log_dir)
    
    # Register signal callback
    engine.register_signal_callback(signal_logger.log_signal)
    
    # Create visualizer
    visualizer = PlaybackVisualizer(output_dir=log_dir)
    
    return engine, signal_logger, visualizer
