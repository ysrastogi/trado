"""
Configuration for Redis Streams data layer
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
import os
from config.settings import settings


@dataclass
class RedisStreamConfig:
    """Configuration for Redis Streams"""
    
    # Redis connection
    redis_url: str = settings.redis_url
    
    # Stream naming
    stream_prefix: str = "market:ticks:"  # e.g., market:ticks:R_10
    consumer_group_prefix: str = "algo:"  # e.g., algo:momentum_trader
    
    # Stream configuration
    max_stream_length: int = 10000  # Maximum messages per stream (MAXLEN)
    trim_strategy: str = "MAXLEN"   # MAXLEN or MINID
    approximate_trim: bool = True   # Use ~ for approximate trimming (more efficient)
    
    # Consumer configuration
    block_time_ms: int = 1000  # Block time for XREADGROUP (0 = block forever)
    batch_size: int = 10  # Number of messages to read per batch
    claim_min_idle_time: int = 60000  # Milliseconds before claiming pending messages
    
    # Retry configuration
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    
    # Connection pool
    max_connections: int = 50
    socket_timeout: int = 5
    socket_connect_timeout: int = 5
    
    # Monitoring
    enable_metrics: bool = True
    metrics_prefix: str = "metrics:stream:"
    
    def get_stream_key(self, symbol: str) -> str:
        """Get the stream key for a symbol"""
        return f"{self.stream_prefix}{symbol}"
    
    def get_consumer_group(self, algo_name: str) -> str:
        """Get the consumer group name for an algorithm"""
        return f"{self.consumer_group_prefix}{algo_name}"
    
    def get_metrics_key(self, key_type: str) -> str:
        """Get the metrics key"""
        return f"{self.metrics_prefix}{key_type}"


# Global configuration instance
redis_stream_config = RedisStreamConfig()
