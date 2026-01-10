import threading
import time
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from broker.interfaces import IBrokerAdapter, OrderRequest, OrderResult, Position, OrderStatus, OrderSide, OrderType
from broker.trading_client import TradingClient

class DerivAdapter(IBrokerAdapter):
    def __init__(self, trading_client: TradingClient):
        self.client = trading_client
        self.timeout = 10.0 # seconds
        self.logger = logging.getLogger(__name__)

    def connect(self) -> bool:
        return self.client.connect()

    def disconnect(self):
        if self.client.market_stream:
            self.client.market_stream.disconnect()

    def place_order(self, order: OrderRequest) -> OrderResult:
        # Only support BUY for now as Deriv "SELL" is closing a position
        if order.side != OrderSide.BUY:
             return OrderResult(
                order_id="",
                status=OrderStatus.REJECTED,
                filled_quantity=0,
                average_price=0,
                timestamp=datetime.now(),
                error_message="DerivAdapter only supports BUY (opening contracts). Use cancel_order/sell_contract to close."
            )

        # 1. Get Proposal
        proposal_event = threading.Event()
        proposal_data = {}
        
        def proposal_callback(data):
            proposal_data.update(data)
            proposal_event.set()

        # Map OrderRequest to Deriv params
        # Default to CALL if not specified, but OrderType should have it
        contract_type = order.order_type.value
        
        # Default duration if not provided (should be provided)
        duration = order.duration if order.duration else 1
        duration_unit = order.duration_unit if order.duration_unit else 'm'
        
        self.logger.info(f"Requesting proposal for {order.symbol} {contract_type}")
        
        self.client.get_proposal(
            symbol=order.symbol,
            contract_type=contract_type,
            amount=order.quantity,
            duration=duration,
            duration_unit=duration_unit,
            callback=proposal_callback
        )
        
        if not proposal_event.wait(self.timeout):
             return OrderResult(
                order_id="",
                status=OrderStatus.FAILED,
                filled_quantity=0,
                average_price=0,
                timestamp=datetime.now(),
                error_message="Proposal timeout"
            )
             
        if 'error' in proposal_data:
             return OrderResult(
                order_id="",
                status=OrderStatus.FAILED,
                filled_quantity=0,
                average_price=0,
                timestamp=datetime.now(),
                error_message=proposal_data['error']['message'],
                raw_response=proposal_data
            )
             
        if 'proposal' not in proposal_data:
             return OrderResult(
                order_id="",
                status=OrderStatus.FAILED,
                filled_quantity=0,
                average_price=0,
                timestamp=datetime.now(),
                error_message="No proposal in response",
                raw_response=proposal_data
            )

        proposal_id = proposal_data['proposal']['id']
        ask_price = proposal_data['proposal']['ask_price']
        
        # 2. Buy Contract
        buy_event = threading.Event()
        buy_data = {}
        
        def buy_callback(data):
            buy_data.update(data)
            buy_event.set()
            
        self.logger.info(f"Buying contract {proposal_id} at {ask_price}")
        self.client.buy_contract(proposal_id, ask_price, callback=buy_callback)
        
        if not buy_event.wait(self.timeout):
             return OrderResult(
                order_id="",
                status=OrderStatus.FAILED,
                filled_quantity=0,
                average_price=0,
                timestamp=datetime.now(),
                error_message="Buy timeout"
            )

        if 'error' in buy_data:
             return OrderResult(
                order_id="",
                status=OrderStatus.FAILED,
                filled_quantity=0,
                average_price=0,
                timestamp=datetime.now(),
                error_message=buy_data['error']['message'],
                raw_response=buy_data
            )

        # Success
        buy_info = buy_data['buy']
        return OrderResult(
            order_id=str(buy_info['contract_id']),
            status=OrderStatus.FILLED,
            filled_quantity=order.quantity,
            average_price=buy_info['buy_price'],
            timestamp=datetime.now(),
            raw_response=buy_data
        )

    def cancel_order(self, order_id: str) -> bool:
        # For Deriv, "cancel" usually means selling the contract back to market
        # Or cancelling a pending order? Deriv usually fills immediately.
        # Assuming this means "Sell Contract" (Close Position)
        
        sell_event = threading.Event()
        sell_data = {}
        
        def sell_callback(data):
            sell_data.update(data)
            sell_event.set()
            
        self.client.sell_contract(int(order_id), callback=sell_callback)
        
        if not sell_event.wait(self.timeout):
            return False
            
        if 'error' in sell_data:
            self.logger.error(f"Failed to sell contract: {sell_data['error']['message']}")
            return False
            
        return True

    def get_positions(self) -> List[Position]:
        portfolio_event = threading.Event()
        portfolio_data = {}
        
        def portfolio_callback(data):
            portfolio_data.update(data)
            portfolio_event.set()
            
        self.client.get_portfolio(callback=portfolio_callback)
        
        if not portfolio_event.wait(self.timeout):
            self.logger.error("Portfolio timeout")
            return []
            
        if 'portfolio' not in portfolio_data:
            return []
            
        contracts = portfolio_data['portfolio'].get('contracts', [])
        positions = []
        for c in contracts:
            # Map Deriv contract to Position
            # contract_id, contract_type, currency, buy_price, bid_price, etc.
            pos = Position(
                symbol=c.get('symbol', ''),
                side=OrderSide.BUY, # Assuming we hold it
                quantity=c.get('buy_price', 0), # Stake? Or amount? Deriv is weird.
                average_entry_price=c.get('buy_price', 0),
                current_price=c.get('bid_price', 0), # Current value
                unrealized_pnl=c.get('bid_price', 0) - c.get('buy_price', 0),
                realized_pnl=0.0,
                position_id=str(c.get('contract_id')),
                open_time=datetime.fromtimestamp(c.get('purchase_time')) if c.get('purchase_time') else None
            )
            positions.append(pos)
            
        return positions

    def get_balance(self) -> float:
        balance_event = threading.Event()
        balance_data = {}
        
        def balance_callback(data):
            balance_data.update(data)
            balance_event.set()
            
        self.client.get_balance(callback=balance_callback)
        
        if not balance_event.wait(self.timeout):
            return 0.0
            
        if 'balance' in balance_data:
            return balance_data['balance'].get('balance', 0.0)
            
        return 0.0
