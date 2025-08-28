#!/usr/bin/env python3
"""
Depth analysis module for order book aggregation and VWAP calculation.
Handles dynamic trade sizing based on available liquidity across multiple levels.
"""

import logging
from typing import Dict, List, Tuple, Optional, NamedTuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DepthLevel:
    """Represents a single level in the order book."""
    price: float
    size: float
    timestamp: int


@dataclass
class AggregatedLiquidity:
    """Aggregated liquidity information for a side of the order book."""
    total_size: float
    vwap: float
    levels_used: int
    max_depth_pct: float
    mid_price: float


class DepthAnalyzer:
    """Analyzes order book depth for optimal trade sizing and execution."""
    
    def __init__(self, config):
        self.config = config
        self.max_depth_pct = config.depth_model.max_depth_pct
        self.vwap_levels = config.depth_model.vwap_calculation_levels
        self.per_order_cap = config.depth_model.per_order_cap_usdc
    
    def analyze_order_book_side(self, 
                               orders: List[Tuple[float, float]], 
                               mid_price: float,
                               side: str) -> AggregatedLiquidity:
        """
        Analyze one side of the order book (bids or asks).
        
        Args:
            orders: List of (price, size) tuples
            mid_price: Current mid price
            side: 'bid' or 'ask'
        
        Returns:
            AggregatedLiquidity with total size, VWAP, and depth info
        """
        if not orders:
            return AggregatedLiquidity(0, 0, 0, 0, mid_price)
        
        # Calculate price limits based on max_depth_pct
        if side == 'bid':
            min_price = mid_price * (1 - self.max_depth_pct / 100)
            # For bids, we want prices >= min_price (higher is better)
            valid_orders = [(p, s) for p, s in orders if p >= min_price]
        else:  # ask
            max_price = mid_price * (1 + self.max_depth_pct / 100)
            # For asks, we want prices <= max_price (lower is better)
            valid_orders = [(p, s) for p, s in orders if p <= max_price]
        
        if not valid_orders:
            return AggregatedLiquidity(0, 0, 0, 0, mid_price)
        
        # Limit to configured number of levels
        valid_orders = valid_orders[:self.vwap_levels]
        
        # Calculate VWAP and total size
        total_notional = 0.0
        total_size = 0.0
        
        for price, size in valid_orders:
            notional = price * size
            total_notional += notional
            total_size += size
        
        vwap = total_notional / total_size if total_size > 0 else 0
        
        # Calculate actual depth used
        if side == 'bid':
            depth_pct = ((mid_price - valid_orders[-1][0]) / mid_price) * 100
        else:
            depth_pct = ((valid_orders[-1][0] - mid_price) / mid_price) * 100
        
        logger.debug(f"Depth analysis {side}: {len(valid_orders)} levels, "
                    f"total size: {total_size:.6f}, VWAP: {vwap:.2f}, "
                    f"depth: {depth_pct:.3f}%")
        
        return AggregatedLiquidity(
            total_size=total_size,
            vwap=vwap,
            levels_used=len(valid_orders),
            max_depth_pct=depth_pct,
            mid_price=mid_price
        )
    
    def calculate_dynamic_trade_size(self, 
                                   buy_liquidity: AggregatedLiquidity,
                                   sell_liquidity: AggregatedLiquidity,
                                   target_size_usdc: float,
                                   min_size_usdc: float) -> Tuple[float, float, float]:
        """
        Calculate optimal trade size based on available liquidity.
        
        Args:
            buy_liquidity: Aggregated liquidity for buy side
            sell_liquidity: Aggregated liquidity for sell side
            target_size_usdc: Target trade size from config
            min_size_usdc: Minimum trade size from config
        
        Returns:
            Tuple of (trade_size_usdc, buy_vwap, sell_vwap)
        """
        # Check if we have sufficient liquidity for target size
        required_liquidity = target_size_usdc * self.config.detector.liquidity_multiplier
        
        # Calculate available size based on smaller side
        available_size = min(buy_liquidity.total_size, sell_liquidity.total_size)
        
        if available_size == 0:
            logger.warning("No liquidity available on either side")
            return 0, 0, 0
        
        # Apply safety factor
        safe_size = available_size * self.config.detector.safety_factor
        
        # Calculate trade size in USD terms
        # Use VWAP for more accurate sizing
        buy_vwap = buy_liquidity.vwap
        sell_vwap = sell_liquidity.vwap
        
        if buy_vwap == 0 or sell_vwap == 0:
            logger.warning("Invalid VWAP prices")
            return 0, 0, 0
        
        # Calculate trade size in base asset
        trade_size_base = safe_size
        
        # Convert to USD terms
        trade_size_usdc = trade_size_base * buy_vwap
        
        # Enforce minimum and maximum limits
        if trade_size_usdc < min_size_usdc:
            logger.info(f"Trade size ${trade_size_usdc:.2f} below minimum ${min_size_usdc}, skipping")
            return 0, 0, 0
        
        if trade_size_usdc > target_size_usdc:
            trade_size_usdc = target_size_usdc
            trade_size_base = trade_size_usdc / buy_vwap
        
        logger.info(f"Dynamic trade sizing: available: {available_size:.6f}, "
                   f"safe: {safe_size:.6f}, final: ${trade_size_usdc:.2f}")
        
        return trade_size_usdc, buy_vwap, sell_vwap
    
    def split_large_orders(self, trade_size_usdc: float) -> List[float]:
        """
        Split large orders into smaller chunks for better execution.
        
        Args:
            trade_size_usdc: Total trade size in USD
        
        Returns:
            List of order sizes to execute
        """
        if trade_size_usdc <= self.per_order_cap:
            return [trade_size_usdc]
        
        # Calculate number of orders needed
        num_orders = int(trade_size_usdc / self.per_order_cap) + 1
        order_size = trade_size_usdc / num_orders
        
        # Ensure no order is below minimum
        if order_size < self.config.detector.min_notional_usdc:
            num_orders = int(trade_size_usdc / self.config.detector.min_notional_usdc)
            order_size = trade_size_usdc / num_orders
        
        orders = [order_size] * num_orders
        
        # Adjust last order to account for rounding
        orders[-1] = trade_size_usdc - sum(orders[:-1])
        
        logger.info(f"Split order: ${trade_size_usdc:.2f} into {num_orders} orders: {orders}")
        
        return orders
    
    def estimate_slippage(self, 
                         buy_liquidity: AggregatedLiquidity,
                         sell_liquidity: AggregatedLiquidity,
                         trade_size_base: float) -> float:
        """
        Estimate slippage based on order book depth.
        
        Args:
            buy_liquidity: Aggregated liquidity for buy side
            sell_liquidity: Aggregated liquidity for sell side
            trade_size_base: Trade size in base asset
        
        Returns:
            Estimated slippage in basis points
        """
        if not self.config.depth_model.enabled:
            return 0.0
        
        # Calculate slippage for each side
        buy_slippage = self._calculate_side_slippage(buy_liquidity, trade_size_base, 'buy')
        sell_slippage = self._calculate_side_slippage(sell_liquidity, trade_size_base, 'sell')
        
        total_slippage = buy_slippage + sell_slippage
        
        logger.debug(f"Slippage estimation: buy: {buy_slippage:.2f} bps, "
                    f"sell: {sell_slippage:.2f} bps, total: {total_slippage:.2f} bps")
        
        return total_slippage
    
    def _calculate_side_slippage(self, 
                                liquidity: AggregatedLiquidity, 
                                trade_size: float, 
                                side: str) -> float:
        """Calculate slippage for one side of the order book."""
        if liquidity.total_size == 0 or trade_size == 0:
            return 0.0
        
        # Simple linear slippage model
        # As trade size approaches total liquidity, slippage increases
        utilization_ratio = trade_size / liquidity.total_size
        
        if utilization_ratio >= 1.0:
            # We're consuming all available liquidity
            return liquidity.max_depth_pct * 100  # Convert to basis points
        
        # Linear interpolation between 0 and max depth
        slippage_pct = utilization_ratio * liquidity.max_depth_pct
        return slippage_pct * 100  # Convert to basis points
