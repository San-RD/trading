"""Binance exchange integration for cross-exchange arbitrage."""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Any, AsyncGenerator
from decimal import Decimal

import ccxt.pro as ccxt

from .base import BaseExchange, Quote, OrderBook, Balance, OrderResult

logger = logging.getLogger(__name__)


class BinanceExchange(BaseExchange):
    """Binance exchange implementation."""

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        
        # Separate clients for public vs private operations
        self.rest_public: Optional[ccxt.binance] = None
        self.ws_public: Optional[ccxt.binance] = None
        self.rest_private: Optional[ccxt.binance] = None
        
        self._connected = False
        self._last_update = 0
        self._markets_loaded = False

    def _init_public_rest(self):
        """Initialize public REST client (no keys)."""
        self.rest_public = ccxt.binance({
            "enableRateLimit": True,
            "timeout": 10000,
            "options": {"defaultType": "spot"},
        })

    def _init_public_ws(self):
        """Initialize public WebSocket client (no keys)."""
        self.ws_public = ccxt.binance({
            "enableRateLimit": True,
            "timeout": 10000,
            "options": {"defaultType": "spot"},
        })

    def _init_private_rest(self):
        """Initialize private REST client (with keys)."""
        acct = self.config["exchanges"]["accounts"]["binance"]
        self.rest_private = ccxt.binance({
            "apiKey": acct["key"],
            "secret": acct["secret"],
            "enableRateLimit": True,
            "timeout": 10000,
            "options": {"defaultType": "spot"},
        })
        
        # Set sandbox mode if configured
        if acct.get("sandbox", False):
            self.rest_private.set_sandbox_mode(True)

    async def connect(self, symbols: list[str]) -> bool:
        """Connect to Binance exchange."""
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
            
            # 4) Load markets on private client for order placement
            await self.rest_private.load_markets()

            # 5) Validate symbols and log filters
            for symbol in symbols:
                if symbol not in self.rest_public.markets:
                    logger.error(f"Binance symbol not found in public markets: {symbol}")
                    return False
                
                # Log symbol filters for precision/rounding
                market = self.rest_public.market(symbol)
                logger.info(f"Binance {symbol} filters:")
                logger.info(f"  LOT_SIZE: stepSize={market.get('precision', {}).get('amount', 'N/A')}, minQty={market.get('limits', {}).get('amount', {}).get('min', 'N/A')}, maxQty={market.get('limits', {}).get('amount', {}).get('max', 'N/A')}")
                logger.info(f"  PRICE_FILTER: tickSize={market.get('precision', {}).get('price', 'N/A')}")
                logger.info(f"  NOTIONAL: min={market.get('limits', {}).get('cost', {}).get('min', 'N/A')}")

            self._connected = True
            self._markets_loaded = True
            logger.info(f"Binance connected with symbols {symbols} (public markets loaded)")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from Binance exchange."""
        try:
            if self.rest_public:
                await self.rest_public.close()
            if self.ws_public:
                await self.ws_public.close()
            if self.rest_private:
                await self.rest_private.close()
            
            self._connected = False
            self._markets_loaded = False
            logger.info("Binance disconnected")
            
        except Exception as e:
            logger.error(f"Error disconnecting from Binance: {e}")

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

        logger.info(f"Starting WebSocket quote monitoring for symbols: {symbols}")
        
        try:
            while self._connected:
                for symbol in symbols:
                    try:
                        logger.debug(f"Attempting to watch ticker for {symbol}")
                        
                        # Use WebSocket for real-time quotes
                        ticker = await self.ws_public.watch_ticker(symbol)
                        
                        logger.debug(f"Received ticker for {symbol}: {ticker}")
                        
                        # Log raw ticker data for debugging
                        logger.info(f"🔍 Raw Binance ticker for {symbol}:")
                        logger.info(f"   Bid: {ticker.get('bid', 'N/A')}")
                        logger.info(f"   Ask: {ticker.get('ask', 'N/A')}")
                        logger.info(f"   Bid size: {ticker.get('bidVolume', 'N/A')}")
                        logger.info(f"   Ask size: {ticker.get('askVolume', 'N/A')}")
                        logger.info(f"   Spread: ${float(ticker.get('ask', 0)) - float(ticker.get('bid', 0)):.2f}")
                        
                        if not ticker or 'bid' not in ticker or 'ask' not in ticker:
                            logger.warning(f"Invalid ticker data for {symbol}: {ticker}")
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
                        
                        logger.info(f"✅ Generated quote for {symbol}: bid={quote.bid}, ask={quote.ask}")
                        
                        self._last_update = quote.ts_local
                        yield quote
                            
                    except Exception as e:
                        logger.error(f"Error watching quotes for {symbol}: {e}")
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
        """Place an order on Binance."""
        if not self.rest_private:
            return OrderResult(False, error="Private REST client not initialized")
        
        try:
            # For market orders with quoteOrderQty, we don't need market info for validation
            # Binance will handle all filter checks automatically
            
            # For market orders, we don't need price precision since we're using quoteOrderQty
            # Price will be determined by market at execution time
            
            # For MARKET orders, use quoteOrderQty (USDC amount)
            # Note: We're using market orders as per config.yaml
            if order_type == 'market':
                # Market orders use quoteOrderQty for the USDC amount
                # IMPORTANT: amount parameter is in base asset (ETH), but quoteOrderQty needs USDC
                if side == 'buy':
                    # For buy orders, convert ETH amount to USDC using current price
                    # We need to estimate the USDC cost for the ETH amount
                    estimated_usdc = amount * 4600  # Approximate ETH price
                    order_params = {
                        'symbol': symbol,
                        'type': 'market',
                        'side': side,
                        'quoteOrderQty': estimated_usdc  # USDC amount
                    }
                    logger.info(f"  Converted {amount} ETH to ~${estimated_usdc:.2f} USDC for quoteOrderQty")
                else:
                    # For sell orders, we need the base asset amount
                    # Binance market sell orders use 'amount' parameter (not 'quantity')
                    order_params = {
                        'symbol': symbol,
                        'type': 'market',
                        'side': side,
                        'amount': amount  # Base asset amount (ETH) - CCXT uses 'amount'
                    }
                    logger.info(f"  Using base asset amount: {amount} ETH for sell order")
            else:  # fallback for other order types
                # Unsupported order type
                return OrderResult(False, error=f"Unsupported order type: {order_type}")
            
            # For market orders, we don't need to validate price/quantity since we're using quoteOrderQty
            # Binance will handle the conversion and apply filters automatically
            if order_type == 'market':
                logger.info(f"Binance market order for {symbol}:")
                logger.info(f"  Quote amount: ${amount} USDC")
                logger.info(f"  Side: {side}")
                logger.info(f"  Order type: {order_type}")
            
            if params:
                order_params.update(params)
            
            logger.info(f"  Sending order to Binance: {order_params}")
            result = await self.rest_private.create_order(**order_params)
            logger.info(f"  Binance response: {result}")
            
            # Validate response structure
            if not result or 'id' not in result:
                logger.error(f"❌ Invalid Binance response: missing order ID")
                return OrderResult(False, error="Invalid response: missing order ID")
            
            order_id = result.get('id')
            if not order_id:
                logger.error(f"❌ Binance order ID is empty")
                return OrderResult(False, error="Empty order ID from Binance")
            
            logger.info(f"✅ Binance order placed successfully: {order_id}")
            
            return OrderResult(
                success=True,
                order_id=order_id,
                filled_qty=float(result.get('filled', 0)),
                avg_price=float(result.get('average', 0)),
                fee_asset=result.get('fee', {}).get('currency', ''),
                fee_amount=float(result.get('fee', {}).get('cost', 0))
            )
            
        except Exception as e:
            logger.error(f"Failed to place order on Binance: {e}")
            return OrderResult(False, error=str(e))

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order."""
        if not self.rest_private:
            return False
        
        try:
            await self.rest_private.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id} on Binance: {e}")
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
            logger.error(f"Failed to fetch balances from Binance: {e}")
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
            logger.warning(f"Binance health check failed: {e}")
            return False

    def get_taker_fee_bps(self) -> float:
        """Get taker fee in basis points."""
        return self.config.get('taker_fee_bps', 10.0)

    def get_maker_fee_bps(self) -> float:
        """Get maker fee in basis points."""
        return self.config.get('maker_fee_bps', 8.0)
    
    def calculate_order_amount(self, symbol: str, notional_usd: float, price: float) -> float:
        """Calculate proper order amount respecting Binance filters."""
        try:
            # Use public client for market info if private not loaded
            if self.rest_private and hasattr(self.rest_private, 'markets') and symbol in self.rest_private.markets:
                market = self.rest_private.market(symbol)
            elif self.rest_public and hasattr(self.rest_public, 'markets') and symbol in self.rest_public.markets:
                market = self.rest_public.market(symbol)
            else:
                logger.warning(f"Markets not loaded for {symbol}, using fallback calculation")
                return notional_usd / price
            
            # Calculate raw amount
            raw_amount = notional_usd / price
            
            # Round to step size - use public client if private not available
            if self.rest_private and hasattr(self.rest_private, 'amount_to_precision'):
                rounded_amount = float(self.rest_private.amount_to_precision(symbol, raw_amount))
            elif self.rest_public and hasattr(self.rest_public, 'amount_to_precision'):
                rounded_amount = float(self.rest_public.amount_to_precision(symbol, raw_amount))
            else:
                logger.warning(f"Precision helpers not available for {symbol}, using raw calculation")
                rounded_amount = raw_amount
            
            # Verify notional after rounding
            actual_notional = rounded_amount * price
            min_notional = market.get('limits', {}).get('cost', {}).get('min', 0)
            
            logger.info(f"Binance amount calculation for {symbol}:")
            logger.info(f"  Target notional: ${notional_usd}")
            logger.info(f"  Price: ${price}")
            logger.info(f"  Raw amount: {raw_amount} ETH")
            logger.info(f"  Rounded amount: {rounded_amount} ETH")
            logger.info(f"  Actual notional: ${actual_notional:.4f}")
            logger.info(f"  Min notional: ${min_notional}")
            
            if actual_notional < min_notional:
                logger.warning(f"Rounded notional ${actual_notional:.4f} below minimum ${min_notional}")
                # Try to bump amount minimally to clear min notional
                min_amount_needed = min_notional / price
                if self.rest_private and hasattr(self.rest_private, 'amount_to_precision'):
                    bumped_amount = float(self.rest_private.amount_to_precision(symbol, min_amount_needed))
                elif self.rest_public and hasattr(self.rest_public, 'amount_to_precision'):
                    bumped_amount = float(self.rest_public.amount_to_precision(symbol, min_amount_needed))
                else:
                    bumped_amount = min_amount_needed
                logger.info(f"Bumped amount to {bumped_amount} ETH to meet minimum notional")
                return bumped_amount
            
            return rounded_amount
            
        except Exception as e:
            logger.error(f"Error calculating order amount: {e}")
            return notional_usd / price  # Fallback to raw calculation
