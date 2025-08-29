"""Spot to Perpetual arbitrage opportunity detection."""

import asyncio
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from loguru import logger

from src.core.types import ArbitrageDirection, ArbitrageOpportunity
from src.core.depth_analysis import DepthAnalyzer
from src.exchanges.base import BaseExchange
from src.config import Config


class SpotPerpDirection(Enum):
    """Direction of spot↔perp arbitrage."""
    SPOT_BUY_PERP_SELL = "spot_buy_perp_sell"  # Buy spot, sell perp (when perp is rich)
    SPOT_SELL_PERP_BUY = "spot_sell_perp_buy"  # Sell spot, buy perp (when perp is cheap)


@dataclass
class SpotPerpOpportunity:
    """Detected spot↔perp arbitrage opportunity."""
    symbol: str
    direction: SpotPerpDirection
    spot_exchange: str
    perp_exchange: str
    
    # Prices
    spot_price: float
    perp_price: float
    
    # VWAP calculations
    spot_vwap: float
    perp_vwap: float
    
    # Quantities and sizing
    trade_size: float
    gross_edge_bps: float
    net_edge_bps: float
    
    # Fees and costs
    total_fees_bps: float
    funding_cost_bps: float
    slippage_buffer_bps: float
    
    # Timestamps
    timestamp: int = 0
    expires_at: int = 0
    
    # Metadata
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        """Set default values after initialization."""
        if self.metadata is None:
            self.metadata = {}
        if self.timestamp == 0:
            self.timestamp = int(time.time() * 1000)
        if self.expires_at == 0:
            self.expires_at = self.timestamp + 5000  # 5 second expiry


