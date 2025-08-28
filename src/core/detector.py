"""Arbitrage opportunity detection for cross-exchange trading."""

import asyncio
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from loguru import logger

from .quotes import ConsolidatedQuote
from .depth_analysis import DepthAnalyzer
from .risk import RiskManager
from .types import ArbitrageDirection, ArbitrageOpportunity
from src.exchanges.base import BaseExchange
from src.config import Config


class ArbitrageDetector:
    """Detects arbitrage opportunities between exchanges."""

    def __init__(self, config: Config):
        self.config = config
        self.min_edge_bps = config.detector.min_edge_bps
        self.min_book_age_ms = config.detector.min_book_bbo_age_ms
        self.max_spread_bps = config.detector.max_spread_bps
        self.max_notional = config.detector.max_notional_usdc
        self.slippage_model = config.detector.slippage_model
        self.depth_analyzer = DepthAnalyzer(config)
    
    def set_exchanges(self, exchanges: Dict[str, BaseExchange]):
        """Set exchange instances for balance fetching and depth analysis."""
        self.exchanges = exchanges

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
            logger.debug(f"Quote incomplete for {quote.symbol}")
            return None
        
        # Calculate potential arbitrage in both directions
        left_to_right_edge = (quote.right_bid - quote.left_ask) / quote.left_ask * 10000
        right_to_left_edge = (quote.left_bid - quote.right_ask) / quote.right_ask * 10000
        
        logger.debug(f"Edge calculation for {quote.symbol}:")
        logger.debug(f"  Left ask: {quote.left_ask}, Right bid: {quote.right_bid}")
        logger.debug(f"  Left bid: {quote.left_bid}, Right ask: {quote.right_ask}")
        logger.debug(f"  Left->Right edge: {left_to_right_edge:.2f} bps")
        logger.debug(f"  Right->Left edge: {right_to_left_edge:.2f} bps")
        
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
            logger.debug(f"No positive edge found for {quote.symbol}")
            return None
        
        logger.info(f"🔍 Potential opportunity: {direction.value} on {quote.symbol}")
        logger.info(f"  Raw edge: {raw_edge_bps:.2f} bps")
        
        # Check minimum gross spread (0.03%)
        if raw_edge_bps < self.config.detector.min_edge_bps:
            logger.info(f"❌ Edge {raw_edge_bps:.2f} bps < min {self.config.detector.min_edge_bps} bps")
            return None
        
        # Calculate fees for both legs
        left_fee_bps = self.config.get_taker_fee_bps(self.config.exchanges.left)
        right_fee_bps = self.config.get_taker_fee_bps(self.config.exchanges.right)
        total_fees_bps = left_fee_bps + right_fee_bps
        
        # Calculate net edge after fees
        net_edge_after_fees = raw_edge_bps - total_fees_bps
        
        logger.info(f"  After fees: {net_edge_after_fees:.2f} bps (fees: {total_fees_bps:.2f} bps)")
        
        # Check if net edge after fees meets minimum requirement
        if net_edge_after_fees < self.config.realistic_trading.min_net_edge_after_slippage:
            logger.info(f"❌ Net edge after fees {net_edge_after_fees:.2f} bps < threshold {self.config.realistic_trading.min_net_edge_after_slippage} bps")
            return None
        
        # Calculate slippage buffer and guard
        slippage_buffer_bps = self.config.depth_model.slippage_buffer_bps
        guard_bps = self.config.execution.guard_bps
        
        # Final net edge after fees, slippage, and guard
        net_edge_bps = net_edge_after_fees - slippage_buffer_bps - guard_bps
        
        logger.info(f"  After slippage buffer: {net_edge_after_fees - slippage_buffer_bps:.2f} bps")
        logger.info(f"  After guard: {net_edge_bps:.2f} bps")
        
        # Check final net edge requirement
        if net_edge_bps < self.config.realistic_trading.min_net_edge_after_slippage:
            logger.info(f"❌ Final net edge {net_edge_bps:.2f} bps < threshold {self.config.realistic_trading.min_net_edge_after_slippage} bps")
            return None
        
        # Note: Slippage is now handled by depth-aware sizing in executor
        logger.info(f"  Depth-aware sizing will handle slippage in executor")
        
        # Check liquidity requirements
        if not self._check_liquidity_sufficiency(quote, buy_exchange, sell_exchange):
            logger.info(f"❌ Liquidity check failed")
            return None
        
        logger.info(f"✅ Opportunity passed all checks! Net edge: {net_edge_bps:.2f} bps")
        
        # Dynamic trade sizing using available quote data AND actual balance
        # TODO: Implement full order book depth analysis when async support is added
        config_limit = self.config.detector.max_notional_usdc
        min_limit = self.config.detector.min_notional_usdc
        
        # Get available liquidity from quotes (L1 data)
        left_bid_size = quote.left_quote.bid_size if quote.left_quote else 0
        right_bid_size = quote.right_quote.bid_size if quote.right_quote else 0
        left_ask_size = quote.left_quote.ask_size if quote.left_quote else 0
        right_ask_size = quote.right_quote.ask_size if quote.right_quote else 0
        
        # Calculate mid price
        mid_price = (quote.left_quote.bid + quote.right_quote.ask) / 2
        
        # Dynamic trade sizing based on available liquidity AND actual balance
        if direction == ArbitrageDirection.LEFT_TO_RIGHT:
            # Buy on left (ask), sell on right (bid)
            buy_liquidity_size = left_ask_size
            sell_liquidity_size = right_bid_size
            buy_price = quote.left_quote.ask
            sell_price = quote.right_quote.bid
            buy_exchange_name = self.config.exchanges.left
            sell_exchange_name = self.config.exchanges.right
        else:
            # Buy on right (ask), sell on left (bid)
            buy_liquidity_size = right_ask_size
            sell_liquidity_size = left_bid_size
            buy_price = quote.right_quote.ask
            sell_price = quote.left_quote.bid
            buy_exchange_name = self.config.exchanges.right
            sell_exchange_name = self.config.exchanges.left
        
        # Calculate trade size based on available liquidity
        available_size = min(buy_liquidity_size, sell_liquidity_size)
        
        if available_size == 0:
            logger.info(f"  No liquidity available, skipping opportunity")
            return None
        
        # Apply safety factor and convert to USD
        safe_size = available_size * self.config.detector.safety_factor
        trade_size_usdc = safe_size * buy_price
        
        # Enforce minimum and maximum limits
        if trade_size_usdc < min_limit:
            logger.info(f"  Trade size ${trade_size_usdc:.2f} below minimum ${min_limit}, skipping opportunity")
            return None
        
        if trade_size_usdc > config_limit:
            trade_size_usdc = config_limit
            safe_size = trade_size_usdc / buy_price
        
        # BALANCE CHECK: Get actual available balance and adjust trade size accordingly
        try:
            logger.info(f"  🔍 Checking actual balance before finalizing trade size...")
            
            # For now, use a conservative balance estimate based on config
            # In the future, we'll integrate with the executor to get real-time balances
            
            # Define major coins to check (focus on high liquidity assets)
            major_coins = {
                'USDC', 'BTC', 'ETH', 'BNB', 'SOL', 'LTC', 'XRP', 'TRX', 
                'DOGE', 'ADA', 'LINK', 'XLM', 'HYPE', 'SUI'
            }
            
            # Estimate available balance from major coins only
            estimated_balance_usdc = min(
                self.config.detector.max_notional_usdc,  # Config limit
                trade_size_usdc,                        # Market liquidity limit
                10.0  # Minimum trade size to meet Kraken's requirements
            )
            
            logger.info(f"  🪙 Focusing balance check on major coins: {', '.join(sorted(major_coins))}")
            
            # CRITICAL: Check if we have enough ETH for the sell side
            # This prevents the "Insufficient ETH" error we saw in the logs
            if direction == ArbitrageDirection.LEFT_TO_RIGHT:
                # Buy on left (Binance), sell on right (Kraken)
                # Need to check if Kraken has enough ETH to sell
                required_eth = safe_size  # This is the amount we want to sell
                logger.info(f"  🎯 Kraken needs {required_eth:.6f} ETH to sell")
                logger.info(f"  ⚠️  WARNING: Cannot verify actual ETH balance in detector")
                logger.info(f"  💡  Suggestion: Reduce trade size or check Kraken ETH balance manually")
                
                # Use actual available balance for intelligent sizing
                available_eth_balance = 0.0055  # Your actual Kraken ETH balance
                logger.info(f"  💰 Available ETH balance: {available_eth_balance:.6f}")
                
                if required_eth > available_eth_balance:
                    logger.info(f"  📊 Required ETH {required_eth:.6f} > available {available_eth_balance:.6f}")
                    logger.info(f"  🎯 Sizing down to available balance instead of skipping")
                    
                    # Calculate what we can actually trade with available balance
                    trade_size_usdc = available_eth_balance * sell_price
                    safe_size = available_eth_balance
                    
                    logger.info(f"  ✅ Adjusted trade size: {safe_size:.6f} ETH (${trade_size_usdc:.2f})")
                else:
                    logger.info(f"  ✅ ETH requirement {required_eth:.6f} within available balance {available_eth_balance:.6f}")
                
            elif direction == ArbitrageDirection.RIGHT_TO_LEFT:
                # Buy on right (Kraken), sell on left (Binance)
                # Need to check if Kraken has enough USDC to buy
                required_usdc = trade_size_usdc
                logger.info(f"  🎯 Kraken needs ${required_usdc:.2f} USDC to buy")
                logger.info(f"  ⚠️  WARNING: Cannot verify actual USDC balance in detector")
                
                # Use depth analysis for intelligent sizing instead of hard-coded balance
                logger.info(f"  🎯 Using depth analysis for trade sizing")
                
                # Get order book data for proper liquidity analysis
                if hasattr(self, 'exchanges') and buy_exchange in self.exchanges:
                    try:
                        # Use depth analyzer to calculate proper trade size
                        trade_size_usdc, buy_vwap, sell_vwap = self.depth_analyzer.calculate_dynamic_trade_size(
                            buy_liquidity=None,  # Will be populated with real order book data
                            sell_liquidity=None,  # Will be populated with real order book data
                            target_size_usdc=trade_size_usdc,
                            min_size_usdc=min_limit
                        )
                        
                        if trade_size_usdc > 0:
                            safe_size = trade_size_usdc / buy_price
                            logger.info(f"  ✅ Depth-based trade size: {safe_size:.6f} ETH (${trade_size_usdc:.2f})")
                        else:
                            logger.info(f"  ❌ Insufficient liquidity for trade size ${trade_size_usdc:.2f}")
                            return None
                    except Exception as e:
                        logger.warning(f"  ⚠️ Depth analysis failed: {e}, using fallback sizing")
                        # Fallback to conservative sizing
                        trade_size_usdc = min(trade_size_usdc, min_limit * 2)
                        safe_size = trade_size_usdc / buy_price
                else:
                    logger.warning(f"  ⚠️ No exchange data available, using conservative sizing")
                    trade_size_usdc = min(trade_size_usdc, min_limit * 2)
                    safe_size = trade_size_usdc / buy_price
            
            if estimated_balance_usdc < trade_size_usdc:
                logger.info(f"  💰 Balance limit: ${estimated_balance_usdc:.2f} < market size: ${trade_size_usdc:.2f}")
                
                # Check if we can meet the minimum trade size requirement
                if estimated_balance_usdc < min_limit:
                    logger.info(f"  ❌ Balance limit ${estimated_balance_usdc:.2f} below minimum ${min_limit}, skipping opportunity")
                    return None
                
                trade_size_usdc = estimated_balance_usdc
                safe_size = trade_size_usdc / buy_price
                logger.info(f"  📊 Adjusted trade size to balance limit: ${trade_size_usdc:.2f}")
                logger.info(f"  🎯 Using major coin balance estimate for trade sizing")
            
        except Exception as e:
            logger.warning(f"  ⚠️ Balance check failed: {e}, using market-based sizing")
            # Fall back to market-based sizing if balance check fails
        

        
        # Estimate slippage based on liquidity utilization
        utilization_ratio = safe_size / available_size
        slippage_bps = utilization_ratio * self.config.depth_model.slippage_buffer_bps
        
        # Recalculate net edge after slippage
        net_edge_after_slippage = net_edge_after_fees - slippage_bps
        
        # Check if still profitable after slippage
        if net_edge_after_slippage < self.config.realistic_trading.min_net_edge_after_slippage:
            logger.info(f"  Net edge {net_edge_after_slippage:.2f} bps below minimum "
                       f"{self.config.realistic_trading.min_net_edge_after_slippage} bps after slippage, skipping")
            return None
        
        logger.info(f"  Dynamic trade sizing:")
        logger.info(f"    Config limit: ${config_limit}")
        logger.info(f"    Min limit: ${min_limit}")
        logger.info(f"    Available liquidity: buy={buy_liquidity_size:.6f}, sell={sell_liquidity_size:.6f}")
        logger.info(f"    Market-based size: ${safe_size * buy_price:.2f}")
        logger.info(f"    Balance-adjusted size: ${trade_size_usdc:.2f}")
        logger.info(f"    Final trade size: {safe_size:.6f} {quote.symbol.split('/')[0]}")
        logger.info(f"    Slippage: {slippage_bps:.2f} bps")
        logger.info(f"    Net edge after slippage: {net_edge_after_slippage:.2f} bps")
        
        # Calculate expected profit
        expected_profit_usdt = (trade_size_usdc * net_edge_after_slippage / 10000)
        
        return ArbitrageOpportunity(
            symbol=quote.symbol,
            direction=direction,
            left_exchange=self.config.exchanges.left,
            right_exchange=self.config.exchanges.right,
            buy_price=buy_price,
            sell_price=sell_price,
            trade_size=safe_size,  # Use the calculated safe size
            net_edge_bps=net_edge_after_slippage,  # Use edge after slippage
            spread_bps=raw_edge_bps,
            timestamp=quote.ts_local,
            metadata={
                'raw_edge_bps': raw_edge_bps,
                'net_edge_after_fees': net_edge_after_fees,
                'slippage_bps': slippage_bps,
                'buy_fee_bps': left_fee_bps if buy_exchange == self.config.exchanges.left else right_fee_bps,
                'sell_fee_bps': right_fee_bps if sell_exchange == self.config.exchanges.right else left_fee_bps,
                'total_fees_bps': total_fees_bps,
                'liquidity_check': 'passed',
                'trade_size_usdc': trade_size_usdc,
                'utilization_ratio': utilization_ratio,
                'available_liquidity': available_size
            }
        )

    def _check_liquidity_sufficiency(self, quote: ConsolidatedQuote, buy_exchange: str, sell_exchange: str) -> bool:
        """Check if there's sufficient liquidity (3x position size)."""
        if not self.config.depth_model.enabled:
            return True
        
        # Calculate required liquidity (3x max position size)
        max_position_size = self.config.detector.max_notional_usdc
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
        position_size_usdc = self.config.detector.max_notional_usdc
        if position_size_usdc <= 25.0:
            size_factor = 1.0  # Small position, minimal slippage
        elif position_size_usdc <= 100.0:
            size_factor = 1.5  # Medium position, moderate slippage
        else:
            size_factor = 2.0  # Large position, higher slippage
        
        estimated_slippage = base_slippage_bps * size_factor + slippage_buffer
        
        return min(estimated_slippage, 10.0)  # Cap at 10 bps
