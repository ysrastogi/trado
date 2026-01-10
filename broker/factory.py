from typing import Dict, Any
import logging
from broker.interfaces import IOrderExecutionService
from broker.services.paper import PaperTradingService
from broker.services.live import LiveExecutionService
from broker.adapters.deriv_adapter import DerivAdapter
from broker.trading_client import TradingClient
from data_layer.market_stream.stream import MarketStream

from common.events import EventBus
from typing import Dict, Any, Optional

class ExecutionServiceFactory:
    @staticmethod
    def create_service(config: Dict[str, Any], market_stream: MarketStream, event_bus: Optional[EventBus] = None) -> IOrderExecutionService:
        """
        Creates an execution service based on configuration.
        
        Args:
            config: Configuration dictionary (loaded from yaml)
            market_stream: Active MarketStream instance
            event_bus: Optional EventBus for publishing execution events
            
        Returns:
            IOrderExecutionService implementation (Paper or Live)
        """
        logger = logging.getLogger(__name__)
        
        # Default to paper if not specified
        mode = config.get('trading', {}).get('execution_mode', 'paper').lower()
        logger.info(f"Initializing Execution Service in {mode.upper()} mode")
        
        if mode == 'paper':
            initial_balance = config.get('trading', {}).get('paper_balance', 10000.0)
            return PaperTradingService(market_stream, initial_balance=initial_balance, event_bus=event_bus)
            
        elif mode == 'live':
            provider = config.get('websocket', {}).get('provider', 'deriv')
            
            if provider == 'deriv':
                # Create TradingClient with the existing market_stream
                # Note: TradingClient might need to be singleton or carefully managed
                client = TradingClient(market_stream)
                adapter = DerivAdapter(client)
                return LiveExecutionService(primary_broker=adapter)
            else:
                raise ValueError(f"Unsupported broker provider: {provider}")
                
        else:
            raise ValueError(f"Unknown execution mode: {mode}")
