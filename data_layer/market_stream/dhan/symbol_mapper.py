import csv
import logging
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

class SymbolMapper:
    def __init__(self):
        # Map "SEGMENT:ID" -> Symbol Name (e.g. "NSE_EQ:1333" -> "HDFCBANK")
        self.id_to_symbol: Dict[str, str] = {}
        # Map Symbol Name -> "SEGMENT:ID"
        self.symbol_to_id: Dict[str, Tuple[str, str]] = {}

    def load_from_csv(self, file_path: str):
        """
        Load mapping from the Dhan Scrip Master CSV.
        """
        try:
            logger.info(f"Loading symbol mapping from {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                count = 0
                for row in reader:
                    exch_id = row.get('EXCH_ID')
                    segment = row.get('SEGMENT') # This might need mapping to Dhan Enum strings if they differ
                    sec_id = row.get('SECURITY_ID')
                    symbol = row.get('SYMBOL_NAME')
                    
                    if not (exch_id and sec_id and symbol):
                        continue

                    # Map CSV Exchange/Segment to Dhan ExchangeSegment Enum String
                    # Logic based on common Dhan patterns:
                    dhan_segment = self._map_segment(exch_id, segment)
                    
                    if dhan_segment:
                        self.symbol_to_id[symbol] = (dhan_segment, sec_id)
                        self.id_to_symbol[f"{dhan_segment}:{sec_id}"] = symbol
                        count += 1
                
                logger.info(f"Loaded {count} symbol mappings")
        except Exception as e:
            logger.error(f"Failed to load symbol mapping from CSV: {e}")

    def _map_segment(self, exch_id: str, segment: str) -> Optional[str]:
        # Mapping logic based on observation and standard Dhan segments
        # NSE_EQ, NSE_FNO, NSE_CUR, BSE_EQ, BSE_FNO, BSE_CUR, MCX_COMM
        
        exch_id = exch_id.upper().strip()
        # segment in CSV seems to be 'E', 'D', 'C', 'F' etc.
        # Let's assume:
        # E -> Equity
        # D -> Derivatives (FNO)
        # C -> Currency
        # F -> Commodity? Or Futures?
        
        # Based on the file snippet: BSE, C -> Currency (USDINR)
        
        if exch_id == 'NSE':
            if segment == 'E': return 'NSE_EQ'
            if segment == 'D': return 'NSE_FNO'
            if segment == 'C': return 'NSE_CUR'
        elif exch_id == 'BSE':
            if segment == 'E': return 'BSE_EQ'
            if segment == 'D': return 'BSE_FNO'
            if segment == 'C': return 'BSE_CUR'
        elif exch_id == 'MCX':
            return 'MCX_COMM'
            
        return None

    def load_mapping(self, mapping_data: Dict[str, str]):
        """
        Load mapping from a dictionary.
        Format: {"HDFCBANK": "NSE_EQ:1333"}
        """
        for symbol, id_str in mapping_data.items():
            parts = id_str.split(":")
            if len(parts) == 2:
                segment, sec_id = parts
                self.symbol_to_id[symbol] = (segment, sec_id)
                self.id_to_symbol[f"{segment}:{sec_id}"] = symbol

    def get_symbol(self, exchange_segment: Any, security_id: Any) -> str:
        # Exchange Segment mapping (from docs Annexure - not provided, assuming int or str)
        # Construct key
        key = f"{exchange_segment}:{security_id}"
        return self.id_to_symbol.get(key, str(security_id))

    def get_security_id(self, symbol: str) -> Optional[Tuple[str, str]]:
        """
        Returns (ExchangeSegment, SecurityId)
        """
        # If symbol is already in format "SEGMENT:ID", return it split
        if ":" in symbol:
            parts = symbol.split(":")
            if len(parts) == 2:
                return parts[0], parts[1]
        
        return self.symbol_to_id.get(symbol)
