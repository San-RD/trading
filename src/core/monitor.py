"""Market monitoring and opportunity detection."""

import asyncio
import time
from typing import Dict, List, Optional, Set
from loguru import logger

from ..exchanges.base import Quote, OrderBook
from ..exchanges.depth_model import DepthModel
from .quotes import QuoteBus
from .detector import ArbitrageDetector
from .executor import ArbitrageExecutor
from .risk import RiskManager
from .session import SessionManager
from .inventory import InventoryManager
from .portfolio import PortfolioManager


@dataclass
class Opportunity:
    """Represents a trading opportunity."""
    triangle: Triangle
    edge_bps: float
    expected_profit: float
    direction: str
    path: List[str]
    legs: List[Dict]
    timestamp: float
    quotes_age_ms: float


class MarketMonitor:
    """Monitors market data and detects arbitrage opportunities."""
    
    def __init__(self, exchange_client: BinanceClient):
        self.exchange = exchange_client
        self.config = get_config()
        self.depth_model = DepthModel(
            enabled=self.config.depth_model.enabled,
            levels=self.config.depth_model.levels
        )
        
        # Market data
        self.symbol_rules: Dict[str, SymbolRule] = {}
        self.triangles: List[Triangle] = []
        self.quotes: Dict[str, Dict] = {}
        self.last_quote_timestamps: Dict[str, float] = {}
        
        # Opportunity tracking
        self.opportunities: List[Opportunity] = []
        self.last_execution_time: Dict[str, float] = {}
        self.debounce_seconds = 2.0
        
        # State
        self.running = False
        self._quote_queue: asyncio.Queue = asyncio.Queue()
        self._opportunity_queue: asyncio.Queue = asyncio.Queue()
    
    async def start(self):
        """Start the market monitor."""
        if self.running:
            return
        
        logger.info("Starting market monitor")
        self.running = True
        
        # Load markets and rules
        await self._load_markets()
        
        # Start monitoring tasks
        tasks = [
            asyncio.create_task(self._quote_processor()),
            asyncio.create_task(self._opportunity_detector()),
            asyncio.create_task(self._websocket_monitor()),
        ]
        
        if self.config.depth_model.enabled:
            tasks.append(asyncio.create_task(self._depth_updater()))
        
        await asyncio.gather(*tasks)
    
    async def stop(self):
        """Stop the market monitor."""
        logger.info("Stopping market monitor")
        self.running = False
    
    async def _load_markets(self):
        """Load markets and trading rules."""
        try:
            self.symbol_rules = await self.exchange.load_markets_and_rules()
            
            # Find triangles
            self.triangles = find_triangles(
                self.symbol_rules,
                self.config.triangles.quote_assets,
                self.config.triangles.exclude_assets,
                self.config.triangles.include_only
            )
            
            logger.info(f"Loaded {len(self.symbol_rules)} symbols and found {len(self.triangles)} triangles")
            
        except Exception as e:
            logger.error(f"Failed to load markets: {e}")
            raise
    
    async def _websocket_monitor(self):
        """Monitor websocket for market data updates."""
        try:
            # Get all pairs from triangles
            all_pairs = set()
            for triangle in self.triangles:
                all_pairs.update(triangle.get_pairs())
            
            pairs_list = list(all_pairs)
            logger.info(f"Monitoring {len(pairs_list)} pairs via WebSocket")
            
            async for ticker in self.exchange.watch_book_tickers(pairs_list):
                await self._quote_queue.put(ticker)
                
        except Exception as e:
            logger.error(f"WebSocket monitor error: {e}")
            if self.running:
                # Restart after delay
                await asyncio.sleep(5)
                asyncio.create_task(self._websocket_monitor())
    
    async def _quote_processor(self):
        """Process incoming quotes."""
        while self.running:
            try:
                ticker = await asyncio.wait_for(self._quote_queue.get(), timeout=1.0)
                
                # Update quotes
                pair = ticker['pair']
                self.quotes[pair] = {
                    'bid': ticker['bid'],
                    'ask': ticker['ask'],
                    'ts': ticker['ts'],
                    'bid_volume': ticker.get('bid_volume', 0),
                    'ask_volume': ticker.get('ask_volume', 0),
                }
                self.last_quote_timestamps[pair] = time.time()
                
                # Update depth model if enabled
                if self.config.depth_model.enabled:
                    # For now, just use top of book
                    # In practice, you'd fetch L10 depth here
                    pass
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Quote processor error: {e}")
    
    async def _opportunity_detector(self):
        """Detect arbitrage opportunities."""
        while self.running:
            try:
                await asyncio.sleep(0.1)  # Check every 100ms
                
                current_time = time.time()
                opportunities = []
                
                for triangle in self.triangles:
                    # Check if we have fresh quotes for all pairs
                    if not self._has_fresh_quotes(triangle):
                        continue
                    
                    # Check debouncing
                    triangle_key = f"{triangle.asset_a}-{triangle.asset_b}-{triangle.asset_c}"
                    if self._is_debounced(triangle_key, current_time):
                        continue
                    
                    # Calculate edge
                    try:
                        edge_bps, profit, details = calculate_triangle_edge(
                            triangle, self.quotes, self.config.risk.max_notional_usdt,
                            self.symbol_rules, self.depth_model
                        )
                        
                        # Check if edge meets minimum threshold
                        if edge_bps >= self.config.risk.min_edge_bps:
                            # Check if quotes are fresh enough
                            quotes_age_ms = self._get_quotes_age_ms(triangle)
                            if quotes_age_ms <= self.config.risk.max_latency_ms:
                                
                                opportunity = Opportunity(
                                    triangle=triangle,
                                    edge_bps=edge_bps,
                                    expected_profit=profit,
                                    direction=details['direction'],
                                    path=details['path'],
                                    legs=details['legs'],
                                    timestamp=current_time,
                                    quotes_age_ms=quotes_age_ms
                                )
                                
                                opportunities.append(opportunity)
                                
                                # Update last execution time
                                self.last_execution_time[triangle_key] = current_time
                                
                    except Exception as e:
                        logger.error(f"Error calculating edge for {triangle}: {e}")
                        continue
                
                # Sort opportunities by edge and put in queue
                opportunities.sort(key=lambda x: x.edge_bps, reverse=True)
                for opp in opportunities:
                    await self._opportunity_queue.put(opp)
                
            except Exception as e:
                logger.error(f"Opportunity detector error: {e}")
    
    async def _depth_updater(self):
        """Periodically update depth data."""
        while self.running:
            try:
                await asyncio.sleep(self.config.depth_model.update_interval_sec)
                
                for triangle in self.triangles:
                    for pair in triangle.get_pairs():
                        try:
                            order_book = await self.exchange.fetch_order_book(pair, self.config.depth_model.levels)
                            if order_book:
                                self.depth_model.update_depth(
                                    pair,
                                    order_book['bids'][:self.config.depth_model.levels],
                                    order_book['asks'][:self.config.depth_model.levels]
                                )
                        except Exception as e:
                            logger.debug(f"Failed to update depth for {pair}: {e}")
                            
            except Exception as e:
                logger.error(f"Depth updater error: {e}")
    
    def _has_fresh_quotes(self, triangle: Triangle) -> bool:
        """Check if we have fresh quotes for all pairs in a triangle."""
        current_time = time.time()
        max_age = self.config.risk.max_latency_ms / 1000.0
        
        for pair in triangle.get_pairs():
            if pair not in self.last_quote_timestamps:
                return False
            
            age = current_time - self.last_quote_timestamps[pair]
            if age > max_age:
                return False
        
        return True
    
    def _is_debounced(self, triangle_key: str, current_time: float) -> bool:
        """Check if a triangle is debounced."""
        if triangle_key not in self.last_execution_time:
            return False
        
        time_since_last = current_time - self.last_execution_time[triangle_key]
        return time_since_last < self.debounce_seconds
    
    def _get_quotes_age_ms(self, triangle: Triangle) -> float:
        """Get the age of quotes for a triangle in milliseconds."""
        current_time = time.time()
        max_age = 0
        
        for pair in triangle.get_pairs():
            if pair in self.last_quote_timestamps:
                age = (current_time - self.last_quote_timestamps[pair]) * 1000
                max_age = max(max_age, age)
        
        return max_age
    
    async def get_opportunities(self) -> AsyncGenerator[Opportunity, None]:
        """Get opportunities as they are detected."""
        while self.running:
            try:
                opportunity = await asyncio.wait_for(self._opportunity_queue.get(), timeout=1.0)
                yield opportunity
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error getting opportunity: {e}")
    
    def get_market_status(self) -> Dict:
        """Get current market status."""
        current_time = time.time()
        
        # Calculate quote freshness
        fresh_quotes = 0
        stale_quotes = 0
        for pair, timestamp in self.last_quote_timestamps.items():
            age = current_time - timestamp
            if age <= self.config.risk.max_latency_ms / 1000.0:
                fresh_quotes += 1
            else:
                stale_quotes += 1
        
        return {
            'running': self.running,
            'symbols_loaded': len(self.symbol_rules),
            'triangles_found': len(self.triangles),
            'quotes_fresh': fresh_quotes,
            'quotes_stale': stale_quotes,
            'last_ws_update': self.exchange.get_last_ws_update(),
            'depth_model_enabled': self.config.depth_model.enabled,
        }
