"""
Data models for the playback engine
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum


class PlaybackState(Enum):
    """Playback engine state"""
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    STEPPING = "stepping"
    SEEKING = "seeking"


@dataclass
class CandleData:
    """OHLC candle data structure"""
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume
        }


@dataclass
class SignalEvent:
    """
    Represents a trading signal emitted by an algorithm
    Captures complete context for analysis and visualization
    """
    timestamp: datetime
    symbol: str
    algorithm: str
    signal_type: str  # bullish_trend, bearish_trend, sideways, etc.
    confidence: float
    reason: str  # Human-readable explanation
    trigger_conditions: List[str] = field(default_factory=list)
    indicators: Dict[str, float] = field(default_factory=dict)
    candle: Optional[Dict[str, float]] = None
    previous_signal: Optional[str] = None
    signal_change: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'algorithm': self.algorithm,
            'signal_type': self.signal_type,
            'confidence': self.confidence,
            'reason': self.reason,
            'trigger_conditions': self.trigger_conditions,
            'indicators': self.indicators,
            'candle': self.candle,
            'previous_signal': self.previous_signal,
            'signal_change': self.signal_change
        }
    
    def to_csv_row(self) -> Dict[str, Any]:
        """Convert to flat dictionary for CSV export"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'algorithm': self.algorithm,
            'signal_type': self.signal_type,
            'confidence': self.confidence,
            'reason': self.reason,
            'trigger_conditions': '; '.join(self.trigger_conditions),
            'previous_signal': self.previous_signal or '',
            'signal_change': self.signal_change,
            **{f'indicator_{k}': v for k, v in self.indicators.items()},
            **{f'candle_{k}': v for k, v in (self.candle or {}).items()}
        }


@dataclass
class TrendPhase:
    """
    Represents a continuous trend phase for timeline visualization
    """
    start_time: datetime
    end_time: datetime
    trend_type: str  # bullish, bearish, sideways
    avg_confidence: float
    signal_count: int
    price_start: float
    price_end: float
    price_change_pct: float
    duration_seconds: float
    algorithm: str
    
    @property
    def duration_hours(self) -> float:
        """Duration in hours"""
        return self.duration_seconds / 3600
    
    @property
    def duration_days(self) -> float:
        """Duration in days"""
        return self.duration_seconds / 86400
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'trend_type': self.trend_type,
            'avg_confidence': self.avg_confidence,
            'signal_count': self.signal_count,
            'price_start': self.price_start,
            'price_end': self.price_end,
            'price_change_pct': self.price_change_pct,
            'duration_seconds': self.duration_seconds,
            'duration_hours': self.duration_hours,
            'duration_days': self.duration_days,
            'algorithm': self.algorithm
        }


@dataclass
class PlaybackMetrics:
    """Metrics collected during playback"""
    total_candles: int = 0
    candles_processed: int = 0
    signals_emitted: int = 0
    trend_changes: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    playback_speed: float = 1.0
    
    @property
    def progress_pct(self) -> float:
        """Playback progress percentage"""
        if self.total_candles == 0:
            return 0.0
        return (self.candles_processed / self.total_candles) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'total_candles': self.total_candles,
            'candles_processed': self.candles_processed,
            'signals_emitted': self.signals_emitted,
            'trend_changes': self.trend_changes,
            'progress_pct': self.progress_pct,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'playback_speed': self.playback_speed
        }


