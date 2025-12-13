"""
Visualization module for creating charts and timeline views
Enhanced with comprehensive technical analysis dashboards
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import mplfinance as mpf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import numpy as np
from typing import List, Dict, Any, Optional, Tuple, Union
from pathlib import Path
import logging
import warnings

from src.playback.models import SignalEvent, TrendPhase, CandleData

logger = logging.getLogger(__name__)
warnings.filterwarnings('ignore', category=FutureWarning)


class PlaybackVisualizer:
    """
    Creates visualizations for playback analysis:
    - Price charts with signal overlays
    - Timeline views showing trend transitions
    """
    
    def __init__(self, output_dir: str):
        """
        Initialize visualizer
        
        Args:
            output_dir: Directory to save visualization outputs
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Style configuration
        plt.style.use('seaborn-v0_8-darkgrid')
        
        logger.info(f"PlaybackVisualizer initialized (output: {output_dir})")
    
    def plot_price_with_signals(
        self,
        candles: List[CandleData],
        signals: List[SignalEvent],
        indicators: Optional[Dict[str, List[float]]] = None,
        title: Optional[str] = None,
        filename: Optional[str] = None
    ) -> str:
        """
        Create comprehensive price chart with signals and indicators
        
        Args:
            candles: List of CandleData objects
            signals: List of SignalEvent objects
            indicators: Dictionary of indicator name -> values list
            title: Chart title
            filename: Output filename (auto-generated if None)
        
        Returns:
            Path to saved chart
        """
        if not candles:
            logger.warning("No candles provided for plotting")
            return ""
        
        # Convert candles to DataFrame for mplfinance
        df = self._candles_to_dataframe(candles)
        
        # Create figure with subplots
        fig = plt.figure(figsize=(16, 10))
        
        # Number of subplots
        num_plots = 2  # Price + Confidence
        if indicators:
            num_plots += 1  # Add indicators subplot
        
        # Main price chart
        ax1 = plt.subplot(num_plots, 1, 1)
        
        # Plot candlesticks
        self._plot_candlesticks(ax1, df)
        
        # Overlay indicators (e.g., SMA line)
        if indicators:
            self._overlay_indicators(ax1, df.index, indicators)
        
        # Mark signals
        self._mark_signals_on_chart(ax1, df, signals)
        
        # Set title and labels
        if title:
            ax1.set_title(title, fontsize=14, fontweight='bold')
        ax1.set_ylabel('Price', fontsize=12)
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='upper left')
        
        # Confidence subplot
        ax2 = plt.subplot(num_plots, 1, 2, sharex=ax1)
        self._plot_confidence_evolution(ax2, signals)
        
        # Indicators subplot (if provided)
        if indicators and num_plots > 2:
            ax3 = plt.subplot(num_plots, 1, 3, sharex=ax1)
            self._plot_indicators_panel(ax3, df.index, indicators)
        
        # Format x-axis
        plt.xlabel('Time', fontsize=12)
        
        # Tight layout
        plt.tight_layout()
        
        # Save figure
        if filename is None:
            symbol = signals[0].symbol if signals else 'unknown'
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'price_signals_{symbol}_{timestamp}.png'
        
        filepath = self.output_dir / filename
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        
        logger.info(f"Saved price chart: {filepath}")
        return str(filepath)
    
    def _candles_to_dataframe(self, candles: List[CandleData]) -> pd.DataFrame:
        """Convert candles to pandas DataFrame"""
        data = []
        for candle in candles:
            data.append({
                'timestamp': candle.timestamp,
                'open': candle.open,
                'high': candle.high,
                'low': candle.low,
                'close': candle.close,
                'volume': candle.volume or 0
            })
        
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        return df
    
    def _plot_candlesticks(self, ax, df: pd.DataFrame) -> None:
        """Plot candlestick chart"""
        # Plot candlesticks manually for more control
        for idx in range(len(df)):
            timestamp = df.index[idx]
            row = df.iloc[idx]
            
            # Determine color
            color = 'green' if row['close'] >= row['open'] else 'red'
            
            # Draw high-low line
            ax.plot([timestamp, timestamp], [row['low'], row['high']],
                   color=color, linewidth=0.5, alpha=0.8)
            
            # Draw open-close box
            height = abs(row['close'] - row['open'])
            bottom = min(row['open'], row['close'])
            
            rect = Rectangle(
                (mdates.date2num(timestamp) - 0.0001, bottom),
                0.0002, height,
                facecolor=color, edgecolor=color, alpha=0.7
            )
            ax.add_patch(rect)
    
    def _overlay_indicators(
        self,
        ax,
        timestamps,
        indicators: Dict[str, List[float]]
    ) -> None:
        """Overlay indicator lines on price chart"""
        # Common indicators to overlay on price chart
        overlay_indicators = ['sma_value', 'ema', 'bb_upper', 'bb_lower']
        
        for name, values in indicators.items():
            if any(ind in name.lower() for ind in overlay_indicators):
                if len(values) == len(timestamps):
                    ax.plot(timestamps, values, label=name, linewidth=2, alpha=0.7)
    
    def _mark_signals_on_chart(
        self,
        ax,
        df: pd.DataFrame,
        signals: List[SignalEvent]
    ) -> None:
        """Mark signal events on price chart"""
        for signal in signals:
            # Find price at signal time
            try:
                # Get closest timestamp
                idx = df.index.get_indexer([signal.timestamp], method='nearest')[0]
                timestamp = df.index[idx]
                price = df.iloc[idx]['close']
                
                # Choose marker based on signal type
                if 'bullish' in signal.signal_type.lower():
                    marker = '^'
                    color = 'green'
                    label = f'Buy ({signal.confidence:.2f})'
                elif 'bearish' in signal.signal_type.lower():
                    marker = 'v'
                    color = 'red'
                    label = f'Sell ({signal.confidence:.2f})'
                else:
                    marker = 'o'
                    color = 'yellow'
                    label = f'Neutral ({signal.confidence:.2f})'
                
                # Plot marker
                ax.scatter(timestamp, price, marker=marker, s=200,
                          color=color, edgecolors='black', linewidths=1.5,
                          alpha=0.8, zorder=5)
                
                # Add annotation with reason
                if signal.reason:
                    ax.annotate(
                        signal.reason[:30] + '...' if len(signal.reason) > 30 else signal.reason,
                        xy=(timestamp, price),
                        xytext=(10, 10),
                        textcoords='offset points',
                        fontsize=8,
                        bbox=dict(boxstyle='round,pad=0.3', facecolor=color, alpha=0.3),
                        arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0')
                    )
            
            except Exception as e:
                logger.warning(f"Failed to mark signal: {e}")
    
    def _plot_confidence_evolution(self, ax, signals: List[SignalEvent]) -> None:
        """Plot confidence evolution over time"""
        if not signals:
            return
        
        timestamps = [s.timestamp for s in signals]
        confidences = [s.confidence for s in signals]
        
        # Color by signal type
        colors = []
        for s in signals:
            if 'bullish' in s.signal_type.lower():
                colors.append('green')
            elif 'bearish' in s.signal_type.lower():
                colors.append('red')
            else:
                colors.append('yellow')
        
        ax.scatter(timestamps, confidences, c=colors, s=50, alpha=0.6)
        ax.plot(timestamps, confidences, 'b-', alpha=0.3, linewidth=1)
        
        ax.set_ylabel('Confidence', fontsize=12)
        ax.set_ylim(0, 1.1)
        ax.axhline(y=0.5, color='gray', linestyle='--', alpha=0.5)
        ax.grid(True, alpha=0.3)
        ax.set_title('Signal Confidence Evolution', fontsize=11)
    
    def _plot_indicators_panel(
        self,
        ax,
        timestamps,
        indicators: Dict[str, List[float]]
    ) -> None:
        """Plot indicators in separate panel"""
        # Plot non-price indicators (MACD, RSI, etc.)
        separate_indicators = ['macd', 'rsi', 'adx', 'histogram']
        
        for name, values in indicators.items():
            if any(ind in name.lower() for ind in separate_indicators):
                if len(values) == len(timestamps):
                    ax.plot(timestamps, values, label=name, linewidth=2, alpha=0.7)
        
        ax.set_ylabel('Indicator Value', fontsize=12)
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
        ax.set_title('Technical Indicators', fontsize=11)
    
    def plot_trend_timeline(
        self,
        phases: List[TrendPhase],
        symbol: str,
        algorithm: str,
        filename: Optional[str] = None
    ) -> str:
        """
        Create horizontal timeline showing trend transitions
        
        Args:
            phases: List of TrendPhase objects
            symbol: Symbol name
            algorithm: Algorithm name
            filename: Output filename
        
        Returns:
            Path to saved timeline
        """
        if not phases:
            logger.warning("No trend phases provided")
            return ""
        
        # Create figure
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 8),
                                        gridspec_kw={'height_ratios': [3, 1]})
        
        # Sort phases by start time
        phases = sorted(phases, key=lambda p: p.start_time)
        
        # Plot timeline
        self._plot_phase_timeline(ax1, phases)
        
        # Plot phase statistics
        self._plot_phase_statistics(ax2, phases)
        
        # Set title
        title = f'Trend Timeline: {symbol} - {algorithm}'
        fig.suptitle(title, fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        
        # Save figure
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'timeline_{symbol}_{algorithm}_{timestamp}.png'
        
        filepath = self.output_dir / filename
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)
        
        logger.info(f"Saved timeline: {filepath}")
        return str(filepath)
    
    def _plot_phase_timeline(self, ax, phases: List[TrendPhase]) -> None:
        """Plot horizontal timeline with colored phase segments"""
        # Color mapping
        color_map = {
            'bullish_trend': 'green',
            'bullish': 'green',
            'bearish_trend': 'red',
            'bearish': 'red',
            'sideways': 'yellow',
            'neutral': 'gray'
        }
        
        y_pos = 0.5
        height = 0.3
        
        for phase in phases:
            # Get color
            color = color_map.get(phase.trend_type, 'gray')
            
            # Calculate width (duration)
            start_num = mdates.date2num(phase.start_time)
            end_num = mdates.date2num(phase.end_time)
            width = end_num - start_num
            
            # Draw rectangle
            rect = Rectangle(
                (start_num, y_pos - height/2),
                width, height,
                facecolor=color, edgecolor='black', linewidth=1, alpha=0.7
            )
            ax.add_patch(rect)
            
            # Add label with confidence
            mid_point = start_num + width / 2
            ax.text(
                mid_point, y_pos,
                f'{phase.avg_confidence:.2f}\n{phase.duration_hours:.1f}h',
                ha='center', va='center',
                fontsize=8, fontweight='bold'
            )
            
            # Mark transition points
            ax.axvline(x=start_num, color='black', linestyle='--',
                      alpha=0.3, linewidth=0.5)
        
        # Format axes
        ax.set_ylim(0, 1)
        ax.set_xlim(
            mdates.date2num(phases[0].start_time),
            mdates.date2num(phases[-1].end_time)
        )
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        ax.set_yticks([])
        ax.set_title('Trend Phase Timeline', fontsize=12)
        ax.grid(True, axis='x', alpha=0.3)
        
        # Legend
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='green', edgecolor='black', label='Bullish'),
            Patch(facecolor='red', edgecolor='black', label='Bearish'),
            Patch(facecolor='yellow', edgecolor='black', label='Sideways')
        ]
        ax.legend(handles=legend_elements, loc='upper right')
    
    def _plot_phase_statistics(self, ax, phases: List[TrendPhase]) -> None:
        """Plot statistics about trend phases"""
        # Count phase types
        phase_counts = {}
        total_duration = {}
        
        for phase in phases:
            trend = phase.trend_type
            phase_counts[trend] = phase_counts.get(trend, 0) + 1
            total_duration[trend] = total_duration.get(trend, 0) + phase.duration_hours
        
        # Create bar chart
        trends = list(phase_counts.keys())
        counts = [phase_counts[t] for t in trends]
        durations = [total_duration[t] for t in trends]
        
        x = range(len(trends))
        width = 0.35
        
        ax.bar([i - width/2 for i in x], counts, width, label='Count', alpha=0.8)
        ax.bar([i + width/2 for i in x], durations, width, label='Duration (hours)', alpha=0.8)
        
        ax.set_xticks(x)
        ax.set_xticklabels(trends, rotation=0)
        ax.set_ylabel('Value')
        ax.set_title('Phase Statistics', fontsize=12)
        ax.legend()
        ax.grid(True, axis='y', alpha=0.3)
    
    def create_interactive_timeline(
        self,
        phases: List[TrendPhase],
        candles: List[CandleData],
        symbol: str,
        algorithm: str,
        filename: Optional[str] = None
    ) -> str:
        """
        Create interactive HTML timeline using Plotly
        
        Args:
            phases: List of TrendPhase objects
            candles: List of CandleData objects
            symbol: Symbol name
            algorithm: Algorithm name
            filename: Output filename
        
        Returns:
            Path to saved HTML file
        """
        # Create subplots
        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.7, 0.3],
            subplot_titles=('Price Action with Trend Phases', 'Confidence Evolution'),
            vertical_spacing=0.1
        )
        
        # Convert candles to DataFrame
        df = self._candles_to_dataframe(candles)
        
        # Add candlestick chart
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Price'
            ),
            row=1, col=1
        )
        
        # Add phase backgrounds
        for phase in phases:
            color = self._get_phase_color(phase.trend_type)
            
            fig.add_vrect(
                x0=phase.start_time,
                x1=phase.end_time,
                fillcolor=color,
                opacity=0.2,
                layer='below',
                line_width=0,
                row=1, col=1
            )
        
        # Add confidence line
        timestamps = [p.start_time for p in phases]
        confidences = [p.avg_confidence for p in phases]
        
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=confidences,
                mode='lines+markers',
                name='Confidence',
                line=dict(color='blue', width=2)
            ),
            row=2, col=1
        )
        
        # Update layout
        fig.update_layout(
            title=f'Interactive Timeline: {symbol} - {algorithm}',
            xaxis_rangeslider_visible=False,
            height=800,
            showlegend=True,
            hovermode='x unified'
        )
        
        # Save to HTML
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'timeline_interactive_{symbol}_{algorithm}_{timestamp}.html'
        
        filepath = self.output_dir / filename
        fig.write_html(str(filepath))
        
        logger.info(f"Saved interactive timeline: {filepath}")
        return str(filepath)
    
    def _get_phase_color(self, trend_type: str) -> str:
        """Get color for trend type"""
        color_map = {
            'bullish_trend': 'green',
            'bullish': 'green',
            'bearish_trend': 'red',
            'bearish': 'red',
            'sideways': 'yellow',
            'neutral': 'gray'
        }
        return color_map.get(trend_type, 'gray')
    
    def create_technical_dashboard(
        self,
        candles: List[CandleData],
        indicators: Dict[str, List[float]],
        signals: Optional[List[SignalEvent]] = None,
        algorithm_name: str = "Technical Analysis",
        symbol: Optional[str] = None,
        filename: Optional[str] = None
    ) -> str:
        """
        Create comprehensive technical analysis dashboard similar to professional trading platforms
        
        Features:
        - Main price chart with candlesticks
        - Multiple moving averages (SMA, EMA)
        - SuperTrend indicator overlay
        - Volume bars with color coding
        - MACD indicator panel
        - RSI indicator panel
        - ADX trend strength panel
        - Signal markers with annotations
        
        Args:
            candles: List of CandleData objects
            indicators: Dictionary containing all indicator values
            signals: Optional list of SignalEvent objects
            algorithm_name: Name of the trading algorithm
            symbol: Symbol being analyzed
            filename: Optional output filename
        
        Returns:
            Path to saved dashboard image
        """
        try:
            if not candles:
                logger.warning("No candles provided for technical dashboard")
                return ""
            
            # Convert candles to DataFrame
            df = self._candles_to_dataframe(candles)
            symbol = symbol or (signals[0].symbol if signals else 'Unknown')
            
            # Create figure with cleaner 4-panel layout
            fig = plt.figure(figsize=(20, 12))
            gs = fig.add_gridspec(4, 1, height_ratios=[3.5, 1, 1.2, 1.2], hspace=0.15)
            
            # Create subplots
            ax_price = fig.add_subplot(gs[0])
            ax_volume = fig.add_subplot(gs[1], sharex=ax_price)
            ax_macd = fig.add_subplot(gs[2], sharex=ax_price)
            ax_oscillators = fig.add_subplot(gs[3], sharex=ax_price)
            
            # 1. MAIN PRICE CHART - Price action with key moving averages only
            self._plot_price_panel_clean(ax_price, df, indicators, signals, algorithm_name)
            
            # 2. VOLUME PANEL - Cleaner volume bars
            self._plot_volume_panel_clean(ax_volume, df)
            
            # 3. MACD PANEL - Standard MACD with histogram
            self._plot_macd_panel_clean(ax_macd, df.index, indicators)
            
            # 4. OSCILLATORS PANEL - Combined RSI and Stochastic
            self._plot_oscillators_panel(ax_oscillators, df.index, indicators)
            
            # Format x-axis (only show on bottom plot)
            for ax in [ax_price, ax_volume, ax_macd]:
                plt.setp(ax.get_xticklabels(), visible=False)
            
            ax_oscillators.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax_oscillators.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.setp(ax_oscillators.xaxis.get_majorticklabels(), rotation=45, ha='right')
            
            # Main title
            title = f"{symbol} - Technical Analysis Dashboard\n{algorithm_name}"
            if candles:
                title += f" | {candles[0].timestamp.strftime('%Y-%m-%d')} to {candles[-1].timestamp.strftime('%Y-%m-%d')}"
            fig.suptitle(title, fontsize=16, fontweight='bold', y=0.995)
            
            # Save figure
            if filename is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'technical_dashboard_{symbol}_{timestamp}.png'
            
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=300, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            
            logger.info(f"Saved technical dashboard: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error creating technical dashboard: {e}", exc_info=True)
            return ""
    
    def _plot_price_panel(
        self,
        ax,
        df: pd.DataFrame,
        indicators: Dict[str, List[float]],
        signals: Optional[List[SignalEvent]],
        algorithm_name: str
    ) -> None:
        """Plot main price panel with candlesticks, moving averages, and SuperTrend"""
        try:
            num_candles = len(df)
            
            # Use line chart for large datasets (cleaner), candlesticks for smaller datasets
            if num_candles > 500:
                # Line chart with price range for clarity
                ax.plot(df.index, df['close'], color='#2962FF', linewidth=1.5, 
                       label='Close Price', zorder=3)
                ax.fill_between(df.index, df['low'], df['high'], 
                               alpha=0.1, color='#2962FF')
            else:
                # Plot candlesticks for smaller datasets
                for idx in range(len(df)):
                    timestamp = df.index[idx]
                    row = df.iloc[idx]
                    
                    is_bullish = row['close'] >= row['open']
                    color = '#26A69A' if is_bullish else '#EF5350'
                    edge_color = '#1B5E20' if is_bullish else '#B71C1C'
                    
                    # Draw high-low line
                    ax.plot([timestamp, timestamp], [row['low'], row['high']],
                           color=edge_color, linewidth=0.8, alpha=0.9, zorder=2)
                    
                    # Draw open-close body
                    height = abs(row['close'] - row['open'])
                    if height < 0.001:  # Doji
                        height = row['high'] - row['low']
                        height = max(height * 0.01, 0.001)
                    
                    bottom = min(row['open'], row['close'])
                    width = mdates.date2num(timestamp) * 0.0004
                    
                    rect = Rectangle(
                        (mdates.date2num(timestamp) - width/2, bottom),
                        width, height,
                        facecolor=color, edgecolor=edge_color, 
                        alpha=0.9, linewidth=0.8, zorder=3
                    )
                    ax.add_patch(rect)
            
            # Plot Moving Averages
            self._plot_moving_averages(ax, df.index, indicators)
            
            # Plot SuperTrend
            self._plot_supertrend(ax, df.index, indicators)
            
            # Mark signals
            if signals:
                self._mark_signals_enhanced(ax, df, signals)
            
            ax.set_ylabel('Price', fontsize=11, fontweight='bold')
            ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
            ax.legend(loc='upper left', fontsize=9, framealpha=0.9, ncol=2)
            ax.set_title(f'{algorithm_name} - Price Action', 
                        fontsize=12, fontweight='bold', pad=10)
            
        except Exception as e:
            logger.error(f"Error plotting price panel: {e}")
    
    def _plot_moving_averages(self, ax, timestamps, indicators: Dict[str, List[float]]) -> None:
        """Plot multiple moving averages with different styles"""
        try:
            ma_configs = [
                ('sma_50', 'SMA 50', '#FF6B6B', '-', 2),
                ('sma_12', 'SMA 12', '#4ECDC4', '-', 2),
                ('sma_26', 'SMA 26', '#FFA07A', '-', 2),
                ('ema_12', 'EMA 12', '#95E1D3', '--', 2),
                ('ema_26', 'EMA 26', '#F38181', '--', 2),
                ('sma_value', 'SMA', '#1E88E5', '-', 2.5),
            ]
            
            for key, label, color, style, width in ma_configs:
                if key in indicators:
                    values = indicators[key]
                    if len(values) == len(timestamps):
                        # Filter out None values
                        valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None]
                        if valid_data:
                            valid_times, valid_values = zip(*valid_data)
                            ax.plot(valid_times, valid_values, label=label, 
                                   color=color, linestyle=style, linewidth=width, alpha=0.8)
        except Exception as e:
            logger.error(f"Error plotting moving averages: {e}")
    
    def _plot_supertrend(self, ax, timestamps, indicators: Dict[str, List[float]]) -> None:
        """Plot SuperTrend indicator"""
        try:
            if 'supertrend' in indicators:
                values = indicators['supertrend']
                if len(values) == len(timestamps):
                    valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None]
                    if valid_data:
                        valid_times, valid_values = zip(*valid_data)
                        ax.plot(valid_times, valid_values, label='SuperTrend',
                               color='#9C27B0', linestyle='-.', linewidth=2.5, alpha=0.9)
        except Exception as e:
            logger.error(f"Error plotting SuperTrend: {e}")
    
    def _plot_volume_panel(self, ax, df: pd.DataFrame) -> None:
        """Plot volume bars with color coding"""
        try:
            if 'volume' not in df.columns or df['volume'].isna().all():
                ax.text(0.5, 0.5, 'No Volume Data', transform=ax.transAxes,
                       ha='center', va='center', fontsize=12, color='gray')
                ax.set_yticks([])
                return
            
            colors = ['#26A69A' if df.iloc[i]['close'] >= df.iloc[i]['open'] 
                     else '#EF5350' for i in range(len(df))]
            
            ax.bar(df.index, df['volume'], color=colors, alpha=0.7, width=0.0008)
            ax.set_ylabel('Volume', fontsize=11, fontweight='bold')
            ax.grid(True, alpha=0.3, axis='y', linestyle='--', linewidth=0.5)
            ax.set_title('Volume', fontsize=10, fontweight='bold')
            
            # Format y-axis for readability
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1e6:.1f}M' if x >= 1e6 else f'{x/1e3:.1f}K'))
            
        except Exception as e:
            logger.error(f"Error plotting volume panel: {e}")
    
    def _plot_macd_panel(self, ax, timestamps, indicators: Dict[str, List[float]]) -> None:
        """Plot MACD indicator with histogram"""
        try:
            has_data = False
            
            # Plot MACD line
            if 'macd_line' in indicators or 'macd' in indicators:
                macd_key = 'macd_line' if 'macd_line' in indicators else 'macd'
                values = indicators[macd_key]
                if len(values) == len(timestamps):
                    valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None]
                    if valid_data:
                        valid_times, valid_values = zip(*valid_data)
                        ax.plot(valid_times, valid_values, label='MACD', 
                               color='#2196F3', linewidth=2, alpha=0.9)
                        has_data = True
            
            # Plot Signal line
            if 'signal_line' in indicators or 'macd_signal' in indicators:
                signal_key = 'signal_line' if 'signal_line' in indicators else 'macd_signal'
                values = indicators[signal_key]
                if len(values) == len(timestamps):
                    valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None]
                    if valid_data:
                        valid_times, valid_values = zip(*valid_data)
                        ax.plot(valid_times, valid_values, label='Signal',
                               color='#FF9800', linewidth=2, alpha=0.9)
                        has_data = True
            
            # Plot Histogram
            if 'macd_histogram' in indicators or 'histogram' in indicators:
                hist_key = 'macd_histogram' if 'macd_histogram' in indicators else 'histogram'
                values = indicators[hist_key]
                if len(values) == len(timestamps):
                    colors = ['#26A69A' if v and v > 0 else '#EF5350' for v in values]
                    ax.bar(timestamps, values, color=colors, alpha=0.5, width=0.0008, label='Histogram')
                    has_data = True
            
            if not has_data:
                ax.text(0.5, 0.5, 'No MACD Data', transform=ax.transAxes,
                       ha='center', va='center', fontsize=10, color='gray')
            
            ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.8, alpha=0.5)
            ax.set_ylabel('MACD', fontsize=11, fontweight='bold')
            ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
            ax.legend(loc='upper left', fontsize=8, framealpha=0.9)
            ax.set_title('MACD', fontsize=10, fontweight='bold')
            
        except Exception as e:
            logger.error(f"Error plotting MACD panel: {e}")
    
    def _plot_rsi_panel(self, ax, timestamps, indicators: Dict[str, List[float]]) -> None:
        """Plot RSI indicator with overbought/oversold zones"""
        try:
            has_data = False
            
            if 'rsi' in indicators:
                values = indicators['rsi']
                if len(values) == len(timestamps):
                    valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None]
                    if valid_data:
                        valid_times, valid_values = zip(*valid_data)
                        ax.plot(valid_times, valid_values, label='RSI',
                               color='#9C27B0', linewidth=2, alpha=0.9)
                        has_data = True
            
            if has_data:
                # Overbought/Oversold zones
                ax.axhline(y=70, color='#EF5350', linestyle='--', linewidth=1, alpha=0.7, label='Overbought')
                ax.axhline(y=30, color='#26A69A', linestyle='--', linewidth=1, alpha=0.7, label='Oversold')
                ax.axhline(y=50, color='gray', linestyle='-', linewidth=0.8, alpha=0.5)
                
                # Fill zones
                ax.fill_between(timestamps, 70, 100, color='red', alpha=0.1)
                ax.fill_between(timestamps, 0, 30, color='green', alpha=0.1)
                
                ax.set_ylim(0, 100)
            else:
                ax.text(0.5, 0.5, 'No RSI Data', transform=ax.transAxes,
                       ha='center', va='center', fontsize=10, color='gray')
            
            ax.set_ylabel('RSI', fontsize=11, fontweight='bold')
            ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
            ax.legend(loc='upper left', fontsize=8, framealpha=0.9)
            ax.set_title('RSI', fontsize=10, fontweight='bold')
            
        except Exception as e:
            logger.error(f"Error plotting RSI panel: {e}")
    
    def _plot_adx_panel(self, ax, timestamps, indicators: Dict[str, List[float]]) -> None:
        """Plot ADX with +DI and -DI"""
        try:
            has_data = False
            
            # Plot ADX
            if 'adx' in indicators:
                values = indicators['adx']
                if len(values) == len(timestamps):
                    valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None]
                    if valid_data:
                        valid_times, valid_values = zip(*valid_data)
                        ax.plot(valid_times, valid_values, label='ADX',
                               color='#FF6B6B', linewidth=2.5, alpha=0.9)
                        has_data = True
            
            # Plot +DI
            if 'plus_di' in indicators or '+di' in indicators:
                key = 'plus_di' if 'plus_di' in indicators else '+di'
                values = indicators[key]
                if len(values) == len(timestamps):
                    valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None]
                    if valid_data:
                        valid_times, valid_values = zip(*valid_data)
                        ax.plot(valid_times, valid_values, label='+DI',
                               color='#26A69A', linewidth=1.5, alpha=0.8)
                        has_data = True
            
            # Plot -DI
            if 'minus_di' in indicators or '-di' in indicators:
                key = 'minus_di' if 'minus_di' in indicators else '-di'
                values = indicators[key]
                if len(values) == len(timestamps):
                    valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None]
                    if valid_data:
                        valid_times, valid_values = zip(*valid_data)
                        ax.plot(valid_times, valid_values, label='-DI',
                               color='#EF5350', linewidth=1.5, alpha=0.8)
                        has_data = True
            
            if has_data:
                # Threshold lines
                ax.axhline(y=25, color='orange', linestyle='--', linewidth=1, alpha=0.6, label='Strong Trend')
                ax.axhline(y=20, color='yellow', linestyle='--', linewidth=1, alpha=0.5, label='Moderate Trend')
            else:
                ax.text(0.5, 0.5, 'No ADX Data', transform=ax.transAxes,
                       ha='center', va='center', fontsize=10, color='gray')
            
            ax.set_ylabel('ADX', fontsize=11, fontweight='bold')
            ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
            ax.legend(loc='upper left', fontsize=8, framealpha=0.9, ncol=2)
            ax.set_title('ADX (Trend Strength)', fontsize=10, fontweight='bold')
            
        except Exception as e:
            logger.error(f"Error plotting ADX panel: {e}")
    
    def _plot_momentum_panel(self, ax, timestamps, indicators: Dict[str, List[float]]) -> None:
        """Plot momentum indicators (ROC, Stochastic, etc.)"""
        try:
            has_data = False
            
            # Plot ROC (Rate of Change)
            if 'roc' in indicators:
                values = indicators['roc']
                if len(values) == len(timestamps):
                    valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None]
                    if valid_data:
                        valid_times, valid_values = zip(*valid_data)
                        ax.plot(valid_times, valid_values, label='ROC',
                               color='#3F51B5', linewidth=2, alpha=0.9)
                        has_data = True
            
            # Plot Stochastic
            if 'stochastic_k' in indicators:
                values = indicators['stochastic_k']
                if len(values) == len(timestamps):
                    valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None]
                    if valid_data:
                        valid_times, valid_values = zip(*valid_data)
                        ax.plot(valid_times, valid_values, label='%K',
                               color='#4CAF50', linewidth=1.5, alpha=0.9)
                        has_data = True
            
            if 'stochastic_d' in indicators:
                values = indicators['stochastic_d']
                if len(values) == len(timestamps):
                    valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None]
                    if valid_data:
                        valid_times, valid_values = zip(*valid_data)
                        ax.plot(valid_times, valid_values, label='%D',
                               color='#FF5722', linewidth=1.5, alpha=0.9)
                        has_data = True
            
            # Plot CCI
            if 'cci' in indicators:
                values = indicators['cci']
                if len(values) == len(timestamps):
                    valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None]
                    if valid_data:
                        valid_times, valid_values = zip(*valid_data)
                        ax.plot(valid_times, valid_values, label='CCI',
                               color='#00BCD4', linewidth=2, alpha=0.9)
                        has_data = True
            
            if not has_data:
                ax.text(0.5, 0.5, 'No Momentum Data', transform=ax.transAxes,
                       ha='center', va='center', fontsize=10, color='gray')
            else:
                ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.8, alpha=0.5)
            
            ax.set_ylabel('Momentum', fontsize=11, fontweight='bold')
            ax.set_xlabel('Date', fontsize=11, fontweight='bold')
            ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
            ax.legend(loc='upper left', fontsize=8, framealpha=0.9)
            ax.set_title('Momentum Indicators', fontsize=10, fontweight='bold')
            
        except Exception as e:
            logger.error(f"Error plotting momentum panel: {e}")
    
    def _plot_price_panel_clean(
        self,
        ax,
        df: pd.DataFrame,
        indicators: Dict[str, List[float]],
        signals: Optional[List[SignalEvent]],
        algorithm_name: str
    ) -> None:
        """Clean price panel with only essential indicators"""
        try:
            num_candles = len(df)
            
            # Use line chart for large datasets (cleaner)
            if num_candles > 500:
                ax.plot(df.index, df['close'], color='#1976D2', linewidth=2, 
                       label='Close Price', zorder=3)
                ax.fill_between(df.index, df['low'], df['high'], 
                               alpha=0.08, color='#1976D2')
            else:
                # Candlesticks for smaller datasets
                for idx in range(len(df)):
                    timestamp = df.index[idx]
                    row = df.iloc[idx]
                    
                    is_bullish = row['close'] >= row['open']
                    color = '#26A69A' if is_bullish else '#EF5350'
                    edge_color = '#1B5E20' if is_bullish else '#B71C1C'
                    
                    ax.plot([timestamp, timestamp], [row['low'], row['high']],
                           color=edge_color, linewidth=0.6, alpha=0.8, zorder=2)
                    
                    height = abs(row['close'] - row['open'])
                    if height < 0.001:
                        height = row['high'] - row['low']
                        height = max(height * 0.01, 0.001)
                    
                    bottom = min(row['open'], row['close'])
                    width = mdates.date2num(timestamp) * 0.0003
                    
                    rect = Rectangle(
                        (mdates.date2num(timestamp) - width/2, bottom),
                        width, height,
                        facecolor=color, edgecolor=edge_color, 
                        alpha=0.9, linewidth=0.6, zorder=3
                    )
                    ax.add_patch(rect)
            
            # Plot only essential moving averages (SMA 20, 50, 200)
            ma_configs = [
                ('sma_20', 'SMA 20', '#FF6B6B', '-', 1.5),
                ('sma_50', 'SMA 50', '#4ECDC4', '-', 1.5),
                ('sma_200', 'SMA 200', '#9C27B0', '-', 2),
            ]
            
            for key, label, color, style, width in ma_configs:
                if key in indicators:
                    values = indicators[key]
                    if len(values) == len(df):
                        valid_data = [(t, v) for t, v in zip(df.index, values) if v is not None and v > 0]
                        if valid_data and len(valid_data) > 20:
                            valid_times, valid_values = zip(*valid_data)
                            ax.plot(valid_times, valid_values, label=label, 
                                   color=color, linestyle=style, linewidth=width, alpha=0.7)
            
            # Mark signals with cleaner markers
            if signals:
                buy_signals = [s for s in signals if s.signal_type.value == 'BUY']
                sell_signals = [s for s in signals if s.signal_type.value == 'SELL']
                
                for signal in buy_signals:
                    try:
                        idx = df.index.get_indexer([signal.timestamp], method='nearest')[0]
                        if 0 <= idx < len(df):
                            price = df.iloc[idx]['low'] * 0.995
                            ax.scatter(df.index[idx], price, marker='^', color='#4CAF50',
                                     s=150, alpha=0.9, zorder=5, edgecolors='white', linewidths=1.5)
                    except:
                        pass
                
                for signal in sell_signals:
                    try:
                        idx = df.index.get_indexer([signal.timestamp], method='nearest')[0]
                        if 0 <= idx < len(df):
                            price = df.iloc[idx]['high'] * 1.005
                            ax.scatter(df.index[idx], price, marker='v', color='#F44336',
                                     s=150, alpha=0.9, zorder=5, edgecolors='white', linewidths=1.5)
                    except:
                        pass
            
            ax.set_ylabel('Price ($)', fontsize=12, fontweight='bold')
            ax.grid(True, alpha=0.2, linestyle='--', linewidth=0.5)
            ax.legend(loc='upper left', fontsize=10, framealpha=0.95, ncol=2)
            ax.set_title(f'{algorithm_name} - Price Action', 
                        fontsize=13, fontweight='bold', pad=10)
            
        except Exception as e:
            logger.error(f"Error plotting clean price panel: {e}")
    
    def _plot_volume_panel_clean(self, ax, df: pd.DataFrame) -> None:
        """Clean volume panel with better formatting"""
        try:
            if 'volume' not in df.columns or df['volume'].isna().all():
                ax.text(0.5, 0.5, 'No Volume Data', transform=ax.transAxes,
                       ha='center', va='center', fontsize=11, color='gray')
                ax.set_yticks([])
                return
            
            colors = ['#26A69A' if df.iloc[i]['close'] >= df.iloc[i]['open'] 
                     else '#EF5350' for i in range(len(df))]
            
            # Use thinner bars for better appearance
            bar_width = 0.0006 if len(df) > 500 else 0.0008
            ax.bar(df.index, df['volume'], color=colors, alpha=0.6, width=bar_width, edgecolor='none')
            
            ax.set_ylabel('Volume', fontsize=11, fontweight='bold')
            ax.grid(True, alpha=0.2, axis='y', linestyle='--', linewidth=0.5)
            
            # Format y-axis
            max_vol = df['volume'].max()
            if max_vol >= 1e9:
                ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1e9:.1f}B'))
            elif max_vol >= 1e6:
                ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1e6:.1f}M'))
            else:
                ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1e3:.0f}K'))
            
        except Exception as e:
            logger.error(f"Error plotting clean volume panel: {e}")
    
    def _plot_macd_panel_clean(self, ax, timestamps, indicators: Dict[str, List[float]]) -> None:
        """Clean MACD panel with better visualization"""
        try:
            has_data = False
            
            # Plot Histogram first (background)
            if 'macd_histogram' in indicators:
                values = indicators['macd_histogram']
                if len(values) == len(timestamps):
                    colors = ['#4CAF50' if v > 0 else '#F44336' for v in values]
                    ax.bar(timestamps, values, color=colors, alpha=0.3, width=0.0006, edgecolor='none')
                    has_data = True
            
            # Plot MACD line
            if 'macd' in indicators:
                values = indicators['macd']
                if len(values) == len(timestamps):
                    valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None and v != 0]
                    if valid_data and len(valid_data) > 20:
                        valid_times, valid_values = zip(*valid_data)
                        ax.plot(valid_times, valid_values, label='MACD', 
                               color='#2196F3', linewidth=2, alpha=0.9)
                        has_data = True
            
            # Plot Signal line
            if 'macd_signal' in indicators:
                values = indicators['macd_signal']
                if len(values) == len(timestamps):
                    valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None and v != 0]
                    if valid_data and len(valid_data) > 20:
                        valid_times, valid_values = zip(*valid_data)
                        ax.plot(valid_times, valid_values, label='Signal',
                               color='#FF9800', linewidth=2, alpha=0.9)
                        has_data = True
            
            if not has_data:
                ax.text(0.5, 0.5, 'No MACD Data', transform=ax.transAxes,
                       ha='center', va='center', fontsize=11, color='gray')
            else:
                ax.axhline(y=0, color='gray', linestyle='-', linewidth=1, alpha=0.5)
                ax.legend(loc='upper left', fontsize=9, framealpha=0.95)
            
            ax.set_ylabel('MACD', fontsize=11, fontweight='bold')
            ax.grid(True, alpha=0.2, linestyle='--', linewidth=0.5)
            
        except Exception as e:
            logger.error(f"Error plotting clean MACD panel: {e}")
    
    def _plot_oscillators_panel(self, ax, timestamps, indicators: Dict[str, List[float]]) -> None:
        """Combined RSI and Stochastic panel"""
        try:
            has_data = False
            
            # Plot RSI
            if 'rsi' in indicators:
                values = indicators['rsi']
                if len(values) == len(timestamps):
                    valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None and v > 0]
                    if valid_data and len(valid_data) > 20:
                        valid_times, valid_values = zip(*valid_data)
                        ax.plot(valid_times, valid_values, label='RSI', 
                               color='#9C27B0', linewidth=2, alpha=0.9)
                        has_data = True
                        
                        # RSI overbought/oversold levels
                        ax.axhline(y=70, color='#F44336', linestyle='--', linewidth=1, alpha=0.4, label='Overbought')
                        ax.axhline(y=30, color='#4CAF50', linestyle='--', linewidth=1, alpha=0.4, label='Oversold')
                        ax.axhline(y=50, color='gray', linestyle='-', linewidth=0.8, alpha=0.3)
            
            # Plot Stochastic %K
            if 'stoch_k' in indicators:
                values = indicators['stoch_k']
                if len(values) == len(timestamps):
                    valid_data = [(t, v) for t, v in zip(timestamps, values) if v is not None and v > 0]
                    if valid_data and len(valid_data) > 20:
                        valid_times, valid_values = zip(*valid_data)
                        ax.plot(valid_times, valid_values, label='Stoch %K', 
                               color='#FF5722', linewidth=1.5, alpha=0.7, linestyle='--')
                        has_data = True
            
            if not has_data:
                ax.text(0.5, 0.5, 'No Oscillator Data', transform=ax.transAxes,
                       ha='center', va='center', fontsize=11, color='gray')
            else:
                ax.set_ylim([0, 100])
                ax.legend(loc='upper left', fontsize=9, framealpha=0.95, ncol=2)
            
            ax.set_ylabel('RSI / Stochastic', fontsize=11, fontweight='bold')
            ax.set_xlabel('Date', fontsize=11, fontweight='bold')
            ax.grid(True, alpha=0.2, linestyle='--', linewidth=0.5)
            
        except Exception as e:
            logger.error(f"Error plotting oscillators panel: {e}")
    
    def _mark_signals_enhanced(self, ax, df: pd.DataFrame, signals: List[SignalEvent]) -> None:
        """Enhanced signal markers with better visibility"""
        try:
            for signal in signals:
                try:
                    idx = df.index.get_indexer([signal.timestamp], method='nearest')[0]
                    timestamp = df.index[idx]
                    price = df.iloc[idx]['close']
                    
                    if 'bullish' in signal.signal_type.lower() or 'buy' in signal.signal_type.lower():
                        marker = '^'
                        color = '#00C853'  # Bright green
                        offset = -15
                    elif 'bearish' in signal.signal_type.lower() or 'sell' in signal.signal_type.lower():
                        marker = 'v'
                        color = '#D50000'  # Bright red
                        offset = 15
                    else:
                        marker = 'o'
                        color = '#FFC107'  # Amber
                        offset = 0
                    
                    # Plot marker
                    ax.scatter(timestamp, price, marker=marker, s=300,
                              color=color, edgecolors='white', linewidths=2,
                              alpha=0.95, zorder=10)
                    
                    # Add confidence text
                    ax.annotate(
                        f'{signal.confidence:.2f}',
                        xy=(timestamp, price),
                        xytext=(0, offset),
                        textcoords='offset points',
                        fontsize=8,
                        fontweight='bold',
                        color='white',
                        bbox=dict(boxstyle='round,pad=0.4', facecolor=color, alpha=0.9, edgecolor='white'),
                        ha='center',
                        zorder=11
                    )
                    
                except Exception as e:
                    logger.warning(f"Failed to mark signal: {e}")
                    
        except Exception as e:
            logger.error(f"Error marking signals: {e}")
    
    def create_interactive_dashboard(
        self,
        candles: List[CandleData],
        indicators: Dict[str, List[float]],
        signals: Optional[List[SignalEvent]] = None,
        algorithm_name: str = "Technical Analysis",
        symbol: Optional[str] = None,
        filename: Optional[str] = None
    ) -> str:
        """
        Create interactive Plotly dashboard with drill-down capabilities
        
        Args:
            candles: List of CandleData objects
            indicators: Dictionary containing all indicator values
            signals: Optional list of SignalEvent objects
            algorithm_name: Name of the trading algorithm
            symbol: Symbol being analyzed
            filename: Optional output filename
        
        Returns:
            Path to saved HTML file
        """
        try:
            if not candles:
                logger.warning("No candles provided for interactive dashboard")
                return ""
            
            df = self._candles_to_dataframe(candles)
            symbol = symbol or (signals[0].symbol if signals else 'Unknown')
            
            # Create subplots
            fig = make_subplots(
                rows=6, cols=1,
                row_heights=[0.35, 0.12, 0.13, 0.13, 0.13, 0.14],
                shared_xaxes=True,
                vertical_spacing=0.02,
                subplot_titles=(
                    f'{symbol} - Price Chart',
                    'Volume',
                    'MACD',
                    'RSI',
                    'ADX',
                    'Momentum'
                )
            )
            
            # Add candlestick chart
            fig.add_trace(
                go.Candlestick(
                    x=df.index,
                    open=df['open'],
                    high=df['high'],
                    low=df['low'],
                    close=df['close'],
                    name='Price',
                    increasing_line_color='#26A69A',
                    decreasing_line_color='#EF5350',
                    increasing_fillcolor='#26A69A',
                    decreasing_fillcolor='#EF5350'
                ),
                row=1, col=1
            )
            
            # Add moving averages
            self._add_plotly_moving_averages(fig, df.index, indicators, row=1)
            
            # Add SuperTrend
            if 'supertrend' in indicators:
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=indicators['supertrend'],
                        name='SuperTrend',
                        line=dict(color='#9C27B0', width=2, dash='dot'),
                        mode='lines'
                    ),
                    row=1, col=1
                )
            
            # Add signals
            if signals:
                self._add_plotly_signals(fig, df, signals, row=1)
            
            # Add volume
            if 'volume' in df.columns and not df['volume'].isna().all():
                colors = ['#26A69A' if df.iloc[i]['close'] >= df.iloc[i]['open'] 
                         else '#EF5350' for i in range(len(df))]
                fig.add_trace(
                    go.Bar(
                        x=df.index,
                        y=df['volume'],
                        name='Volume',
                        marker_color=colors,
                        opacity=0.7
                    ),
                    row=2, col=1
                )
            
            # Add MACD
            self._add_plotly_macd(fig, df.index, indicators, row=3)
            
            # Add RSI
            self._add_plotly_rsi(fig, df.index, indicators, row=4)
            
            # Add ADX
            self._add_plotly_adx(fig, df.index, indicators, row=5)
            
            # Add Momentum
            self._add_plotly_momentum(fig, df.index, indicators, row=6)
            
            # Update layout
            fig.update_layout(
                title=dict(
                    text=f'{symbol} - {algorithm_name}<br><sub>Interactive Technical Analysis Dashboard</sub>',
                    font=dict(size=20)
                ),
                xaxis_rangeslider_visible=False,
                height=1400,
                showlegend=True,
                hovermode='x unified',
                template='plotly_white',
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )
            
            # Update x-axes
            fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
            
            # Save to HTML
            if filename is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'interactive_dashboard_{symbol}_{timestamp}.html'
            
            filepath = self.output_dir / filename
            fig.write_html(str(filepath))
            
            logger.info(f"Saved interactive dashboard: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error creating interactive dashboard: {e}", exc_info=True)
            return ""
    
    def _add_plotly_moving_averages(self, fig, timestamps, indicators: Dict[str, List[float]], row: int) -> None:
        """Add moving averages to Plotly figure"""
        ma_configs = [
            ('sma_50', 'SMA 50', '#FF6B6B'),
            ('sma_12', 'SMA 12', '#4ECDC4'),
            ('sma_26', 'SMA 26', '#FFA07A'),
            ('ema_12', 'EMA 12', '#95E1D3'),
            ('ema_26', 'EMA 26', '#F38181'),
            ('sma_value', 'SMA', '#1E88E5'),
        ]
        
        for key, label, color in ma_configs:
            if key in indicators and len(indicators[key]) == len(timestamps):
                fig.add_trace(
                    go.Scatter(
                        x=timestamps,
                        y=indicators[key],
                        name=label,
                        line=dict(color=color, width=2),
                        mode='lines'
                    ),
                    row=row, col=1
                )
    
    def _add_plotly_signals(self, fig, df: pd.DataFrame, signals: List[SignalEvent], row: int) -> None:
        """Add signal markers to Plotly figure"""
        buy_signals = []
        sell_signals = []
        neutral_signals = []
        
        for signal in signals:
            try:
                idx = df.index.get_indexer([signal.timestamp], method='nearest')[0]
                timestamp = df.index[idx]
                price = df.iloc[idx]['close']
                
                signal_data = {
                    'x': timestamp,
                    'y': price,
                    'text': f'Confidence: {signal.confidence:.2f}<br>{signal.reason[:50] if signal.reason else ""}',
                }
                
                if 'bullish' in signal.signal_type.lower() or 'buy' in signal.signal_type.lower():
                    buy_signals.append(signal_data)
                elif 'bearish' in signal.signal_type.lower() or 'sell' in signal.signal_type.lower():
                    sell_signals.append(signal_data)
                else:
                    neutral_signals.append(signal_data)
            except Exception as e:
                logger.warning(f"Failed to add signal marker: {e}")
        
        # Add buy signals
        if buy_signals:
            fig.add_trace(
                go.Scatter(
                    x=[s['x'] for s in buy_signals],
                    y=[s['y'] for s in buy_signals],
                    mode='markers',
                    name='Buy Signal',
                    marker=dict(
                        symbol='triangle-up',
                        size=15,
                        color='#00C853',
                        line=dict(color='white', width=2)
                    ),
                    text=[s['text'] for s in buy_signals],
                    hovertemplate='<b>BUY</b><br>%{text}<extra></extra>'
                ),
                row=row, col=1
            )
        
        # Add sell signals
        if sell_signals:
            fig.add_trace(
                go.Scatter(
                    x=[s['x'] for s in sell_signals],
                    y=[s['y'] for s in sell_signals],
                    mode='markers',
                    name='Sell Signal',
                    marker=dict(
                        symbol='triangle-down',
                        size=15,
                        color='#D50000',
                        line=dict(color='white', width=2)
                    ),
                    text=[s['text'] for s in sell_signals],
                    hovertemplate='<b>SELL</b><br>%{text}<extra></extra>'
                ),
                row=row, col=1
            )
    
    def _add_plotly_macd(self, fig, timestamps, indicators: Dict[str, List[float]], row: int) -> None:
        """Add MACD to Plotly figure"""
        if 'macd_line' in indicators or 'macd' in indicators:
            macd_key = 'macd_line' if 'macd_line' in indicators else 'macd'
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=indicators[macd_key],
                    name='MACD',
                    line=dict(color='#2196F3', width=2)
                ),
                row=row, col=1
            )
        
        if 'signal_line' in indicators or 'macd_signal' in indicators:
            signal_key = 'signal_line' if 'signal_line' in indicators else 'macd_signal'
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=indicators[signal_key],
                    name='Signal',
                    line=dict(color='#FF9800', width=2)
                ),
                row=row, col=1
            )
        
        if 'macd_histogram' in indicators or 'histogram' in indicators:
            hist_key = 'macd_histogram' if 'macd_histogram' in indicators else 'histogram'
            colors = ['#26A69A' if v and v > 0 else '#EF5350' for v in indicators[hist_key]]
            fig.add_trace(
                go.Bar(
                    x=timestamps,
                    y=indicators[hist_key],
                    name='Histogram',
                    marker_color=colors,
                    opacity=0.5
                ),
                row=row, col=1
            )
        
        # Add zero line
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=row, col=1)
    
    def _add_plotly_rsi(self, fig, timestamps, indicators: Dict[str, List[float]], row: int) -> None:
        """Add RSI to Plotly figure"""
        if 'rsi' in indicators:
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=indicators['rsi'],
                    name='RSI',
                    line=dict(color='#9C27B0', width=2)
                ),
                row=row, col=1
            )
            
            # Add overbought/oversold lines
            fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.6, 
                         annotation_text="Overbought", row=row, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.6,
                         annotation_text="Oversold", row=row, col=1)
            fig.add_hline(y=50, line_dash="dot", line_color="gray", opacity=0.4, row=row, col=1)
            
            # Update y-axis range
            fig.update_yaxes(range=[0, 100], row=row, col=1)
    
    def _add_plotly_adx(self, fig, timestamps, indicators: Dict[str, List[float]], row: int) -> None:
        """Add ADX to Plotly figure"""
        if 'adx' in indicators:
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=indicators['adx'],
                    name='ADX',
                    line=dict(color='#FF6B6B', width=2.5)
                ),
                row=row, col=1
            )
        
        if 'plus_di' in indicators or '+di' in indicators:
            key = 'plus_di' if 'plus_di' in indicators else '+di'
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=indicators[key],
                    name='+DI',
                    line=dict(color='#26A69A', width=1.5)
                ),
                row=row, col=1
            )
        
        if 'minus_di' in indicators or '-di' in indicators:
            key = 'minus_di' if 'minus_di' in indicators else '-di'
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=indicators[key],
                    name='-DI',
                    line=dict(color='#EF5350', width=1.5)
                ),
                row=row, col=1
            )
        
        # Add threshold lines
        fig.add_hline(y=25, line_dash="dash", line_color="orange", opacity=0.6,
                     annotation_text="Strong", row=row, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color="yellow", opacity=0.5,
                     annotation_text="Moderate", row=row, col=1)
    
    def _add_plotly_momentum(self, fig, timestamps, indicators: Dict[str, List[float]], row: int) -> None:
        """Add momentum indicators to Plotly figure"""
        if 'roc' in indicators:
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=indicators['roc'],
                    name='ROC',
                    line=dict(color='#3F51B5', width=2)
                ),
                row=row, col=1
            )
        
        if 'stochastic_k' in indicators:
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=indicators['stochastic_k'],
                    name='%K',
                    line=dict(color='#4CAF50', width=1.5)
                ),
                row=row, col=1
            )
        
        if 'stochastic_d' in indicators:
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=indicators['stochastic_d'],
                    name='%D',
                    line=dict(color='#FF5722', width=1.5)
                ),
                row=row, col=1
            )
        
        if 'cci' in indicators:
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=indicators['cci'],
                    name='CCI',
                    line=dict(color='#00BCD4', width=2)
                ),
                row=row, col=1
            )
        
        # Add zero line
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=row, col=1)
    
    def create_algorithm_comparison_dashboard(
        self,
        candles: List[CandleData],
        algorithms_data: Dict[str, Dict[str, Any]],
        symbol: str,
        filename: Optional[str] = None
    ) -> str:
        """
        Create comparison dashboard for multiple algorithms
        
        Args:
            candles: List of CandleData objects
            algorithms_data: Dictionary with algorithm names as keys and dict with 'indicators' and 'signals'
            symbol: Symbol being analyzed
            filename: Optional output filename
        
        Returns:
            Path to saved comparison chart
        """
        try:
            if not candles or not algorithms_data:
                logger.warning("No data provided for comparison dashboard")
                return ""
            
            df = self._candles_to_dataframe(candles)
            num_algorithms = len(algorithms_data)
            
            # Create figure with subplots for each algorithm
            fig = plt.figure(figsize=(20, 6 * num_algorithms))
            gs = fig.add_gridspec(num_algorithms, 1, hspace=0.3)
            
            for idx, (algo_name, algo_data) in enumerate(algorithms_data.items()):
                ax = fig.add_subplot(gs[idx])
                
                # Plot price with indicators
                self._plot_candlesticks(ax, df)
                
                indicators = algo_data.get('indicators', {})
                signals = algo_data.get('signals', [])
                
                # Overlay indicators
                if indicators:
                    self._overlay_indicators(ax, df.index, indicators)
                
                # Mark signals
                if signals:
                    self._mark_signals_enhanced(ax, df, signals)
                
                ax.set_title(f'{algo_name}', fontsize=14, fontweight='bold', pad=15)
                ax.set_ylabel('Price', fontsize=12)
                ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
                ax.legend(loc='upper left', fontsize=9)
            
            # Main title
            fig.suptitle(f'{symbol} - Algorithm Comparison Dashboard',
                        fontsize=16, fontweight='bold', y=0.998)
            
            # Save figure
            if filename is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'algorithm_comparison_{symbol}_{timestamp}.png'
            
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=300, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            
            logger.info(f"Saved algorithm comparison dashboard: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error creating algorithm comparison dashboard: {e}", exc_info=True)
            return ""
    
    def create_performance_heatmap(
        self,
        signals: List[SignalEvent],
        candles: List[CandleData],
        symbol: str,
        filename: Optional[str] = None
    ) -> str:
        """
        Create performance heatmap showing signal accuracy over time
        
        Args:
            signals: List of SignalEvent objects
            candles: List of CandleData objects
            symbol: Symbol being analyzed
            filename: Optional output filename
        
        Returns:
            Path to saved heatmap
        """
        try:
            if not signals or not candles:
                logger.warning("No data provided for performance heatmap")
                return ""
            
            # Create DataFrame from signals
            signal_data = []
            for signal in signals:
                signal_data.append({
                    'timestamp': signal.timestamp,
                    'confidence': signal.confidence,
                    'signal_type': signal.signal_type,
                })
            
            df_signals = pd.DataFrame(signal_data)
            df_signals['hour'] = df_signals['timestamp'].dt.hour
            df_signals['day'] = df_signals['timestamp'].dt.day_name()
            
            # Create pivot table for heatmap
            pivot_confidence = df_signals.pivot_table(
                values='confidence',
                index='day',
                columns='hour',
                aggfunc='mean'
            )
            
            # Reorder days
            day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            pivot_confidence = pivot_confidence.reindex([d for d in day_order if d in pivot_confidence.index])
            
            # Create heatmap
            fig, ax = plt.subplots(figsize=(16, 8))
            
            im = ax.imshow(pivot_confidence.values, cmap='RdYlGn', aspect='auto', vmin=0, vmax=1)
            
            # Set ticks
            ax.set_xticks(np.arange(len(pivot_confidence.columns)))
            ax.set_yticks(np.arange(len(pivot_confidence.index)))
            ax.set_xticklabels(pivot_confidence.columns)
            ax.set_yticklabels(pivot_confidence.index)
            
            # Rotate x labels
            plt.setp(ax.get_xticklabels(), rotation=0, ha="center")
            
            # Add colorbar
            cbar = plt.colorbar(im, ax=ax)
            cbar.set_label('Average Confidence', rotation=270, labelpad=20, fontsize=12)
            
            # Add values in cells
            for i in range(len(pivot_confidence.index)):
                for j in range(len(pivot_confidence.columns)):
                    value = pivot_confidence.values[i, j]
                    if not np.isnan(value):
                        text = ax.text(j, i, f'{value:.2f}',
                                     ha="center", va="center", color="black", fontsize=9)
            
            ax.set_title(f'{symbol} - Signal Confidence Heatmap (by Time)',
                        fontsize=14, fontweight='bold', pad=20)
            ax.set_xlabel('Hour of Day', fontsize=12, fontweight='bold')
            ax.set_ylabel('Day of Week', fontsize=12, fontweight='bold')
            
            plt.tight_layout()
            
            # Save figure
            if filename is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'performance_heatmap_{symbol}_{timestamp}.png'
            
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=300, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            
            logger.info(f"Saved performance heatmap: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error creating performance heatmap: {e}", exc_info=True)
            return ""
