"""
Stream Worker

A dedicated worker for managing the MarketStream lifecycle.
This worker handles connection, subscription, and monitoring of market data streams.
"""

import logging
import threading
import time
import signal
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime

from data_layer.market_stream.factory import MarketStreamFactory
from data_layer.worker_manager import WorkerManager

logger = logging.getLogger(__name__)

class StreamWorker:
    """
    Worker that manages MarketStream operations.

    This worker:
    - Manages MarketStream connection lifecycle
    - Handles automatic reconnection
    - Provides monitoring and health checks
    - Supports graceful shutdown
    """

    def __init__(self,
                 name: str = "stream_worker",
                 config_path: str = "config/tradding_config.yaml",
                 auth_token: Optional[str] = None,
                 enable_redis_stream: bool = True,
                 reconnect_interval: int = 30,
                 health_check_interval: int = 10):
    
        self.name = name
        self.config_path = config_path
        self.auth_token = auth_token
        self.enable_redis_stream = enable_redis_stream
        self.reconnect_interval = reconnect_interval
        self.health_check_interval = health_check_interval

        # Worker state
        self._running = False
        self._stream = None  # Type: IMarketDataSource
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
            'uptime_seconds': 0
        }

        # Callbacks
        self._connection_callbacks: List[Callable] = []
        self._disconnection_callbacks: List[Callable] = []

        logger.info(f"StreamWorker '{name}' initialized")

    def add_connection_callback(self, callback: Callable) -> None:
        """Add callback to be called when stream connects"""
        self._connection_callbacks.append(callback)

    def add_disconnection_callback(self, callback: Callable) -> None:
        """Add callback to be called when stream disconnects"""
        self._disconnection_callbacks.append(callback)

    def start(self) -> bool:
        """
        Start the stream worker.

        Returns:
            True if started successfully, False otherwise
        """
        if self._running:
            logger.warning(f"StreamWorker '{self.name}' is already running")
            return True

        logger.info(f"Starting StreamWorker '{self.name}'...")

        try:
            # Initialize MarketStream (Data Source)
            self._stream = MarketStreamFactory.create_data_source(
                config_path=self.config_path,
                auth_token=self.auth_token,
                enable_redis_stream=self.enable_redis_stream
            )

            # Connect to stream
            if not self._connect_stream():
                logger.error(f"Failed to connect stream for worker '{self.name}'")
                return False

            # Start monitoring thread
            self._running = True
            self._shutdown_event.clear()
            self._stats['start_time'] = datetime.now()

            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name=f"{self.name}_monitor",
                daemon=True
            )
            self._monitor_thread.start()

            # Start reconnection thread
            self._reconnect_thread = threading.Thread(
                target=self._reconnect_loop,
                name=f"{self.name}_reconnect",
                daemon=True
            )
            self._reconnect_thread.start()

            logger.info(f"StreamWorker '{self.name}' started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start StreamWorker '{self.name}': {e}")
            self._cleanup()
            return False

    def stop(self) -> bool:
        if not self._running:
            logger.warning(f"StreamWorker '{self.name}' is not running")
            return True

        logger.info(f"Stopping StreamWorker '{self.name}'...")

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

        logger.info(f"StreamWorker '{self.name}' stopped successfully")
        return True

    def _connect_stream(self) -> bool:
        """Connect to the market stream"""
        if not self._stream:
            return False

        self._stats['connection_attempts'] += 1

        try:
            if self._stream.connect():
                self._stats['successful_connections'] += 1
                logger.info(f"Stream connected for worker '{self.name}'")

                # Call connection callbacks
                for callback in self._connection_callbacks:
                    try:
                        callback()
                    except Exception as e:
                        logger.error(f"Error in connection callback: {e}")

                return True
            else:
                logger.error(f"Failed to connect stream for worker '{self.name}'")
                return False

        except Exception as e:
            logger.error(f"Exception during stream connection for '{self.name}': {e}")
            return False

    def _disconnect_stream(self) -> None:
        """Disconnect from the market stream"""
        if self._stream:
            try:
                self._stream.disconnect()
                self._stats['disconnection_count'] += 1
                logger.info(f"Stream disconnected for worker '{self.name}'")

                # Call disconnection callbacks
                for callback in self._disconnection_callbacks:
                    try:
                        callback()
                    except Exception as e:
                        logger.error(f"Error in disconnection callback: {e}")

            except Exception as e:
                logger.error(f"Error disconnecting stream for '{self.name}': {e}")

    def _monitor_loop(self) -> None:
        """Monitor stream health and connection status"""
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
                time.sleep(1)  # Brief pause before retry

        logger.info(f"Monitor loop stopped for '{self.name}'")

    def _reconnect_loop(self) -> None:
        """Handle automatic reconnection"""
        logger.info(f"Starting reconnect loop for '{self.name}'")

        while not self._shutdown_event.is_set():
            try:
                # Check if we need to reconnect
                if self._stream and not self._stream.is_ready():
                    logger.info(f"Stream not ready, attempting reconnection for '{self.name}'")
                    self._disconnect_stream()
                    time.sleep(2)  # Brief pause
                    self._connect_stream()

                # Wait before next check
                if self._shutdown_event.wait(timeout=self.reconnect_interval):
                    break

            except Exception as e:
                logger.error(f"Error in reconnect loop for '{self.name}': {e}")
                time.sleep(5)  # Longer pause on error

        logger.info(f"Reconnect loop stopped for '{self.name}'")

    def _perform_health_check(self) -> None:
        """Perform health check on the stream"""
        if not self._stream:
            return

        try:
            is_ready = self._stream.is_ready()
            self._stats['last_health_check'] = datetime.now()

            if not is_ready:
                logger.warning(f"Health check failed for '{self.name}': stream not ready")
            else:
                logger.debug(f"Health check passed for '{self.name}'")

        except Exception as e:
            logger.error(f"Health check error for '{self.name}': {e}")

    def _update_stats(self) -> None:
        """Update runtime statistics"""
        if self._stats['start_time']:
            self._stats['uptime_seconds'] = (datetime.now() - self._stats['start_time']).total_seconds()

    def _cleanup(self) -> None:
        """Clean up resources"""
        self._stream = None
        self._monitor_thread = None
        self._reconnect_thread = None

    def get_status(self) -> Dict[str, Any]:
        """Get current status and statistics"""
        return {
            'name': self.name,
            'running': self._running,
            'connected': self._stream.is_ready() if self._stream else False,
            'config_path': self.config_path,
            'enable_redis_stream': self.enable_redis_stream,
            'stats': self._stats.copy()
        }

    def get_active_subscriptions(self) -> List[str]:
        """Get list of active subscriptions"""
        if self._stream:
            return self._stream.get_active_subscriptions()
        return []

    def add_callback(self, event_type: str, callback: Callable) -> None:
        """Add callback for stream events"""
        if self._stream:
            self._stream.add_callback(event_type, callback)

    def remove_callback(self, event_type: str, callback: Callable) -> bool:
        """Remove callback for stream events"""
        if self._stream:
            return self._stream.remove_callback(event_type, callback)
        return False

    @property
    def is_running(self) -> bool:
        """Check if worker is running"""
        return self._running

    @property
    def stream(self):
        """Get the underlying MarketStream instance"""
        return self._stream