class SpotPerpDetector:
    """Detects spot↔perp arbitrage opportunities."""

    def __init__(self, config: Config):
        self.config = config
        self.min_edge_bps = config.detector.min_edge_bps
        self.min_book_age_ms = config.detector.min_book_bbo_age_ms
        self.max_spread_bps = config.detector.max_spread_bps
        self.max_venue_skew_ms = config.detector.max_venue_clock_skew_ms
        self.min_net_edge = config.realistic_trading.min_net_edge_after_slippage
        
        # Depth model settings
        self.depth_levels = config.depth_model.levels
        self.max_depth_pct = config.depth_model.max_depth_pct
        self.liquidity_multiplier = config.depth_model.min_liquidity_multiplier
        self.safety_factor = config.depth_model.safety_factor
        self.slippage_buffer_bps = config.depth_model.slippage_buffer_bps
        
        # Perp-specific settings
        self.max_hold_minutes = config.perp.max_hold_minutes
        self.funding_cost_bps_per_8h = config.perp.funding_cost_bps_per_8h
        self.require_funding_sign_ok = config.perp.require_funding_sign_ok
        
        # Fee structure
        self.fees = config.fees
        
        # Initialize depth analyzer
        self.depth_analyzer = DepthAnalyzer(config)
        
        # Exchange instances
        self.spot_exchange: Optional[BaseExchange] = None
        self.perp_exchange: Optional[BaseExchange] = None

    def set_exchanges(self, spot_exchange: BaseExchange, perp_exchange: BaseExchange):
        """Set exchange instances for the detector."""
        self.spot_exchange = spot_exchange
        self.perp_exchange = perp_exchange

    def detect_opportunities(self, spot_quotes: List[Any], perp_quotes: List[Any]) -> List[SpotPerpOpportunity]:
        """Detect spot↔perp arbitrage opportunities."""
        opportunities = []
        
        # Since quotes are already mapped by the runner, we can process them directly
        if len(spot_quotes) != len(perp_quotes):
            logger.warning(f"⚠️ Mismatched quote counts: {len(spot_quotes)} spot vs {len(perp_quotes)} perp")
            return opportunities
        
        # Process each mapped pair
        for i in range(len(spot_quotes)):
            spot_quote = spot_quotes[i]
            perp_quote = perp_quotes[i]
            
            # Use spot symbol as the base symbol for the opportunity
            symbol = spot_quote.symbol
            
            if not self._is_valid_quote_pair(spot_quote, perp_quote):
                continue
            
            # Check both directions
            for direction in SpotPerpDirection:
                opportunity = self._check_direction(symbol, spot_quote, perp_quote, direction)
                if opportunity:
                    opportunities.append(opportunity)
        
        # Sort by net edge (descending)
        opportunities.sort(key=lambda x: x.net_edge_bps, reverse=True)
        
        return opportunities

    def _is_valid_quote_pair(self, spot_quote: Any, perp_quote: Any) -> bool:
        """Check if quote pair is valid for arbitrage detection."""
        # Check quote age
        current_time = int(time.time() * 1000)
        
        if current_time - spot_quote.ts_exchange > self.min_book_age_ms:
            return False
        
        if current_time - perp_quote.ts_exchange > self.min_book_age_ms:
            return False
        
        # Check venue clock skew (more lenient in mock mode)
        skew_ms = abs(spot_quote.ts_exchange - perp_quote.ts_exchange)
        # In mock mode, be more lenient with venue clock skew
        max_skew = self.max_venue_skew_ms * 10 if hasattr(self, 'mock_mode') and self.mock_mode else self.max_venue_skew_ms
        if skew_ms > max_skew:
            return False
        
        # Check spreads
        if spot_quote.spread_bps > self.max_spread_bps:
            return False
        
        if perp_quote.spread_bps > self.max_spread_bps:
            return False
        
        return True

    def _check_direction(self, symbol: str, spot_quote: Any, perp_quote: Any, 
                        direction: SpotPerpDirection) -> Optional[SpotPerpOpportunity]:
        """Check if there's an arbitrage opportunity in the given direction."""
        try:
            if direction == SpotPerpDirection.SPOT_BUY_PERP_SELL:
                # Buy spot (ask), sell perp (bid)
                spot_price = spot_quote.ask
                perp_price = perp_quote.bid
                spot_vwap = self._calculate_vwap(spot_quote, "ask", direction)
                perp_vwap = self._calculate_vwap(perp_quote, "bid", direction)
                
            else:  # SPOT_SELL_PERP_BUY
                # Sell spot (bid), buy perp (ask)
                spot_price = spot_quote.bid
                perp_price = perp_quote.ask
                spot_vwap = self._calculate_vwap(spot_quote, "bid", direction)
                perp_vwap = self._calculate_vwap(perp_quote, "ask", direction)
            
            # Calculate gross edge
            if direction == SpotPerpDirection.SPOT_BUY_PERP_SELL:
                gross_edge_bps = ((perp_vwap - spot_vwap) / spot_vwap) * 10000
            else:
                gross_edge_bps = ((spot_vwap - perp_vwap) / perp_vwap) * 10000
            
            # Check minimum gross edge
            if gross_edge_bps < self.min_edge_bps:
                logger.debug(f"❌ Gross edge {gross_edge_bps:.2f} bps < minimum {self.min_edge_bps} bps for {symbol} {direction.value}")
                return None
            
            logger.debug(f"✅ Gross edge {gross_edge_bps:.2f} bps >= minimum {self.min_edge_bps} bps for {symbol} {direction.value}")
            
            # Calculate fees
            spot_fee_bps = self.fees.taker_bps.get(self.spot_exchange.name, 7.5)
            perp_fee_bps = self.fees.taker_bps.get(self.perp_exchange.name, 3.0)
            total_fees_bps = spot_fee_bps + perp_fee_bps
            
            # Calculate funding cost
            funding_cost_bps = self._calculate_funding_cost(direction)
            
            # Calculate net edge
            net_edge_bps = gross_edge_bps - total_fees_bps - self.slippage_buffer_bps - funding_cost_bps
            
            # Check minimum net edge
            if net_edge_bps < self.min_net_edge:
                logger.debug(f"❌ Net edge {net_edge_bps:.2f} bps < minimum {self.min_net_edge} bps for {symbol} {direction.value}")
                logger.debug(f"   Breakdown: Gross {gross_edge_bps:.2f} - Fees {total_fees_bps:.2f} - Slippage {self.slippage_buffer_bps:.2f} - Funding {funding_cost_bps:.2f} = {net_edge_bps:.2f}")
                return None
            
            logger.debug(f"✅ Net edge {net_edge_bps:.2f} bps >= minimum {self.min_net_edge} bps for {symbol} {direction.value}")
            
            # Calculate trade size based on available liquidity
            trade_size = self._calculate_trade_size(spot_quote, perp_quote, direction)
            if trade_size <= 0:
                logger.debug(f"❌ Trade size {trade_size:.4f} <= 0 for {symbol} {direction.value}")
                return None
            
            logger.debug(f"✅ Trade size {trade_size:.4f} > 0 for {symbol} {direction.value}")
            
            # Create opportunity
            opportunity = SpotPerpOpportunity(
                symbol=symbol,
                direction=direction,
                spot_exchange=self.spot_exchange.name,
                perp_exchange=self.perp_exchange.name,
                spot_price=spot_price,
                perp_price=perp_price,
                spot_vwap=spot_vwap,
                perp_vwap=perp_vwap,
                trade_size=trade_size,
                gross_edge_bps=gross_edge_bps,
                net_edge_bps=net_edge_bps,
                total_fees_bps=total_fees_bps,
                funding_cost_bps=funding_cost_bps,
                slippage_buffer_bps=self.slippage_buffer_bps
            )
            
            logger.info(f"Spot↔Perp opportunity detected: {symbol} {direction.value}")
            logger.info(f"  Gross edge: {gross_edge_bps:.2f} bps, Net edge: {net_edge_bps:.2f} bps")
            logger.info(f"  Spot VWAP: {spot_vwap:.4f}, Perp VWAP: {perp_vwap:.4f}")
            logger.info(f"  Trade size: {trade_size:.4f}")
            
            return opportunity
            
        except Exception as e:
            logger.error(f"Error checking direction {direction} for {symbol}: {e}")
            return None

    def _calculate_vwap(self, quote: Any, side: str, direction: SpotPerpDirection) -> float:
        """Calculate VWAP for the given side and direction."""
        try:
            # For now, use simple VWAP calculation
            # In production, this would use the depth analyzer for more sophisticated calculations
            
            if side == "bid":
                # Use bid side for selling
                if hasattr(quote, 'bids') and quote.bids:
                    total_value = sum(price * size for price, size in quote.bids[:self.depth_levels])
                    total_size = sum(size for _, size in quote.bids[:self.depth_levels])
                    return total_value / total_size if total_size > 0 else quote.bid
                else:
                    return quote.bid
            else:  # ask
                # Use ask side for buying
                if hasattr(quote, 'asks') and quote.asks:
                    total_value = sum(price * size for price, size in quote.asks[:self.depth_levels])
                    total_size = sum(size for _, size in quote.asks[:self.depth_levels])
                    return total_value / total_size if total_size > 0 else quote.ask
                else:
                    return quote.ask
                    
        except Exception as e:
            logger.error(f"Error calculating VWAP: {e}")
            # Fallback to best bid/ask
            return quote.bid if side == "bid" else quote.ask

    def _calculate_funding_cost(self, direction: SpotPerpDirection) -> float:
        """Calculate funding cost for the expected holding period."""
        try:
            # Convert 8h funding rate to per-minute
            funding_per_minute = self.funding_cost_bps_per_8h / (8 * 60)
            
            # Calculate total funding cost for expected holding period
            total_funding_bps = funding_per_minute * self.max_hold_minutes
            
            # For SPOT_BUY_PERP_SELL, we're short perp so we receive funding
            # For SPOT_SELL_PERP_BUY, we're long perp so we pay funding
            if direction == SpotPerpDirection.SPOT_BUY_PERP_SELL:
                total_funding_bps = -total_funding_bps  # Negative cost = benefit
            
            return total_funding_bps
            
        except Exception as e:
            logger.error(f"Error calculating funding cost: {e}")
            return 0.0

    def _calculate_trade_size(self, spot_quote: Any, perp_quote: Any, 
                             direction: SpotPerpDirection) -> float:
        """Calculate optimal trade size based on available liquidity."""
        try:
            # Get available liquidity on both sides
            if direction == SpotPerpDirection.SPOT_BUY_PERP_SELL:
                spot_liquidity = self._get_side_liquidity(spot_quote, "ask")
                perp_liquidity = self._get_side_liquidity(perp_quote, "bid")
            else:
                spot_liquidity = self._get_side_liquidity(spot_quote, "bid")
                perp_liquidity = self._get_side_liquidity(perp_quote, "ask")
            
            # Use the smaller of the two for safety
            max_size = min(spot_liquidity, perp_liquidity)
            
            # Apply safety factors
            safe_size = max_size / self.liquidity_multiplier * self.safety_factor
            
            # Check minimum notional
            min_notional = self.config.detector.min_notional_usdc
            if safe_size * spot_quote.mid_price < min_notional:
                return 0.0
            
            return safe_size
            
        except Exception as e:
            logger.error(f"Error calculating trade size: {e}")
            return 0.0

    def _get_side_liquidity(self, quote: Any, side: str) -> float:
        """Get available liquidity for the given side."""
        try:
            if side == "bid":
                levels = getattr(quote, 'bids', [])
            else:
                levels = getattr(quote, 'asks', [])
            
            if not levels:
                return 0.0
            
            # Calculate total liquidity within max_depth_pct
            mid_price = quote.mid_price
            max_depth_price = mid_price * (1 + self.max_depth_pct) if side == "ask" else mid_price * (1 - self.max_depth_pct)
            
            total_liquidity = 0.0
            for price, size in levels:
                if side == "ask" and price <= max_depth_price:
                    total_liquidity += size
                elif side == "bid" and price >= max_depth_price:
                    total_liquidity += size
            
            return total_liquidity
            
        except Exception as e:
            logger.error(f"Error getting side liquidity: {e}")
            return 0.0
