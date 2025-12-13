from typing import Type, Dict
from strategy_engine.base_strategy import BaseStrategy

class StrategyFactory:
    """Factory for creating strategy classes"""
    
    _registry: Dict[str, Type[BaseStrategy]] = {}
    
    @classmethod
    def get_strategy_class(cls, strategy_type: str) -> Type[BaseStrategy]:
        """Get strategy class by type"""
        strategy_class = cls._registry.get(strategy_type)
        if not strategy_class:
            raise ValueError(f"Strategy type '{strategy_type}' not found in registry")
        return strategy_class
        
    @classmethod
    def register(cls, name: str, strategy_class: Type[BaseStrategy]):
        """Register a new strategy"""
        cls._registry[name] = strategy_class
