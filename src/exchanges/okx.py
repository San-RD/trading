"""OKX exchange integration for cross-exchange arbitrage."""

import asyncio
import time
from typing import Dict, List, Optional, Any, AsyncGenerator
from decimal import Decimal

import ccxt.pro as ccxt
from loguru import logger

from .base import BaseExchange, Quote, OrderBook, Balance, OrderResult
from .filters import SymbolRule


class OKXExchange(BaseExchange):
    """OKX exchange implementation."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("okx", config)
        self.rest_client: Optional[ccxt.okx] = None
        self.ws_client: Optional[ccxt.okx] = None
        self.symbol_rules: Dict[str, SymbolRule] = {}
        self._connected = False
        self._last_update = 0
        
        # Initialize clients
        self._init_rest_client()
        self._init_ws_client()

    def _init_rest_client(self):
        """Initialize REST client."""
        try:
            account_config = self.config.exchanges.accounts["okx"]
            self.rest_client = ccxt.okx({
                'apiKey': account_config.key,
                'secret': account_config.secret,
                'password': account_config.password,  # OKX passphrase
                'sandbox': account_config.sandbox,  # Use config setting
                'timeout': 5000,
                'enableRateLimit': True,
            })
            logger.info("OKX REST client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize OKX REST client: {e}")
            self.rest_client = None

    def _init_ws_client(self):
        """Initialize WebSocket client."""
        try:
            account_config = self.config.exchanges.accounts["okx"]
            self.ws_client = ccxt.okx({
                'apiKey': account_config.key,
                'secret': account_config.secret,
                'password': account_config.password,  # OKX passphrase
                'sandbox': account_config.sandbox,  # Use config setting
            })
            logger.info("OKX WebSocket client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize OKX WebSocket client: {e}")
            self.ws_client = None

    async def connect(self) -> None:
        """Connect to OKX."""
        if self._connected:
            return
        
        try:
            if self.rest_client:
                await self.rest_client.load_markets()
                logger.info("OKX REST client connected and markets loaded")
            
            if self.ws_client:
                await self.ws_client.load_markets()
                logger.info("OKX WebSocket client connected and markets loaded")
            
            self._connected = True
        except Exception as e:
            logger.error(f"Failed to connect to OKX: {e}")
            self._connected = False
            raise

    async def disconnect(self) -> None:
        """Disconnect from OKX."""
        try:
            if self.ws_client:
                await self.ws_client.close()
            if self.rest_client:
                await self.rest_client.close()
            
            self._connected = False
            logger.info("Disconnected from OKX")
        except Exception as e:
            logger.error(f"Error during OKX disconnect: {e}")

    async def load_markets(self) -> Dict[str, Any]:
        """Load OKX markets and trading rules."""
        if not self.rest_client:
            raise RuntimeError("REST client not initialized")
        
        try:
            markets = await self.rest_client.load_markets()
            exchange_info = self.rest_client.markets
            
            # Parse symbol rules from markets data
            for symbol, market_info in exchange_info.items():
                # Skip non-spot markets
                if not market_info.get('spot', False):
                    continue
                
                # Create symbol rule with basic info
                rule = SymbolRule(
                    symbol=symbol,
                    base_asset=market_info.get('base', ''),
                    quote_asset=market_info.get('quote', ''),
                    price_precision=market_info.get('precision', {}).get('price', 8),
                    quantity_precision=market_info.get('precision', {}).get('amount', 8),
                    min_qty=float(market_info.get('limits', {}).get('amount', {}).get('min') or '0'),
                    max_qty=float(market_info.get('limits', {}).get('amount', {}).get('max') or '999999'),
                    step_size=float(market_info.get('precision', {}).get('amount') or 0.00000001),
                    min_notional=float(market_info.get('limits', {}).get('cost', {}).get('min') or '0'),
                    max_notional=float(market_info.get('limits', {}).get('cost', {}).get('max') or '999999'),
                    min_price=float(market_info.get('limits', {}).get('price', {}).get('min') or '0'),
                    max_price=float(market_info.get('limits', {}).get('price', {}).get('max') or '999999'),
                    tick_size=float(market_info.get('precision', {}).get('price') or 0.00000001),
                    status='TRADING' if market_info.get('active', False) else 'INACTIVE',
                    is_spot_trading_allowed=market_info.get('spot', False),
                    is_margin_trading_allowed=market_info.get('margin', False),
                )
                
                self.symbol_rules[symbol] = rule
            
            logger.info(f"Loaded {len(self.symbol_rules)} OKX symbol rules")
            return markets
            
        except Exception as e:
            logger.error(f"Failed to load OKX markets and rules: {e}")
            raise

    async def watch_quotes(self, symbols: List[str]) -> AsyncGenerator[Quote, None]:
        """Watch real-time quotes for given symbols."""
        if not self.ws_client:
            raise RuntimeError("WebSocket client not initialized")
        
        try:
            logger.info(f"Starting quote monitoring for {len(symbols)} symbols on OKX")
            
            while self._connected:
                try:
                    # For now, use REST API to simulate real-time updates
                    # In production, use proper WebSocket streams
                    for symbol in symbols:
                        try:
                            ticker = await self.rest_client.fetch_ticker(symbol)
                            
                            # Extract relevant data
                            quote = Quote(
                                venue=self.name,
                                symbol=symbol,
                                bid=float(ticker['bid']),
                                ask=float(ticker['ask']),
                                bid_size=float(ticker.get('bidVolume', 0)),
                                ask_size=float(ticker.get('askVolume', 0)),
                                ts_exchange=ticker['timestamp'],
                                ts_local=int(time.time() * 1000)
                            )
                            
                            self._last_update = quote.ts_local
                            yield quote
                            
                        except Exception as e:
                            logger.error(f"Error fetching ticker for {symbol}: {e}")
                    
                    # Wait before next update
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error in quote monitoring: {e}")
                    await asyncio.sleep(1)
                    
        except Exception as e:
            logger.error(f"Failed to watch quotes: {e}")
            raise

    async def fetch_order_book(self, symbol: str, limit: int = 10) -> Optional[OrderBook]:
        """Fetch order book for a symbol."""
        if not self.rest_client:
            return None
        
        try:
            order_book = await self.rest_client.fetch_order_book(symbol, limit)
            
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
        if not self.rest_client:
            return OrderResult(False, error="REST client not initialized")
        
        try:
            # Validate order parameters
            if symbol not in self.symbol_rules:
                return OrderResult(False, error=f"Symbol {symbol} not found in rules")
            
            rule = self.symbol_rules[symbol]
            
            # Round price and quantity
            if price:
                price = rule.round_price(price)
            amount = rule.round_qty(amount)
            
            # Validate parameters
            is_valid, error_msg = rule.validate_order_params(side, price or 0, amount)
            if not is_valid:
                return OrderResult(False, error=error_msg)
            
            # Prepare order parameters
            order_params = {
                'symbol': symbol,
                'side': side.upper(),
                'type': order_type.upper(),
                'quantity': amount,
            }
            
            if price:
                order_params['price'] = price
            
            if params:
                order_params.update(params)
            
            # Place order
            logger.info(f"Placing OKX order: {order_params}")
            start_time = time.time()
            
            result = await self.rest_client.create_order(**order_params)
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Parse result
            order_id = result.get('id')
            filled_qty = float(result.get('filled', 0))
            avg_price = float(result.get('average', 0))
            fee_asset = result.get('fee', {}).get('currency', '')
            fee_amount = float(result.get('fee', {}).get('cost', 0))
            
            logger.info(f"OKX order placed successfully: {order_id}, filled: {filled_qty}, avg_price: {avg_price}")
            
            return OrderResult(
                success=True,
                order_id=order_id,
                filled_qty=filled_qty,
                avg_price=avg_price,
                fee_asset=fee_asset,
                fee_amount=fee_amount,
                latency_ms=latency_ms
            )
            
        except Exception as e:
            error_msg = f"Failed to place OKX order: {e}"
            logger.error(error_msg)
            return OrderResult(False, error=error_msg)

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order on OKX."""
        if not self.rest_client:
            return False
        
        try:
            await self.rest_client.cancel_order(order_id, symbol)
            logger.info(f"OKX order {order_id} cancelled successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel OKX order {order_id}: {e}")
            return False

    async def fetch_balances(self) -> Dict[str, Balance]:
        """Fetch account balances from OKX."""
        if not self.rest_client:
            raise RuntimeError("REST client not initialized")
        
        try:
            balances_data = await self.rest_client.fetch_balance()
            balances = {}
            
            for asset, balance_info in balances_data['total'].items():
                if float(balance_info) > 0:
                    free = float(balances_data['free'].get(asset, 0))
                    total = float(balance_info)
                    balances[asset] = Balance(
                        asset=asset,
                        free=free,
                        total=total,
                        ts=int(time.time() * 1000)
                    )
            
            logger.info(f"Fetched balances for {len(balances)} assets from OKX")
            return balances
            
        except Exception as e:
            logger.error(f"Failed to fetch OKX balances: {e}")
            raise

    async def health_check(self) -> bool:
        """Perform health check on OKX."""
        try:
            if not self.rest_client:
                return False
            
            # Try to fetch server time
            await self.rest_client.fetch_time()
            return True
        except Exception:
            return False

    def get_symbol_rule(self, symbol: str) -> Optional[SymbolRule]:
        """Get symbol rule for a given symbol."""
        return self.symbol_rules.get(symbol)
