import sys
import logging
import time
import argparse
import threading
from typing import Dict, Any, List, Optional
import json
import signal
import os
from data_layer.market_stream import MarketStream

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import modules
from data_layer.worker_manager import WorkerManager
from data_layer.aggregator.worker import MarketAggregatorProcessor, AggregatorWorker
from data_layer.market_stream import MarketStream
from data_layer.market_stream.stream_worker import StreamWorker
from data_layer.aggregator.market_aggregator import get_aggregator_instance


class WorkerCLI:
    """Command-line interface for worker management"""
    
    def __init__(self):
        """Initialize the CLI"""
        self.worker_manager = WorkerManager.get_instance()
        self.running = False
        self.demo_resources = {}
    
    def register_default_workers(self):
        """Register default workers for testing"""
        # Register Stream Worker
        if not self._is_worker_registered("stream_worker"):
            logger.info("Registering stream worker...")
            
            stream_worker = StreamWorker(
                name="stream_worker",
                enable_redis_stream=True
            )
            
            # Save resources for cleanup
            self.demo_resources["stream_worker"] = stream_worker
            
            # Register with worker manager
            self.worker_manager.register_worker("stream_worker", stream_worker)
            
            logger.info("Stream worker registered successfully")
            return True
        
        # For now we just have the market data worker
        if not self._is_worker_registered("market_data_worker"):
            logger.info("Registering market data worker...")
            
            # Create a demo market stream
            market_stream = MarketStream()
            market_stream.connect()
            
            # Create processor with callback to log data
            processor = MarketAggregatorProcessor(
                market_stream=market_stream,
                process_callback=self._process_market_data,
                worker_name="market_data_worker"
            )
            
            # Save resources for cleanup
            self.demo_resources["market_stream"] = market_stream
            self.demo_resources["processor"] = processor
            
            # Register with worker manager manually (processor.start would also do this, 
            # but we want to register without starting)
            self.worker_manager.register_worker("market_data_worker", processor.worker)
            
            # The MarketStream will automatically subscribe to symbols from config
            # when connected and authenticated - no need to manually subscribe
            
            logger.info("Market data worker registered successfully")
            return True
        return False
    
    def _is_worker_registered(self, name: str) -> bool:
        """Check if a worker is registered"""
        status = self.worker_manager.get_all_worker_status()
        return name in status
    
    def _process_market_data(self, data: Dict[str, Any]):
        """Process market data (demo callback)"""
        symbol = data.get("symbol", "unknown")
        price = data.get("price", 0.0)
        
        # Log only every 10th tick to avoid flooding
        if hash(f"{symbol}_{price}") % 10 == 0:
            logger.info(f"Market data: {symbol} @ {price:.2f}")
    
    def start_worker(self, name: str) -> bool:
        """Start a worker by name"""
        if not self._is_worker_registered(name):
            logger.error(f"Worker '{name}' is not registered")
            return False
        
        logger.info(f"Starting worker '{name}'...")
        result = self.worker_manager.start_worker(name)
        
        if result:
            logger.info(f"Worker '{name}' started successfully")
        else:
            logger.error(f"Failed to start worker '{name}'")
        
        return result
    
    def stop_worker(self, name: str) -> bool:
        """Stop a worker by name"""
        if not self._is_worker_registered(name):
            logger.error(f"Worker '{name}' is not registered")
            return False
        
        logger.info(f"Stopping worker '{name}'...")
        result = self.worker_manager.stop_worker(name)
        
        if result:
            logger.info(f"Worker '{name}' stopped successfully")
        else:
            logger.error(f"Failed to stop worker '{name}'")
        
        return result
    
    def start_all_workers(self) -> Dict[str, bool]:
        """Start all registered workers"""
        logger.info("Starting all workers...")
        results = self.worker_manager.start_all_workers()
        
        # Log results
        success_count = sum(1 for v in results.values() if v)
        logger.info(f"Started {success_count}/{len(results)} workers")
        
        return results
    
    def stop_all_workers(self) -> Dict[str, bool]:
        """Stop all registered workers"""
        logger.info("Stopping all workers...")
        results = self.worker_manager.stop_all_workers()
        
        # Log results
        success_count = sum(1 for v in results.values() if v)
        logger.info(f"Stopped {success_count}/{len(results)} workers")
        
        return results
    
    def get_worker_status(self, name: Optional[str] = None) -> Dict[str, Any]:
        """Get status of a worker or all workers"""
        if name:
            if not self._is_worker_registered(name):
                logger.error(f"Worker '{name}' is not registered")
                return {}
            
            status = self.worker_manager.get_worker_status(name)
            return {name: status}
        else:
            # Get all worker statuses
            return self.worker_manager.get_all_worker_status()
    
    def list_workers(self) -> List[str]:
        """List all registered workers"""
        status = self.worker_manager.get_all_worker_status()
        return list(status.keys())
    
    def monitor_workers(self, interval: float = 2.0):
        """Monitor all workers continuously"""
        self.running = True
        
        # Start monitoring in worker manager
        self.worker_manager.start_monitoring(interval=interval)
        
        try:
            # Display headers
            print("\n{:<20} {:<10} {:<15} {:<10} {:<15} {:<10}".format(
                "Worker Name", "Status", "Processed", "Dropped", "Queue Size", "Errors"
            ))
            print("-" * 80)
            
            # Monitor loop
            while self.running:
                os.system('cls' if os.name == 'nt' else 'clear')
                print(f"Worker Monitor - Press Ctrl+C to exit - {time.strftime('%H:%M:%S')}")
                print("\n{:<20} {:<10} {:<15} {:<10} {:<15} {:<10}".format(
                    "Worker Name", "Status", "Processed", "Dropped", "Queue Size", "Errors"
                ))
                print("-" * 80)
                
                # Get all worker statuses
                statuses = self.worker_manager.get_all_worker_status()
                
                for name, status in statuses.items():
                    running = status.get("running", False)
                    running_status = "RUNNING" if running else "STOPPED"
                    processed = status.get("processed_count", 0)
                    dropped = status.get("dropped_count", 0)
                    queue_size = status.get("queue_size", 0)
                    errors = status.get("error_count", 0)
                    
                    print("{:<20} {:<10} {:<15} {:<10} {:<15} {:<10}".format(
                        name, running_status, processed, dropped, queue_size, errors
                    ))
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        
        finally:
            self.running = False
            self.worker_manager.stop_monitoring()
    
    def handle_stream_command(self, action: str) -> None:
        """Handle stream worker commands"""
        worker_name = "stream_worker"
        
        if action == "start":
            logger.info("Starting stream worker in background...")
            
            try:
                import subprocess
                # Run the stream worker script in background
                env = os.environ.copy()
                env['PYTHONPATH'] = os.getcwd()
                process = subprocess.Popen(
                    [sys.executable, "scripts/run_stream_worker.py"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=os.getcwd(),
                    env=env
                )
                
                # Give it a moment to start
                time.sleep(2)
                
                # Check if process is still running
                if process.poll() is None:
                    logger.info("Stream worker started successfully in background.")
                    logger.info("Use 'stream monitor' to monitor it, or 'stream stop' to stop it.")
                else:
                    logger.error("Stream worker failed to start")
                    
            except Exception as e:
                logger.error(f"Error starting stream worker: {e}")
        
        elif action == "stop":
            STATUS_FILE = "/tmp/stream_worker_status.json"
            
            try:
                if os.path.exists(STATUS_FILE):
                    with open(STATUS_FILE, 'r') as f:
                        status = json.load(f)
                    
                    pid = status.get("pid")
                    if pid:
                        logger.info(f"Stopping stream worker process {pid}...")
                        os.kill(pid, signal.SIGTERM)
                        # Remove status file
                        os.remove(STATUS_FILE)
                        logger.info("Stream worker stopped successfully")
                    else:
                        logger.error("No PID found in status file")
                else:
                    logger.error("Stream worker status file not found")
            except Exception as e:
                logger.error(f"Error stopping stream worker: {e}")
        
        elif action == "status":
            statuses = self.get_worker_status(worker_name)
            if statuses:
                self.print_status_table(statuses)
                
                # Get additional stream-specific info
                if worker_name in self.demo_resources:
                    worker = self.demo_resources[worker_name]
                    stream_status = worker.get_status()
                    subscriptions = worker.get_active_subscriptions()
                    
                    print(f"\nStream Worker Details:")
                    print(f"  Connected: {stream_status['connected']}")
                    print(f"  Active Subscriptions: {len(subscriptions)}")
                    if subscriptions:
                        print(f"  Subscriptions: {', '.join(subscriptions[:5])}{'...' if len(subscriptions) > 5 else ''}")
                    print(f"  Connection Attempts: {stream_status['stats']['connection_attempts']}")
                    print(f"  Successful Connections: {stream_status['stats']['successful_connections']}")
                    print(f"  Uptime: {stream_status['stats']['uptime_seconds']:.1f} seconds")
                    print()
            else:
                logger.error("Stream worker not found")
        
        elif action == "monitor":
            STATUS_FILE = "/tmp/stream_worker_status.json"
            
            logger.info("Monitoring stream worker... (Press Ctrl+C to stop)")
            
            try:
                while True:
                    try:
                        if os.path.exists(STATUS_FILE):
                            with open(STATUS_FILE, 'r') as f:
                                status = json.load(f)
                            
                            running = status.get("running", False)
                            connected = status.get("connected", False)
                            subscriptions = status.get("subscriptions", 0)
                            uptime = status.get("uptime_seconds", 0)
                            
                            print(f"Worker Name          Status     Uptime          Processed  Errors")
                            print("-" * 80)
                            print(f"stream_worker        {'RUNNING' if running else 'STOPPED'}    {uptime:.0f}s              0          0")
                            print(f"\nStream Status: Connected={connected}, Subscriptions={subscriptions}")
                        else:
                            print("Worker Name          Status     Uptime          Processed  Errors")
                            print("-" * 80)
                            print("stream_worker        STOPPED    0s              0          0")
                            print("\nStream Status: Not running")
                    
                    except Exception as e:
                        logger.error(f"Error reading status: {e}")
                        print("Worker Name          Status     Uptime          Processed  Errors")
                        print("-" * 80)
                        print("stream_worker        ERROR      0s              0          0")
                    
                    time.sleep(5)  # Update every 5 seconds
                    
            except KeyboardInterrupt:
                logger.info("Stream monitoring stopped")
    
    def run_demo(self):
        """Run a demo with the market data worker"""
        logger.info("Starting market data demo...")
        
        # Register workers if not already done
        self.register_default_workers()
        
        # Start the market data worker
        if self.start_worker("market_data_worker"):
            logger.info("Market data worker started. Press Ctrl+C to stop...")
            
            try:
                # Keep running until interrupted
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Demo interrupted by user")
            
            # Stop the worker
            self.stop_worker("market_data_worker")
        
        logger.info("Market data demo completed")
    
    def print_status_table(self, statuses: Dict[str, Dict[str, Any]]):
        """Print worker status as a formatted table"""
        if not statuses:
            print("No workers registered")
            return
            
        # Print headers
        print("\n{:<20} {:<10} {:<15} {:<10} {:<15}".format(
            "Worker Name", "Status", "Uptime", "Processed", "Errors"
        ))
        print("-" * 70)
        
        # Print each worker status
        for name, status in statuses.items():
            running = status.get("running", False)
            running_status = "RUNNING" if running else "STOPPED"
            
            uptime = status.get("uptime_seconds", 0)
            uptime_str = f"{int(uptime)}s" if uptime < 60 else f"{int(uptime/60)}m {int(uptime%60)}s"
            
            processed = status.get("processed_count", 0)
            errors = status.get("error_count", 0)
            
            print("{:<20} {:<10} {:<15} {:<10} {:<15}".format(
                name, running_status, uptime_str, processed, errors
            ))
        
        print()


def main():
    """Main entry point for the CLI"""
    parser = argparse.ArgumentParser(description="Worker Management CLI")
    
    # Define commands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all registered workers")
    
    # Start command
    start_parser = subparsers.add_parser("start", help="Start a worker")
    start_parser.add_argument("name", help="Name of the worker to start")
    
    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop a worker")
    stop_parser.add_argument("name", help="Name of the worker to stop")
    
    # Start all command
    start_all_parser = subparsers.add_parser("start-all", help="Start all registered workers")
    
    # Stop all command
    stop_all_parser = subparsers.add_parser("stop-all", help="Stop all registered workers")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show status of a worker or all workers")
    status_parser.add_argument("name", nargs="?", help="Name of the worker (optional)")
    
    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Monitor all workers continuously")
    
    # Demo command
    demo_parser = subparsers.add_parser("demo", help="Run a demo with market data worker")
    
    # Stream command
    stream_parser = subparsers.add_parser("stream", help="Manage the stream worker")
    stream_parser.add_argument("action", choices=["start", "stop", "status", "monitor"], 
                              help="Action to perform on the stream worker")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Create CLI instance
    cli = WorkerCLI()
    
    # Handle signals
    def signal_handler(sig, frame):
        logger.info("Stopping workers due to signal")
        cli.stop_all_workers()
        cli.running = False
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Register default workers for testing (skip for stream commands)
    if args.command != "stream":
        cli.register_default_workers()
    
    # Execute command
    if args.command == "list":
        workers = cli.list_workers()
        print(f"\nRegistered workers ({len(workers)}):")
        for worker in workers:
            print(f"  - {worker}")
        print()
    
    elif args.command == "start":
        cli.start_worker(args.name)
    
    elif args.command == "stop":
        cli.stop_worker(args.name)
    
    elif args.command == "start-all":
        cli.start_all_workers()
    
    elif args.command == "stop-all":
        cli.stop_all_workers()
    
    elif args.command == "status":
        statuses = cli.get_worker_status(args.name)
        cli.print_status_table(statuses)
    
    elif args.command == "monitor":
        try:
            cli.monitor_workers()
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
    
    elif args.command == "demo":
        cli.run_demo()
    
    elif args.command == "stream":
        cli.handle_stream_command(args.action)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()