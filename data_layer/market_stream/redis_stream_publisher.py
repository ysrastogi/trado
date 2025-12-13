"""
Redis Stream Publisher for Ticks Data

This module publishes tick data to Redis Streams, allowing multiple
consumers (algorithms) to process the same data independently.
"""

import logging
import redis
import json
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from contextlib import contextmanager

from data_layer.market_stream.redis_stream_config import redis_stream_config, RedisStreamConfig
from data_layer.market_stream.models import TickData

logger = logging.getLogger(__name__)


class RedisStreamPublisher:
    """
    Publisher for market tick data to Redis Streams.
    
    Each symbol gets its own stream (e.g., market:ticks:R_10)
    Multiple consumers can read from each stream via consumer groups.
    """
    
    def __init__(self, config: Optional[RedisStreamConfig] = None):
        """
        Initialize the Redis Stream Publisher
        
        Args:
            config: Optional configuration override
        """
        self.logger = logger.getChild("RedisStreamPublisher")
        self.config = config or redis_stream_config
        
        # Initialize Redis connection
        self._redis: Optional[redis.Redis] = None
        self._connection_pool: Optional[redis.ConnectionPool] = None
        self._connect()
        
        # Statistics
        self._stats = {
            'messages_published': 0,
            'failed_publishes': 0,
            'symbols': set(),
            'last_publish_time': None
        }
    
    def _connect(self) -> None:
        """Establish Redis connection with connection pooling"""
        try:
            self._connection_pool = redis.ConnectionPool.from_url(
                self.config.redis_url,
                max_connections=self.config.max_connections,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                decode_responses=False  # We'll handle encoding/decoding
            )
            
            self._redis = redis.Redis(connection_pool=self._connection_pool)
            
            # Test connection
            self._redis.ping()
            self.logger.info(f"Connected to Redis at {self.config.redis_url}")
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    def _serialize_tick(self, tick: TickData) -> Dict[str, bytes]:
        """
        Serialize tick data for Redis Stream
        
        Args:
            tick: TickData object to serialize
            
        Returns:
            Dictionary with string keys and bytes values for Redis
        """
        # Convert TickData to dictionary
        tick_dict = {
            'symbol': str(tick.symbol),
            'quote': str(tick.quote),
            'timestamp': str(tick.timestamp),
            'epoch': str(tick.epoch),
            'ask': str(tick.ask) if tick.ask is not None else '',
            'bid': str(tick.bid) if tick.bid is not None else '',
            'pip_size': str(tick.pip_size) if tick.pip_size is not None else '',
            'subscription_id': str(tick.subscription_id) if tick.subscription_id is not None else ''
        }
        
        # Convert to bytes for Redis
        return {k: v.encode('utf-8') for k, v in tick_dict.items()}
    
    def publish_tick(self, tick: TickData, retry: bool = True) -> bool:
        """
        Publish a tick to the appropriate Redis Stream
        
        Args:
            tick: TickData object to publish
            retry: Whether to retry on failure
            
        Returns:
            True if published successfully, False otherwise
        """
        if not self._redis:
            self.logger.error("Redis connection not established")
            return False
        
        stream_key = self.config.get_stream_key(tick.symbol)
        
        for attempt in range(self.config.max_retries if retry else 1):
            try:
                # Serialize tick data
                data = self._serialize_tick(tick)
                
                # Add metadata
                data[b'published_at'] = str(time.time()).encode('utf-8')
                
                # Publish to stream with MAXLEN trimming
                message_id = self._redis.xadd(
                    stream_key,
                    data,
                    maxlen=self.config.max_stream_length,
                    approximate=self.config.approximate_trim
                )
                
                # Update statistics
                self._stats['messages_published'] += 1
                self._stats['symbols'].add(tick.symbol)
                self._stats['last_publish_time'] = datetime.now()
                
                # Update metrics if enabled
                if self.config.enable_metrics:
                    self._update_metrics(stream_key, tick.symbol)
                
                self.logger.debug(f"Published tick for {tick.symbol} to stream {stream_key}, ID: {message_id}")
                return True
                
            except redis.ConnectionError as e:
                self.logger.warning(f"Connection error publishing tick (attempt {attempt + 1}): {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay_seconds)
                    self._connect()  # Reconnect
                else:
                    self._stats['failed_publishes'] += 1
                    self.logger.error(f"Failed to publish tick after {self.config.max_retries} attempts")
                    return False
                    
            except Exception as e:
                self.logger.error(f"Error publishing tick for {tick.symbol}: {e}")
                self._stats['failed_publishes'] += 1
                return False
        
        return False
    
    def publish_batch(self, ticks: List[TickData]) -> int:
        """
        Publish multiple ticks efficiently using pipeline
        
        Args:
            ticks: List of TickData objects to publish
            
        Returns:
            Number of successfully published ticks
        """
        if not self._redis or not ticks:
            return 0
        
        try:
            # Group ticks by symbol for efficient batch processing
            symbol_groups: Dict[str, List[TickData]] = {}
            for tick in ticks:
                if tick.symbol not in symbol_groups:
                    symbol_groups[tick.symbol] = []
                symbol_groups[tick.symbol].append(tick)
            
            # Use pipeline for batch operations
            pipe = self._redis.pipeline()
            total_added = 0
            
            for symbol, symbol_ticks in symbol_groups.items():
                stream_key = self.config.get_stream_key(symbol)
                
                for tick in symbol_ticks:
                    data = self._serialize_tick(tick)
                    data[b'published_at'] = str(time.time()).encode('utf-8')
                    
                    pipe.xadd(
                        stream_key,
                        data,
                        maxlen=self.config.max_stream_length,
                        approximate=self.config.approximate_trim
                    )
                    total_added += 1
            
            # Execute pipeline
            results = pipe.execute()
            
            # Update statistics
            self._stats['messages_published'] += total_added
            self._stats['symbols'].update(symbol_groups.keys())
            self._stats['last_publish_time'] = datetime.now()
            
            self.logger.info(f"Published batch of {total_added} ticks across {len(symbol_groups)} symbols")
            return total_added
            
        except Exception as e:
            self.logger.error(f"Error publishing batch: {e}")
            return 0
    
    def _update_metrics(self, stream_key: str, symbol: str) -> None:
        """Update metrics in Redis"""
        try:
            metrics_key = self.config.get_metrics_key(symbol)
            pipe = self._redis.pipeline()
            pipe.hincrby(metrics_key, 'total_published', 1)
            pipe.hset(metrics_key, 'last_publish', str(time.time()))
            pipe.expire(metrics_key, 86400)  # Keep metrics for 24 hours
            pipe.execute()
        except Exception as e:
            self.logger.debug(f"Failed to update metrics: {e}")
    
    def get_stream_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a stream
        
        Args:
            symbol: Symbol to get stream info for
            
        Returns:
            Dictionary with stream information or None if not found
        """
        if not self._redis:
            return None
        
        stream_key = self.config.get_stream_key(symbol)
        
        try:
            info = self._redis.xinfo_stream(stream_key)
            return {
                'length': info[b'length'],
                'first_entry': info[b'first-entry'],
                'last_entry': info[b'last-entry'],
                'groups': info[b'groups']
            }
        except redis.ResponseError:
            self.logger.debug(f"Stream {stream_key} does not exist")
            return None
        except Exception as e:
            self.logger.error(f"Error getting stream info: {e}")
            return None
    
    def create_consumer_group(self, symbol: str, group_name: str, from_beginning: bool = False) -> bool:
        """
        Create a consumer group for a symbol's stream
        
        Args:
            symbol: Symbol to create group for
            group_name: Name of the consumer group
            from_beginning: If True, start from beginning of stream, else start from new messages
            
        Returns:
            True if created successfully, False otherwise
        """
        if not self._redis:
            return False
        
        stream_key = self.config.get_stream_key(symbol)
        
        try:
            # Create consumer group
            # Use '0' to read from beginning or '$' for new messages only
            start_id = '0' if from_beginning else '$'
            
            self._redis.xgroup_create(
                stream_key,
                group_name,
                id=start_id,
                mkstream=True  # Create stream if it doesn't exist
            )
            
            self.logger.info(f"Created consumer group '{group_name}' for stream {stream_key}")
            return True
            
        except redis.ResponseError as e:
            if 'BUSYGROUP' in str(e):
                self.logger.debug(f"Consumer group '{group_name}' already exists for {stream_key}")
                return True
            else:
                self.logger.error(f"Error creating consumer group: {e}")
                return False
        except Exception as e:
            self.logger.error(f"Error creating consumer group: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get publisher statistics"""
        return {
            'messages_published': self._stats['messages_published'],
            'failed_publishes': self._stats['failed_publishes'],
            'active_symbols': list(self._stats['symbols']),
            'last_publish_time': self._stats['last_publish_time'].isoformat() if self._stats['last_publish_time'] else None
        }
    
    def close(self) -> None:
        """Close Redis connection"""
        if self._redis:
            self._redis.close()
        if self._connection_pool:
            self._connection_pool.disconnect()
        self.logger.info("Redis Stream Publisher closed")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
