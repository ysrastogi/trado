from typing import List, Optional
from broker.interfaces import IOrderExecutionService, IBrokerAdapter, OrderRequest, OrderResult, Position, OrderStatus
import logging

class LiveExecutionService(IOrderExecutionService):
    def __init__(self, primary_broker: IBrokerAdapter, backup_brokers: List[IBrokerAdapter] = None):
        self.primary_broker = primary_broker
        self.backup_brokers = backup_brokers or []
        self.logger = logging.getLogger(__name__)

    def start(self):
        self.logger.info("Starting Live Execution Service")
        if not self.primary_broker.connect():
            self.logger.error("Failed to connect to primary broker")
            # Logic to switch to backup could go here
        
        for broker in self.backup_brokers:
            if not broker.connect():
                self.logger.warning("Failed to connect to backup broker")

    def stop(self):
        self.logger.info("Stopping Live Execution Service")
        self.primary_broker.disconnect()
        for b in self.backup_brokers:
            b.disconnect()

    def execute_order(self, order: OrderRequest) -> OrderResult:
        # Try primary
        try:
            result = self.primary_broker.place_order(order)
            if result.status == OrderStatus.FILLED:
                return result
            
            self.logger.warning(f"Primary broker failed to fill order: {result.error_message}")
            
            # Failover logic (simplified)
            # Only failover if it's a system error, not user error (like insufficient funds)
            # For now, we don't have error codes to distinguish easily.
            # Assuming we don't failover for now to avoid double execution risks.
            return result
            
        except Exception as e:
            self.logger.error(f"Exception in primary broker execution: {e}")
            return OrderResult(
                order_id="",
                status=OrderStatus.FAILED,
                filled_quantity=0,
                average_price=0,
                timestamp=None,
                error_message=str(e)
            )

    def get_active_positions(self) -> List[Position]:
        # Aggregate positions from all brokers? Or just primary?
        # For now, just primary.
        return self.primary_broker.get_positions()

    def get_account_balance(self) -> float:
        return self.primary_broker.get_balance()
