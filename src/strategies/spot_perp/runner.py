"""Spot to Perpetual arbitrage strategy runner."""

import asyncio
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from loguru import logger
from datetime import datetime

from .detector import SpotPerpDetector, SpotPerpOpportunity
from .planner import SpotPerpPlanner, ExecutionPlan, ExecutionLeg
from src.exchanges.binance import BinanceExchange
from src.exchanges.hyperliquid import HyperliquidExchange
from src.notify.telegram_readonly import TelegramReadOnlyNotifier, TelegramConfig
from src.config import Config, RouteConfig


@dataclass
class StrategyState:
    """Current state of the spot↔perp strategy."""
    is_running: bool = False
    is_paused: bool = False
    last_opportunity_check: int = 0
    opportunities_detected: int = 0
    trades_executed: int = 0
    total_pnl: float = 0.0
    last_trade_time: int = 0
    session_start_time: int = 0


class SpotPerpRunner:
    """Main runner for the spot↔perp arbitrage strategy."""

    def __init__(self, config: Config, route: RouteConfig):
        self.config = config
        self.route = route
        self.state = StrategyState()
        
        # Initialize components with error handling
        try:
            self.detector = SpotPerpDetector(config)
            self.planner = SpotPerpPlanner(config)
        except Exception as e:
            logger.error(f"Failed to initialize strategy components: {e}")
            raise
        
        # Exchange instances
        self.spot_exchange: Optional[BinanceExchange] = None
        self.perp_exchange: Optional[HyperliquidExchange] = None
        
        # Telegram notifier
        self.telegram = None
        if hasattr(config, 'alerts') and config.alerts:
            telegram_config = TelegramConfig(
                token=config.alerts.telegram_token,
                chat_id=config.alerts.telegram_chat_id,
                notify_all_trades=config.alerts.notify_all_trades,
                notify_risk_events=config.alerts.notify_risk_events,
                notify_session_summary=config.alerts.notify_session_summary
            )
            self.telegram = TelegramReadOnlyNotifier(telegram_config)
        
        # Market data streams
        self.spot_quotes: List[Any] = []
        self.perp_quotes: List[Any] = []
        
        # Execution tracking
        self.active_orders: Dict[str, Dict[str, Any]] = {}
        self.completed_trades: List[Dict[str, Any]] = []
        
        # Risk management
        self.daily_notional = 0.0
        self.consecutive_losses = 0
        self.daily_loss = 0.0
        
        # Route-specific configuration
        self.spot_symbol = route.left['symbol']
        self.perp_symbol = route.right['symbol']
        self.spot_exchange_name = route.left['ex']
        self.perp_exchange_name = route.right['ex']

    async def start(self):
        """Start the spot↔perp strategy."""
        try:
            logger.info("Starting Spot↔Perp arbitrage strategy...")
            
            # Initialize exchanges
            await self._initialize_exchanges()
            
            # Set exchange instances in components
            self.detector.set_exchanges(self.spot_exchange, self.perp_exchange)
            self.planner.set_exchanges(self.spot_exchange, self.perp_exchange)
            
            # Test Telegram connection
            if self.telegram:
                await self.telegram.test_connection()
            
            # Start market data streams
            await self._start_market_data_streams()
            
            # Set running state
            self.state.is_running = True
            self.state.session_start_time = int(time.time() * 1000)
            
            # Start main event loop
            await self._main_loop()
            
        except Exception as e:
            logger.error(f"Error starting strategy: {e}")
            await self.stop()

    async def stop(self):
        """Stop the spot↔perp strategy."""
        try:
            logger.info("Stopping Spot↔Perp arbitrage strategy...")
            
            self.state.is_running = False
            
            # Cancel all active orders
            await self._cancel_all_orders()
            
            # Disconnect exchanges
            if self.spot_exchange:
                await self.spot_exchange.disconnect()
            if self.perp_exchange:
                await self.perp_exchange.disconnect()
            
            # Send session summary
            if self.telegram:
                await self.telegram.send_session_summary()
            
            logger.info("Strategy stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping strategy: {e}")

    async def pause(self):
        """Pause trading (in-memory only)."""
        self.state.is_paused = True
        logger.info("Trading paused (in-memory only)")
        
        if self.telegram:
            await self.telegram.send_message("⏸️ Trading paused (in-memory only)")

    async def resume(self):
        """Resume trading."""
        self.state.is_paused = False
        logger.info("Trading resumed")
        
        if self.telegram:
            await self.telegram.send_message("▶️ Trading resumed")

    async def get_status(self) -> Dict[str, Any]:
        """Get current status of the strategy."""
        try:
            # Get current prices
            spot_price = None
            perp_price = None
            spread_bps = 0.0
            
            if hasattr(self, 'spot_quotes') and self.spot_quotes:
                spot_quote = self.spot_quotes[0]
                spot_price = (spot_quote.bid + spot_quote.ask) / 2
                
            if hasattr(self, 'perp_quotes') and self.perp_quotes:
                perp_quote = self.perp_quotes[0]
                perp_price = (perp_quote.bid + perp_quote.ask) / 2
                
            if spot_price and perp_price:
                spread_bps = abs(perp_price - spot_price) / spot_price * 10000
            
            # Get trade statistics
            total_trades = getattr(self.state, 'total_trades', 0)
            total_pnl = getattr(self.state, 'total_pnl', 0.0)
            
            return {
                'name': f"{self.spot_symbol} ↔ {self.perp_symbol}",
                'status': '🟢 Active' if self.state.is_running and not self.state.is_paused else '🔴 Inactive',
                'spot_price': f"${spot_price:.4f}" if spot_price else "N/A",
                'perp_price': f"${perp_price:.4f}" if perp_price else "N/A",
                'spread_bps': f"{spread_bps:.1f} bps",
                'min_edge_bps': self.config.detector.min_edge_bps,
                'total_trades': total_trades,
                'total_pnl': total_pnl,
                'is_running': self.state.is_running,
                'is_paused': self.state.is_paused,
                'last_opportunity_check': getattr(self.state, 'last_opportunity_check', 0)
            }
            
        except Exception as e:
            logger.error(f"Error getting strategy status: {e}")
            return {
                'name': f"{self.spot_symbol} ↔ {self.perp_symbol}",
                'status': f'❌ Error: {e}',
                'error': str(e)
            }

    async def _initialize_exchanges(self):
        """Initialize exchange connections with retry logic."""
        try:
            # Initialize Binance (spot) - support both ETH and BTC
            logger.info("🔌 Connecting to Binance spot exchange...")
            self.spot_exchange = BinanceExchange("binance", self.config.dict())
            
            # Add retry logic for Binance connection
            max_retries = 3
            retry_delay = 2  # seconds
            
            for attempt in range(max_retries):
                try:
                    connected = await self.spot_exchange.connect([self.spot_symbol])
                    if connected:
                        logger.info(f"✅ Binance spot exchange connected ({self.spot_symbol})")
                        break
                    else:
                        if attempt < max_retries - 1:
                            logger.warning(f"⚠️  Binance connection attempt {attempt + 1} failed, retrying in {retry_delay}s...")
                            await asyncio.sleep(retry_delay)
                        else:
                            raise Exception("Failed to connect to Binance after all retries")
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"⚠️  Binance connection error (attempt {attempt + 1}): {e}, retrying in {retry_delay}s...")
                        await asyncio.sleep(retry_delay)
                    else:
                        raise Exception(f"Failed to connect to Binance after {max_retries} attempts: {e}")
            
            # Initialize Hyperliquid perp exchange
            try:
                logger.info("🔌 Connecting to Hyperliquid perp exchange...")
                self.perp_exchange = HyperliquidExchange("hyperliquid", self.config.dict())
                
                # Connect to Hyperliquid
                if not await self.perp_exchange.connect([self.perp_symbol]):
                    raise Exception("Failed to connect to Hyperliquid")
                
                # Start subscriptions after connection is stable
                logger.info("🚀 Starting Hyperliquid market data subscriptions...")
                try:
                    subscription_result = await self.perp_exchange.start_subscriptions()
                    if not subscription_result:
                        raise Exception("Failed to start Hyperliquid subscriptions")
                    logger.info("✅ Hyperliquid subscriptions started successfully")
                    
                    # Wait for subscriptions to stabilize before proceeding
                    logger.info("⏳ Waiting for subscriptions to stabilize...")
                    await asyncio.sleep(2.0)  # Give WebSocket time to process subscriptions
                    logger.info("✅ Subscriptions should be stable now")
                    
                except Exception as e:
                    logger.error(f"❌ CRITICAL ERROR starting subscriptions: {e}")
                    import traceback
                    traceback.print_exc()
                    raise Exception(f"Failed to start Hyperliquid subscriptions: {e}")
                
                logger.info(f"✅ Hyperliquid perp exchange connected ({self.perp_symbol})")
            except Exception as e:
                logger.error(f"Failed to connect to Hyperliquid: {e}")
                raise
            
        except Exception as e:
            logger.error(f"Error initializing exchanges: {e}")
            raise

    async def _start_market_data_streams(self):
        """Start market data streams for both exchanges."""
        try:
            # Fetch initial quotes from REST API as fallback
            logger.info("Fetching initial quotes from REST API...")
            await self.perp_exchange.fetch_initial_quotes([self.perp_symbol])
            
            # Start spot quote stream
            asyncio.create_task(self._stream_spot_quotes())
            
            # Start perp quote stream
            asyncio.create_task(self._stream_perp_quotes())
            
            logger.info("Market data streams started")
            
        except Exception as e:
            logger.error(f"Error starting market data streams: {e}")
            raise

    async def _stream_spot_quotes(self):
        """Stream spot quotes from Binance."""
        try:
            logger.info(f"🔄 Starting spot quote stream for {self.spot_symbol}")
            logger.info(f"Spot exchange connected: {self.spot_exchange.is_connected()}")
            
            async for quote in self.spot_exchange.watch_quotes([self.spot_symbol]):
                                        # Store quotes by symbol
                        if not hasattr(self, 'spot_quotes_by_symbol'):
                            self.spot_quotes_by_symbol = {}
                            logger.info(f"📊 First spot quote: {quote.symbol} bid=${quote.bid:.4f} ask=${quote.ask:.4f}")
                        
                        # Check if price changed significantly (>0.1%)
                        old_quote = self.spot_quotes_by_symbol.get(quote.symbol)
                        if old_quote:
                            old_mid = (old_quote.bid + old_quote.ask) / 2
                            new_mid = (quote.bid + quote.ask) / 2
                            price_change_pct = abs(new_mid - old_mid) / old_mid * 100
                            if price_change_pct > 0.1:  # Only log if >0.1% change
                                logger.info(f"📊 Spot price update: {quote.symbol} ${old_mid:.4f} → ${new_mid:.4f} ({price_change_pct:+.2f}%)")
                        
                        self.spot_quotes_by_symbol[quote.symbol] = quote
                        self.spot_quotes = list(self.spot_quotes_by_symbol.values())
                        self.state.last_opportunity_check = int(time.time() * 1000)
                
        except Exception as e:
            logger.error(f"Error in spot quote stream: {e}")
            import traceback
            traceback.print_exc()

    async def _stream_perp_quotes(self):
        """Stream perp quotes from Hyperliquid."""
        try:
            logger.info(f"🔄 Starting perp quote stream for {self.perp_symbol}")
            logger.info(f"Perp exchange connected: {self.perp_exchange.is_connected()}")
            
            # Add debugging to see if we reach watch_quotes
            logger.info(f"🔍 About to call watch_quotes on perp_exchange...")
            logger.info(f"🔍 perp_exchange type: {type(self.perp_exchange)}")
            logger.info(f"🔍 perp_exchange methods: {[method for method in dir(self.perp_exchange) if not method.startswith('_')]}")
            
            async for quote in self.perp_exchange.watch_quotes([self.perp_symbol]):
                                        # Store quotes by symbol
                        if not hasattr(self, 'perp_quotes_by_symbol'):
                            self.perp_quotes_by_symbol = {}
                            logger.info(f"📊 First perp quote: {quote.symbol} bid=${quote.bid:.4f} ask=${quote.ask:.4f}")
                        
                        # Check if price changed significantly (>0.1%)
                        old_quote = self.perp_quotes_by_symbol.get(quote.symbol)
                        if old_quote:
                            old_mid = (old_quote.bid + old_quote.ask) / 2
                            new_mid = (quote.bid + quote.ask) / 2
                            price_change_pct = abs(new_mid - old_mid) / old_mid * 100
                            if price_change_pct > 0.1:  # Only log if >0.1% change
                                logger.info(f"📊 Perp price update: {quote.symbol} ${old_mid:.4f} → ${new_mid:.4f} ({price_change_pct:+.2f}%)")
                        
                        self.perp_quotes_by_symbol[quote.symbol] = quote
                        self.perp_quotes = list(self.perp_quotes_by_symbol.values())
                        self.state.last_opportunity_check = int(time.time() * 1000)
                
        except Exception as e:
            logger.error(f"❌ Error in perp quote stream: {e}")
            import traceback
            traceback.print_exc()

    async def _main_loop(self):
        """Main event loop for the strategy."""
        try:
            last_heartbeat = time.time()
            last_hourly_summary = time.time()
            last_price_heartbeat = time.time()  # Price heartbeat timer
            
            while self.state.is_running:
                try:
                    current_time = time.time()
                    
                    # Check for opportunities (every 500ms - reduced frequency)
                    if current_time - last_heartbeat >= 0.5:
                        if not self.state.is_paused:
                            await self._check_opportunities()
                        last_heartbeat = current_time
                    
                    # Send price heartbeat every 30 seconds
                    if current_time - last_price_heartbeat >= 30:  # Every 30 seconds
                        await self._send_price_heartbeat()
                        last_price_heartbeat = current_time
                    
                    # Send hourly summary
                    if current_time - last_hourly_summary >= 3600:  # Every hour
                        if self.telegram:
                            await self.telegram.send_hourly_summary()
                        last_hourly_summary = current_time
                    
                    # Risk management checks
                    await self._check_risk_limits()
                    
                    # Clean up completed orders
                    await self._cleanup_completed_orders()
                    
                    # Small delay to prevent CPU spinning
                    await asyncio.sleep(0.01)
                    
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    await asyncio.sleep(1)  # Wait before retrying
                    
        except Exception as e:
            logger.error(f"Fatal error in main loop: {e}")
            raise
        finally:
            # Ensure cleanup on exit
            logger.info("Main loop exited, cleaning up...")
            await self.stop()

    async def _send_price_heartbeat(self):
        """Send price heartbeat to show bot is working and monitoring prices."""
        try:
            if not self.telegram:
                logger.warning("No Telegram notifier available for heartbeat")
                return
                
            # Get current prices from both exchanges
            spot_price = None
            perp_price = None
            
            # Get spot price from Binance
            if hasattr(self, 'spot_quotes') and self.spot_quotes:
                spot_quote = self.spot_quotes[0]  # Get first quote
                spot_price = (spot_quote.bid + spot_quote.ask) / 2
                spot_bid = spot_quote.bid
                spot_ask = spot_quote.ask
            else:
                logger.warning("No spot quotes available")
                return
            
            # Get perp price from Hyperliquid
            if hasattr(self, 'perp_quotes') and self.perp_quotes:
                perp_quote = self.perp_quotes[0]  # Get first quote
                perp_price = (perp_quote.bid + perp_quote.ask) / 2
                perp_bid = perp_quote.bid
                perp_ask = perp_quote.ask
            else:
                logger.warning("No perp quotes available")
                return
            
            if spot_price and perp_price:
                # Calculate spread
                spread_bps = abs(perp_price - spot_price) / spot_price * 10000
                
                # Format heartbeat message
                message = f"""
💓 <b>PRICE HEARTBEAT - {self.spot_symbol} ↔ {self.perp_symbol}</b>

⏰ Time: {datetime.now().strftime('%H:%M:%S')}
🔄 Status: <b>ACTIVE</b> - Monitoring for opportunities

📊 <b>Current Prices:</b>
• Binance Spot: ${spot_price:.4f} (${spot_bid:.4f} / ${spot_ask:.4f})
• HL Perp: ${perp_price:.4f} (${perp_bid:.4f} / ${perp_ask:.4f})

📈 <b>Spread Analysis:</b>
• Spread: {spread_bps:.1f} bps
• Min Required: {self.config.detector.min_edge_bps} bps
• Status: {'🟢 Profitable' if spread_bps >= self.config.detector.min_edge_bps else '🔴 Below threshold'}

🎯 <b>Bot Status:</b>
• Market Data: ✅ Streaming
• Opportunity Detection: ✅ Active
• Risk Management: ✅ Monitoring
                """
                
                await self.telegram.send_message(message)
                logger.info(f"Price heartbeat sent - Spot: ${spot_price:.4f}, Perp: ${perp_price:.4f}, Spread: {spread_bps:.1f} bps")
            else:
                # Send a simple status heartbeat even without prices
                message = f"""
💓 <b>STATUS HEARTBEAT - {self.spot_symbol} ↔ {self.perp_symbol}</b>

⏰ Time: {datetime.now().strftime('%H:%M:%S')}
🔄 Status: <b>ACTIVE</b> - Waiting for market data

📊 <b>Current Status:</b>
• Bot: ✅ Running
• Market Data: ⏳ Initializing
• Opportunity Detection: ✅ Active
• Risk Management: ✅ Monitoring

💡 <b>Note:</b> Waiting for first price quotes from exchanges...
                """
                
                await self.telegram.send_message(message)
                logger.info("Status heartbeat sent (waiting for price data)")
            
        except Exception as e:
            logger.error(f"Error sending price heartbeat: {e}")
            import traceback
            traceback.print_exc()

    async def _log_market_conditions(self):
        """Log current market conditions for debugging."""
        try:
            if not self.spot_quotes or not self.perp_quotes:
                return
            
            for spot_quote in self.spot_quotes:
                base_asset = spot_quote.symbol.split('/')[0]
                perp_symbol = f"{base_asset}-PERP"
                
                # Find matching perp quote
                matching_perp = None
                for perp_quote in self.perp_quotes:
                    if perp_quote.symbol == perp_symbol:
                        matching_perp = perp_quote
                        break
                
                if matching_perp:
                    # Calculate current spread
                    spot_mid = (spot_quote.bid + spot_quote.ask) / 2
                    perp_mid = (matching_perp.bid + matching_perp.ask) / 2
                    spread_bps = abs(perp_mid - spot_mid) / spot_mid * 10000
                    
                    logger.debug(f"📊 Market conditions for {spot_quote.symbol} ↔ {perp_symbol}:")
                    logger.debug(f"   Spot: ${spot_quote.bid:.4f} / ${spot_quote.ask:.4f} (mid: ${spot_mid:.4f})")
                    logger.debug(f"   Perp: ${matching_perp.bid:.4f} / ${matching_perp.ask:.4f} (mid: ${perp_mid:.4f})")
                    logger.debug(f"   Spread: {spread_bps:.2f} bps (min required: {self.config.detector.min_edge_bps} bps)")
                    
                    # Check if spread meets minimum threshold
                    if spread_bps >= self.config.detector.min_edge_bps:
                        logger.debug(f"   🟢 Spread {spread_bps:.2f} bps >= minimum {self.config.detector.min_edge_bps} bps")
                    else:
                        logger.debug(f"   🔴 Spread {spread_bps:.2f} bps < minimum {self.config.detector.min_edge_bps} bps")
                        
        except Exception as e:
            logger.error(f"Error logging market conditions: {e}")

    async def _check_opportunities(self):
        """Check for arbitrage opportunities."""
        try:
            if not self.spot_quotes or not self.perp_quotes:
                logger.debug("No quotes available for opportunity detection")
                return
            
            # Log current market conditions
            await self._log_market_conditions()
            
            # Map spot quotes to corresponding perp quotes
            mapped_quotes = []
            for spot_quote in self.spot_quotes:
                # Find corresponding perp quote (ETH/USDC -> ETH-PERP)
                base_asset = spot_quote.symbol.split('/')[0]
                perp_symbol = f"{base_asset}-PERP"
                
                # Find matching perp quote
                matching_perp = None
                for perp_quote in self.perp_quotes:
                    if perp_quote.symbol == perp_symbol:
                        matching_perp = perp_quote
                        break
                
                if matching_perp:
                    mapped_quotes.append((spot_quote, matching_perp))
            
            if not mapped_quotes:
                logger.debug("No mapped quote pairs found")
                return
            
            logger.debug(f"Checking opportunities for {len(mapped_quotes)} mapped pairs")
            
            # Detect opportunities for each mapped pair
            for spot_quote, perp_quote in mapped_quotes:
                logger.debug(f"🔍 Detecting opportunities for {spot_quote.symbol} ↔ {perp_quote.symbol}")
                
                opportunities = self.detector.detect_opportunities(
                    [spot_quote], [perp_quote]
                )
                
                if opportunities:
                    self.state.opportunities_detected += len(opportunities)
                    logger.info(f"🎯 Detected {len(opportunities)} opportunities for {spot_quote.symbol} ↔ {perp_quote.symbol}")
                    
                    # Take the best opportunity
                    best_opportunity = opportunities[0]
                    logger.info(f"📊 Best opportunity: {best_opportunity.gross_edge_bps:.2f} bps gross, {best_opportunity.net_edge_bps:.2f} bps net")
                    
                    # Check if we should execute
                    if await self._should_execute(best_opportunity):
                        logger.info(f"🚀 Executing opportunity: {best_opportunity.symbol} {best_opportunity.direction.value}")
                        await self._execute_opportunity(best_opportunity)
                        break  # Only execute one opportunity at a time
                    else:
                        logger.debug(f"❌ Opportunity not executed due to execution checks")
                else:
                    logger.debug(f"❌ No opportunities detected for {spot_quote.symbol} ↔ {perp_quote.symbol}")
                    
        except Exception as e:
            logger.error(f"Error checking opportunities: {e}")
            import traceback
            traceback.print_exc()

    async def _should_execute(self, opportunity: SpotPerpOpportunity) -> bool:
        """Check if we should execute the opportunity."""
        try:
            logger.debug(f"🔍 Checking execution conditions for {opportunity.symbol} {opportunity.direction.value}")
            
            # Check if opportunity has expired
            if time.time() * 1000 > opportunity.expires_at:
                logger.debug(f"❌ Opportunity expired: {opportunity.expires_at} < {int(time.time() * 1000)}")
                return False
            
            logger.debug(f"✅ Opportunity not expired")
            
            # Check risk limits
            if not await self._check_risk_limits():
                logger.debug(f"❌ Risk limits check failed")
                return False
            
            logger.debug(f"✅ Risk limits check passed")
            
            # Check if we have active orders
            if self.active_orders:
                logger.debug(f"❌ Active orders exist: {len(self.active_orders)}")
                return False
            
            logger.debug(f"✅ No active orders")
            
            # Check minimum time between trades
            min_trade_interval = 5.0  # 5 seconds
            if time.time() - (self.state.last_trade_time / 1000) < min_trade_interval:
                logger.debug(f"❌ Trade interval too short: {time.time() - (self.state.last_trade_time / 1000):.1f}s < {min_trade_interval}s")
                return False
            
            logger.debug(f"✅ Trade interval check passed")
            logger.debug(f"✅ All execution checks passed - ready to execute")
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking execution conditions: {e}")
            return False

    async def _execute_opportunity(self, opportunity: SpotPerpOpportunity):
        """Execute an arbitrage opportunity."""
        try:
            logger.info(f"Executing opportunity: {opportunity.symbol} {opportunity.direction.value}")
            
            # Create execution plan
            plan = self.planner.create_execution_plan(opportunity)
            if not plan:
                logger.warning("Failed to create execution plan")
                return
            
            # Execute both legs
            execution_results = await self._execute_plan(plan)
            
            if execution_results:
                await self._handle_execution_results(execution_results, opportunity)
            
        except Exception as e:
            logger.error(f"Error executing opportunity: {e}")

    async def _execute_plan(self, plan: ExecutionPlan) -> List[Dict[str, Any]]:
        """Execute a trading plan."""
        try:
            results = []
            
            # Execute all legs concurrently
            execution_tasks = []
            for leg in plan.legs:
                task = self._execute_leg(leg)
                execution_tasks.append(task)
            
            # Wait for all legs to complete
            leg_results = await asyncio.gather(*execution_tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(leg_results):
                if isinstance(result, Exception):
                    logger.error(f"Leg {i} execution failed: {result}")
                    results.append({
                        'success': False,
                        'error': str(result),
                        'leg': plan.legs[i]
                    })
                else:
                    results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Error executing plan: {e}")
            return []

    async def _execute_leg(self, leg: ExecutionLeg) -> Dict[str, Any]:
        """Execute a single trading leg."""
        try:
            start_time = time.time()
            
            # Determine which exchange to use
            if leg.exchange == self.spot_exchange.name:
                exchange = self.spot_exchange
                result = await exchange.place_order(
                    symbol=leg.symbol,
                    side=leg.side,
                    order_type=leg.order_type,
                    amount=leg.amount,
                    price=leg.price
                )
            else:  # Hyperliquid
                exchange = self.perp_exchange
                result = await exchange.create_order_perp(
                    symbol=leg.symbol,
                    side=leg.side,
                    amount_base=leg.amount,
                    price=leg.price,
                    tif=leg.order_type,
                    reduce_only=leg.reduce_only
                )
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # Add execution metadata
            result.metadata = {
                'exchange': leg.exchange,
                'symbol': leg.symbol,
                'side': leg.side,
                'amount': leg.amount,
                'price': leg.price,
                'execution_time_ms': execution_time_ms
            }
            
            return {
                'success': result.success,
                'order_id': result.order_id,
                'filled_qty': result.filled_qty,
                'avg_price': result.avg_price,
                'fee_amount': result.fee_amount,
                'execution_time_ms': execution_time_ms,
                'leg': leg,
                'result': result
            }
            
        except Exception as e:
            logger.error(f"Error executing leg: {e}")
            return {
                'success': False,
                'error': str(e),
                'leg': leg
            }

    async def _handle_execution_results(self, results: List[Dict[str, Any]], 
                                      opportunity: SpotPerpOpportunity):
        """Handle execution results and determine next actions."""
        try:
            successful_legs = [r for r in results if r['success']]
            failed_legs = [r for r in results if not r['success']]
            
            if len(successful_legs) == 2:
                # Both legs succeeded - complete trade
                await self._handle_successful_trade(results, opportunity)
                
            elif len(successful_legs) == 1:
                # One leg succeeded - need to unwind
                await self._handle_partial_fill(successful_legs[0], opportunity)
                
            else:
                # Both legs failed
                logger.warning("Both legs failed to execute")
                
        except Exception as e:
            logger.error(f"Error handling execution results: {e}")

    async def _handle_successful_trade(self, results: List[Dict[str, Any]], 
                                     opportunity: SpotPerpOpportunity):
        """Handle a successful two-leg trade."""
        try:
            # Calculate realized PnL
            total_cost = sum(r['filled_qty'] * r['avg_price'] for r in results)
            total_fees = sum(r['fee_amount'] for r in results)
            
            # For now, use expected PnL from opportunity
            realized_pnl = opportunity.net_edge_bps * total_cost / 10000 - total_fees
            
            # Update state
            self.state.trades_executed += 1
            self.state.total_pnl += realized_pnl
            self.state.last_trade_time = int(time.time() * 1000)
            
            # Update daily notional
            trade_notional = opportunity.trade_size * opportunity.spot_price
            self.daily_notional += trade_notional
            
            # Update consecutive losses
            if realized_pnl < 0:
                self.consecutive_losses += 1
                self.daily_loss += abs(realized_pnl)
            else:
                self.consecutive_losses = 0
            
            # Log trade
            logger.info(f"Trade completed: {opportunity.symbol} {opportunity.direction.value}")
            logger.info(f"  Realized PnL: ${realized_pnl:.4f}")
            logger.info(f"  Total fees: ${total_fees:.4f}")
            
            # Send Telegram notification
            if self.telegram:
                trade_data = {
                    'symbol': opportunity.symbol,
                    'direction': opportunity.direction.value,
                    'trade_size': opportunity.trade_size,
                    'net_edge_bps': opportunity.net_edge_bps,
                    'realized_pnl': realized_pnl,
                    'execution_time_ms': max(r['execution_time_ms'] for r in results)
                }
                await self.telegram.notify_trade_filled(trade_data)
                
        except Exception as e:
            logger.error(f"Error handling successful trade: {e}")

    async def _handle_partial_fill(self, filled_leg: Dict[str, Any], 
                                 opportunity: SpotPerpOpportunity):
        """Handle partial fill - unwind the filled leg."""
        try:
            logger.warning(f"Partial fill detected on {filled_leg['leg'].exchange}")
            
            # Create unwind plan
            unwind_plan = self.planner.create_unwind_plan(
                filled_leg['leg'], opportunity
            )
            
            if unwind_plan:
                # Execute unwind
                unwind_results = await self._execute_plan(unwind_plan)
                
                if unwind_results and unwind_results[0]['success']:
                    logger.info("Successfully unwound partial position")
                    
                    # Send Telegram notification
                    if self.telegram:
                        partial_data = {
                            'symbol': opportunity.symbol,
                            'exchange': filled_leg['leg'].exchange,
                            'fill_percentage': 100.0,  # Full fill on one leg
                            'action': 'Unwound',
                            'pnl_impact': 0.0,  # Unwind is for risk management
                            'status': 'Completed'
                        }
                        await self.telegram.notify_partial_fill(partial_data)
                else:
                    logger.error("Failed to unwind partial position")
                    
        except Exception as e:
            logger.error(f"Error handling partial fill: {e}")

    async def _check_risk_limits(self) -> bool:
        """Check risk management limits."""
        try:
            # Check daily notional limit
            if self.daily_notional > self.config.risk.daily_notional_limit:
                logger.warning("Daily notional limit exceeded")
                await self._handle_risk_event("daily_notional_limit", "Daily notional limit exceeded")
                return False
            
            # Check consecutive losses
            if self.consecutive_losses >= self.config.risk.max_consecutive_losses:
                logger.warning("Max consecutive losses reached")
                await self._handle_risk_event("consecutive_losses", "Max consecutive losses reached")
                return False
            
            # Check daily loss limit
            if self.daily_loss > self.config.risk.max_daily_loss_pct * self.daily_notional / 100:
                logger.warning("Daily loss limit exceeded")
                await self._handle_risk_event("daily_loss_limit", "Daily loss limit exceeded")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking risk limits: {e}")
            return False

    async def _handle_risk_event(self, event_type: str, reason: str):
        """Handle risk events."""
        try:
            logger.warning(f"Risk event: {event_type} - {reason}")
            
            # Pause trading
            await self.pause()
            
            # Send Telegram notification
            if self.telegram:
                risk_data = {
                    'type': event_type,
                    'reason': reason,
                    'severity': 'High',
                    'details': f"Trading paused due to {event_type}",
                    'action': 'Trading paused automatically'
                }
                await self.telegram.notify_risk_event(risk_data)
                
        except Exception as e:
            logger.error(f"Error handling risk event: {e}")

    async def _cancel_all_orders(self):
        """Cancel all active orders."""
        try:
            for order_id, order_info in self.active_orders.items():
                exchange_name = order_info['exchange']
                
                if exchange_name == self.spot_exchange.name:
                    await self.spot_exchange.cancel_order(order_info['symbol'], order_id)
                else:
                    await self.perp_exchange.cancel_order(order_info['symbol'])
                    
            self.active_orders.clear()
            logger.info("All active orders cancelled")
            
        except Exception as e:
            logger.error(f"Error cancelling orders: {e}")

    async def _cleanup_completed_orders(self):
        """Clean up completed orders from tracking."""
        try:
            # Remove orders older than 1 hour
            current_time = time.time()
            expired_orders = []
            
            for order_id, order_info in self.active_orders.items():
                if current_time - order_info['timestamp'] > 3600:
                    expired_orders.append(order_id)
            
            for order_id in expired_orders:
                del self.active_orders[order_id]
                
        except Exception as e:
            logger.error(f"Error cleaning up orders: {e}")

    def _get_guards_status(self) -> str:
        """Get status of risk guards."""
        try:
            guards = []
            
            if self.daily_notional > self.config.risk.daily_notional_limit * 0.8:
                guards.append("Daily notional: 80%+")
            
            if self.consecutive_losses > 0:
                guards.append(f"Consecutive losses: {self.consecutive_losses}")
            
            if self.daily_loss > 0:
                guards.append(f"Daily loss: ${self.daily_loss:.2f}")
            
            return ", ".join(guards) if guards else "All clear"
            
        except Exception as e:
            logger.error(f"Error getting guards status: {e}")
            return "Unknown"
