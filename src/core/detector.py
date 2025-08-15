"""Arbitrage opportunity detection for cross-exchange trading."""

import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from loguru import logger

from .quotes import ConsolidatedQuote
from ..config import Config


class ArbitrageDirection(Enum):
    """Direction of arbitrage trade."""
    LEFT_TO_RIGHT = "left_to_right"  # Buy on left, sell on right
    RIGHT_TO_LEFT = "right_to_left"  # Buy on right, sell on left


@dataclass
class ArbitrageOpportunity:
    """Detected arbitrage opportunity."""
    symbol: str
    direction: ArbitrageDirection
    left_exchange: str
    right_exchange: str
    
    # Prices
    buy_price: float
    sell_price: float
    
    # Quantities and sizing
    trade_size: float
    net_edge_bps: float
    spread_bps: float
    
    # Timestamps
    timestamp: int = 0
    
    # Optional fields with defaults
    notional_value: float = 0.0
    expected_profit_usdt: float = 0.0
    quotes_age_ms: int = 0
    confidence_score: float = 1.0
    expires_at: int = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        """Set default values after initialization."""
        if self.metadata is None:
            self.metadata = {}
        if self.notional_value == 0.0:
            self.notional_value = self.trade_size * self.buy_price
        if self.expected_profit_usdt == 0.0:
            self.expected_profit_usdt = self.notional_value * self.net_edge_bps / 10000
        if self.timestamp == 0:
            self.timestamp = int(time.time() * 1000)
        if self.expires_at == 0:
            self.expires_at = self.timestamp + 5000  # 5 second expiry


