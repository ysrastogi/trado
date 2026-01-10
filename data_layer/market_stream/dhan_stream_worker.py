"""
Dhan Stream Worker

A dedicated worker for managing the DhanMarketStream lifecycle.
This worker handles connection, subscription, and monitoring of Dhan market data streams.
"""

import logging
import threading
import time
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime

from data_layer.market_stream.dhan.dhan_market_stream import DhanMarketStream

logger = logging.getLogger(__name__)


class DhanStreamWorker:
    """
    Worker that manages DhanMarketStream operations.

    This worker:
    - Manages DhanMarketStream connection lifecycle
    - Handles automatic reconnection
    - Provides monitoring and health checks
    - Supports graceful shutdown
    - Tracks Dhan-specific statistics
    """

    def __init__(self,
                 name: str = "dhan_stream_worker",
                 config_path: str = "config/tradding_config.yaml",
                 enable_redis_stream: bool = True,
                 reconnect_interval: int = 30,
                 health_check_interval: int = 10,
                 auto_reconnect: bool = True):
        """
        Initialize the Dhan Stream Worker.

        Args:
            name: Worker name for identification
            config_path: Path to trading configuration YAML
            enable_redis_stream: Whether to publish data to Redis stream
            reconnect_interval: Seconds between reconnection attempts
            health_check_interval: Seconds between health checks
            auto_reconnect: Enable automatic reconnection on disconnection
        """
        self.name = name
        self.config_path = config_path
        self.enable_redis_stream = enable_redis_stream
        self.reconnect_interval = reconnect_interval
        self.health_check_interval = health_check_interval
        self.auto_reconnect = auto_reconnect

        # Worker state
        self._running = False
        self._stream: Optional[DhanMarketStream] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._reconnect_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()

        # Statistics
        self._stats = {
            'start_time': None,
            'connection_attempts': 0,
            'successful_connections': 0,
            'disconnection_count': 0,
            'last_health_check': None,
            'uptime_seconds': 0,
            'total_ticks_received': 0,
            'last_tick_time': None,
            'reconnection_count': 0
        }

        # Callbacks
        self._connection_callbacks: List[Callable] = []
        self._disconnection_callbacks: List[Callable] = []
        self._error_callbacks: List[Callable[[Exception], None]] = []

        logger.info(f"DhanStreamWorker '{name}' initialized")

    def add_connection_callback(self, callback: Callable) -> None:
        """Add callback to be called when stream connects."""
        self._connection_callbacks.append(callback)

    def add_disconnection_callback(self, callback: Callable) -> None:
        """Add callback to be called when stream disconnects."""
        self._disconnection_callbacks.append(callback)

    def add_error_callback(self, callback: Callable[[Exception], None]) -> None:
        """Add callback to be called when an error occurs."""
        self._error_callbacks.append(callback)

    def start(self) -> bool:
        """
        Start the Dhan stream worker.

        Returns:
            True if started successfully, False otherwise
        """
        if self._running:
            logger.warning(f"DhanStreamWorker '{self.name}' is already running")
            return True

        logger.info(f"Starting DhanStreamWorker '{self.name}'...")

        try:
            # Initialize DhanMarketStream
            self._stream = DhanMarketStream(
                config_path=self.config_path,
                enable_redis_stream=self.enable_redis_stream
            )

            # Add internal tick callback for statistics
            self._stream.add_callback('tick', self._on_tick_received)

            # Connect to stream
            if not self._connect_stream():
                logger.error(f"Failed to connect Dhan stream for worker '{self.name}'")
                return False

            # Start monitoring and reconnection threads
            self._running = True
            self._shutdown_event.clear()
            self._stats['start_time'] = datetime.now()

            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name=f"{self.name}_monitor",
                daemon=True
            )
            self._monitor_thread.start()

            if self.auto_reconnect:
                self._reconnect_thread = threading.Thread(
                    target=self._reconnect_loop,
                    name=f"{self.name}_reconnect",
                    daemon=True
                )
                self._reconnect_thread.start()

            logger.info(f"DhanStreamWorker '{self.name}' started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start DhanStreamWorker '{self.name}': {e}")
            self._call_error_callbacks(e)
            self._cleanup()
            return False

    def stop(self) -> bool:
        """
        Stop the Dhan stream worker.

        Returns:
            True if stopped successfully
        """
        if not self._running:
            logger.warning(f"DhanStreamWorker '{self.name}' is not running")
            return True

        logger.info(f"Stopping DhanStreamWorker '{self.name}'...")

        # Signal shutdown
        self._running = False
        self._shutdown_event.set()

        # Disconnect stream
        self._disconnect_stream()

        # Wait for threads to finish
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5.0)
            if self._monitor_thread.is_alive():
                logger.warning(f"Monitor thread for '{self.name}' did not stop gracefully")

        if self._reconnect_thread and self._reconnect_thread.is_alive():
            self._reconnect_thread.join(timeout=5.0)
            if self._reconnect_thread.is_alive():
                logger.warning(f"Reconnect thread for '{self.name}' did not stop gracefully")

        # Cleanup
        self._cleanup()

        logger.info(f"DhanStreamWorker '{self.name}' stopped successfully")
        return True

    def _connect_stream(self) -> bool:
        """Connect to the Dhan market stream."""
        if not self._stream:
            return False

        self._stats['connection_attempts'] += 1

        try:
            if self._stream.connect():
                self._stats['successful_connections'] += 1
                logger.info(f"Dhan stream connected for worker '{self.name}'")

                # Call connection callbacks
                for callback in self._connection_callbacks:
                    try:
                        callback()
                    except Exception as e:
                        logger.error(f"Error in connection callback: {e}")

                return True
            else:
                logger.error(f"Failed to connect Dhan stream for worker '{self.name}'")
                return False

        except Exception as e:
            logger.error(f"Exception during Dhan stream connection for '{self.name}': {e}")
            self._call_error_callbacks(e)
            return False

    def _disconnect_stream(self) -> None:
        """Disconnect from the Dhan market stream."""
        if self._stream:
            try:
                self._stream.disconnect()
                self._stats['disconnection_count'] += 1
                logger.info(f"Dhan stream disconnected for worker '{self.name}'")

                # Call disconnection callbacks
                for callback in self._disconnection_callbacks:
                    try:
                        callback()
                    except Exception as e:
                        logger.error(f"Error in disconnection callback: {e}")

            except Exception as e:
                logger.error(f"Error disconnecting Dhan stream for '{self.name}': {e}")
                self._call_error_callbacks(e)

    def _monitor_loop(self) -> None:
        """Monitor stream health and connection status."""
        logger.info(f"Starting monitor loop for '{self.name}'")

        while not self._shutdown_event.is_set():
            try:
                self._perform_health_check()
                self._update_stats()

                # Wait for next check or shutdown
                if self._shutdown_event.wait(timeout=self.health_check_interval):
                    break

            except Exception as e:
                logger.error(f"Error in monitor loop for '{self.name}': {e}")
                self._call_error_callbacks(e)
                time.sleep(1)  # Brief pause before retry

        logger.info(f"Monitor loop stopped for '{self.name}'")

    def _reconnect_loop(self) -> None:
        """Handle automatic reconnection."""
        logger.info(f"Starting reconnect loop for '{self.name}'")

        while not self._shutdown_event.is_set():
            try:
                # Check if we need to reconnect
                if self._stream and not self._stream.is_ready():
                    logger.info(f"Dhan stream not ready, attempting reconnection for '{self.name}'")
                    self._stats['reconnection_count'] += 1
                    
                    self._disconnect_stream()
                    time.sleep(2)  # Brief pause before reconnection
                    
                    if self._connect_stream():
                        logger.info(f"Reconnection successful for '{self.name}'")
                        # Resubscribe to symbols if needed
                        self._resubscribe_symbols()
                    else:
                        logger.error(f"Reconnection failed for '{self.name}'")

                # Wait before next check
                if self._shutdown_event.wait(timeout=self.reconnect_interval):
                    break

            except Exception as e:
                logger.error(f"Error in reconnect loop for '{self.name}': {e}")
                self._call_error_callbacks(e)
                time.sleep(5)  # Longer pause on error

        logger.info(f"Reconnect loop stopped for '{self.name}'")

    def _perform_health_check(self) -> None:
        """Perform health check on the Dhan stream."""
        if not self._stream:
            return

        try:
            is_ready = self._stream.is_ready()
            self._stats['last_health_check'] = datetime.now()

            if not is_ready:
                logger.warning(f"Health check failed for '{self.name}': Dhan stream not ready")
            else:
                logger.debug(f"Health check passed for '{self.name}'")

        except Exception as e:
            logger.error(f"Health check error for '{self.name}': {e}")
            self._call_error_callbacks(e)

    def _update_stats(self) -> None:
        """Update runtime statistics."""
        if self._stats['start_time']:
            self._stats['uptime_seconds'] = (datetime.now() - self._stats['start_time']).total_seconds()

    def _on_tick_received(self, tick_data: Dict[str, Any]) -> None:
        """Internal callback to track tick statistics."""
        self._stats['total_ticks_received'] += 1
        self._stats['last_tick_time'] = datetime.now()

    def _resubscribe_symbols(self) -> None:
        """Resubscribe to previously subscribed symbols after reconnection."""
        if self._stream:
            try:
                subscriptions = self._stream.get_active_subscriptions()
                if subscriptions:
                    logger.info(f"Resubscribing to {len(subscriptions)} symbols after reconnection")
                    self._stream.subscribe_symbols(subscriptions)
            except Exception as e:
                logger.error(f"Error resubscribing to symbols: {e}")

    def _call_error_callbacks(self, error: Exception) -> None:
        """Call all registered error callbacks."""
        for callback in self._error_callbacks:
            try:
                callback(error)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")

    def _cleanup(self) -> None:
        """Clean up resources."""
        self._stream = None
        self._monitor_thread = None
        self._reconnect_thread = None

    def get_status(self) -> Dict[str, Any]:
        """
        Get current status and statistics.

        Returns:
            Dictionary containing worker status and stats
        """
        return {
            'name': self.name,
            'running': self._running,
            'connected': self._stream.is_ready() if self._stream else False,
            'config_path': self.config_path,
            'enable_redis_stream': self.enable_redis_stream,
            'auto_reconnect': self.auto_reconnect,
            'stats': self._stats.copy()
        }

    def get_active_subscriptions(self) -> List[str]:
        """
        Get list of active subscriptions.

        Returns:
            List of subscribed symbol identifiers
        """
        if self._stream:
            return self._stream.get_active_subscriptions()
        return []

    def subscribe_symbols(self, symbols: List[str]) -> bool:
        """
        Subscribe to symbols.

        Args:
            symbols: List of symbols to subscribe to (format: SEGMENT:SECURITY_ID or mapped names)

        Returns:
            True if subscription successful
        """
        if self._stream and self._stream.is_ready():
            return self._stream.subscribe_symbols(symbols)
        else:
            logger.error(f"Cannot subscribe: stream not ready for '{self.name}'")
            return False

    def unsubscribe_symbols(self, symbols: List[str]) -> bool:
        """
        Unsubscribe from symbols.

        Args:
            symbols: List of symbols to unsubscribe from

        Returns:
            True if unsubscription successful
        """
        if self._stream and self._stream.is_ready():
            return self._stream.unsubscribe_symbols(symbols)
        else:
            logger.error(f"Cannot unsubscribe: stream not ready for '{self.name}'")
            return False

    def add_callback(self, event_type: str, callback: Callable) -> None:
        """
        Add callback for stream events.

        Args:
            event_type: Type of event (e.g., 'tick', 'candle', 'ohlc')
            callback: Callback function to be called on event
        """
        if self._stream:
            self._stream.add_callback(event_type, callback)

    def remove_callback(self, event_type: str, callback: Callable) -> bool:
        """
        Remove callback for stream events.

        Args:
            event_type: Type of event
            callback: Callback function to remove

        Returns:
            True if callback was removed
        """
        if self._stream:
            return self._stream.remove_callback(event_type, callback)
        return False

    @property
    def is_running(self) -> bool:
        """Check if worker is running."""
        return self._running

    @property
    def is_connected(self) -> bool:
        """Check if stream is connected."""
        return self._stream.is_ready() if self._stream else False

    @property
    def stream(self) -> Optional[DhanMarketStream]:
        """Get the underlying DhanMarketStream instance."""
        return self._stream

    def get_detailed_stats(self) -> Dict[str, Any]:
        """
        Get detailed statistics including tick rates and health metrics.

        Returns:
            Dictionary with detailed statistics
        """
        stats = self._stats.copy()
        
        # Calculate tick rate
        if stats['last_tick_time'] and stats['start_time']:
            time_diff = (datetime.now() - stats['start_time']).total_seconds()
            if time_diff > 0:
                stats['ticks_per_second'] = stats['total_ticks_received'] / time_diff
            else:
                stats['ticks_per_second'] = 0.0
        else:
            stats['ticks_per_second'] = 0.0

        # Time since last tick
        if stats['last_tick_time']:
            stats['seconds_since_last_tick'] = (datetime.now() - stats['last_tick_time']).total_seconds()
        else:
            stats['seconds_since_last_tick'] = None

        # Connection success rate
        if stats['connection_attempts'] > 0:
            stats['connection_success_rate'] = stats['successful_connections'] / stats['connection_attempts']
        else:
            stats['connection_success_rate'] = 0.0

        return stats
