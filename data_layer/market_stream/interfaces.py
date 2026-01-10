from abc import ABC, abstractmethod
from typing import Any, Callable, List, Optional, Dict

class IConnectionManager(ABC):
    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        pass

    @abstractmethod
    def send_message(self, message: Any) -> None:
        pass

    @abstractmethod
    def get_next_request_id(self) -> int:
        pass

class ISubscriptionManager(ABC):
    @abstractmethod
    def subscribe_ticks(self, symbol: str, callback: Optional[Callable] = None) -> bool:
        pass

    @abstractmethod
    def unsubscribe_ticks(self, symbol: str) -> bool:
        pass

    @abstractmethod
    def subscribe_candles(self, symbol: str, interval: str = "1m", callback: Optional[Callable] = None) -> bool:
        pass

    @abstractmethod
    def subscribe_ohlc(self, symbol: str, interval: str = "1m", callback: Optional[Callable] = None) -> bool:
        pass

    @abstractmethod
    def unsubscribe_ohlc(self, symbol: str, interval: str = "1m") -> bool:
        pass

    @abstractmethod
    def get_active_subscriptions(self) -> List[str]:
        pass

class IMessageHandler(ABC):
    @abstractmethod
    def handle_message(self, data: Any) -> None:
        pass

class IMarketStream(ABC):
    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def subscribe_ticks(self, symbol: str, callback: Optional[Callable] = None) -> bool:
        pass

    @abstractmethod
    def unsubscribe_ticks(self, symbol: str) -> bool:
        pass

    @abstractmethod
    def subscribe_candles(self, symbol: str, interval: str = "1m", callback: Optional[Callable] = None) -> bool:
        pass

    @abstractmethod
    def subscribe_ohlc(self, symbol: str, interval: str = "1m", callback: Optional[Callable] = None) -> bool:
        pass

    @abstractmethod
    def unsubscribe_ohlc(self, symbol: str, interval: str = "1m") -> bool:
        pass

    @abstractmethod
    def add_callback(self, event_type: str, callback: Callable) -> None:
        pass

    @abstractmethod
    def remove_callback(self, event_type: str, callback: Callable) -> bool:
        pass

    @abstractmethod
    def get_active_subscriptions(self) -> List[str]:
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        pass

class IMarketDataSource(ABC):
    @abstractmethod
    def connect(self) -> bool:
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        pass
    
    @abstractmethod
    def subscribe_symbols(self, symbols: List[str]) -> bool:
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        pass
