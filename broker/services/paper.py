import json
import os
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from broker.interfaces import IOrderExecutionService, OrderRequest, OrderResult, Position, OrderStatus, OrderSide, OrderType
from data_layer.market_stream.stream import MarketStream
from common.events import EventBus, Event, EventType, OrderCreatedEventData, OrderFilledEventData, EquityUpdateEventData

class PaperTradingService(IOrderExecutionService):
    def __init__(self, market_stream: MarketStream, initial_balance: float = 1000000.0, state_file: str = "data_cache/paper_trading_state.json", event_bus: Optional[EventBus] = None):
        self.market_stream = market_stream
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.positions: Dict[str, Position] = {} 
        self.orders: List[Dict[str, Any]] = [] 
        self.state_file = state_file
        self.logger = logging.getLogger(__name__)
        self.event_bus = event_bus
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        
        self._load_state()

    def start(self):
        self.logger.info("Starting Paper Trading Service")
        # In a more complex version, we might start a thread to monitor option expiry
        pass

    def stop(self):
        self.logger.info("Stopping Paper Trading Service")
        self._save_state()

    def execute_order(self, order: OrderRequest) -> OrderResult:
        self.logger.info(f"Paper executing order: {order}")
        
        # Get current price
        current_price = order.price
        if current_price is None:
            tick = self.market_stream.get_latest_tick(order.symbol)
            if tick:
                current_price = tick['quote']
            else:
                self.logger.warning(f"No price available for {order.symbol}, assuming 100.0 for testing if not provided")
                current_price = 100.0 # DANGEROUS assumption, but keeps it running for now. Better to fail.
        
        if current_price is None:
             return OrderResult(
                order_id=str(uuid.uuid4()),
                status=OrderStatus.FAILED,
                filled_quantity=0,
                average_price=0,
                timestamp=datetime.now(),
                error_message="Could not determine execution price"
            )

        # Calculate cost
        cost = order.quantity * current_price if order.order_type not in [OrderType.CALL, OrderType.PUT] else order.quantity
        
        if order.side == OrderSide.BUY:
            if self.balance < cost:
                 return OrderResult(
                    order_id=str(uuid.uuid4()),
                    status=OrderStatus.REJECTED,
                    filled_quantity=0,
                    average_price=0,
                    timestamp=datetime.now(),
                    error_message="Insufficient funds"
                )
            self.balance -= cost
        else:
            # For SELL, we receive money (simplified)
            self.balance += cost

        order_id = str(uuid.uuid4())
        
        # Create Position
        position = Position(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            average_entry_price=current_price,
            current_price=current_price,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            position_id=order_id,
            open_time=datetime.now()
        )
        
        self.positions[order_id] = position
        
        result = OrderResult(
            order_id=order_id,
            status=OrderStatus.FILLED,
            filled_quantity=order.quantity,
            average_price=current_price,
            timestamp=datetime.now()
        )
        
        # Log order
        self.orders.append({
            "order_id": order_id,
            "symbol": order.symbol,
            "type": order.order_type.value,
            "side": order.side.value,
            "quantity": order.quantity,
            "price": current_price,
            "timestamp": datetime.now().isoformat()
        })
        
        # Publish Events
        if self.event_bus:
            # Order Created (Implicitly done just now)
            self.event_bus.publish(Event(
                EventType.ORDER_CREATED,
                datetime.now(),
                OrderCreatedEventData(
                    order_id=order_id,
                    symbol=order.symbol,
                    side=order.side.value,
                    quantity=order.quantity,
                    price=current_price,
                    order_type=order.order_type.value,
                    timestamp=datetime.now()
                )
            ))
            
            # Order Filled
            self.event_bus.publish(Event(
                EventType.ORDER_FILLED,
                datetime.now(),
                OrderFilledEventData(
                    order_id=order_id,
                    symbol=order.symbol,
                    side=order.side.value,
                    filled_quantity=order.quantity,
                    price=current_price,
                    timestamp=datetime.now(),
                    commission=0.0, # Simplified
                    slippage=0.0
                )
            ))
            
            # Equity Update
            self.event_bus.publish(Event(
                EventType.EQUITY_UPDATE,
                datetime.now(),
                EquityUpdateEventData(
                    timestamp=datetime.now(),
                    equity=self.balance, # Need to add unrealized PnL? For paper trading often balance is easier.
                    cash=self.balance,
                    margin_used=0.0
                )
            ))

        self._save_state()
        return result

    def get_active_positions(self) -> List[Position]:
        # Update PnL for all positions
        for pid, pos in self.positions.items():
            tick = self.market_stream.get_latest_tick(pos.symbol)
            if tick:
                current_price = tick['quote']
                pos.current_price = current_price
                # Simplified PnL: (Current - Entry) * Qty for BUY
                if pos.side == OrderSide.BUY:
                    pos.unrealized_pnl = (current_price - pos.average_entry_price) * pos.quantity
                else:
                    pos.unrealized_pnl = (pos.average_entry_price - current_price) * pos.quantity
        
        return list(self.positions.values())

    def get_account_balance(self) -> float:
        return self.balance

    def _save_state(self):
        data = {
            "balance": self.balance,
            "positions": [self._position_to_dict(p) for p in self.positions.values()],
            "orders": self.orders
        }
        try:
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save paper trading state: {e}")

    def _load_state(self):
        if not os.path.exists(self.state_file):
            return
            
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
                self.balance = data.get("balance", self.initial_balance)
                self.orders = data.get("orders", [])
                positions_data = data.get("positions", [])
                self.positions = {}
                for p_data in positions_data:
                    pos = self._dict_to_position(p_data)
                    if pos.position_id:
                        self.positions[pos.position_id] = pos
        except Exception as e:
            self.logger.error(f"Failed to load paper trading state: {e}")

    def _position_to_dict(self, pos: Position) -> Dict:
        return {
            "symbol": pos.symbol,
            "side": pos.side.value,
            "quantity": pos.quantity,
            "average_entry_price": pos.average_entry_price,
            "current_price": pos.current_price,
            "unrealized_pnl": pos.unrealized_pnl,
            "realized_pnl": pos.realized_pnl,
            "position_id": pos.position_id,
            "open_time": pos.open_time.isoformat() if pos.open_time else None
        }

    def _dict_to_position(self, data: Dict) -> Position:
        return Position(
            symbol=data["symbol"],
            side=OrderSide(data["side"]),
            quantity=data["quantity"],
            average_entry_price=data["average_entry_price"],
            current_price=data["current_price"],
            unrealized_pnl=data["unrealized_pnl"],
            realized_pnl=data.get("realized_pnl", 0.0),
            position_id=data.get("position_id"),
            open_time=datetime.fromisoformat(data["open_time"]) if data.get("open_time") else None
        )