class OrderType(Enum):
    """Types of orders"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    """Order execution status"""
    PENDING = "pending"
    PARTIAL = "partial"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass
class ExecutionConfig:
    """Configuration for execution simulation"""
    slippage_bps: float = 5.0  # Basis points
    latency_ms: float = 100.0  # Milliseconds
    market_impact_factor: float = 0.1  # Price impact per % of ADV
    commission_bps: float = 1.0  # Commission in basis points
    min_fill_rate: float = 0.95  # Minimum order fill rate
    max_position_size_pct: float = 10.0  # Max % of ADV per order
    use_realistic_latency: bool = True
    simulate_partial_fills: bool = True
    
    def to_dict(self) -> Dict:
        from dataclasses import asdict
        return asdict(self)


@dataclass
class OrderExecution:
    """Results of order execution"""
    order_id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    order_type: OrderType
    requested_quantity: float
    filled_quantity: float
    requested_price: float
    executed_price: float
    average_fill_price: float
    slippage: float
    slippage_bps: float
    commission: float
    market_impact: float
    market_impact_bps: float
    timestamp: datetime
    latency_ms: float
    status: OrderStatus
    fills: List[Dict[str, Any]]
    rejection_reason: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            'order_id': self.order_id,
            'symbol': self.symbol,
            'side': self.side,
            'order_type': self.order_type.value,
            'requested_quantity': self.requested_quantity,
            'filled_quantity': self.filled_quantity,
            'requested_price': self.requested_price,
            'executed_price': self.executed_price,
            'average_fill_price': self.average_fill_price,
            'slippage': self.slippage,
            'slippage_bps': self.slippage_bps,
            'commission': self.commission,
            'market_impact': self.market_impact,
            'market_impact_bps': self.market_impact_bps,
            'timestamp': self.timestamp.isoformat(),
            'latency_ms': self.latency_ms,
            'status': self.status.value,
            'fills': self.fills,
            'rejection_reason': self.rejection_reason
        }
    
    def get_total_cost(self) -> float:
        """Calculate total execution cost"""
        return self.slippage + self.commission + (self.market_impact * self.executed_price * self.filled_quantity)
    
    def get_effective_price(self) -> float:
        """Get effective price including all costs"""
        if self.filled_quantity == 0:
            return 0.0
        
        total_cost = self.get_total_cost()
        if self.side == 'buy':
            return self.average_fill_price + (total_cost / self.filled_quantity)
        else:
            return self.average_fill_price - (total_cost / self.filled_quantity)


@dataclass
class MarketConditions:
    """Current market conditions for a symbol"""
    symbol: str
    current_price: float
    bid_price: float
    ask_price: float
    spread_bps: float
    average_daily_volume: float
    current_volume: float
    volatility: float  # Annualized
    liquidity_score: float  # 0-1, higher is more liquid
    
    def to_dict(self) -> Dict:
        from dataclasses import asdict
        return asdict(self)


class ExitReason(Enum):
    """Reasons for exiting a trade"""
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    SIGNAL_REVERSAL = "signal_reversal"
    MANUAL_EXIT = "manual_exit"
    TIMEOUT = "timeout"  # Position held too long
    LIQUIDATION = "liquidation"  # Forced closure
    OTHER = "other"


@dataclass
class TradeRecord:
    """
    Comprehensive record of a completed trade with full lifecycle details.
    Combines signal context, execution microstructure, and calculated metrics.
    """
    # Trade identification
    trade_id: str
    symbol: str
    trade_number: int  # Sequential trade number
    
    # Entry details
    entry_time: datetime
    entry_price: float
    entry_quantity: float
    entry_signal: Optional[SignalEvent] = None  # Signal that triggered entry
    entry_confidence: float = 0.0  # Confidence level (0-1) from signal
    entry_reason: str = ""  # Human-readable entry reason
    entry_trigger_conditions: List[str] = field(default_factory=list)  # Indicator setup
    entry_indicators: Dict[str, float] = field(default_factory=dict)  # Indicator values at entry
    
    # Execution microstructure (entry leg)
    entry_execution: Optional[OrderExecution] = None  # Entry order details
    entry_slippage_bps: float = 0.0
    entry_commission: float = 0.0
    entry_market_impact: float = 0.0
    
    # Exit details
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_quantity: Optional[float] = None
    exit_signal: Optional[SignalEvent] = None  # Signal that triggered exit
    exit_reason: Optional[ExitReason] = None  # Why the trade was exited
    exit_reason_text: str = ""  # Human-readable exit reason
    exit_trigger_conditions: List[str] = field(default_factory=list)  # Indicator setup at exit
    exit_indicators: Dict[str, float] = field(default_factory=dict)  # Indicator values at exit
    
    # Execution microstructure (exit leg)
    exit_execution: Optional[OrderExecution] = None  # Exit order details
    exit_slippage_bps: float = 0.0
    exit_commission: float = 0.0
    exit_market_impact: float = 0.0
    
    # P&L and Risk Metrics
    gross_pnl: float = 0.0  # P&L before costs
    total_costs: float = 0.0  # Slippage + commissions + market impact
    net_pnl: float = 0.0  # P&L after costs
    pnl_pct: float = 0.0  # Return percentage
    
    # Intra-trade tracking
    max_price: Optional[float] = None  # Highest price during trade
    min_price: Optional[float] = None  # Lowest price during trade
    max_favorable_excursion: Optional[float] = None  # MFE in absolute terms
    max_favorable_excursion_pct: Optional[float] = None  # MFE as percentage
    max_adverse_excursion: Optional[float] = None  # MAE in absolute terms
    max_adverse_excursion_pct: Optional[float] = None  # MAE as percentage
    
    # Risk-adjusted metrics
    risk_multiple: Optional[float] = None  # R-multiple (if stop loss defined)
    risk_reward_ratio: Optional[float] = None  # Win/Loss ratio for this trade
    consecutive_winner: bool = False  # Part of winning streak
    consecutive_loser: bool = False  # Part of losing streak
    
    # Trade duration
    duration_seconds: Optional[float] = None
    holding_period: Optional[str] = None  # Human-readable duration
    
    # Market context
    entry_candle: Optional[Dict[str, float]] = None  # OHLCV at entry
    exit_candle: Optional[Dict[str, float]] = None  # OHLCV at exit
    volatility_at_entry: Optional[float] = None
    volatility_at_exit: Optional[float] = None
    
    # Tags and notes
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    
    def is_open(self) -> bool:
        """Check if trade is still open"""
        return self.exit_time is None
    
    def is_winner(self) -> bool:
        """Check if trade is profitable"""
        return self.net_pnl > 0
    
    def is_loser(self) -> bool:
        """Check if trade is a loss"""
        return self.net_pnl < 0
    
    def is_breakeven(self) -> bool:
        """Check if trade is breakeven"""
        return abs(self.net_pnl) < 0.01  # Within 1 cent
    
    def get_duration_hours(self) -> float:
        """Get duration in hours"""
        if self.duration_seconds is None:
            return 0.0
        return self.duration_seconds / 3600
    
    def get_duration_days(self) -> float:
        """Get duration in days"""
        if self.duration_seconds is None:
            return 0.0
        return self.duration_seconds / 86400
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'trade_id': self.trade_id,
            'symbol': self.symbol,
            'trade_number': self.trade_number,
            'entry_time': self.entry_time.isoformat(),
            'entry_price': self.entry_price,
            'entry_quantity': self.entry_quantity,
            'entry_confidence': self.entry_confidence,
            'entry_reason': self.entry_reason,
            'entry_trigger_conditions': self.entry_trigger_conditions,
            'entry_indicators': self.entry_indicators,
            'entry_slippage_bps': self.entry_slippage_bps,
            'entry_commission': self.entry_commission,
            'entry_market_impact': self.entry_market_impact,
            'exit_time': self.exit_time.isoformat() if self.exit_time else None,
            'exit_price': self.exit_price,
            'exit_quantity': self.exit_quantity,
            'exit_reason': self.exit_reason.value if self.exit_reason else None,
            'exit_reason_text': self.exit_reason_text,
            'exit_trigger_conditions': self.exit_trigger_conditions,
            'exit_indicators': self.exit_indicators,
            'exit_slippage_bps': self.exit_slippage_bps,
            'exit_commission': self.exit_commission,
            'exit_market_impact': self.exit_market_impact,
            'gross_pnl': self.gross_pnl,
            'total_costs': self.total_costs,
            'net_pnl': self.net_pnl,
            'pnl_pct': self.pnl_pct,
            'max_price': self.max_price,
            'min_price': self.min_price,
            'max_favorable_excursion': self.max_favorable_excursion,
            'max_favorable_excursion_pct': self.max_favorable_excursion_pct,
            'max_adverse_excursion': self.max_adverse_excursion,
            'max_adverse_excursion_pct': self.max_adverse_excursion_pct,
            'risk_multiple': self.risk_multiple,
            'risk_reward_ratio': self.risk_reward_ratio,
            'duration_seconds': self.duration_seconds,
            'holding_period': self.holding_period,
            'volatility_at_entry': self.volatility_at_entry,
            'volatility_at_exit': self.volatility_at_exit,
            'is_winner': self.is_winner(),
            'is_loser': self.is_loser(),
            'is_breakeven': self.is_breakeven(),
            'tags': self.tags,
            'notes': self.notes
        }
    
    def to_csv_row(self) -> Dict[str, Any]:
        """Convert to flat dictionary for CSV export"""
        return {
            'trade_id': self.trade_id,
            'symbol': self.symbol,
            'trade_number': self.trade_number,
            'entry_time': self.entry_time.isoformat(),
            'exit_time': self.exit_time.isoformat() if self.exit_time else '',
            'entry_price': self.entry_price,
            'exit_price': self.exit_price or '',
            'quantity': self.entry_quantity,
            'duration_hours': self.get_duration_hours(),
            'entry_confidence': self.entry_confidence,
            'entry_reason': self.entry_reason,
            'exit_reason': self.exit_reason.value if self.exit_reason else '',
            'gross_pnl': self.gross_pnl,
            'total_costs': self.total_costs,
            'net_pnl': self.net_pnl,
            'pnl_pct': self.pnl_pct,
            'entry_slippage_bps': self.entry_slippage_bps,
            'exit_slippage_bps': self.exit_slippage_bps,
            'total_slippage_bps': self.entry_slippage_bps + self.exit_slippage_bps,
            'max_favorable_excursion_pct': self.max_favorable_excursion_pct or '',
            'max_adverse_excursion_pct': self.max_adverse_excursion_pct or '',
            'risk_multiple': self.risk_multiple or '',
            'is_winner': self.is_winner(),
            'is_loser': self.is_loser(),
            'notes': self.notes
        }
