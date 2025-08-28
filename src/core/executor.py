"""Arbitrage trade execution for cross-exchange trading."""

import asyncio
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
from loguru import logger

from src.exchanges.base import BaseExchange, OrderResult
from .types import ArbitrageOpportunity, ArbitrageDirection
from src.config import Config


class ExecutionStatus(Enum):
    """Execution status."""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ExecutionResult:
    """Result of arbitrage execution."""
    success: bool
    opportunity: ArbitrageOpportunity
    left_order: Optional[OrderResult]
    right_order: Optional[OrderResult]
    execution_time_ms: int
    realized_pnl: float
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ArbitrageExecutor:
    """Executes arbitrage trades across exchanges."""

    def __init__(self, config: Config, exchanges: Dict[str, BaseExchange], mode: str):
        self.config = config
        self.exchanges = exchanges
        self.mode = mode
        self.execution_type = config.execution.type
        self.guard_bps = config.execution.guard_bps
        self.max_latency_ms = config.execution.max_leg_latency_ms
        self.atomic_hedge = config.execution.hedge.get('atomic', True)
        self.cancel_on_partial = config.execution.hedge.get('cancel_on_partial', True)

    async def execute_arbitrage(self, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """Execute an arbitrage opportunity with latency enforcement."""
        start_time = time.time()
        logger.info(f"Executing arbitrage: {opportunity.symbol} {opportunity.direction.value}")
        
        try:
            if self.mode == "paper":
                return await self._execute_paper_trade(opportunity, start_time)
            else:
                return await self._execute_live_trade(opportunity, start_time)
                
        except Exception as e:
            error_msg = f"Execution failed: {e}"
            logger.error(error_msg)
            
            return ExecutionResult(
                success=False,
                opportunity=opportunity,
                left_order=None,
                right_order=None,
                execution_time_ms=int((time.time() - start_time) * 1000),
                realized_pnl=0.0,
                error=error_msg
            )

    async def _execute_paper_trade(self, opportunity: ArbitrageOpportunity, start_time: float) -> ExecutionResult:
        """Execute paper trade (simulation) with realistic modeling."""
        logger.info("Executing paper trade")
        
        # Simulate execution delays
        await asyncio.sleep(0.1)
        
        # Simulate realistic execution with potential partial fills
        left_fill_ratio = self._simulate_fill_ratio(opportunity, 'buy')
        right_fill_ratio = self._simulate_fill_ratio(opportunity, 'sell')
        
        # Check if we need to handle partial fills
        if left_fill_ratio < self.config.execution.partial_fill_threshold or right_fill_ratio < self.config.execution.partial_fill_threshold:
            return await self._handle_partial_fill(opportunity, left_fill_ratio, right_fill_ratio, start_time)
        
        # Calculate realistic fill prices with slippage
        left_fill_price = self._calculate_realistic_fill_price(opportunity, 'buy', left_fill_ratio)
        right_fill_price = self._calculate_realistic_fill_price(opportunity, 'sell', right_fill_ratio)
        
        # Calculate actual quantities filled
        left_filled_qty = opportunity.trade_size * left_fill_ratio
        right_filled_qty = opportunity.trade_size * right_fill_ratio
        
        # Calculate fees (realistic)
        left_fee = left_filled_qty * left_fill_price * (opportunity.metadata['buy_fee_bps'] / 10000)
        right_fee = right_filled_qty * right_fill_price * (opportunity.metadata['sell_fee_bps'] / 10000)
        
        # Calculate realized PnL
        buy_cost = left_filled_qty * left_fill_price + left_fee
        sell_proceeds = right_filled_qty * right_fill_price - right_fee
        realized_pnl = sell_proceeds - buy_cost
        
        # Simulate successful execution
        left_order = OrderResult(
            success=True,
            order_id=f"paper_left_{int(time.time())}",
            filled_qty=left_filled_qty,
            avg_price=left_fill_price,
            fee_asset=opportunity.quote_asset,
            fee_amount=left_fee,
            latency_ms=50
        )
        
        right_order = OrderResult(
            success=True,
            order_id=f"paper_right_{int(time.time())}",
            filled_qty=right_filled_qty,
            avg_price=right_fill_price,
            fee_asset=opportunity.quote_asset,
            fee_amount=right_fee,
            latency_ms=45
        )
        
        execution_time = int((time.time() - start_time) * 1000)
        
        logger.info(f"Paper trade completed: PnL ${realized_pnl:.4f}")
        
        return ExecutionResult(
            success=True,
            opportunity=opportunity,
            left_order=left_order,
            right_order=right_order,
            execution_time_ms=execution_time,
            realized_pnl=realized_pnl,
            metadata={
                'left_fill_ratio': left_fill_ratio,
                'right_fill_ratio': right_fill_ratio,
                'left_slippage_bps': self._calculate_slippage_bps(opportunity.buy_price, left_fill_price),
                'right_slippage_bps': self._calculate_slippage_bps(opportunity.sell_price, right_fill_price),
                'total_fees': left_fee + right_fee,
                'execution_type': 'full_fill'
            }
        )

    def _simulate_fill_ratio(self, opportunity: ArbitrageOpportunity, side: str) -> float:
        """Simulate realistic fill ratio based on market conditions."""
        import random
        
        # Base fill ratio (90-100% for most trades)
        base_fill = random.uniform(0.90, 1.0)
        
        # Adjust based on spread (tighter spreads = better fills)
        spread_factor = 1.0 - (opportunity.spread_bps / 1000)  # Reduce fill ratio for wide spreads
        base_fill *= max(0.8, spread_factor)
        
        # Adjust based on edge (higher edge = better fills)
        edge_factor = min(1.2, 1.0 + (opportunity.net_edge_bps / 1000))
        base_fill *= edge_factor
        
        return min(1.0, max(0.7, base_fill))  # Clamp between 70-100%

    def _calculate_realistic_fill_price(self, opportunity: ArbitrageOpportunity, side: str, fill_ratio: float) -> float:
        """Calculate realistic fill price considering slippage."""
        if side == 'buy':
            base_price = opportunity.buy_price
            # Slippage increases price for buys
            slippage_factor = 1.0 + (opportunity.metadata.get('slippage_bps', 0) / 10000)
        else:
            base_price = opportunity.sell_price
            # Slippage decreases price for sells
            slippage_factor = 1.0 - (opportunity.metadata.get('slippage_bps', 0) / 10000)
        
        # Apply slippage
        realistic_price = base_price * slippage_factor
        
        # Add some randomness to simulate market noise
        import random
        noise_factor = random.uniform(0.9995, 1.0005)
        realistic_price *= noise_factor
        
        return realistic_price

    def _calculate_slippage_bps(self, expected_price: float, actual_price: float) -> float:
        """Calculate slippage in basis points."""
        if expected_price <= 0:
            return 0.0
        return abs((actual_price - expected_price) / expected_price) * 10000

    async def _handle_partial_fill(self, opportunity: ArbitrageOpportunity, left_fill_ratio: float, right_fill_ratio: float, start_time: float) -> ExecutionResult:
        """Handle partial fill scenario with unwind logic."""
        logger.warning(f"Partial fill detected: left={left_fill_ratio:.2%}, right={right_fill_ratio:.2%}")
        
        # Cancel peer leg if partial fill threshold not met
        if self.cancel_on_partial:
            # Simulate canceling the worse-performing leg
            if left_fill_ratio < right_fill_ratio:
                # Cancel right leg, unwind left
                unwind_cost = self._calculate_unwind_cost(opportunity, 'left', left_fill_ratio)
                realized_pnl = -unwind_cost
                execution_type = 'partial_unwind_left'
            else:
                # Cancel left leg, unwind right
                unwind_cost = self._calculate_unwind_cost(opportunity, 'right', right_fill_ratio)
                realized_pnl = -unwind_cost
                execution_type = 'partial_unwind_right'
        else:
            # Accept partial fills
            realized_pnl = self._calculate_partial_pnl(opportunity, left_fill_ratio, right_fill_ratio)
            execution_type = 'partial_accept'
        
        execution_time = int((time.time() - start_time) * 1000)
        
        logger.info(f"Partial fill handled: PnL ${realized_pnl:.4f}, type: {execution_type}")
        
        return ExecutionResult(
            success=True,
            opportunity=opportunity,
            left_order=None,
            right_order=None,
            execution_time_ms=execution_time,
            realized_pnl=realized_pnl,
            metadata={
                'left_fill_ratio': left_fill_ratio,
                'right_fill_ratio': right_fill_ratio,
                'execution_type': execution_type,
                'partial_fill_handling': 'unwind' if self.cancel_on_partial else 'accept'
            }
        )

    def _calculate_unwind_cost(self, opportunity: ArbitrageOpportunity, side: str, fill_ratio: float) -> float:
        """Calculate cost to unwind a partial position."""
        # Estimate unwind price (worse than original due to market impact)
        if side == 'left':
            unwind_price = opportunity.buy_price * 1.001  # 1 bps worse
            fee_rate = opportunity.metadata['buy_fee_bps'] / 10000
        else:
            unwind_price = opportunity.sell_price * 0.999  # 1 bps worse
            fee_rate = opportunity.metadata['sell_fee_bps'] / 10000
        
        filled_qty = opportunity.trade_size * fill_ratio
        unwind_cost = filled_qty * unwind_price * fee_rate
        
        return unwind_cost

    def _calculate_partial_pnl(self, opportunity: ArbitrageOpportunity, left_fill_ratio: float, right_fill_ratio: float) -> float:
        """Calculate PnL for partial fills."""
        # Use the smaller fill ratio to determine actual trade size
        actual_fill_ratio = min(left_fill_ratio, right_fill_ratio)
        
        # Calculate costs and proceeds for the actual filled amount
        buy_cost = opportunity.trade_size * actual_fill_ratio * opportunity.buy_price
        sell_proceeds = opportunity.trade_size * actual_fill_ratio * opportunity.sell_price
        
        # Apply fees
        buy_fee = buy_cost * (opportunity.metadata['buy_fee_bps'] / 10000)
        sell_fee = sell_proceeds * (opportunity.metadata['sell_fee_bps'] / 10000)
        
        return (sell_proceeds - sell_fee) - (buy_cost + buy_fee)
    
    async def _place_order_with_latency_check(self, exchange: BaseExchange, symbol: str, side: str,
                                            order_type: str, amount: float, price: float,
                                            start_time: float, leg_name: str) -> OrderResult:
        """Place order with latency enforcement."""
        order_start = time.time()
        
        try:
            # Check balance before placing order
            balance_check = await self._validate_balance(exchange, symbol, side, amount)
            if not balance_check['valid']:
                error_msg = f"Insufficient balance for {side} {amount} {symbol}: {balance_check['reason']}"
                logger.error(f"❌ {error_msg}")
                return OrderResult(False, error=error_msg)
            
            logger.info(f"✅ Balance validated for {side} {amount} {symbol}")
            
            # Place the order
            order_result = await exchange.place_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                amount=amount,
                price=price
            )
            
            # Check latency
            order_latency = int((time.time() - order_start) * 1000)
            total_latency = int((time.time() - start_time) * 1000)
            
            if order_latency > self.max_latency_ms:
                logger.warning(f"{leg_name} order latency {order_latency}ms exceeds limit {self.max_latency_ms}ms")
                # Consider cancelling if latency is too high
                if order_result.success and self.cancel_on_partial:
                    try:
                        await exchange.cancel_order(symbol, order_result.order_id)
                        logger.info(f"Cancelled {leg_name} order due to high latency")
                        return OrderResult(False, error=f"Order cancelled due to high latency: {order_latency}ms")
                    except Exception as e:
                        logger.error(f"Failed to cancel {leg_name} order: {e}")
            
            if total_latency > self.max_latency_ms * 2:
                logger.warning(f"Total execution latency {total_latency}ms exceeds limit {self.max_latency_ms * 2}ms")
            
            # Add latency metadata
            if hasattr(order_result, 'metadata'):
                order_result.metadata = order_result.metadata or {}
            else:
                order_result.metadata = {}
            
            order_result.metadata['leg_latency_ms'] = order_latency
            order_result.metadata['total_latency_ms'] = total_latency
            
            return order_result
            
        except Exception as e:
            order_latency = int((time.time() - order_start) * 1000)
            logger.error(f"{leg_name} order failed after {order_latency}ms: {e}")
            return OrderResult(False, error=str(e))
    
    def _aggregate_order_results(self, results: List, side: str) -> OrderResult:
        """Aggregate multiple order results into a single result."""
        successful_orders = []
        failed_orders = []
        
        for i, result in enumerate(results):
            logger.info(f"🔍 Processing {side} order {i+1}: {result}")
            
            if isinstance(result, Exception):
                failed_orders.append(f"Order {i+1} failed: {result}")
                logger.error(f"❌ {side} order {i+1} exception: {result}")
            elif not result.success:
                failed_orders.append(f"Order {i+1} failed: {result.error}")
                logger.error(f"❌ {side} order {i+1} failed: {result.error}")
            else:
                successful_orders.append(result)
                logger.info(f"✅ {side} order {i+1} succeeded: ID={result.order_id}, filled={result.filled_qty}")
        
        if not successful_orders:
            # All orders failed
            error_msg = f"All {side} orders failed: {'; '.join(failed_orders)}"
            return OrderResult(False, error=error_msg)
        
        if failed_orders:
            # Some orders failed
            logger.warning(f"Partial {side} execution: {len(successful_orders)}/{len(results)} orders succeeded")
            logger.warning(f"Failed orders: {'; '.join(failed_orders)}")
        
        # Aggregate successful orders
        total_filled = sum(order.filled_qty for order in successful_orders)
        total_notional = sum(order.filled_qty * order.avg_price for order in successful_orders)
        avg_price = total_notional / total_filled if total_filled > 0 else 0
        
        # CRITICAL FIX: Use REAL order IDs, not fake ones
        real_order_ids = [order.order_id for order in successful_orders if order.order_id and order.order_id != 'None']
        if not real_order_ids:
            logger.error(f"❌ CRITICAL: No real order IDs found for {side} orders!")
            logger.error(f"  Successful orders: {[order.order_id for order in successful_orders]}")
            return OrderResult(False, error=f"No real order IDs for {side} orders")
        
        # Use first real order ID as primary, others as backup
        primary_order_id = real_order_ids[0]
        logger.info(f"✅ Aggregated {side} orders with real ID: {primary_order_id}")
        
        # Use first successful order's metadata
        metadata = successful_orders[0].metadata if successful_orders else {}
        metadata['num_orders'] = len(successful_orders)
        metadata['failed_orders'] = failed_orders
        metadata['all_order_ids'] = real_order_ids
        
        return OrderResult(
            success=True,
            order_id=primary_order_id,  # REAL order ID, not fake!
            filled_qty=total_filled,
            avg_price=avg_price,
            fee_asset='',
            fee_amount=0.0,
            metadata=metadata
        )

    async def _execute_live_trade(self, opportunity: ArbitrageOpportunity, start_time: float) -> ExecutionResult:
        """Execute live trade on exchanges with latency enforcement."""
        logger.info("Executing live trade")
        
        try:
            if self.atomic_hedge:
                return await self._execute_atomic_hedge(opportunity, start_time)
            else:
                return await self._execute_sequential_hedge(opportunity, start_time)
                
        except Exception as e:
            error_msg = f"Live execution failed: {e}"
            logger.error(error_msg)
            raise

    async def _execute_atomic_hedge(self, opportunity: ArbitrageOpportunity, start_time: float) -> ExecutionResult:
        """Execute both legs concurrently (atomic hedge) with latency enforcement."""
        
        # Debug logging
        logger.info(f"Available exchanges: {list(self.exchanges.keys())}")
        logger.info(f"Opportunity left_exchange: {opportunity.left_exchange}")
        logger.info(f"Opportunity right_exchange: {opportunity.right_exchange}")
        
        # Check if exchanges exist
        if opportunity.left_exchange not in self.exchanges:
            raise RuntimeError(f"Left exchange '{opportunity.left_exchange}' not found in {list(self.exchanges.keys())}")
        if opportunity.right_exchange not in self.exchanges:
            raise RuntimeError(f"Right exchange '{opportunity.right_exchange}' not found in {list(self.exchanges.keys())}")
        
        # Determine which exchange to buy from and sell to
        if opportunity.direction == ArbitrageDirection.LEFT_TO_RIGHT:
            buy_exchange = self.exchanges[opportunity.left_exchange]
            sell_exchange = self.exchanges[opportunity.right_exchange]
            buy_price = opportunity.buy_price * (1 + self.guard_bps / 10000)
            sell_price = opportunity.sell_price * (1 - self.guard_bps / 10000)
        else:
            buy_exchange = self.exchanges[opportunity.right_exchange]
            sell_exchange = self.exchanges[opportunity.left_exchange]
            buy_price = opportunity.buy_price * (1 + self.guard_bps / 10000)
            sell_price = opportunity.sell_price * (1 - self.guard_bps / 10000)
        
        # Dynamic order splitting for large trades
        from .depth_analysis import DepthAnalyzer
        depth_analyzer = DepthAnalyzer(self.config)
        
        # Get trade size in USD from opportunity metadata
        trade_size_usdc = opportunity.metadata.get('trade_size_usdc', 
                                                  opportunity.trade_size * buy_price)
        
        # Pre-flight checks: validate order parameters before execution
        await self._validate_order_parameters(
            buy_exchange, sell_exchange, opportunity.symbol, 
            trade_size_usdc, buy_price, sell_price
        )
        
        # DEPTH-AWARE DYNAMIC SIZING: Fetch order books and calculate optimal size
        trade_size_usdc, buy_vwap, sell_vwap = await self._calculate_depth_aware_size(
            buy_exchange, sell_exchange, opportunity.symbol, 
            trade_size_usdc, buy_price, sell_price
        )
        
        if trade_size_usdc <= 0:
            raise ValueError(f"Depth analysis resulted in invalid trade size: {trade_size_usdc}")
        
        # Split large orders if needed
        order_sizes = depth_analyzer.split_large_orders(trade_size_usdc)
        
        logger.info(f"Executing trade with {len(order_sizes)} orders: {order_sizes}")
        
        # Execute all orders concurrently
        buy_tasks = []
        sell_tasks = []
        
        for i, order_size_usdc in enumerate(order_sizes):
            order_size_base = order_size_usdc / buy_price
            
            buy_task = asyncio.create_task(
                self._place_order_with_latency_check(
                    buy_exchange, opportunity.symbol, 'buy', self.execution_type,
                    order_size_base, buy_price, start_time, f'buy_{i+1}'
                )
            )
            
            sell_task = asyncio.create_task(
                self._place_order_with_latency_check(
                    sell_exchange, opportunity.symbol, 'sell', self.execution_type,
                    order_size_base, sell_price, start_time, f'sell_{i+1}'
                )
            )
            
            buy_tasks.append(buy_task)
            sell_tasks.append(sell_task)
        
        # Wait for all orders to complete
        all_buy_results = await asyncio.gather(*buy_tasks, return_exceptions=True)
        all_sell_results = await asyncio.gather(*sell_tasks, return_exceptions=True)
        
        # Aggregate results
        left_order = self._aggregate_order_results(all_buy_results, 'buy')
        right_order = self._aggregate_order_results(all_sell_results, 'sell')
        
        # Check execution results
        if not left_order.success or not right_order.success:
            # CRITICAL SAFETY: Cancel successful order if other failed
            if left_order.success and self.cancel_on_partial:
                try:
                    logger.warning(f"🚨 SAFETY: Cancelling successful buy order due to sell failure")
                    if left_order.order_id:
                        await buy_exchange.cancel_order(opportunity.symbol, left_order.order_id)
                        logger.info(f"✅ Successfully cancelled buy order {left_order.order_id}")
                    else:
                        logger.error(f"❌ Cannot cancel buy order - no order ID available")
                except Exception as e:
                    logger.error(f"❌ Failed to cancel buy order: {e}")
                    
            if right_order.success and self.cancel_on_partial:
                try:
                    logger.warning(f"🚨 SAFETY: Cancelling successful sell order due to buy failure")
                    if right_order.order_id:
                        await sell_exchange.cancel_order(opportunity.symbol, right_order.order_id)
                        logger.info(f"✅ Successfully cancelled sell order {right_order.order_id}")
                    else:
                        logger.error(f"❌ Cannot cancel sell order - no order ID available")
                except Exception as e:
                    logger.error(f"❌ Failed to cancel sell order: {e}")
            
            error_msg = f"Partial execution: left={left_order.success}, right={right_order.success}"
            logger.error(error_msg)
            
            return ExecutionResult(
                success=False,
                opportunity=opportunity,
                left_order=left_order,
                right_order=right_order,
                execution_time_ms=int((time.time() - start_time) * 1000),
                realized_pnl=0.0,
                error=error_msg
            )
        
        # Check fill ratios
        left_fill_ratio = left_order.filled_qty / opportunity.trade_size
        right_fill_ratio = right_order.filled_qty / opportunity.trade_size
        
        if left_fill_ratio < 0.95 or right_fill_ratio < 0.95:
            # CRITICAL SAFETY: Partial fills - cancel remaining to prevent unbalanced positions
            if self.cancel_on_partial:
                if left_fill_ratio < 1.0:
                    try:
                        logger.warning(f"🚨 SAFETY: Cancelling partial buy order (fill: {left_fill_ratio:.2%})")
                        if left_order.order_id:
                            await buy_exchange.cancel_order(opportunity.symbol, left_order.order_id)
                            logger.info(f"✅ Successfully cancelled partial buy order {left_order.order_id}")
                        else:
                            logger.error(f"❌ Cannot cancel partial buy order - no order ID available")
                    except Exception as e:
                        logger.error(f"❌ Failed to cancel partial buy order: {e}")
                        
                if right_fill_ratio < 1.0:
                    try:
                        logger.warning(f"🚨 SAFETY: Cancelling partial sell order (fill: {right_fill_ratio:.2%})")
                        if right_order.order_id:
                            await sell_exchange.cancel_order(opportunity.symbol, right_order.order_id)
                            logger.info(f"✅ Successfully cancelled partial sell order {right_order.order_id}")
                        else:
                            logger.error(f"❌ Cannot cancel partial sell order - no order ID available")
                    except Exception as e:
                        logger.error(f"❌ Failed to cancel partial sell order: {e}")
            
            logger.warning(f"Partial fills: left={left_fill_ratio:.2%}, right={right_fill_ratio:.2%}")
        
        # Calculate realized PnL
        realized_pnl = self._calculate_realized_pnl(opportunity, left_order, right_order)
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(f"Live trade completed: PnL ${realized_pnl:.4f}, time {execution_time_ms}ms")
        
        return ExecutionResult(
            success=True,
            opportunity=opportunity,
            left_order=left_order,
            right_order=right_order,
            execution_time_ms=execution_time_ms,
            realized_pnl=realized_pnl,
            metadata={'mode': 'live', 'left_fill_ratio': left_fill_ratio, 'right_fill_ratio': right_fill_ratio}
        )

    async def _execute_sequential_hedge(self, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """Execute legs sequentially (non-atomic hedge)."""
        start_time = time.time()
        
        # This is a simplified sequential execution
        # In practice, you'd want more sophisticated logic
        logger.warning("Sequential hedge execution not fully implemented")
        
        return ExecutionResult(
            success=False,
            opportunity=opportunity,
            left_order=None,
            right_order=None,
            execution_time_ms=int((time.time() - start_time) * 1000),
            realized_pnl=0.0,
            error="Sequential hedge not implemented"
        )

    def _calculate_realized_pnl(self, opportunity: ArbitrageOpportunity, 
                               left_order: OrderResult, right_order: OrderResult) -> float:
        """Calculate realized PnL from execution results."""
        if not left_order.success or not right_order.success:
            return 0.0
        
        # Calculate based on actual fills
        left_cost = left_order.filled_qty * left_order.avg_price
        right_proceeds = right_order.filled_qty * right_order.avg_price
        
        # Calculate fees
        left_fees = left_order.fee_amount
        right_fees = right_order.fee_amount
        total_fees = left_fees + right_fees
        
        # Calculate PnL
        pnl = right_proceeds - left_cost - total_fees
        
        return pnl

    def get_execution_summary(self) -> Dict[str, Any]:
        """Get execution summary."""
        return {
            'mode': self.mode,
            'execution_type': self.execution_type,
            'guard_bps': self.guard_bps,
            'max_latency_ms': self.max_latency_ms,
            'atomic_hedge': self.atomic_hedge,
            'cancel_on_partial': self.cancel_on_partial
        }

    async def _calculate_depth_aware_size(self, buy_exchange: BaseExchange, sell_exchange: BaseExchange,
                                        symbol: str, target_size_usdc: float, buy_price: float, sell_price: float) -> tuple[float, float, float]:
        """Calculate optimal trade size using order book depth analysis."""
        try:
            logger.info(f"🔍 Calculating depth-aware trade size for {symbol}")
            
            # Fetch order books from both exchanges
            buy_orderbook = await buy_exchange.fetch_order_book(symbol)
            sell_orderbook = await sell_exchange.fetch_order_book(symbol)
            
            # Calculate mid price
            mid_price = (buy_price + sell_price) / 2
            
            # Analyze buy side (asks) - we buy at ask prices
            buy_asks = buy_orderbook.get('asks', [])
            buy_liquidity = self._analyze_order_book_side(
                buy_asks, mid_price, 'ask', 
                self.config.depth_model.max_depth_pct,
                self.config.depth_model.vwap_calculation_levels
            )
            
            # Analyze sell side (bids) - we sell at bid prices  
            sell_bids = sell_orderbook.get('bids', [])
            sell_liquidity = self._analyze_order_book_side(
                sell_bids, mid_price, 'bid',
                self.config.depth_model.max_depth_pct,
                self.config.depth_model.vwap_calculation_levels
            )
            
            # Calculate optimal trade size based on available liquidity
            available_size = min(buy_liquidity['total_size'], sell_liquidity['total_size'])
            
            if available_size == 0:
                logger.warning(f"No liquidity available on either side")
                return 0, 0, 0
            
            # Apply liquidity multiplier (3x-5x) for safety
            required_liquidity = target_size_usdc * self.config.depth_model.min_liquidity_multiplier
            
            if available_size < required_liquidity:
                logger.warning(f"Insufficient liquidity: available {available_size:.6f} < required {required_liquidity:.6f}")
                # Scale down trade size to fit available liquidity
                target_size_usdc = available_size / self.config.depth_model.min_liquidity_multiplier
            
            # Apply safety factor
            safe_size = target_size_usdc * self.config.detector.safety_factor
            
            # Convert to USD terms using VWAP
            trade_size_usdc = safe_size * buy_liquidity['vwap']
            
            # Enforce minimum and maximum limits
            min_limit = self.config.detector.min_notional_usdc
            max_limit = self.config.detector.max_notional_usdc
            
            if trade_size_usdc < min_limit:
                logger.info(f"Trade size ${trade_size_usdc:.2f} below minimum ${min_limit}, skipping")
                return 0, 0, 0
            
            if trade_size_usdc > max_limit:
                trade_size_usdc = max_limit
                safe_size = trade_size_usdc / buy_liquidity['vwap']
            
            logger.info(f"✅ Depth-aware sizing completed:")
            logger.info(f"  Available liquidity: {available_size:.6f}")
            logger.info(f"  Safe size: {safe_size:.6f}")
            logger.info(f"  Trade size USD: ${trade_size_usdc:.2f}")
            logger.info(f"  Buy VWAP: {buy_liquidity['vwap']:.2f}")
            logger.info(f"  Sell VWAP: {sell_liquidity['vwap']:.2f}")
            
            return trade_size_usdc, buy_liquidity['vwap'], sell_liquidity['vwap']
            
        except Exception as e:
            logger.error(f"Depth-aware sizing failed: {e}, using fallback")
            # Fallback to original sizing
            return target_size_usdc, buy_price, sell_price
    
    def _analyze_order_book_side(self, orders: List[List[float]], mid_price: float, 
                                side: str, max_depth_pct: float, vwap_levels: int) -> Dict[str, Any]:
        """Analyze one side of the order book for liquidity and VWAP."""
        if not orders:
            return {'total_size': 0, 'vwap': 0, 'levels_used': 0}
        
        # Calculate price limits based on max_depth_pct
        if side == 'bid':
            min_price = mid_price * (1 - max_depth_pct / 100)
            # For bids, we want prices >= min_price (higher is better)
            valid_orders = [(p, s) for p, s in orders if p >= min_price]
        else:  # ask
            max_price = mid_price * (1 + max_depth_pct / 100)
            # For asks, we want prices <= max_price (lower is better)
            valid_orders = [(p, s) for p, s in orders if p <= max_price]
        
        if not valid_orders:
            return {'total_size': 0, 'vwap': 0, 'levels_used': 0}
        
        # Limit to configured number of levels
        valid_orders = valid_orders[:vwap_levels]
        
        # Calculate VWAP and total size
        total_notional = 0.0
        total_size = 0.0
        
        for price, size in valid_orders:
            notional = price * size
            total_notional += notional
            total_size += size
        
        vwap = total_notional / total_size if total_size > 0 else 0
        
        return {
            'total_size': total_size,
            'vwap': vwap,
            'levels_used': len(valid_orders)
        }

    async def _validate_order_parameters(self, buy_exchange: BaseExchange, sell_exchange: BaseExchange,
                                       symbol: str, trade_size_usdc: float, buy_price: float, sell_price: float):
        """Validate order parameters before execution."""
        try:
            logger.info(f"🔍 Pre-flight validation for {symbol}")
            
            # Get market info for both exchanges
            buy_market = await buy_exchange.fetch_market(symbol)
            sell_market = await sell_exchange.fetch_market(symbol)
            
            # Validate minimum notional
            buy_min_notional = buy_market.get('minAmount', 0) * buy_price
            sell_min_notional = sell_market.get('minAmount', 0) * sell_price
            
            if trade_size_usdc < buy_min_notional:
                raise ValueError(f"Trade size ${trade_size_usdc:.2f} below buy exchange minimum ${buy_min_notional:.2f}")
            
            if trade_size_usdc < sell_min_notional:
                raise ValueError(f"Trade size ${trade_size_usdc:.2f} below sell exchange minimum ${sell_min_notional:.2f}")
            
            # Validate price precision
            buy_price_precision = buy_market.get('precision', {}).get('price', 8)
            sell_price_precision = sell_market.get('precision', {}).get('price', 8)
            
            # Round prices to exchange precision
            buy_price_rounded = round(buy_price, buy_price_precision)
            sell_price_rounded = round(sell_price, sell_price_precision)
            
            if abs(buy_price - buy_price_rounded) > 0.0001:
                logger.warning(f"Buy price {buy_price} rounded to {buy_price_rounded} for precision {buy_price_precision}")
            
            if abs(sell_price - sell_price_rounded) > 0.0001:
                logger.warning(f"Sell price {sell_price} rounded to {sell_price_rounded} for precision {sell_price_precision}")
            
            # Validate amount precision
            buy_amount_precision = buy_market.get('precision', {}).get('amount', 8)
            sell_amount_precision = sell_market.get('precision', {}).get('amount', 8)
            
            trade_size_base = trade_size_usdc / buy_price
            buy_amount_rounded = round(trade_size_base, buy_amount_precision)
            sell_amount_rounded = round(trade_size_base, sell_amount_precision)
            
            logger.info(f"✅ Pre-flight validation passed:")
            logger.info(f"  Trade size: ${trade_size_usdc:.2f} ({trade_size_base:.6f} {symbol.split('/')[0]})")
            logger.info(f"  Buy price: {buy_price_rounded} (precision: {buy_price_precision})")
            logger.info(f"  Sell price: {sell_price_rounded} (precision: {sell_price_precision})")
            logger.info(f"  Buy amount: {buy_amount_rounded} (precision: {buy_amount_precision})")
            logger.info(f"  Sell amount: {sell_amount_rounded} (precision: {sell_amount_precision})")
            
        except Exception as e:
            logger.error(f"❌ Pre-flight validation failed: {e}")
            raise ValueError(f"Order validation failed: {e}")

    async def _validate_balance(self, exchange: BaseExchange, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        """Validate that exchange has sufficient balance for the order."""
        try:
            # Get current balances
            balances = await exchange.fetch_balances()
            
            # Parse symbol to get base and quote assets
            if '/' in symbol:
                base_asset, quote_asset = symbol.split('/')
            else:
                # Handle non-slash symbols (fallback)
                base_asset = symbol[:3]  # Assume first 3 chars are base
                quote_asset = symbol[3:]  # Rest is quote
            
            logger.info(f"🔍 Validating balance for {side} {amount} {symbol}")
            logger.info(f"  Base asset: {base_asset}")
            logger.info(f"  Quote asset: {quote_asset}")
            logger.info(f"  Available balances: {list(balances.keys())}")
            
            if side == 'buy':
                # For buy orders, we need quote currency (USDC)
                required_quote = amount * 4600  # Approximate ETH price
                available_balance = balances.get(quote_asset)
                
                if available_balance is None:
                    return {
                        'valid': False,
                        'reason': f"No {quote_asset} balance found"
                    }
                
                available_quote = available_balance.free if hasattr(available_balance, 'free') else float(available_balance)
                
                logger.info(f"  Buy order requires: ${required_quote:.2f} {quote_asset}")
                logger.info(f"  Available balance: {available_quote} {quote_asset}")
                
                if available_quote < required_quote:
                    return {
                        'valid': False,
                        'reason': f"Insufficient {quote_asset}: need ${required_quote:.2f}, have ${available_quote:.2f}"
                    }
                
            elif side == 'sell':
                # For sell orders, we need base currency (ETH)
                available_balance = balances.get(base_asset)
                
                if available_balance is None:
                    return {
                        'valid': False,
                        'reason': f"No {base_asset} balance found"
                    }
                
                available_base = available_balance.free if hasattr(available_balance, 'free') else float(available_balance)
                
                logger.info(f"  Sell order requires: {amount} {base_asset}")
                logger.info(f"  Available balance: {available_base} {base_asset}")
                
                if available_base < amount:
                    return {
                        'valid': False,
                        'reason': f"Insufficient {base_asset}: need {amount}, have {available_base}"
                    }
            
            return {'valid': True, 'reason': 'Sufficient balance'}
            
        except Exception as e:
            logger.error(f"Balance validation error: {e}")
            # If we can't validate balance, allow the order but log warning
            return {'valid': True, 'reason': f'Balance validation failed: {e}, allowing order'}
