"""Spot to Perpetual arbitrage execution planning."""

import asyncio
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from loguru import logger

from .detector import SpotPerpOpportunity, SpotPerpDirection
from src.exchanges.base import BaseExchange


@dataclass
class ExecutionLeg:
    """Single leg of a spot↔perp arbitrage execution."""
    exchange: str
    symbol: str
    side: str  # "buy" or "sell"
    order_type: str  # "IOC" or "FOK"
    amount: float
    price: float
    reduce_only: bool = False
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        """Set default values after initialization."""
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ExecutionPlan:
    """Complete execution plan for spot↔perp arbitrage."""
    opportunity: SpotPerpOpportunity
    legs: List[ExecutionLeg]
    expected_pnl: float
    max_slippage_bps: float
    execution_timeout_ms: int
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        """Set default values after initialization."""
        if self.metadata is None:
            self.metadata = {}


class SpotPerpPlanner:
    """Plans execution of spot↔perp arbitrage opportunities."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Execution settings
        self.execution_type = config.execution.type
        self.guard_bps = config.execution.guard_bps
        self.max_leg_latency_ms = config.execution.max_leg_latency_ms
        self.partial_fill_threshold = config.execution.partial_fill_threshold
        self.per_order_cap_usd = config.execution.per_order_cap_usd
        
        # Risk settings
        self.max_notional = config.risk.max_notional_usdc
        
        # Exchange instances
        self.spot_exchange: Optional[BaseExchange] = None
        self.perp_exchange: Optional[BaseExchange] = None

    def set_exchanges(self, spot_exchange: BaseExchange, perp_exchange: BaseExchange):
        """Set exchange instances for the planner."""
        self.spot_exchange = spot_exchange
        self.perp_exchange = perp_exchange

    def create_execution_plan(self, opportunity: SpotPerpOpportunity) -> Optional[ExecutionPlan]:
        """Create an execution plan from a detected opportunity."""
        try:
            # Validate opportunity
            if not self._validate_opportunity(opportunity):
                return None
            
            # Create execution legs
            legs = self._create_execution_legs(opportunity)
            if not legs:
                return None
            
            # Calculate expected PnL
            expected_pnl = self._calculate_expected_pnl(opportunity)
            
            # Calculate max slippage
            max_slippage_bps = self._calculate_max_slippage(opportunity)
            
            # Create execution plan
            plan = ExecutionPlan(
                opportunity=opportunity,
                legs=legs,
                expected_pnl=expected_pnl,
                max_slippage_bps=max_slippage_bps,
                execution_timeout_ms=self.max_leg_latency_ms
            )
            
            logger.info(f"Created execution plan for {opportunity.symbol}")
            logger.info(f"  Direction: {opportunity.direction.value}")
            logger.info(f"  Expected PnL: ${expected_pnl:.4f}")
            logger.info(f"  Max slippage: {max_slippage_bps:.2f} bps")
            logger.info(f"  Execution legs: {len(legs)}")
            
            return plan
            
        except Exception as e:
            logger.error(f"Error creating execution plan: {e}")
            return None

    def _validate_opportunity(self, opportunity: SpotPerpOpportunity) -> bool:
        """Validate that the opportunity is suitable for execution."""
        try:
            # Check if opportunity has expired
            if time.time() * 1000 > opportunity.expires_at:
                logger.debug(f"Opportunity expired for {opportunity.symbol}")
                return False
            
            # Check minimum trade size
            min_notional = self.config.detector.min_notional_usdc
            trade_notional = opportunity.trade_size * opportunity.spot_price
            if trade_notional < min_notional:
                logger.debug(f"Trade notional too small: ${trade_notional:.2f} < ${min_notional}")
                return False
            
            # Check maximum trade size
            if trade_notional > self.max_notional:
                logger.debug(f"Trade notional too large: ${trade_notional:.2f} > ${self.max_notional}")
                return False
            
            # Check if exchanges are available
            if not self.spot_exchange or not self.perp_exchange:
                logger.error("Exchanges not set in planner")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating opportunity: {e}")
            return False

    def _create_execution_legs(self, opportunity: SpotPerpOpportunity) -> List[ExecutionLeg]:
        """Create execution legs for the opportunity."""
        try:
            legs = []
            
            if opportunity.direction == SpotPerpDirection.SPOT_BUY_PERP_SELL:
                # Buy spot, sell perp
                spot_leg = ExecutionLeg(
                    exchange=self.spot_exchange.name,
                    symbol=opportunity.symbol,
                    side="buy",
                    order_type=self.execution_type,
                    amount=opportunity.trade_size,
                    price=opportunity.spot_vwap,
                    reduce_only=False
                )
                
                perp_leg = ExecutionLeg(
                    exchange=self.perp_exchange.name,
                    symbol=opportunity.symbol,
                    side="sell",
                    order_type=self.execution_type,
                    amount=opportunity.trade_size,
                    price=opportunity.perp_vwap,
                    reduce_only=False
                )
                
            else:  # SPOT_SELL_PERP_BUY
                # Sell spot, buy perp
                spot_leg = ExecutionLeg(
                    exchange=self.spot_exchange.name,
                    symbol=opportunity.symbol,
                    side="sell",
                    order_type=self.execution_type,
                    amount=opportunity.trade_size,
                    price=opportunity.spot_vwap,
                    reduce_only=False
                )
                
                perp_leg = ExecutionLeg(
                    exchange=self.perp_exchange.name,
                    symbol=opportunity.symbol,
                    side="buy",
                    order_type=self.execution_type,
                    amount=opportunity.trade_size,
                    price=opportunity.perp_vwap,
                    reduce_only=False
                )
            
            # Apply precision and sizing adjustments
            spot_leg = self._adjust_leg_for_exchange(spot_leg, self.spot_exchange)
            perp_leg = self._adjust_leg_for_exchange(perp_leg, self.perp_exchange)
            
            if spot_leg and perp_leg:
                legs = [spot_leg, perp_leg]
            
            return legs
            
        except Exception as e:
            logger.error(f"Error creating execution legs: {e}")
            return []

    def _adjust_leg_for_exchange(self, leg: ExecutionLeg, exchange: BaseExchange) -> Optional[ExecutionLeg]:
        """Adjust leg for exchange-specific requirements."""
        try:
            # Apply price precision
            if hasattr(exchange, 'price_to_precision'):
                leg.price = exchange.price_to_precision(leg.price, leg.symbol)
            
            # Apply amount precision
            if hasattr(exchange, 'amount_to_precision'):
                leg.amount = exchange.amount_to_precision(leg.amount, leg.symbol)
            
            # Check minimum notional
            min_notional = self.config.detector.min_notional_usdc
            leg_notional = leg.amount * leg.price
            if leg_notional < min_notional:
                logger.debug(f"Leg notional too small after precision: ${leg_notional:.2f}")
                return None
            
            # Split large orders if needed
            if leg_notional > self.per_order_cap_usd:
                legs = self._split_large_order(leg, exchange)
                return legs[0] if legs else None  # For now, just return first split
            
            return leg
            
        except Exception as e:
            logger.error(f"Error adjusting leg for exchange: {e}")
            return None

    def _split_large_order(self, leg: ExecutionLeg, exchange: BaseExchange) -> List[ExecutionLeg]:
        """Split large orders into smaller chunks."""
        try:
            # Calculate number of splits needed
            leg_notional = leg.amount * leg.price
            num_splits = int(leg_notional / self.per_order_cap_usd) + 1
            split_amount = leg.amount / num_splits
            
            # Apply precision to split amount
            if hasattr(exchange, 'amount_to_precision'):
                split_amount = exchange.amount_to_precision(split_amount, leg.symbol)
            
            # Create split legs
            split_legs = []
            for i in range(num_splits):
                split_leg = ExecutionLeg(
                    exchange=leg.exchange,
                    symbol=leg.symbol,
                    side=leg.side,
                    order_type=leg.order_type,
                    amount=split_amount,
                    price=leg.price,
                    reduce_only=leg.reduce_only,
                    metadata={"split_index": i, "total_splits": num_splits}
                )
                split_legs.append(split_leg)
            
            logger.info(f"Split order into {num_splits} parts: {leg.symbol} {leg.side}")
            return split_legs
            
        except Exception as e:
            logger.error(f"Error splitting large order: {e}")
            return []

    def _calculate_expected_pnl(self, opportunity: SpotPerpOpportunity) -> float:
        """Calculate expected PnL from the opportunity."""
        try:
            # Calculate notional value
            notional = opportunity.trade_size * opportunity.spot_price
            
            # Calculate PnL in basis points
            pnl_bps = opportunity.net_edge_bps
            
            # Convert to USD
            expected_pnl = notional * pnl_bps / 10000
            
            return expected_pnl
            
        except Exception as e:
            logger.error(f"Error calculating expected PnL: {e}")
            return 0.0

    def _calculate_max_slippage(self, opportunity: SpotPerpOpportunity) -> float:
        """Calculate maximum acceptable slippage."""
        try:
            # Base slippage from depth model
            base_slippage = self.config.depth_model.slippage_buffer_bps
            
            # Add execution guard
            total_slippage = base_slippage + self.guard_bps
            
            # Ensure we don't exceed the net edge
            max_slippage = min(total_slippage, opportunity.net_edge_bps * 0.5)
            
            return max_slippage
            
        except Exception as e:
            logger.error(f"Error calculating max slippage: {e}")
            return self.config.depth_model.slippage_buffer_bps

    def create_unwind_plan(self, filled_leg: ExecutionLeg, 
                          opportunity: SpotPerpOpportunity) -> Optional[ExecutionPlan]:
        """Create an unwind plan when one leg fills but the other doesn't."""
        try:
            if not filled_leg:
                return None
            
            # Determine which leg filled and create opposite unwind
            if filled_leg.exchange == self.spot_exchange.name:
                # Spot leg filled, need to unwind spot position
                unwind_leg = ExecutionLeg(
                    exchange=self.spot_exchange.name,
                    symbol=filled_leg.symbol,
                    side="sell" if filled_leg.side == "buy" else "buy",
                    order_type="IOC",
                    amount=filled_leg.amount,
                    price=0.0,  # Market order
                    reduce_only=True,
                    metadata={"unwind": True, "original_opportunity": opportunity.symbol}
                )
                
            else:  # Perp leg filled
                # Perp leg filled, need to unwind perp position
                unwind_leg = ExecutionLeg(
                    exchange=self.perp_exchange.name,
                    symbol=filled_leg.symbol,
                    side="buy" if filled_leg.side == "sell" else "sell",
                    order_type="IOC",
                    amount=filled_leg.amount,
                    price=0.0,  # Market order
                    reduce_only=True,
                    metadata={"unwind": True, "original_opportunity": opportunity.symbol}
                )
            
            # Create unwind plan
            unwind_plan = ExecutionPlan(
                opportunity=opportunity,
                legs=[unwind_leg],
                expected_pnl=0.0,  # Unwind is for risk management, not profit
                max_slippage_bps=self.config.depth_model.slippage_buffer_bps * 2,  # Allow more slippage for unwind
                execution_timeout_ms=self.max_leg_latency_ms,
                metadata={"unwind": True}
            )
            
            logger.info(f"Created unwind plan for {filled_leg.symbol} on {filled_leg.exchange}")
            return unwind_plan
            
        except Exception as e:
            logger.error(f"Error creating unwind plan: {e}")
            return None
