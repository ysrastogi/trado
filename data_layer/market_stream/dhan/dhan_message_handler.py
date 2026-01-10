import logging
import struct
from typing import Dict, Callable, Any, Optional
from datetime import datetime

from data_layer.market_stream.callback_manager import CallbackManager
from data_layer.market_stream.models import TickData, OHLCData
from data_layer.market_stream.redis_stream_publisher import RedisStreamPublisher
from data_layer.market_stream.interfaces import IMessageHandler
from data_layer.market_stream.dhan.symbol_mapper import SymbolMapper

logger = logging.getLogger(__name__)

class DhanMessageHandler(IMessageHandler):
    def __init__(
        self,
        callback_manager: CallbackManager,
        subscription_manager,
        enable_redis_stream: bool = True,
        symbol_mapper: Optional[SymbolMapper] = None
    ):
        self.logger = logger.getChild("DhanMessageHandler")
        self.callback_manager = callback_manager
        self.subscription_manager = subscription_manager
        self.enable_redis_stream = enable_redis_stream
        self.symbol_mapper = symbol_mapper
        self.redis_publisher: Optional[RedisStreamPublisher] = None
        
        if self.enable_redis_stream:
            try:
                self.redis_publisher = RedisStreamPublisher()
                self.logger.info("Redis Stream Publisher initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize Redis Stream Publisher: {e}")

    def handle_message(self, data: Any) -> None:
        if isinstance(data, bytes):
            self._parse_binary_message(data)
        else:
            self.logger.warning(f"Received non-binary message: {data}")

    def _parse_binary_message(self, data: bytes):
        if len(data) < 8:
            self.logger.warning("Received packet too short for header")
            return

        # Header: FeedResponseCode (1), MessageLength (2), ExchangeSegment (1), SecurityId (4)
        # Little Endian (<)
        header_fmt = "<B H B I"
        header_size = struct.calcsize(header_fmt)
        
        feed_response_code, message_length, exchange_segment, security_id = struct.unpack(header_fmt, data[:header_size])
        
        payload = data[header_size:]
        
        if feed_response_code == 2: # Ticker Packet
            self._handle_ticker_packet(payload, exchange_segment, security_id)
        elif feed_response_code == 4: # Quote Packet
            self._handle_quote_packet(payload, exchange_segment, security_id)
        elif feed_response_code == 8: # Full Packet
            self._handle_full_packet(payload, exchange_segment, security_id)
        elif feed_response_code == 50: # Disconnect
            self._handle_disconnect_packet(payload)
        else:
            self.logger.debug(f"Unhandled feed response code: {feed_response_code}")

    def _handle_ticker_packet(self, payload, exchange_segment, security_id):
        # LTP (4 bytes float), LTT (4 bytes int)
        fmt = "<f I"
        if len(payload) < struct.calcsize(fmt):
            return
            
        ltp, ltt = struct.unpack(fmt, payload[:struct.calcsize(fmt)])
        
        # Map security_id to symbol
        symbol = str(security_id)
        if self.symbol_mapper:
            # We need to map exchange_segment int to string if possible, but mapper expects string
            # Assuming exchange_segment is int from binary, we might need a reverse map for that too?
            # Actually, SymbolMapper.get_symbol takes (exchange_segment, security_id)
            # But we need to know what the int value maps to (e.g. 1 -> NSE_EQ)
            # For now, let's pass the raw values and let mapper handle if it can, or just use ID
            # Wait, SymbolMapper uses string keys "SEGMENT:ID".
            # We need to map int segment to string segment.
            # Let's assume standard Dhan segment IDs:
            # NSE_EQ = 1, NSE_FNO = 2, NSE_CUR = 3, BSE_EQ = 4, etc.
            # This mapping is missing. I'll add a helper method or dictionary here.
            segment_str = self._map_segment_id_to_str(exchange_segment)
            symbol = self.symbol_mapper.get_symbol(segment_str, str(security_id))
        
        tick_data = {
            'symbol': symbol,
            'quote': ltp,
            'epoch': ltt,
            'exchange_segment': exchange_segment
        }
        
        self.logger.debug(f"Tick: {symbol} {ltp} @ {ltt}")
        
        # Trigger callbacks
        self.callback_manager.trigger_callbacks("tick", tick_data)
        
        # Structured data
        try:
            timestamp = datetime.fromtimestamp(ltt)
            structured_tick = TickData(symbol=symbol, quote=ltp, epoch=ltt, timestamp=timestamp)
            self.callback_manager.trigger_callbacks("tick_structured", structured_tick)
            
            if self.redis_publisher:
                self.redis_publisher.publish_tick(structured_tick)
        except Exception as e:
            self.logger.error(f"Error processing tick data: {e}")

    def _map_segment_id_to_str(self, segment_id: int) -> str:
        # Mapping based on Dhan documentation (Annexure)
        # 1: NSE_EQ, 2: NSE_FNO, 3: NSE_CUR, 4: BSE_EQ, 5: MCX_COMM, 7: BSE_CUR, 8: BSE_FNO
        mapping = {
            1: "NSE_EQ",
            2: "NSE_FNO",
            3: "NSE_CUR",
            4: "BSE_EQ",
            5: "MCX_COMM",
            7: "BSE_CUR",
            8: "BSE_FNO"
        }
        return mapping.get(segment_id, str(segment_id))

    def _handle_quote_packet(self, payload, exchange_segment, security_id):
        # LTP(4), LastQty(2), LTT(4), ATP(4), Vol(4), TotalSellQty(4), TotalBuyQty(4), Open(4), Close(4), High(4), Low(4)
        fmt = "<f H I f I I I f f f f"
        if len(payload) < struct.calcsize(fmt):
            return
            
        ltp, last_qty, ltt, atp, vol, total_sell, total_buy, open_val, close_val, high_val, low_val = struct.unpack(fmt, payload[:struct.calcsize(fmt)])
        
        symbol = str(security_id)
        if self.symbol_mapper:
            segment_str = self._map_segment_id_to_str(exchange_segment)
            symbol = self.symbol_mapper.get_symbol(segment_str, str(security_id))
        
        quote_data = {
            'symbol': symbol,
            'ltp': ltp,
            'ltt': ltt,
            'volume': vol,
            'open': open_val,
            'close': close_val,
            'high': high_val,
            'low': low_val
        }
        
        self.callback_manager.trigger_callbacks("quote", quote_data)

    def _handle_full_packet(self, payload, exchange_segment, security_id):
        # Similar to Quote but with OI and Market Depth
        # For now, treat as Quote + OI
        # LTP(4), LastQty(2), LTT(4), ATP(4), Vol(4), TotalSellQty(4), TotalBuyQty(4), OI(4), HighestOI(4), LowestOI(4), Open(4), Close(4), High(4), Low(4)
        # Then 100 bytes of depth
        fmt = "<f H I f I I I I I I f f f f"
        base_size = struct.calcsize(fmt)
        
        if len(payload) < base_size:
            return
            
        unpacked = struct.unpack(fmt, payload[:base_size])
        ltp = unpacked[0]
        ltt = unpacked[2]
        
        symbol = str(security_id)
        if self.symbol_mapper:
            segment_str = self._map_segment_id_to_str(exchange_segment)
            symbol = self.symbol_mapper.get_symbol(segment_str, str(security_id))
        
        # Just trigger tick for now
        tick_data = {
            'symbol': symbol,
            'quote': ltp,
            'epoch': ltt,
            'exchange_segment': exchange_segment
        }
        self.callback_manager.trigger_callbacks("tick", tick_data)

    def _handle_disconnect_packet(self, payload):
        if len(payload) >= 2:
            code = struct.unpack("<H", payload[:2])[0]
            self.logger.warning(f"Dhan Disconnect Packet Received. Code: {code}")
