"""OKX exchange integration for cross-exchange arbitrage."""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Any, AsyncGenerator
from decimal import Decimal

import ccxt.pro as ccxt

from .base import BaseExchange, Quote, OrderBook, Balance, OrderResult

logger = logging.getLogger(__name__)


class OKXExchange(BaseExchange):
    """OKX exchange implementation."""

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        
        # Separate clients for public vs private operations
        self.rest_public: Optional[ccxt.okx] = None
        self.ws_public: Optional[ccxt.okx] = None
        self.rest_private: Optional[ccxt.okx] = None
        
        self._connected = False
        self._last_update = 0
        self._markets_loaded = False

    def _init_public_rest(self):
        """Initialize public REST client (no keys)."""
        self.rest_public = ccxt.okx({
            "enableRateLimit": True,
            "timeout": 10000,
            "options": {"defaultType": "spot"},
        })

    def _init_public_ws(self):
        """Initialize public WebSocket client (no keys)."""
        self.ws_public = ccxt.okx({
            "enableRateLimit": True,
            "timeout": 10000,
            "options": {"defaultType": "spot"},
        })

    def _init_private_rest(self):
        """Initialize private REST client (with keys)."""
        acct = self.config["exchanges"]["accounts"]["okx"]
        self.rest_private = ccxt.okx({
            "apiKey": acct["key"],
            "secret": acct["secret"],
            "password": acct["password"],  # OKX password
            "enableRateLimit": True,
            "timeout": 10000,
            "options": {"defaultType": "spot"},
        })
        
        # Set sandbox mode if configured
        if acct.get("sandbox", False):
            self.rest_private.set_sandbox_mode(True)

    async def connect(self, symbols: list[str]) -> bool:
        """Connect to OKX exchange."""
        try:
            # 1) Initialize clients
            self._init_public_rest()
            self._init_public_ws()
            self._init_private_rest()

            # 2) Guard: public clients must not have keys
            assert not getattr(self.rest_public, "apiKey", None), "Public REST has apiKey!"
            assert not getattr(self.ws_public, "apiKey", None), "Public WS has apiKey!"

            # 3) Load markets on public clients only
            await self.rest_public.load_markets()
            await self.ws_public.load_markets()

            # 4) Validate symbols
            for symbol in symbols:
                if symbol not in self.rest_public.markets:
                    logger.error(f"OKX symbol not found in public markets: {symbol}")
                    return False

            self._connected = True
            self._markets_loaded = True
            logger.info(f"OKX connected with symbols {symbols} (public markets loaded)")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to OKX: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from OKX exchange."""
        try:
            if self.rest_public:
                await self.rest_public.close()
            if self.ws_public:
                await self.ws_public.close()
            if self.rest_private:
                await self.rest_private.close()
            
            self._connected = False
            self._markets_loaded = False
            logger.info("OKX disconnected")
            
        except Exception as e:
            logger.error(f"Error disconnecting from OKX: {e}")

    def is_connected(self) -> bool:
        """Check if exchange is connected."""
        return self._connected

    async def load_markets(self) -> Dict[str, Any]:
        """Load exchange markets and trading rules."""
        if not self.rest_public:
            raise RuntimeError("Public REST client not initialized")
        return await self.rest_public.load_markets()

    async def watch_quotes(self, symbols: List[str]) -> AsyncGenerator[Quote, None]:
        """Watch real-time quotes for given symbols."""
        if not self.ws_public:
            raise RuntimeError("Public WebSocket client not initialized")

        try:
            while self._connected:
                for symbol in symbols:
                    try:
                        # Use WebSocket for real-time quotes
                        ticker = await self.ws_public.watch_ticker(symbol)
                        if not ticker or 'bid' not in ticker or 'ask' not in ticker:
                            continue
                        
                        quote = Quote(
                            venue=self.name,
                            symbol=symbol,
                            bid=float(ticker['bid']),
                            ask=float(ticker['ask']),
                            bid_size=float(ticker.get('bidVolume', 0) or 0),
                            ask_size=float(ticker.get('askVolume', 0) or 0),
                            ts_exchange=ticker.get('timestamp', int(time.time() * 1000)),
                            ts_local=int(time.time() * 1000)
                        )
                        
                        self._last_update = quote.ts_local
                        yield quote
                            
                    except Exception as e:
                        logger.warning(f"Error watching quotes for {symbol}: {e}")
                        await asyncio.sleep(1)
                        
                await asyncio.sleep(0.1)  # Small delay between symbol cycles
                
        except Exception as e:
            logger.error(f"Failed to watch quotes: {e}")
            raise

    async def fetch_order_book(self, symbol: str, limit: int = 10) -> Optional[OrderBook]:
        """Fetch order book for a symbol."""
        if not self.rest_public:
            return None
        
        try:
            order_book = await self.rest_public.fetch_order_book(symbol, limit)
            
            return OrderBook(
                venue=self.name,
                symbol=symbol,
                bids=order_book['bids'][:limit],
                asks=order_book['asks'][:limit],
                ts_exchange=order_book['timestamp'],
                ts_local=int(time.time() * 1000)
            )
        except Exception as e:
            logger.error(f"Failed to fetch order book for {symbol}: {e}")
            return None

    async def place_order(self, symbol: str, side: str, order_type: str,
                         amount: float, price: Optional[float] = None,
                         params: Optional[Dict] = None) -> OrderResult:
        """Place an order on OKX."""
        if not self.rest_private:
            return OrderResult(False, error="Private REST client not initialized")
        
        try:
            order_params = {
                'symbol': symbol,
                'type': order_type,
                'side': side,
                'amount': amount,
                'timeInForce': 'IOC',  # Immediate or Cancel
            }
            
            if price:
                order_params['price'] = price
            
            if params:
                order_params.update(params)
            
            result = await self.rest_private.create_order(**order_params)
            
            return OrderResult(
                success=True,
                order_id=result.get('id'),
                filled_qty=float(result.get('filled', 0)),
                avg_price=float(result.get('average', 0)),
                fee_asset=result.get('fee', {}).get('currency', ''),
                fee_amount=float(result.get('fee', {}).get('cost', 0))
            )
            
        except Exception as e:
            logger.error(f"Failed to place order on OKX: {e}")
            return OrderResult(False, error=str(e))

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order."""
        if not self.rest_private:
            return False
        
        try:
            await self.rest_private.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id} on OKX: {e}")
            return False

    async def fetch_balances(self) -> Dict[str, Balance]:
        """Fetch account balances."""
        if not self.rest_private:
            return {}
        
        try:
            balances = await self.rest_private.fetch_balance()
            result = {}
            
            for asset, balance_data in balances['total'].items():
                if float(balance_data) > 0:
                    result[asset] = Balance(
                        asset=asset,
                        free=float(balances['free'].get(asset, 0)),
                        total=float(balance_data),
                        ts=int(time.time() * 1000)
                    )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch balances from OKX: {e}")
            return {}

    async def health_check(self) -> bool:
        """Perform health check."""
        try:
            if not self.rest_public:
                return False
            
            # Simple health check - try to fetch a basic endpoint
            await self.rest_public.fetch_ticker('ETH/USDC')
            return True
            
        except Exception as e:
            logger.warning(f"OKX health check failed: {e}")
            return False

    def get_taker_fee_bps(self) -> float:
        """Get taker fee in basis points."""
        return self.config.get('taker_fee_bps', 10.0)

    def get_maker_fee_bps(self) -> float:
        """Get maker fee in basis points."""
        return self.config.get('maker_fee_bps', 8.0)

