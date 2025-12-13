"""
Execution Simulator
Models realistic slippage, latency, and market impact
"""

import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import random
import json
import logging

from common.models import (
    OrderType,
    OrderStatus,
    ExecutionConfig,
    OrderExecution,
    MarketConditions
)

logger = logging.getLogger(__name__)

class ExecutionSimulator:
    """Simulate realistic order execution with market microstructure"""
    
    def __init__(self, config: Optional[ExecutionConfig] = None):
        self.config = config or ExecutionConfig()
        self.execution_history: List[OrderExecution] = []
        self.market_state: Dict[str, MarketConditions] = {}
        self.current_time = datetime.utcnow()
    
    def update_market_conditions(self, symbol: str, conditions: MarketConditions):
        """Update market conditions for a symbol"""
        self.market_state[symbol] = conditions
    
    def simulate_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        current_price: Optional[float] = None,
        average_daily_volume: Optional[float] = None,
        volatility: Optional[float] = None
    ) -> OrderExecution:
        """
        Simulate execution of a single order
        
        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            quantity: Number of shares/contracts
            order_type: Type of order (market, limit, etc.)
            limit_price: Limit price for limit orders
            current_price: Current market price (if not using market_state)
            average_daily_volume: Average daily trading volume
            volatility: Current volatility estimate
        
        Returns:
            OrderExecution with realistic fills and costs
        """
        
        start_time = datetime.utcnow()
        order_id = f"ORD-{start_time.strftime('%Y%m%d%H%M%S%f')}-{random.randint(1000, 9999)}"
        
        # Get market conditions
        if symbol in self.market_state:
            market = self.market_state[symbol]
            current_price = market.current_price
            average_daily_volume = market.average_daily_volume
            volatility = market.volatility
            bid_price = market.bid_price
            ask_price = market.ask_price
        else:
            # Use provided values or defaults
            current_price = current_price or 100.0
            average_daily_volume = average_daily_volume or 1000000
            volatility = volatility or 0.20  # 20% annualized
            spread_bps = 10.0  # Default 10 bps spread
            bid_price = current_price * (1 - spread_bps / 20000)
            ask_price = current_price * (1 + spread_bps / 20000)
        
        # Validate order
        rejection_reason = self._validate_order(
            quantity, current_price, average_daily_volume
        )
        
        if rejection_reason:
            return self._create_rejected_order(
                order_id, symbol, side, order_type, quantity,
                current_price, rejection_reason, start_time
            )
        
        # Calculate latency
        latency = self._calculate_latency()
        
        # Simulate price movement during latency
        price_at_execution = self._simulate_price_movement(
            current_price, volatility, latency
        )
        
        # Calculate order size impact
        order_pct_of_adv = quantity / average_daily_volume if average_daily_volume > 0 else 0
        
        # Determine if order can be filled
        if order_type == OrderType.LIMIT and limit_price:
            can_fill = self._can_fill_limit_order(
                side, limit_price, bid_price, ask_price, price_at_execution
            )
            if not can_fill:
                return self._create_rejected_order(
                    order_id, symbol, side, order_type, quantity,
                    current_price, "Limit price not reached", start_time
                )
        
        # Calculate market impact
        market_impact_bps = self._calculate_market_impact(
            order_pct_of_adv, volatility
        )
        
        # Calculate slippage
        total_slippage_bps = self._calculate_slippage(
            order_type, volatility, order_pct_of_adv, bid_price, ask_price, current_price
        )
        
        # Determine execution price
        if side == 'buy':
            slippage_factor = total_slippage_bps / 10000
            impact_factor = market_impact_bps / 10000
            executed_price = price_at_execution * (1 + slippage_factor + impact_factor)
        else:  # sell
            slippage_factor = total_slippage_bps / 10000
            impact_factor = market_impact_bps / 10000
            executed_price = price_at_execution * (1 - slippage_factor - impact_factor)
        
        # Calculate fill rate and simulate fills
        fill_rate = self._calculate_fill_rate(order_pct_of_adv, order_type)
        
        if self.config.simulate_partial_fills and fill_rate < 1.0:
            fills = self._simulate_partial_fills(
                quantity, executed_price, fill_rate, volatility
            )
        else:
            fills = [{
                'quantity': quantity * fill_rate,
                'price': executed_price,
                'timestamp': (start_time + timedelta(milliseconds=latency)).isoformat()
            }]
        
        filled_quantity = sum(f['quantity'] for f in fills)
        average_fill_price = sum(f['quantity'] * f['price'] for f in fills) / filled_quantity if filled_quantity > 0 else 0
        
        # Calculate commission
        commission = (filled_quantity * average_fill_price) * (self.config.commission_bps / 10000)
        
        # Determine status
        if filled_quantity == 0:
            status = OrderStatus.REJECTED
            rejection_reason = "No liquidity available"
        elif filled_quantity < quantity * 0.99:  # Less than 99% filled
            status = OrderStatus.PARTIAL
        else:
            status = OrderStatus.FILLED
        
        # Calculate actual slippage
        slippage_amount = abs(average_fill_price - current_price) * filled_quantity
        slippage_bps_actual = (abs(average_fill_price - current_price) / current_price) * 10000 if current_price > 0 else 0
        
        execution = OrderExecution(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            requested_quantity=quantity,
            filled_quantity=filled_quantity,
            requested_price=current_price,
            executed_price=executed_price,
            average_fill_price=average_fill_price,
            slippage=slippage_amount,
            slippage_bps=slippage_bps_actual,
            commission=commission,
            market_impact=order_pct_of_adv,
            market_impact_bps=market_impact_bps,
            timestamp=start_time,
            latency_ms=latency,
            status=status,
            fills=fills,
            rejection_reason=rejection_reason
        )
        
        self.execution_history.append(execution)
        return execution
    
    def simulate_batch_orders(
        self,
        orders: List[Dict[str, Any]],
        market_data: Optional[Dict[str, Dict[str, float]]] = None
    ) -> List[OrderExecution]:
        """Simulate execution of multiple orders"""
        
        executions = []
        market_data = market_data or {}
        
        for order in orders:
            symbol = order['symbol']
            market_info = market_data.get(symbol, {})
            
            execution = self.simulate_order(
                symbol=symbol,
                side=order.get('side', 'buy'),
                quantity=order.get('quantity', 100),
                order_type=OrderType(order.get('order_type', 'market')),
                limit_price=order.get('limit_price'),
                current_price=market_info.get('price'),
                average_daily_volume=market_info.get('adv'),
                volatility=market_info.get('volatility')
            )
            executions.append(execution)
        
        return executions
    
    def _validate_order(
        self,
        quantity: float,
        price: float,
        average_daily_volume: float
    ) -> Optional[str]:
        """Validate order parameters"""
        
        if quantity <= 0:
            return "Invalid quantity: must be positive"
        
        if price <= 0:
            return "Invalid price: must be positive"
        
        order_pct_of_adv = quantity / average_daily_volume if average_daily_volume > 0 else 0
        if order_pct_of_adv > self.config.max_position_size_pct / 100:
            return f"Order too large: exceeds {self.config.max_position_size_pct}% of ADV"
        
        return None
    
    def _calculate_latency(self) -> float:
        """Calculate realistic latency with jitter"""
        
        if not self.config.use_realistic_latency:
            return self.config.latency_ms
        
        # Latency follows log-normal distribution
        base_latency = self.config.latency_ms
        jitter = np.random.lognormal(0, 0.3)  # Log-normal jitter
        latency = base_latency * jitter
        
        # Add occasional network spikes (1% chance)
        if random.random() < 0.01:
            latency *= random.uniform(2, 5)
        
        return max(10, min(latency, 5000))  # Clamp between 10ms and 5s
    
    def _simulate_price_movement(
        self,
        current_price: float,
        volatility: float,
        latency_ms: float
    ) -> float:
        """Simulate price movement during order latency"""
        
        # Convert latency to fraction of year (for volatility scaling)
        time_fraction = (latency_ms / 1000) / (252 * 24 * 3600)  # Trading days
        
        # Geometric Brownian Motion
        drift = 0  # Assume no drift for short timeframes
        diffusion = volatility * np.sqrt(time_fraction) * np.random.normal(0, 1)
        
        new_price = current_price * np.exp(drift + diffusion)
        return new_price
    
    def _can_fill_limit_order(
        self,
        side: str,
        limit_price: float,
        bid_price: float,
        ask_price: float,
        current_price: float
    ) -> bool:
        """Check if limit order can be filled at current prices"""
        
        if side == 'buy':
            # Buy limit: can fill if limit >= ask
            return limit_price >= ask_price
        else:  # sell
            # Sell limit: can fill if limit <= bid
            return limit_price <= bid_price
    
    def _calculate_market_impact(
        self,
        order_pct_of_adv: float,
        volatility: float
    ) -> float:
        """Calculate market impact in basis points"""
        
        # Square root law of market impact
        # Impact ~ sqrt(order_size / ADV) * volatility
        
        base_impact = self.config.market_impact_factor * np.sqrt(order_pct_of_adv) * 10000
        volatility_adjustment = (volatility / 0.20)  # Normalize to 20% vol
        
        market_impact_bps = base_impact * volatility_adjustment
        
        return max(0, market_impact_bps)
    
    def _calculate_slippage(
        self,
        order_type: OrderType,
        volatility: float,
        order_pct_of_adv: float,
        bid_price: float,
        ask_price: float,
        mid_price: float
    ) -> float:
        """Calculate slippage in basis points"""
        
        # Base slippage from config
        base_slippage = self.config.slippage_bps
        
        # Volatility component
        volatility_slippage = (volatility / 0.20) * base_slippage * 0.5
        
        # Order size component
        size_slippage = order_pct_of_adv * 100 * base_slippage * 0.3
        
        # Spread crossing for market orders
        if order_type == OrderType.MARKET:
            spread_bps = abs(ask_price - bid_price) / mid_price * 10000 if mid_price > 0 else 0
            spread_slippage = spread_bps * 0.5  # Cross half the spread on average
        else:
            spread_slippage = 0
        
        total_slippage = base_slippage + volatility_slippage + size_slippage + spread_slippage
        
        return max(0, total_slippage)
    
    def _calculate_fill_rate(
        self,
        order_pct_of_adv: float,
        order_type: OrderType
    ) -> float:
        """Calculate fill rate based on order size and type"""
        
        if not self.config.simulate_partial_fills:
            return 1.0
        
        # Market orders have better fill rates
        if order_type == OrderType.MARKET:
            if order_pct_of_adv <= 0.01:  # <= 1% of ADV
                return 1.0
            elif order_pct_of_adv <= 0.05:  # 1-5% of ADV
                return 0.95 + np.random.uniform(-0.02, 0.03)
            elif order_pct_of_adv <= 0.1:  # 5-10% of ADV
                return 0.85 + np.random.uniform(-0.05, 0.08)
            else:  # > 10% of ADV
                fill_rate = max(0.5, 1 - (order_pct_of_adv - 0.1) * 2)
                return fill_rate + np.random.uniform(-0.1, 0.1)
        else:  # Limit orders
            # Limit orders have lower fill probability
            base_rate = self._calculate_fill_rate(order_pct_of_adv, OrderType.MARKET)
            limit_penalty = 0.1  # 10% lower fill rate for limits
            return max(0.3, base_rate - limit_penalty)
    
    def _simulate_partial_fills(
        self,
        quantity: float,
        avg_price: float,
        fill_rate: float,
        volatility: float
    ) -> List[Dict[str, Any]]:
        """Simulate partial fills over time"""
        
        total_filled = quantity * fill_rate
        remaining = total_filled
        fills = []
        
        # Break into 1-5 fills
        num_fills = min(random.randint(1, 5), int(total_filled / 10) + 1)
        
        base_time = datetime.utcnow()
        
        for i in range(num_fills):
            if i == num_fills - 1:
                # Last fill gets remaining quantity
                fill_qty = remaining
            else:
                # Random portion of remaining
                fill_qty = remaining * random.uniform(0.1, 0.5)
            
            # Slight price variation per fill
            price_variation = np.random.normal(0, volatility / 100)
            fill_price = avg_price * (1 + price_variation)
            
            # Timestamp for this fill
            fill_time = base_time + timedelta(milliseconds=random.uniform(10, 1000) * (i + 1))
            
            fills.append({
                'quantity': fill_qty,
                'price': fill_price,
                'timestamp': fill_time.isoformat()
            })
            
            remaining -= fill_qty
        
        return fills
    
    def _create_rejected_order(
        self,
        order_id: str,
        symbol: str,
        side: str,
        order_type: OrderType,
        quantity: float,
        price: float,
        reason: str,
        timestamp: datetime
    ) -> OrderExecution:
        """Create a rejected order execution"""
        
        return OrderExecution(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            requested_quantity=quantity,
            filled_quantity=0,
            requested_price=price,
            executed_price=0,
            average_fill_price=0,
            slippage=0,
            slippage_bps=0,
            commission=0,
            market_impact=0,
            market_impact_bps=0,
            timestamp=timestamp,
            latency_ms=0,
            status=OrderStatus.REJECTED,
            fills=[],
            rejection_reason=reason
        )
    
    def get_execution_statistics(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get aggregate execution statistics"""
        
        # Filter executions
        filtered = self.execution_history
        
        if symbol:
            filtered = [e for e in filtered if e.symbol == symbol]
        
        if start_date:
            filtered = [e for e in filtered if e.timestamp >= start_date]
        
        if end_date:
            filtered = [e for e in filtered if e.timestamp <= end_date]
        
        if not filtered:
            return {
                'total_orders': 0,
                'message': 'No executions found for the given criteria'
            }
        
        # Calculate statistics
        filled_orders = [e for e in filtered if e.status == OrderStatus.FILLED]
        partial_orders = [e for e in filtered if e.status == OrderStatus.PARTIAL]
        rejected_orders = [e for e in filtered if e.status == OrderStatus.REJECTED]
        
        total_slippage = sum(e.slippage for e in filled_orders + partial_orders)
        total_commission = sum(e.commission for e in filled_orders + partial_orders)
        total_market_impact = sum(e.market_impact * e.filled_quantity * e.executed_price 
                                  for e in filled_orders + partial_orders)
        
        avg_fill_rate = np.mean([e.filled_quantity / e.requested_quantity 
                                 for e in filtered if e.requested_quantity > 0])
        avg_latency = np.mean([e.latency_ms for e in filtered])
        avg_slippage_bps = np.mean([e.slippage_bps for e in filled_orders + partial_orders]) if filled_orders + partial_orders else 0
        
        # Group by symbol
        by_symbol = {}
        for execution in filtered:
            if execution.symbol not in by_symbol:
                by_symbol[execution.symbol] = {
                    'count': 0,
                    'total_volume': 0,
                    'avg_slippage_bps': []
                }
            by_symbol[execution.symbol]['count'] += 1
            by_symbol[execution.symbol]['total_volume'] += execution.filled_quantity
            if execution.status != OrderStatus.REJECTED:
                by_symbol[execution.symbol]['avg_slippage_bps'].append(execution.slippage_bps)
        
        # Finalize by_symbol stats
        for sym, stats in by_symbol.items():
            if stats['avg_slippage_bps']:
                stats['avg_slippage_bps'] = np.mean(stats['avg_slippage_bps'])
            else:
                stats['avg_slippage_bps'] = 0
        
        return {
            'total_orders': len(filtered),
            'filled_orders': len(filled_orders),
            'partial_orders': len(partial_orders),
            'rejected_orders': len(rejected_orders),
            'fill_rate_pct': avg_fill_rate * 100,
            'total_slippage': total_slippage,
            'total_commission': total_commission,
            'total_market_impact': total_market_impact,
            'total_cost': total_slippage + total_commission + total_market_impact,
            'avg_slippage_bps': avg_slippage_bps,
            'avg_slippage_per_order': total_slippage / len(filled_orders + partial_orders) if filled_orders + partial_orders else 0,
            'avg_commission_per_order': total_commission / len(filled_orders + partial_orders) if filled_orders + partial_orders else 0,
            'avg_latency_ms': avg_latency,
            'min_latency_ms': min(e.latency_ms for e in filtered),
            'max_latency_ms': max(e.latency_ms for e in filtered),
            'by_symbol': by_symbol,
            'time_period': {
                'start': min(e.timestamp for e in filtered).isoformat(),
                'end': max(e.timestamp for e in filtered).isoformat()
            }
        }
    
    def export_execution_history(self, filepath: str):
        """Export execution history to JSON file"""
        with open(filepath, 'w') as f:
            json.dump([e.to_dict() for e in self.execution_history], f, indent=2)
    
    def clear_history(self):
        """Clear execution history"""
        self.execution_history = []
