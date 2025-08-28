"""Quote management and WebSocket handlers for cross-exchange arbitrage."""

import asyncio
import time
from typing import Dict, List, Optional, AsyncGenerator, Callable, Any
from dataclasses import dataclass
from collections import defaultdict
from loguru import logger

from src.exchanges.base import BaseExchange, Quote
from src.config import Config


@dataclass
class ConsolidatedQuote:
    """Consolidated quote data across exchanges."""
    symbol: str
    left_quote: Optional[Quote]
    right_quote: Optional[Quote]
    ts_local: int
    
    @property
    def is_complete(self) -> bool:
        """Check if we have quotes from both exchanges."""
        return self.left_quote is not None and self.right_quote is not None
    
    @property
    def age_ms(self) -> int:
        """Get age of oldest quote in milliseconds."""
        if not self.is_complete:
            return float('inf')
        
        oldest_ts = min(self.left_quote.ts_local, self.right_quote.ts_local)
        return int(time.time() * 1000) - oldest_ts
    
    @property
    def left_bid(self) -> float:
        """Get left exchange bid price."""
        return self.left_quote.bid if self.left_quote else 0.0
    
    @property
    def left_ask(self) -> float:
        """Get left exchange ask price."""
        return self.left_quote.ask if self.left_quote else 0.0
    
    @property
    def right_bid(self) -> float:
        """Get right exchange bid price."""
        return self.right_quote.bid if self.right_quote else 0.0
    
    @property
    def right_ask(self) -> float:
        """Get right exchange ask price."""
        return self.right_quote.ask if self.right_quote else 0.0


class QuoteManager:
    """Manages consolidated quotes across exchanges."""

    def __init__(self, config: Config):
        self.config = config
        self.quotes: Dict[str, ConsolidatedQuote] = {}
        self.quote_callbacks: List[Callable[[ConsolidatedQuote], None]] = []
        self._running = False
        self._last_update = 0

    def add_quote_callback(self, callback: Callable[[ConsolidatedQuote], None]):
        """Add callback for new consolidated quotes."""
        self.quote_callbacks.append(callback)

    def update_quote(self, quote: Quote):
        """Update quote from an exchange."""
        symbol = quote.symbol
        venue = quote.venue
        
        if symbol not in self.quotes:
            self.quotes[symbol] = ConsolidatedQuote(
                symbol=symbol,
                left_quote=None,
                right_quote=None,
                ts_local=int(time.time() * 1000)
            )
        
        consolidated = self.quotes[symbol]
        
        # Update quote based on venue
        if venue == self.config.exchanges.left:
            consolidated.left_quote = quote
        elif venue == self.config.exchanges.right:
            consolidated.right_quote = quote
        
        consolidated.ts_local = int(time.time() * 1000)
        self._last_update = consolidated.ts_local
        
        # Notify callbacks if we have a complete quote
        if consolidated.is_complete:
            for callback in self.quote_callbacks:
                try:
                    callback(consolidated)
                except Exception as e:
                    logger.error(f"Error in quote callback: {e}")

    def get_quote(self, symbol: str) -> Optional[ConsolidatedQuote]:
        """Get consolidated quote for a symbol."""
        return self.quotes.get(symbol)

    def get_all_quotes(self) -> List[ConsolidatedQuote]:
        """Get all consolidated quotes."""
        return list(self.quotes.values())

    def get_fresh_quotes(self, max_age_ms: Optional[int] = None) -> List[ConsolidatedQuote]:
        """Get quotes that are fresh (within max_age_ms)."""
        if max_age_ms is None:
            max_age_ms = self.config.detector.min_book_bbo_age_ms
        
        current_time = int(time.time() * 1000)
        fresh_quotes = []
        
        for quote in self.quotes.values():
            if quote.is_complete and (current_time - quote.ts_local) <= max_age_ms:
                fresh_quotes.append(quote)
        
        return fresh_quotes

    def cleanup_stale_quotes(self, max_age_ms: int = 60000):
        """Remove quotes older than max_age_ms."""
        current_time = int(time.time() * 1000)
        stale_symbols = []
        
        for symbol, quote in self.quotes.items():
            if (current_time - quote.ts_local) > max_age_ms:
                stale_symbols.append(symbol)
        
        for symbol in stale_symbols:
            del self.quotes[symbol]
        
        if stale_symbols:
            logger.info(f"Cleaned up {len(stale_symbols)} stale quotes")

    def get_quote_summary(self) -> Dict[str, Any]:
        """Get summary of quote status."""
        total_quotes = len(self.quotes)
        complete_quotes = sum(1 for q in self.quotes.values() if q.is_complete)
        fresh_quotes = len(self.get_fresh_quotes())
        
        return {
            'total_quotes': total_quotes,
            'complete_quotes': complete_quotes,
            'fresh_quotes': fresh_quotes,
            'last_update_ms': self._last_update,
            'symbols': list(self.quotes.keys())
        }


