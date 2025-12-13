import logging
from typing import Dict, Optional
from datetime import datetime

class RiskManager:
    """
    Centralized Risk Manager component.
    Enforces trading limits and risk policies.
    """
    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Risk limits
        risk_config = self.config.get('trading', {}).get('risk_management', {})
        self.max_daily_loss = risk_config.get('max_loss_per_day', 100)
        self.max_trades_per_day = risk_config.get('max_trades_per_day', 50)
        self.max_stake = self.config.get('trading', {}).get('max_stake', 1000)
        self.default_stake = self.config.get('trading', {}).get('default_stake', 10)
        
        # State
        self.daily_trades_count = 0
        self.daily_loss = 0.0
        self.last_reset_date = datetime.now().date()

    def check_trade_allowed(self, stake: float) -> bool:
        """Check if a new trade is allowed based on current risk state."""
        self._reset_daily_counters_if_needed()
        
        if self.daily_trades_count >= self.max_trades_per_day:
            self.logger.warning("Max daily trades reached")
            return False
            
        if self.daily_loss >= self.max_daily_loss:
            self.logger.warning("Max daily loss reached")
            return False
            
        if stake > self.max_stake:
            self.logger.warning(f"Stake {stake} exceeds max stake {self.max_stake}")
            return False
            
        return True

    def update_trade_outcome(self, profit_loss: float):
        """Update risk state after a trade completes."""
        self._reset_daily_counters_if_needed()
        self.daily_trades_count += 1
        if profit_loss < 0:
            self.daily_loss += abs(profit_loss)

    def _reset_daily_counters_if_needed(self):
        """Reset daily counters if the day has changed."""
        if datetime.now().date() > self.last_reset_date:
            self.daily_trades_count = 0
            self.daily_loss = 0.0
            self.last_reset_date = datetime.now().date()
