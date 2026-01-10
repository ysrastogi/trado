import logging
from typing import Dict, Optional, Deque
from collections import deque, defaultdict
from datetime import datetime

from strategy_engine.base_strategy import BaseStrategy
from common.models import SignalEvent, CandleData

logger = logging.getLogger(__name__)

class MomentumStrategy(BaseStrategy):
    """
    Momentum Strategy with Multi-Timeframe Confirmation
    
    Entry Rules (ALL must be true):
    1. Range Compression: (DonchHigh - DonchLow) < 1.5 * ATR
    2. Confirmed Breakout: Close > PrevDonchHigh
    3. Momentum Persistence: ROC > 0 AND (ROC Rising OR ROC > ROC_SMA)
    4. Participation:
       - Stocks: Volume > 1.3 * SMA(Volume)
       - Index: Candle Range > 1.2 * ATR
    5. HTF Alignment: 15m Close > 15m EMA(20)
    6. Cooldown: Not active (5 bars after exit)
    
    Exit Rules (EXACT):
    1. Initial SL = Entry - 1.2 * ATR
    2. Delayed Breakeven: At +2R AND Close > EMA(9)
    3. Trailing Stop at +2.5R: SL = Highest Close − 0.8 * ATR
    4. Momentum Decay Exit: Range Contraction + ROC Decay + Stagnation (5 bars)
    5. End of Day: Square off all positions (intraday only, at 16:00)
    """
    
    def __init__(self, config: Dict = None):
        super().__init__(config or {})
        self.risk_per_trade = self.config.get('risk_per_trade', 0.005)
        
        # Indicator Parameters
        self.roc_period = self.config.get('roc_period', 12)
        self.roc_sma_period = self.config.get('roc_sma_period', 10)  # New parameter for ROC SMA
        self.donchian_period = self.config.get('donchian_period', 20)
        self.volume_ma_period = self.config.get('volume_ma_period', 20)
        self.atr_period = self.config.get('atr_period', 14)
        self.htf_ema_period = self.config.get('htf_ema_period', 20)
        
        # History buffers for comparison with previous values
        # Increased maxlen to support SMA calculation
        self.history: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=30))
        
        # Trading State
        self.bars_in_trade = 0
        self.min_hold_bars = self.config.get('min_hold_bars', 3)
        self.trail_start_r = self.config.get('trail_start_r', 2.0)
        self.atr_trail_mult = self.config.get('atr_trail_mult', 1.5)

        self.in_position = False
        self.entry_price = 0.0
        self.stop_loss = 0.0
        self.highest_price = 0.0
        self.atr_at_entry = 0.0
        self.trailing_active = False
        
        # Exit state tracking
        self.breakeven_hit = False  # Track if +1R was reached
        self.candles_since_high = 0  # Track candles without new high
        self.high_since_entry = 0.0  # Track highest close since entry
        self.entry_hour = 0  # Track entry hour for end-of-day exit
        
        # Cooldown and Asset Type
        self.cooldown_bars = self.config.get('cooldown_bars', 5)
        self.bars_since_exit = self.cooldown_bars  # Start ready to trade
        self.asset_type = self.config.get('asset_type', 'index')  # 'stock' or 'index'
        
    def setup_indicators(self):
        # Indicators are configured externally in FeatureConfig
        pass

    def on_tick(self, tick_data: Dict) -> Optional[SignalEvent]:
        return None

    def on_bar(self, bar_data: Dict) -> Optional[SignalEvent]:
        return None

    def on_candle(self, candle: CandleData, features: Optional[Dict[str, float]] = None) -> Optional[SignalEvent]:
        if not features:
            return None
            
        # Update History
        for k, v in features.items():
            self.history[k].append(v)
            
        # Ensure we have enough history
        roc_key = f'ROC_{self.roc_period}'
        if len(self.history[roc_key]) < 2:
            return None
            
        # Update cooldown
        if not self.in_position:
            self.bars_since_exit += 1
            
        # Check Exits
        if self.in_position:
            return self._check_exit(candle, features)
            
        # Check Entries
        return self._check_entry(candle, features)

    def _calculate_ema(self, series_name: str, period: int) -> float:
        """Calculate EMA from history"""
        if len(self.history[series_name]) < period:
            return 0.0
        
        data = list(self.history[series_name])
        multiplier = 2 / (period + 1)
        # Initialize EMA with Simple Moving Average of the first `period` elements
        # OR use the first element if not enough history for SMA (less accurate)
        # Here we use the stored history effectively.
        # But `self.history` is limited to 30. If period is close to 30, it works.
        
        # A simple approximation if we don't have full history:
        # Start EMA from the first available point in history
        ema = data[0]
        
        for price in data[1:]:
            ema = (price - ema) * multiplier + ema
            
        return ema

    def _check_entry(self, candle: CandleData, features: Dict[str, float]) -> Optional[SignalEvent]:
        # --- OLD LOGIC (Commented Out) ---
        # roc_key = f'ROC_{self.roc_period}'
        # roc = features.get(roc_key, 0)
        # donchian_key = f'DonchianHigh_{self.donchian_period}'
        # prev_donchian = self.history[donchian_key][-2] if len(self.history[donchian_key]) >= 2 else float('inf')
        # is_breakout = candle.close > prev_donchian
        # prev_roc = self.history[roc_key][-2] if len(self.history[roc_key]) >= 2 else 0
        # is_momentum = roc > 0 and roc > prev_roc
        # vol_sma_key = f'SMA_{self.volume_ma_period}_volume'
        # vol_sma = features.get(vol_sma_key, float('inf'))
        # is_volume = candle.volume > 0.8 * vol_sma
        # atr_key = f'ATRr_{self.atr_period}'
        # atr = features.get(atr_key, 0)
        # prev_atr = self.history[atr_key][-2] if len(self.history[atr_key]) >= 2 else 0
        # is_volatility = atr > prev_atr
        # htf_close = features.get('15m_SMA_1', 0) 
        # htf_ema_key = f'15m_EMA_{self.htf_ema_period}'
        # htf_ema = features.get(htf_ema_key, float('inf'))
        # is_htf_trend = htf_close > htf_ema
        # if not is_breakout: return None
        # if not is_momentum: return None
        # if not is_volatility: return None
        # if not is_htf_trend: return None
        # ---------------------------------

        # --- NEW ENTRY LOGIC ---
        
        # 0. Cooldown Check
        if self.bars_since_exit < self.cooldown_bars:
            return None

        # Prepare Data
        atr_key = f'ATRr_{self.atr_period}'
        atr = features.get(atr_key, 0)
        if atr == 0: return None

        donchian_high_key = f'DonchianHigh_{self.donchian_period}'
        donchian_low_key = f'DonchianLow_{self.donchian_period}'
        donchian_high = features.get(donchian_high_key, 0)
        donchian_low = features.get(donchian_low_key, 0)
        
        roc_key = f'ROC_{self.roc_period}'
        roc = features.get(roc_key, 0)
        
        # 1. Range Compression: (DonchHigh - DonchLow) < 1.5 * ATR
        is_compressed = (donchian_high - donchian_low) < (1.50 * atr)
        
        # 2. Confirmed Breakout: Close > PrevDonchHigh
        prev_donchian_high = self.history[donchian_high_key][-2] if len(self.history[donchian_high_key]) >= 2 else float('inf')
        is_breakout = candle.close > prev_donchian_high
        
        # 3. Momentum Checks
        # Velocity
        k = 3
        if len(self.history['SMA_1']) < k + 1:
            return None

        price_now = candle.close
        price_prev = self.history['SMA_1'][-(k+1)]
        velocity = (price_now - price_prev) / atr
        is_velocity = velocity > 0.8
        
        candle_range = abs(candle.high - candle.low)

        # Range expansion
        recent_ranges = [
            abs(self.history['High'][i] - self.history['Low'][i])
            for i in range(-10, 0)
            if i >= -len(self.history['High'])
        ]
        
        if not recent_ranges:
            median_range = max(atr, 0.0001)
        else:
            median_range = sorted(recent_ranges)[len(recent_ranges)//2]
            
        range_ratio = candle_range / median_range if median_range > 0 else 0
        is_expansion = range_ratio > 1.2

        # Persistence
        bullish_count = sum(
            1 for i in range(3)
            # Check length is guaranteed by k+1 check above
            if self.history['SMA_1'][-(i+1)] > self.history['SMA_1'][-(i+2)]
        )
        is_persistent = bullish_count >= 2

        is_momentum = is_velocity and is_expansion and is_persistent
        
        # 4. Participation
        is_participation = candle_range > (0.6 * atr)
            
        # 5. HTF Alignment: 15m Close > 15m EMA20
        htf_close = features.get('15m_SMA_1', 0) 
        htf_ema_key = f'15m_EMA_{self.htf_ema_period}'
        htf_ema = features.get(htf_ema_key, float('inf'))
        is_htf_trend = htf_close > htf_ema
        
        # 6. EMA 9 Pullback Check (New)
        ema_9 = self._calculate_ema('SMA_1', 9)
        pullback_to_ema_9 = (candle.low <= ema_9) and (candle.close > ema_9)

        # --- Decision Logic ---
        entry_type = None
        confidence = 0.0
        stop_loss_level = 0.0

        if not is_htf_trend:
            return None

        if is_compressed and is_breakout and is_momentum and is_participation:
             entry_type = "IGNITION"
             confidence = 1.0
             stop_loss_level = candle.close - (1.2 * atr)
        # elif (not is_compressed) and pullback_to_ema_9:
        #      entry_type = "CONTINUATION"
        #      confidence = 0.5
        #      stop_loss_level = candle.close - (0.8 * atr)
             
        if not entry_type:
            return None
            
        # 2. Enforce minimum risk distance (0.4% of Price)
        calculated_risk = candle.close - stop_loss_level
        min_risk_dist = candle.close * 0.004
        
        if calculated_risk < min_risk_dist:
             return None
             
        # Execute Entry
        self.in_position = True
        self.entry_price = candle.close
        # ATR at entry required for trailing stops
        self.atr_at_entry = atr
        self.execution_risk = calculated_risk  # Store real risk
        
        self.highest_price = candle.close
        self.high_since_entry = candle.close
        self.candles_since_high = 0
        self.breakeven_hit = False
        self.entry_hour = candle.timestamp.hour
        
        self.stop_loss = stop_loss_level
        
        logger.info(f"{entry_type} ENTRY: {candle.symbol} @ {candle.close}, SL: {self.stop_loss:.4f} (Risk: {self.execution_risk:.4f})")
        self.bars_in_trade = 0
        
        return SignalEvent(
            timestamp=candle.timestamp,
            symbol=candle.symbol,
            algorithm="MomentumStrategy",
            signal_type="BUY",
            confidence=confidence,
            reason=f"{entry_type} Entry",
            indicators={
                'price': candle.close,
                'stop_loss': self.stop_loss,
                'atr': atr,
                'ema_9': ema_9
            }
        )

    def _check_exit(self, candle: CandleData, features: Dict[str, float]) -> Optional[SignalEvent]:
        """
        Exact Exit Logic:
        1. Initial SL = Entry − 1.2×ATR
        2. When price reaches +1R: Move SL → Entry (breakeven)
        3. After +1.5R: Activate trailing stop with SL = Highest Close − 0.8×ATR
        4. Force Exit if: ROC < 0 AND Volume < 20MA AND No new high in last 6 candles
        5. End of day: Square off all positions (intraday only)
        """
        self.bars_in_trade += 1
        atr = features.get(f'ATRr_{self.atr_period}', self.atr_at_entry)
        
        # Update highest price and close tracking
        self.highest_price = max(self.highest_price, candle.high)
        self.high_since_entry = max(self.high_since_entry, candle.close)
        
        # Calculate R multiple based on REAL RISK (Entry - Initial SL)
        safe_risk = self.execution_risk if hasattr(self, 'execution_risk') and self.execution_risk > 0 else max(self.atr_at_entry, 1.0)
        r_multiple = (self.highest_price - self.entry_price) / safe_risk
        
        # EMA 9 for BE Check
        ema_9 = self._calculate_ema('Close', 9)

        # ===== FIX #1: Delayed Breakeven =====
        if not self.breakeven_hit:
            # BE only after: +2R AND no close below EMA(9) (meaning Close > EMA9)
            if r_multiple >= 3.0 and candle.close > ema_9:
                self.stop_loss = self.entry_price
                self.breakeven_hit = True
                logger.info(f"Delayed Breakeven activated at +{r_multiple:.2f}R, SL moved to Entry")
        
        # ===== TRAILING STOP (Adjusted) =====
        if r_multiple >= 4.0 and not self.trailing_active:
            self.trailing_active = True
            logger.info(f"Trailing stop activated at +{r_multiple:.2f}R")
        
        if self.trailing_active:
            # SL = Highest Close − 0.8×ATR
            trailing_sl = self.high_since_entry - (0.8 * atr)
            self.stop_loss = max(self.stop_loss, trailing_sl)
        
        # ===== EXIT RULE 3: Check Stop Loss Hit =====
        if candle.low <= self.stop_loss:
            self.in_position = False
            self.trailing_active = False
            self.breakeven_hit = False
            self.bars_in_trade = 0
            self.bars_since_exit = 0  # Reset cooldown
            logger.info(f"EXIT SIGNAL: {candle.symbol} @ {self.stop_loss:.4f} (Stop Loss at {r_multiple:.2f}R)")
            
            return SignalEvent(
                timestamp=candle.timestamp,
                symbol=candle.symbol,
                algorithm="MomentumStrategy",
                signal_type="SELL",
                confidence=1.0,
                reason=f"Stop Loss Hit at {r_multiple:.2f}R"
            )
        
        # ===== FIX #3: Momentum Decay Exit =====
        # Exit when ALL THREE happen:
        # 1. Range contraction (range < 0.8 × median)
        # 2. ROC slope turns negative
        # 3. No new high in 5 bars
        
        # Update Stagnation
        if candle.close < self.high_since_entry:
            self.candles_since_high += 1
        else:
            self.candles_since_high = 0
            
        # 1. Range Contraction
        current_range = abs(candle.high - candle.low)
        recent_ranges = [abs(self.history['High'][i] - self.history['Low'][i]) 
                         for i in range(-11, -1) if i >= -len(self.history['High'])]
        
        if not recent_ranges:
            median_range = max(atr, 0.0001)
        else:
            median_range = sorted(recent_ranges)[len(recent_ranges)//2]
            
        is_contraction = current_range < (0.8 * median_range)
        
        # 2. ROC Decay
        roc_key = f'ROC_{self.roc_period}'
        roc_curr = features.get(roc_key, 0)
        roc_prev = self.history[roc_key][-2] if len(self.history[roc_key]) >= 2 else 0
        is_roc_decay = roc_curr < roc_prev
        
        # 3. Stagnation
        is_stagnant = self.candles_since_high >= 5
        
        # if is_contraction and is_roc_decay and is_stagnant:
        #     self.in_position = False
        #     self.trailing_active = False
        #     self.breakeven_hit = False
        #     self.bars_in_trade = 0
        #     self.bars_since_exit = 0  # Reset cooldown
        #     logger.info(f"EXIT SIGNAL: {candle.symbol} @ {candle.close:.4f} (Momentum Decay)")
            
            # return SignalEvent(
            #     timestamp=candle.timestamp,
            #     symbol=candle.symbol,
            #     algorithm="MomentumStrategy",
            #     signal_type="SELL",
            #     confidence=1.0,
            #     reason="Momentum Decay Exit"
            # )
        
        # ===== EXACT EXIT RULE 5: End of Day (intraday only) =====
        # Check if we've crossed into next hour/day relative to entry
        current_hour = candle.timestamp.hour
        # Simple EOD check: if current hour is in next business day or after 16:00 (4 PM)
        is_eod = False
        if hasattr(candle.timestamp, 'hour'):
            # For intraday: exit at 4 PM (16:00) or if day changed
            if current_hour >= 16:  # 4 PM
                is_eod = True
        
        if is_eod:
            self.in_position = False
            self.trailing_active = False
            self.breakeven_hit = False
            self.bars_in_trade = 0
            self.bars_since_exit = 0  # Reset cooldown
            logger.info(f"EXIT SIGNAL: {candle.symbol} @ {candle.close:.4f} (End of Day)")
            
            return SignalEvent(
                timestamp=candle.timestamp,
                symbol=candle.symbol,
                algorithm="MomentumStrategy",
                signal_type="SELL",
                confidence=1.0,
                reason="End of Day Exit"
            )
        
        return None
