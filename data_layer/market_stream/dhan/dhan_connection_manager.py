import json
import logging
import time
import threading
import websocket
from typing import Dict, Any, Optional, Callable

from data_layer.market_stream.interfaces import IConnectionManager

logger = logging.getLogger(__name__)

class DhanConnectionManager(IConnectionManager):
    def __init__(
        self, 
        ws_url: str, 
        client_id: str,
        access_token: str,
        reconnect_attempts: int,
        reconnect_delay: int,
        message_handler: Callable[[Any], None]
    ):
        self.logger = logger.getChild("DhanConnectionManager")
        # Construct URL with auth params
        # wss://api-feed.dhan.co?version=2&token=...&clientId=...&authType=2
        self.ws_url = f"{ws_url}?version=2&token={access_token}&clientId={client_id}&authType=2"
        self.reconnect_attempts = reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.message_handler = message_handler
        
        self.ws = None
        self.is_connected_flag = False
        self.running = False
        self.connection_thread = None
        self._request_id = 1

    def get_next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def connect(self) -> bool:
        try:
            self.logger.info(f"Connecting to Dhan WebSocket")
            
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            
            self.running = True
            self.connection_thread = threading.Thread(target=self.ws.run_forever)
            self.connection_thread.daemon = False
            self.connection_thread.start()
            
            timeout = 10
            start_time = time.time()
            while not self.is_connected_flag and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            if self.is_connected_flag:
                self.logger.info("Successfully connected to Dhan WebSocket")
                return True
            else:
                self.logger.error("Failed to connect to Dhan WebSocket")
                return False
                
        except Exception as e:
            self.logger.error(f"Error connecting to WebSocket: {e}")
            return False

    def disconnect(self):
        self.logger.info("Disconnecting from Dhan WebSocket")
        self.running = False
        self.is_connected_flag = False
        
        if self.ws:
            self.ws.close()
        
        if self.connection_thread and self.connection_thread.is_alive():
            self.connection_thread.join(timeout=1)

    def _on_open(self, ws):
        self.logger.info("WebSocket connection opened")
        self.is_connected_flag = True

    def _on_message(self, ws, message):
        try:
            # Dhan sends binary data for market feed, but text/json for some control messages?
            # Docs say: "All request messages over WebSocket are in JSON whereas all response messages over WebSocket are in Binary."
            # But also: "In case of WebSocket disconnection from server side, you will receive disconnection packet, which will have disconnection reason code."
            
            # We pass raw message to handler, it will decide how to parse
            self.message_handler(message)
            
        except Exception as e:
            self.logger.error(f"Error handling WebSocket message: {e}")

    def _on_error(self, ws, error):
        self.logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        self.logger.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")
        self.is_connected_flag = False
        
        if self.running:
            self._reconnect()

    def send_message(self, message: Any):
        if self.ws and self.is_connected_flag:
            try:
                if isinstance(message, dict):
                    message_data = json.dumps(message)
                    self.ws.send(message_data)
                elif isinstance(message, bytes):
                    self.ws.send(message, opcode=websocket.ABNF.OPCODE_BINARY)
                else:
                    self.ws.send(message)
            except Exception as e:
                self.logger.error(f"Error sending message: {e}")
        else:
            self.logger.error("WebSocket not connected, cannot send message")

    def _reconnect(self) -> bool:
        for attempt in range(self.reconnect_attempts):
            self.logger.info(f"Reconnection attempt {attempt + 1}/{self.reconnect_attempts}")
            time.sleep(self.reconnect_delay)
            
            if self.connect():
                return True
        
        self.logger.error("Failed to reconnect after maximum attempts")
        return False

    def is_ready(self) -> bool:
        return self.is_connected_flag
