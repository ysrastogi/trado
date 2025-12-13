"""
Redis Stream Consumer Base Class

This module provides a base class for consuming tick data from Redis Streams.
Algorithms can inherit from this class to process tick data.
"""

import logging
import redis
import time
import threading
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from abc import ABC, abstractmethod

from data_layer.market_stream.redis_stream_config import redis_stream_config, RedisStreamConfig
from data_layer.market_stream.models import TickData

logger = logging.getLogger(__name__)


class RedisStreamConsumer(ABC):
    """
    Base class for consuming tick data from Redis Streams.
    
    Inherit from this class and implement process_tick() to create
    an algorithm that consumes tick data.
    """
    
    def __init__(
        self,
        consumer_name: str,
        symbols: List[str],
        config: Optional[RedisStreamConfig] = None,
        from_beginning: bool = False
    ):
        """
        Initialize the Redis Stream Consumer
        
        Args:
            consumer_name: Unique name for this consumer (e.g., 'momentum_algo_1')
            symbols: List of symbols to consume
            config: Optional configuration override
            from_beginning: If True, read from beginning of stream, else only new messages
        """
        self.logger = logger.getChild(f"Consumer.{consumer_name}")
        self.consumer_name = consumer_name
        self.symbols = symbols
        self.config = config or redis_stream_config
        self.from_beginning = from_beginning
        
        # Generate consumer group name
        self.consumer_group = self.config.get_consumer_group(self.consumer_name)
        
        # Initialize Redis connection
        self._redis: Optional[redis.Redis] = None
        self._connection_pool: Optional[redis.ConnectionPool] = None
        self._connect()
        
        # Consumer state
        self._running = False
        self._consumer_thread: Optional[threading.Thread] = None
        
        # Statistics
        self._stats = {
            'messages_processed': 0,
            'processing_errors': 0,
            'last_message_time': None,
            'start_time': None,
            'symbols': {}
        }
        
        # Initialize consumer groups for all symbols
        self._initialize_consumer_groups()
    
    def _connect(self) -> None:
        """Establish Redis connection with connection pooling"""
        try:
            self._connection_pool = redis.ConnectionPool.from_url(
                self.config.redis_url,
                max_connections=self.config.max_connections,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                decode_responses=False
            )
            
            self._redis = redis.Redis(connection_pool=self._connection_pool)
            
            # Test connection
            self._redis.ping()
            self.logger.info(f"Consumer connected to Redis at {self.config.redis_url}")
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    def _initialize_consumer_groups(self) -> None:
        """Initialize consumer groups for all symbols"""
        for symbol in self.symbols:
            stream_key = self.config.get_stream_key(symbol)
            
            try:
                # Create consumer group
                start_id = '0' if self.from_beginning else '$'
                
                self._redis.xgroup_create(
                    stream_key,
                    self.consumer_group,
                    id=start_id,
                    mkstream=True
                )
                
                self.logger.info(f"Created consumer group '{self.consumer_group}' for {symbol}")
                
            except redis.ResponseError as e:
                if 'BUSYGROUP' in str(e):
                    self.logger.debug(f"Consumer group '{self.consumer_group}' already exists for {symbol}")
                else:
                    self.logger.error(f"Error creating consumer group for {symbol}: {e}")
            except Exception as e:
                self.logger.error(f"Error creating consumer group for {symbol}: {e}")
    
    def _deserialize_tick(self, data: Dict[bytes, bytes]) -> TickData:
        """
        Deserialize tick data from Redis Stream
        
        Args:
            data: Raw data from Redis Stream
            
        Returns:
            TickData object
        """
        # Decode bytes to strings
        decoded = {k.decode('utf-8'): v.decode('utf-8') for k, v in data.items()}
        
        # Parse tick data
        from datetime import datetime
        timestamp_str = decoded.get('timestamp', '')
        try:
            timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now()
        except ValueError:
            timestamp = datetime.now()
        
        return TickData(
            symbol=decoded.get('symbol', ''),
            quote=float(decoded.get('quote', 0)),
            timestamp=timestamp,
            epoch=int(decoded.get('epoch', 0)),
            ask=float(decoded['ask']) if decoded.get('ask') else None,
            bid=float(decoded['bid']) if decoded.get('bid') else None,
            pip_size=int(decoded['pip_size']) if decoded.get('pip_size') else None,
            subscription_id=decoded.get('subscription_id') or None
        )
    
    @abstractmethod
    def process_tick(self, tick: TickData, message_id: str) -> bool:
        """
        Process a single tick. Override this method in your algorithm.
        
        Args:
            tick: TickData object to process
            message_id: Redis Stream message ID
            
        Returns:
            True if processed successfully and should be acknowledged,
            False if there was an error and message should be retried
        """
        pass
    
    def on_start(self) -> None:
        """
        Called when consumer starts. Override for initialization logic.
        """
        pass
    
    def on_stop(self) -> None:
        """
        Called when consumer stops. Override for cleanup logic.
        """
        pass
    
    def on_error(self, error: Exception, tick: Optional[TickData] = None) -> None:
        """
        Called when an error occurs during processing.
        Override for custom error handling.
        
        Args:
            error: The exception that occurred
            tick: The tick that was being processed (if available)
        """
        self.logger.error(f"Error processing tick: {error}")
    
    def _consume_messages(self) -> None:
        """Main consumer loop - runs in separate thread"""
        self.logger.info(f"Consumer '{self.consumer_name}' started for symbols: {self.symbols}")
        self._stats['start_time'] = datetime.now()
        
        # Call on_start hook
        try:
            self.on_start()
        except Exception as e:
            self.logger.error(f"Error in on_start: {e}")
        
        # Build streams dictionary for XREADGROUP
        streams = {
            self.config.get_stream_key(symbol): '>' for symbol in self.symbols
        }
        
        while self._running:
            try:
                # Read messages from all streams
                messages = self._redis.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.consumer_name,
                    streams=streams,
                    count=self.config.batch_size,
                    block=self.config.block_time_ms
                )
                
                if not messages:
                    continue

                for stream_key, stream_messages in messages:
                    stream_key_str = stream_key.decode('utf-8')
                    symbol = stream_key_str.replace(self.config.stream_prefix, '')
                    
                    for message_id, data in stream_messages:
                        message_id_str = message_id.decode('utf-8')
                        try:
                            tick = self._deserialize_tick(data)
                            if tick.symbol != symbol:
                                self.logger.warning(f"Symbol mismatch in message {message_id_str}: expected {symbol}, got {tick.symbol}."
                                                    f"Overriding tick symbol to {symbol}.")
                                tick.symbol = symbol
                            success = self.process_tick(tick, message_id_str)
                            if success:
                                self._redis.xack(
                                    stream_key,
                                    self.consumer_group,
                                    message_id
                                )
                                
                                # Update stats
                                self._stats['messages_processed'] += 1
                                self._stats['last_message_time'] = datetime.now()
                                
                                if symbol not in self._stats['symbols']:
                                    self._stats['symbols'][symbol] = 0
                                self._stats['symbols'][symbol] += 1
                            else:
                                self.logger.warning(f"Message {message_id_str} not acknowledged - will be retried")
                                
                        except Exception as e:
                            self.logger.error(f"Error processing message {message_id_str}: {e}")
                            self._stats['processing_errors'] += 1
                            
                            # Call error hook
                            try:
                                self.on_error(e, tick if 'tick' in locals() else None)
                            except Exception as hook_error:
                                self.logger.error(f"Error in on_error hook: {hook_error}")
                
            except redis.ConnectionError as e:
                self.logger.error(f"Redis connection error: {e}")
                time.sleep(self.config.retry_delay_seconds)
                try:
                    self._connect()
                    self._initialize_consumer_groups()
                except Exception as reconnect_error:
                    self.logger.error(f"Failed to reconnect: {reconnect_error}")
                    
            except Exception as e:
                self.logger.error(f"Unexpected error in consumer loop: {e}")
                time.sleep(self.config.retry_delay_seconds)
        
        # Call on_stop hook
        try:
            self.on_stop()
        except Exception as e:
            self.logger.error(f"Error in on_stop: {e}")
        
        self.logger.info(f"Consumer '{self.consumer_name}' stopped")
    
    def start(self) -> None:
        """Start consuming messages"""
        if self._running:
            self.logger.warning("Consumer already running")
            return
        
        self._running = True
        self._consumer_thread = threading.Thread(target=self._consume_messages, daemon=False)
        self._consumer_thread.start()
        self.logger.info(f"Consumer '{self.consumer_name}' starting...")
    
    def stop(self, wait: bool = True, timeout: float = 10.0) -> None:
        """
        Stop consuming messages
        
        Args:
            wait: If True, wait for consumer thread to finish
            timeout: Maximum time to wait in seconds
        """
        if not self._running:
            self.logger.warning("Consumer not running")
            return
        
        self.logger.info(f"Stopping consumer '{self.consumer_name}'...")
        self._running = False
        
        if wait and self._consumer_thread:
            self._consumer_thread.join(timeout=timeout)
            if self._consumer_thread.is_alive():
                self.logger.warning("Consumer thread did not stop within timeout")
    
    def is_running(self) -> bool:
        """Check if consumer is running"""
        return self._running
    
    def get_stats(self) -> Dict[str, Any]:
        """Get consumer statistics"""
        uptime = None
        if self._stats['start_time']:
            uptime = (datetime.now() - self._stats['start_time']).total_seconds()
        
        return {
            'consumer_name': self.consumer_name,
            'consumer_group': self.consumer_group,
            'symbols': list(self._stats['symbols'].keys()),
            'messages_processed': self._stats['messages_processed'],
            'processing_errors': self._stats['processing_errors'],
            'last_message_time': self._stats['last_message_time'].isoformat() if self._stats['last_message_time'] else None,
            'uptime_seconds': uptime,
            'symbol_counts': self._stats['symbols']
        }
    
    def get_pending_messages(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Get pending messages for this consumer group
        
        Args:
            symbol: Symbol to check pending messages for
            
        Returns:
            List of pending message info
        """
        stream_key = self.config.get_stream_key(symbol)
        
        try:
            # Get pending messages for this consumer
            pending = self._redis.xpending_range(
                stream_key,
                self.consumer_group,
                min='-',
                max='+',
                count=100,
                consumername=self.consumer_name
            )
            
            return [
                {
                    'message_id': msg[b'message_id'].decode('utf-8'),
                    'consumer': msg[b'consumer'].decode('utf-8'),
                    'idle_time_ms': msg[b'time_since_delivered'],
                    'delivery_count': msg[b'times_delivered']
                }
                for msg in pending
            ]
            
        except Exception as e:
            self.logger.error(f"Error getting pending messages: {e}")
            return []
    
    def claim_pending_messages(self, symbol: str, min_idle_time_ms: Optional[int] = None) -> int:
        """
        Claim and reprocess pending messages that have been idle too long
        
        Args:
            symbol: Symbol to claim pending messages for
            min_idle_time_ms: Minimum idle time in milliseconds (default from config)
            
        Returns:
            Number of messages claimed
        """
        if min_idle_time_ms is None:
            min_idle_time_ms = self.config.claim_min_idle_time
        
        stream_key = self.config.get_stream_key(symbol)
        
        try:
            # Get pending messages
            pending = self._redis.xpending(stream_key, self.consumer_group)
            
            if not pending or pending[b'pending'] == 0:
                return 0
            
            # Claim idle messages
            claimed = self._redis.xautoclaim(
                stream_key,
                self.consumer_group,
                self.consumer_name,
                min_idle_time=min_idle_time_ms,
                count=self.config.batch_size,
                start_id='0-0'
            )
            
            claimed_count = len(claimed[1]) if claimed and len(claimed) > 1 else 0
            
            if claimed_count > 0:
                self.logger.info(f"Claimed {claimed_count} pending messages for {symbol}")
            
            return claimed_count
            
        except Exception as e:
            self.logger.error(f"Error claiming pending messages: {e}")
            return 0
    
    def close(self) -> None:
        """Close consumer and clean up resources"""
        self.stop(wait=True)
        
        if self._redis:
            self._redis.close()
        if self._connection_pool:
            self._connection_pool.disconnect()
        
        self.logger.info("Consumer closed")
    
    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