class WebSocketManager:
    """Manages WebSocket connections and quote streams."""

    def __init__(self, config: Config, quote_manager: QuoteManager):
        self.config = config
        self.quote_manager = quote_manager
        self.exchanges: Dict[str, BaseExchange] = {}
        self._running = False
        self._tasks: List[asyncio.Task] = []

    def add_exchange(self, name: str, exchange: BaseExchange):
        """Add an exchange to monitor."""
        self.exchanges[name] = exchange

    async def start(self, symbols: List[str]):
        """Start monitoring quotes for given symbols."""
        if self._running:
            return
        
        self._running = True
        logger.info(f"Starting WebSocket monitoring for {len(symbols)} symbols")
        
        # Start monitoring tasks for each exchange
        for name, exchange in self.exchanges.items():
            if exchange.is_connected():
                task = asyncio.create_task(
                    self._monitor_exchange(name, exchange, symbols)
                )
                self._tasks.append(task)
                logger.info(f"Started monitoring {name} exchange")
            else:
                logger.warning(f"Exchange {name} not connected, skipping")

    async def stop(self):
        """Stop all monitoring tasks."""
        if not self._running:
            return
        
        self._running = False
        logger.info("Stopping WebSocket monitoring")
        
        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        logger.info("WebSocket monitoring stopped")

    async def _monitor_exchange(self, name: str, exchange: BaseExchange, symbols: List[str]):
        """Monitor quotes from a specific exchange."""
        try:
            async for quote in exchange.watch_quotes(symbols):
                if not self._running:
                    break
                
                # Update quote manager
                self.quote_manager.update_quote(quote)
                
        except Exception as e:
            logger.error(f"Error monitoring {name} exchange: {e}")
            if self._running:
                # Try to restart monitoring after delay
                await asyncio.sleep(5)
                if self._running:
                    logger.info(f"Restarting monitoring for {name}")
                    await self._monitor_exchange(name, exchange, symbols)

    def get_status(self) -> Dict[str, Any]:
        """Get status of WebSocket connections."""
        status = {
            'running': self._running,
            'active_tasks': len(self._tasks),
            'exchanges': {}
        }
        
        for name, exchange in self.exchanges.items():
            status['exchanges'][name] = {
                'connected': exchange.is_connected(),
                'last_update': exchange.get_last_update()
            }
        
        return status


class QuoteBus:
    """Central quote bus for distributing quotes to components."""

    def __init__(self, config: Config):
        self.config = config
        self.quote_manager = QuoteManager(config)
        self.ws_manager = WebSocketManager(config, self.quote_manager)
        self._subscribers: Dict[str, List[Callable[[ConsolidatedQuote], None]]] = defaultdict(list)

    def subscribe(self, subscriber_id: str, callback: Callable[[ConsolidatedQuote], None]):
        """Subscribe to quote updates."""
        self._subscribers[subscriber_id].append(callback)
        self.quote_manager.add_quote_callback(callback)

    def unsubscribe(self, subscriber_id: str):
        """Unsubscribe from quote updates."""
        if subscriber_id in self._subscribers:
            del self._subscribers[subscriber_id]

    def add_exchange(self, name: str, exchange: BaseExchange):
        """Add an exchange to the quote bus."""
        self.ws_manager.add_exchange(name, exchange)

    async def start(self, symbols: List[str]):
        """Start the quote bus."""
        await self.ws_manager.start(symbols)

    async def stop(self):
        """Stop the quote bus."""
        await self.ws_manager.stop()

    def get_quote(self, symbol: str) -> Optional[ConsolidatedQuote]:
        """Get consolidated quote for a symbol."""
        return self.quote_manager.get_quote(symbol)

    def get_fresh_quotes(self, max_age_ms: Optional[int] = None) -> List[ConsolidatedQuote]:
        """Get fresh consolidated quotes."""
        return self.quote_manager.get_fresh_quotes(max_age_ms)

    def get_status(self) -> Dict[str, Any]:
        """Get status of quote bus."""
        return {
            'quotes': self.quote_manager.get_quote_summary(),
            'websocket': self.ws_manager.get_status()
        }
