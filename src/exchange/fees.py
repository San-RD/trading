"""Fee calculation and management for exchanges."""

from typing import Dict, Optional
from ..config import get_config


class FeeManager:
    """Manages trading fees for different symbols and VIP tiers."""
    
    def __init__(self):
        self.config = get_config()
        self._symbol_fees: Dict[str, Dict[str, float]] = {}
        self._default_taker_bps = self.config.fees.taker_bps
        self._default_maker_bps = self.config.fees.maker_bps
    
    def set_symbol_fees(self, symbol: str, taker_bps: float, maker_bps: float):
        """Set custom fees for a specific symbol."""
        self._symbol_fees[symbol] = {
            "taker": taker_bps,
            "maker": maker_bps
        }
    
    def get_taker_fee_bps(self, symbol: str) -> float:
        """Get taker fee in basis points for a symbol."""
        if symbol in self._symbol_fees:
            return self._symbol_fees[symbol]["taker"]
        return self._default_taker_bps
    
    def get_maker_fee_bps(self, symbol: str) -> float:
        """Get maker fee in basis points for a symbol."""
        if symbol in self._symbol_fees:
            return self._symbol_fees[symbol]["maker"]
        return self._default_maker_bps
    
    def get_taker_fee_rate(self, symbol: str) -> float:
        """Get taker fee as a decimal rate (e.g., 0.001 for 10 bps)."""
        return self.get_taker_fee_bps(symbol) / 10000
    
    def get_maker_fee_rate(self, symbol: str) -> float:
        """Get maker fee as a decimal rate (e.g., 0.0008 for 8 bps)."""
        return self.get_maker_fee_bps(symbol) / 10000
    
    def calculate_fee_amount(self, symbol: str, notional: float, is_taker: bool = True) -> float:
        """Calculate fee amount for a given notional."""
        if is_taker:
            fee_rate = self.get_taker_fee_rate(symbol)
        else:
            fee_rate = self.get_maker_fee_rate(symbol)
        
        return notional * fee_rate


# Global fee manager instance
_fee_manager = FeeManager()


def get_taker_fee_bps(symbol: str) -> float:
    """Get taker fee in basis points for a symbol."""
    return _fee_manager.get_taker_fee_bps(symbol)


def get_maker_fee_bps(symbol: str) -> float:
    """Get maker fee in basis points for a symbol."""
    return _fee_manager.get_maker_fee_bps(symbol)


def get_taker_fee_rate(symbol: str) -> float:
    """Get taker fee as a decimal rate."""
    return _fee_manager.get_taker_fee_rate(symbol)


def get_maker_fee_rate(symbol: str) -> float:
    """Get maker fee as a decimal rate."""
    return _fee_manager.get_maker_fee_rate(symbol)


def calculate_fee_amount(symbol: str, notional: float, is_taker: bool = True) -> float:
    """Calculate fee amount for a given notional."""
    return _fee_manager.calculate_fee_amount(symbol, notional, is_taker)


def set_symbol_fees(symbol: str, taker_bps: float, maker_bps: float):
    """Set custom fees for a specific symbol."""
    _fee_manager.set_symbol_fees(symbol, taker_bps, maker_bps)