class ArbitrageDetector:
    """Detects arbitrage opportunities between exchanges."""

    def __init__(self, config: Config):
        self.config = config
        self.min_edge_bps = config.detector.min_edge_bps
        self.min_book_age_ms = config.detector.min_book_bbo_age_ms
        self.max_spread_bps = config.detector.max_spread_bps
        self.max_notional = config.detector.max_notional_usdt
        self.slippage_model = config.detector.slippage_model

    def detect_opportunities(self, quotes: List[ConsolidatedQuote]) -> List[ArbitrageOpportunity]:
        """Detect arbitrage opportunities from consolidated quotes."""
        opportunities = []
        
        for quote in quotes:
            if not self._is_valid_quote(quote):
                continue
            
            # Check for arbitrage opportunity
            opportunity = self._check_direction(quote)
            if opportunity:
                opportunities.append(opportunity)
        
        # Sort by net edge (descending)
        opportunities.sort(key=lambda x: x.net_edge_bps, reverse=True)
        
        return opportunities

    def _is_valid_quote(self, quote: ConsolidatedQuote) -> bool:
        """Check if quote is valid for arbitrage detection."""
        if not quote.is_complete:
            return False
        
        # Check quote age
        if quote.age_ms > self.min_book_age_ms:
            return False
        
        # Check spreads (estimate from bid-ask)
        if quote.left_quote and quote.left_quote.bid > 0:
            left_spread = abs(quote.left_ask - quote.left_bid) / quote.left_bid * 10000
            if left_spread > self.max_spread_bps:
                return False
        
        if quote.right_quote and quote.right_quote.bid > 0:
            right_spread = abs(quote.right_ask - quote.right_bid) / quote.right_bid * 10000
            if right_spread > self.max_spread_bps:
                return False
        
        return True

    def _check_direction(self, quote: ConsolidatedQuote) -> Optional[ArbitrageOpportunity]:
        """Check if there's an arbitrage opportunity in either direction."""
        # Calculate raw edge (gross spread) using left vs right exchange prices
        # For left_to_right: buy on left (ask), sell on right (bid)
        # For right_to_left: buy on right (ask), sell on left (bid)
        
        # Check if we have complete quotes
        if not quote.is_complete:
            return None
        
        # Calculate potential arbitrage in both directions
        left_to_right_edge = (quote.right_bid - quote.left_ask) / quote.left_ask * 10000
        right_to_left_edge = (quote.left_bid - quote.right_ask) / quote.right_ask * 10000
        
        # Determine which direction has the better opportunity
        if left_to_right_edge > right_to_left_edge and left_to_right_edge > 0:
            direction = ArbitrageDirection.LEFT_TO_RIGHT
            raw_edge_bps = left_to_right_edge
            buy_price = quote.left_ask
            sell_price = quote.right_bid
            buy_exchange = self.config.exchanges.left
            sell_exchange = self.config.exchanges.right
        elif right_to_left_edge > 0:
            direction = ArbitrageDirection.RIGHT_TO_LEFT
            raw_edge_bps = right_to_left_edge
            buy_price = quote.right_ask
            sell_price = quote.left_bid
            buy_exchange = self.config.exchanges.right
            sell_exchange = self.config.exchanges.left
        else:
            return None
        
        # Check minimum gross spread (0.50%)
        if raw_edge_bps < self.config.detector.min_edge_bps:
            return None
        
        # Calculate fees for both legs
        left_fee_bps = self.config.get_taker_fee_bps(self.config.exchanges.left)
        right_fee_bps = self.config.get_taker_fee_bps(self.config.exchanges.right)
        total_fees_bps = left_fee_bps + right_fee_bps
        
        # Calculate net edge after fees
        net_edge_after_fees = raw_edge_bps - total_fees_bps
        
        # Check if net edge after fees meets minimum requirement
        if net_edge_after_fees < self.config.realistic_trading.min_net_edge_after_slippage:
            return None
        
        # Estimate slippage if depth model is enabled
        slippage_bps = 0.0
        if self.config.depth_model.enabled:
            slippage_bps = self._estimate_slippage(quote, buy_exchange, 'buy') + \
                          self._estimate_slippage(quote, sell_exchange, 'sell')
        
        # Final net edge after fees and slippage
        net_edge_bps = net_edge_after_fees - slippage_bps
        
        # Check final net edge requirement (0.35%)
        if net_edge_bps < self.config.realistic_trading.min_net_edge_after_slippage:
            return None
        
        # Check liquidity requirements (3x position size available)
        if not self._check_liquidity_sufficiency(quote, buy_exchange, sell_exchange):
            return None
        
        # Calculate trade size (respect max $25 per leg)
        max_trade_size_usdt = min(
            self.config.detector.max_notional_usdt,
            quote.left_quote.bid_size if buy_exchange == self.config.exchanges.left else quote.right_quote.bid_size,
            quote.left_quote.ask_size if sell_exchange == self.config.exchanges.left else quote.right_quote.ask_size
        )
        
        # Calculate expected profit
        expected_profit_usdt = (max_trade_size_usdt * net_edge_bps / 10000)
        
        return ArbitrageOpportunity(
            symbol=quote.symbol,
            direction=direction,
            left_exchange=self.config.exchanges.left,
            right_exchange=self.config.exchanges.right,
            buy_price=buy_price,
            sell_price=sell_price,
            trade_size=max_trade_size_usdt / buy_price,
            net_edge_bps=net_edge_bps,
            spread_bps=raw_edge_bps,
            timestamp=quote.ts_local,
            metadata={
                'raw_edge_bps': raw_edge_bps,
                'net_edge_after_fees': net_edge_after_fees,
                'slippage_bps': slippage_bps,
                'buy_fee_bps': left_fee_bps if buy_exchange == self.config.exchanges.left else right_fee_bps,
                'sell_fee_bps': right_fee_bps if sell_exchange == self.config.exchanges.right else left_fee_bps,
                'total_fees_bps': total_fees_bps,
                'liquidity_check': 'passed'
            }
        )

    def _check_liquidity_sufficiency(self, quote: ConsolidatedQuote, buy_exchange: str, sell_exchange: str) -> bool:
        """Check if there's sufficient liquidity (3x position size)."""
        if not self.config.depth_model.enabled:
            return True
        
        # Calculate required liquidity (3x max position size)
        max_position_size = self.config.detector.max_notional_usdt
        required_liquidity = max_position_size * self.config.depth_model.min_liquidity_multiplier
        
        # Check buy side liquidity
        buy_quote = quote.left_quote if buy_exchange == self.config.exchanges.left else quote.right_quote
        if buy_quote and buy_quote.bid_size * buy_quote.bid < required_liquidity:
            return False
        
        # Check sell side liquidity
        sell_quote = quote.left_quote if sell_exchange == self.config.exchanges.left else quote.right_quote
        if sell_quote and sell_quote.ask_size * sell_quote.ask < required_liquidity:
            return False
        
        return True

    def _calculate_trade_size(self, quote: ConsolidatedQuote, direction: ArbitrageDirection) -> Tuple[float, float]:
        """Calculate optimal trade size based on liquidity and configuration."""
        if direction == ArbitrageDirection.LEFT_TO_RIGHT:
            buy_quote = quote.left_quote
            sell_quote = quote.right_quote
        else:
            buy_quote = quote.right_quote
            sell_quote = quote.left_quote
        
        # Get available liquidity
        buy_liquidity = buy_quote.ask_size
        sell_liquidity = sell_quote.bid_size
        
        # Calculate size based on configuration
        size_pct = self.config.inventory.size_pct_of_side_liquidity
        
        # Use smaller of the two sides
        max_size = min(buy_liquidity, sell_liquidity) * size_pct
        
        # Cap by maximum notional
        max_size_by_notional = self.max_notional / buy_quote.ask
        
        # Use smaller of the two
        trade_size = min(max_size, max_size_by_notional)
        
        # Calculate notional value
        notional_value = trade_size * buy_quote.ask
        
        return trade_size, notional_value

    def _calculate_confidence(self, quote: ConsolidatedQuote, net_edge_bps: float) -> float:
        """Calculate confidence score for the opportunity."""
        confidence = 1.0
        
        # Reduce confidence for older quotes
        age_factor = max(0, 1 - (quote.age_ms / self.config.detector.min_book_bbo_age_ms))
        confidence *= age_factor
        
        # Reduce confidence for high spreads (estimate spread from bid-ask)
        if quote.is_complete:
            left_spread = abs(quote.left_ask - quote.left_bid) / quote.left_bid * 10000 if quote.left_bid > 0 else 0
            right_spread = abs(quote.right_ask - quote.right_bid) / quote.right_bid * 10000 if quote.right_bid > 0 else 0
            max_spread = max(left_spread, right_spread)
            spread_factor = max(0, 1 - (max_spread / self.config.detector.max_spread_bps))
            confidence *= spread_factor
        
        # Boost confidence for higher edges
        edge_factor = min(1.0, net_edge_bps / (self.config.detector.min_edge_bps * 2))
        confidence *= (0.5 + 0.5 * edge_factor)
        
        return max(0.0, min(1.0, confidence))

    def filter_opportunities(self, opportunities: List[ArbitrageOpportunity], 
                           min_edge_bps: Optional[float] = None,
                           max_notional: Optional[float] = None,
                           min_confidence: Optional[float] = None) -> List[ArbitrageOpportunity]:
        """Filter opportunities based on criteria."""
        filtered = []
        
        for opp in opportunities:
            # Check edge
            if min_edge_bps and opp.net_edge_bps < min_edge_bps:
                continue
            
            # Check notional
            if max_notional and opp.notional_value > max_notional:
                continue
            
            # Check confidence
            if min_confidence and opp.confidence_score < min_confidence:
                continue
            
            filtered.append(opp)
        
        return filtered

    def get_opportunity_summary(self, opportunities: List[ArbitrageOpportunity]) -> Dict[str, Any]:
        """Get summary of detected opportunities."""
        if not opportunities:
            return {
                'count': 0,
                'total_edge_bps': 0,
                'total_profit_usdt': 0,
                'avg_edge_bps': 0,
                'avg_profit_usdt': 0
            }
        
        total_edge_bps = sum(opp.net_edge_bps for opp in opportunities)
        total_profit_usdt = sum(opp.expected_profit_usdt for opp in opportunities)
        
        return {
            'count': len(opportunities),
            'total_edge_bps': total_edge_bps,
            'total_profit_usdt': total_profit_usdt,
            'avg_edge_bps': total_edge_bps / len(opportunities),
            'avg_profit_usdt': total_profit_usdt / len(opportunities),
            'top_opportunities': [
                {
                    'symbol': opp.symbol,
                    'direction': opp.direction.value,
                    'edge_bps': opp.net_edge_bps,
                    'profit_usdt': opp.expected_profit_usdt,
                    'confidence': opp.confidence_score
                }
                for opp in opportunities[:5]
            ]
        }

    def _estimate_slippage(self, quote: ConsolidatedQuote, exchange: str, side: str) -> float:
        """Estimate slippage in basis points for a given exchange and side."""
        # For now, return a conservative slippage estimate
        # In a full implementation, this would use order book depth data
        
        # Base slippage estimate (conservative)
        base_slippage_bps = 2.0  # 2 bps base slippage
        
        # Add slippage buffer from config
        slippage_buffer = self.config.depth_model.slippage_buffer_bps
        
        # Estimate based on position size relative to typical market depth
        # For $25 position size, assume minimal slippage
        position_size_usdt = self.config.detector.max_notional_usdt
        if position_size_usdt <= 25.0:
            size_factor = 1.0  # Small position, minimal slippage
        elif position_size_usdt <= 100.0:
            size_factor = 1.5  # Medium position, moderate slippage
        else:
            size_factor = 2.0  # Large position, higher slippage
        
        estimated_slippage = base_slippage_bps * size_factor + slippage_buffer
        
        return min(estimated_slippage, 10.0)  # Cap at 10 bps
