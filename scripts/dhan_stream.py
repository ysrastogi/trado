from data_layer.market_stream.dhan_stream_worker import DhanStreamWorker

# Initialize
worker = DhanStreaamWorker(
    name="my_dhan_worker",
    enable_redis_stream=True,
    auto_reconnect=True
)

# Add callbacks
worker.add_connection_callback(lambda: print("Connected!"))
worker.add_callback('tick', lambda data: print(f"Tick: {data}"))

# Start
worker.start()

# Subscribe to symbols
worker.subscribe_symbols(["NSE_EQ:1333", "NSE_EQ:11536"])

# Get status
status = worker.get_status()
print(status)