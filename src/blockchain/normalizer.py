"""
Transaction normalizer.
Converts raw Web3 data into clean Python dicts for our database.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List
from loguru import logger


class TransactionNormalizer:
    """
    Converts raw Web3 transactions into our normalized format.
    """

    WEI_PER_ETH = Decimal(10 ** 18)
    WEI_PER_GWEI = Decimal(10 ** 9)

    @staticmethod
    def _to_hex_string(value) -> str:
        """Convert bytes/HexBytes/string to a single '0x...' string."""
        if value is None:
            return ""

        # HexBytes has .hex() method — returns hex without 0x
        if hasattr(value, 'hex'):
            hex_str = value.hex()
            if not hex_str.startswith('0x'):
                hex_str = '0x' + hex_str
            return hex_str

        # Already a string — ensure it starts with exactly one '0x'
        s = str(value)
        if not s.startswith('0x'):
            s = '0x' + s
        return s

    @staticmethod
    def _to_address_string(address) -> str:
        """Convert address to lowercase '0x...' string, exactly 42 chars."""
        if not address:
            return "0x0000000000000000000000000000000000000000"

        s = str(address).lower()
        if not s.startswith('0x'):
            s = '0x' + s
        if len(s) != 42 or any(ch not in '0123456789abcdef' for ch in s[2:]):
            raise ValueError(f'Invalid Ethereum address: {address!r}')
        return s

    @staticmethod
    def _utc_naive_timestamp(value) -> datetime:
        """Return a deterministic UTC-naive datetime for a Unix timestamp.

        The current PostgreSQL schema stores transaction timestamps as
        ``timestamp without time zone``. Until that schema is deliberately
        migrated, persist UTC wall-clock values explicitly so normalization is
        identical regardless of the worker host timezone.
        """
        try:
            unix_seconds = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid block timestamp: {value!r}") from exc
        if unix_seconds < 0:
            raise ValueError(f"Invalid block timestamp: {value!r}")
        return datetime.fromtimestamp(unix_seconds, tz=timezone.utc).replace(tzinfo=None)

    def normalize(self, raw_tx: Dict, block: Dict) -> Dict:
        """Convert a raw Web3 transaction into our database format."""
        tx_hash = self._to_hex_string(raw_tx.get('hash'))
        sender = raw_tx.get('from')
        if sender is None or sender == '':
            raise ValueError('Transaction sender address is missing')
        from_addr = self._to_address_string(sender)

        # 'to' is None for contract creation
        to_raw = raw_tx.get('to')
        to_addr = self._to_address_string(to_raw) if to_raw else \
                  "0x0000000000000000000000000000000000000000"

        value_wei = int(raw_tx.get('value', 0) or 0)
        gas_price = int(raw_tx.get('gasPrice', 0) or 0)

        block_ts = block.get('timestamp', 0)
        timestamp = self._utc_naive_timestamp(block_ts)

        return {
            'hash': tx_hash,
            'from_address': from_addr,
            'to_address': to_addr,
            'value': value_wei,
            'gas_price': gas_price,
            'gas_used': int(raw_tx.get('gas', 0) or 0),
            'block_number': int(block.get('number', 0)),
            'timestamp': timestamp,
            'status': 'confirmed',
            'risk_score': 0,
        }

    def normalize_batch(self, raw_txs: List[Dict], block: Dict) -> List[Dict]:
        """Normalize a list of transactions from the same block."""
        normalized = []
        for raw_tx in raw_txs:
            try:
                normalized.append(self.normalize(raw_tx, block))
            except Exception as e:
                logger.warning(f"Skipping malformed tx: {e}")
        return normalized
