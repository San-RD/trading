"""Order book depth model for slippage estimation."""

from typing import Dict, List, Tuple, Optional
from decimal import Decimal
import asyncio
from loguru import logger


class DepthLevel:
    """Represents a single level in the order book."""
    
    def __init__(self, price: float, quantity: float):
        self.price = Decimal(str(price))
        self.quantity = Decimal(str(quantity))
    
    def __repr__(self) -> str:
        return f"DepthLevel(price={self.price}, qty={self.quantity})"


class DepthModel:
    """Models order book depth for slippage estimation."""
    
    def __init__(self, enabled: bool = False, levels: int = 10):
        self.enabled = enabled
        self.levels = levels
        self._depth_cache: Dict[str, Dict[str, List[DepthLevel]]] = {}
        self._last_update: Dict[str, float] = {}
        self._update_interval = 30  # seconds
    
    def update_depth(self, symbol: str, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]]):
        """Update depth data for a symbol."""
        if not self.enabled:
            return
        
        current_time = asyncio.get_event_loop().time()
        
        # Convert to DepthLevel objects
        bid_levels = [DepthLevel(price, qty) for price, qty in bids[:self.levels]]
        ask_levels = [DepthLevel(price, qty) for price, qty in asks[:self.levels]]
        
        self._depth_cache[symbol] = {
            "bids": bid_levels,
            "asks": ask_levels
        }
        self._last_update[symbol] = current_time
        
        logger.debug(f"Updated depth for {symbol}: {len(bid_levels)} bids, {len(ask_levels)} asks")
    
    def get_effective_price(self, symbol: str, side: str, quantity: float) -> Optional[float]:
        """Calculate effective price for a given quantity considering depth."""
        if not self.enabled or symbol not in self._depth_cache:
            return None
        
        current_time = asyncio.get_event_loop().time()
        if current_time - self._last_update.get(symbol, 0) > self._update_interval:
            logger.warning(f"Depth data for {symbol} is stale")
            return None
        
        levels = self._depth_cache[symbol]["asks" if side == "buy" else "bids"]
        target_qty = Decimal(str(quantity))
        cumulative_qty = Decimal("0")
        cumulative_value = Decimal("0")
        
        for level in levels:
            if cumulative_qty >= target_qty:
                break
            
            # Calculate how much we can take from this level
            available_qty = min(level.quantity, target_qty - cumulative_qty)
            cumulative_qty += available_qty
            cumulative_value += available_qty * level.price
        
        if cumulative_qty < target_qty:
            logger.warning(f"Insufficient depth for {quantity} {symbol} on {side} side")
            return None
        
        effective_price = float(cumulative_value / cumulative_qty)
        return effective_price
    
    def estimate_slippage_bps(self, symbol: str, side: str, quantity: float) -> Optional[float]:
        """Estimate slippage in basis points for a given quantity."""
        if not self.enabled:
            return 0.0
        
        # Get top of book price
        top_price = self._get_top_price(symbol, side)
        if top_price is None:
            return None
        
        # Get effective price
        effective_price = self.get_effective_price(symbol, side, quantity)
        if effective_price is None:
            return None
        
        # Calculate slippage
        if side == "buy":
            slippage_bps = ((effective_price - top_price) / top_price) * 10000
        else:
            slippage_bps = ((top_price - effective_price) / top_price) * 10000
        
        return max(0.0, slippage_bps)
    
    def _get_top_price(self, symbol: str, side: str) -> Optional[float]:
        """Get top of book price for a symbol and side."""
        if symbol not in self._depth_cache:
            return None
        
        levels = self._depth_cache[symbol]["asks" if side == "buy" else "bids"]
        if not levels:
            return None
        
        return float(levels[0].price)
    
    def is_data_fresh(self, symbol: str) -> bool:
        """Check if depth data is fresh for a symbol."""
        if not self.enabled or symbol not in self._last_update:
            return False
        
        current_time = asyncio.get_event_loop().time()
        return current_time - self._last_update[symbol] <= self._update_interval
    
    def get_depth_summary(self, symbol: str) -> Optional[Dict]:
        """Get a summary of current depth for a symbol."""
        if not self.enabled or symbol not in self._depth_cache:
            return None
        
        bids = self._depth_cache[symbol]["bids"]
        asks = self._depth_cache[symbol]["asks"]
        
        total_bid_qty = sum(level.quantity for level in bids)
        total_ask_qty = sum(level.quantity for level in asks)
        
        return {
            "symbol": symbol,
            "bid_levels": len(bids),
            "ask_levels": len(asks),
            "total_bid_qty": float(total_bid_qty),
            "total_ask_qty": float(total_ask_qty),
            "spread_bps": self._calculate_spread_bps(symbol),
            "last_update": self._last_update.get(symbol, 0)
        }
    
    def _calculate_spread_bps(self, symbol: str) -> Optional[float]:
        """Calculate current spread in basis points."""
        if symbol not in self._depth_cache:
            return None
        
        bids = self._depth_cache[symbol]["bids"]
        asks = self._depth_cache[symbol]["asks"]
        
        if not bids or not asks:
            return None
        
        best_bid = float(bids[0].price)
        best_ask = float(asks[0].price)
        
        spread_bps = ((best_ask - best_bid) / best_bid) * 10000
        return spread_bps
