"""Binance exchange integration using ccxt."""

import asyncio
import time
from typing import Dict, List, Optional, Tuple, Any, AsyncGenerator
from decimal import Decimal

import ccxt.pro as ccxt
from loguru import logger

from .filters import SymbolRule
from ..config import get_config


class OrderResult:
    """Result of an order placement."""
    
    def __init__(self, success: bool, order_id: Optional[str] = None, 
                 filled_qty: float = 0.0, avg_price: float = 0.0, 
                 error: Optional[str] = None):
        self.success = success
        self.order_id = order_id
        self.filled_qty = filled_qty
        self.avg_price = avg_price
        self.error = error


class Balance:
    """Account balance for an asset."""
    
    def __init__(self, asset: str, free: float, total: float):
        self.asset = asset
        self.free = free
        self.total = total
    
    def __repr__(self) -> str:
        return f"Balance({self.asset}: free={self.free}, total={self.total})"


class BinanceClient:
    """Binance exchange client using ccxt and ccxt.pro."""
    
    def __init__(self):
        self.config = get_config()
        self.rest_client: Optional[ccxt.binance] = None
        self.ws_client: Optional[ccxt.binance] = None
        self.symbol_rules: Dict[str, SymbolRule] = {}
        self._connected = False
        self._last_ws_update = 0
        
        # Initialize clients
        self._init_rest_client()
        self._init_ws_client()
    
    def _init_rest_client(self):
        """Initialize REST client."""
        try:
            self.rest_client = ccxt.binance({
                'apiKey': self.config.account.api_key,
                'secret': self.config.account.secret,
                'sandbox': False,  # TODO: make configurable
                'timeout': self.config.network_timeout_ms,
                'enableRateLimit': True,
            })
            logger.info("REST client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize REST client: {e}")
            self.rest_client = None
    
    def _init_ws_client(self):
        """Initialize WebSocket client."""
        try:
            self.ws_client = ccxt.binance({
                'apiKey': self.config.account.api_key,
                'secret': self.config.account.secret,
                'sandbox': False,  # TODO: make configurable
                'timeout': self.config.network_timeout_ms,
                'enableRateLimit': True,
            })
            logger.info("WebSocket client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize WebSocket client: {e}")
            self.ws_client = None
    
    async def connect(self):
        """Connect to Binance."""
        if self._connected:
            return
        
        try:
            if self.rest_client:
                # load_markets() is synchronous in regular ccxt
                self.rest_client.load_markets()
                logger.info("REST client connected and markets loaded")
            
            if self.ws_client:
                # load_markets() is synchronous in regular ccxt
                self.ws_client.load_markets()
                logger.info("WebSocket client connected and markets loaded")
            
            self._connected = True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            self._connected = False
            raise
    
    async def disconnect(self):
        """Disconnect from Binance."""
        try:
            if self.ws_client:
                await self.ws_client.close()
            if self.rest_client:
                await self.rest_client.close()
            
            self._connected = False
            logger.info("Disconnected from Binance")
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
    
    async def load_markets_and_rules(self) -> Dict[str, SymbolRule]:
        """Load markets and trading rules."""
        if not self.rest_client:
            raise RuntimeError("REST client not initialized")
        
        try:
            markets = self.rest_client.load_markets()
            # Use the markets data that's already loaded
            exchange_info = self.rest_client.markets
            
            # Parse symbol rules from markets data
            for symbol, market_info in exchange_info.items():
                # Skip non-spot markets
                if not market_info.get('spot', False):
                    continue
                
                # Create symbol rule with basic info
                rule = SymbolRule(symbol, {
                    'baseAsset': market_info.get('base', ''),
                    'quoteAsset': market_info.get('quote', ''),
                    'pricePrecision': market_info.get('precision', {}).get('price', 8),
                    'quantityPrecision': market_info.get('precision', {}).get('amount', 8),
                    'minQty': market_info.get('limits', {}).get('amount', {}).get('min', '0'),
                    'maxQty': market_info.get('limits', {}).get('amount', {}).get('max', '999999'),
                    'stepSize': market_info.get('precision', {}).get('amount', 0.00000001),
                    'minNotional': market_info.get('limits', {}).get('cost', {}).get('min', '0'),
                    'maxNotional': market_info.get('limits', {}).get('cost', {}).get('max', '999999'),
                    'minPrice': market_info.get('limits', {}).get('price', {}).get('min', '0'),
                    'maxPrice': market_info.get('limits', {}).get('price', {}).get('max', '999999'),
                    'tickSize': market_info.get('precision', {}).get('price', 0.00000001),
                    'status': 'TRADING' if market_info.get('active', False) else 'INACTIVE',
                    'isSpotTradingAllowed': market_info.get('spot', False),
                    'isMarginTradingAllowed': market_info.get('margin', False),
                })
                
                self.symbol_rules[symbol] = rule
            
            logger.info(f"Loaded {len(self.symbol_rules)} symbol rules")
            return self.symbol_rules
            
        except Exception as e:
            logger.error(f"Failed to load markets and rules: {e}")
            raise
    
    async def watch_book_tickers(self, pairs: List[str]) -> AsyncGenerator[Dict[str, Any], None]:
        """Watch book tickers for given pairs via WebSocket."""
        if not self.ws_client:
            raise RuntimeError("WebSocket client not initialized")
        
        try:
            logger.info(f"Starting book ticker monitoring for pairs: {pairs}")
            
            while self._connected:
                try:
                    # For now, use REST API to simulate real-time updates
                    # In a production environment, you'd use proper WebSocket streams
                    for pair in pairs:
                        try:
                            ticker = await self.rest_client.fetch_ticker(pair)
                            
                            # Extract relevant data
                            result = {
                                'pair': pair,
                                'bid': float(ticker['bid']),
                                'ask': float(ticker['ask']),
                                'ts': ticker['timestamp'],
                                'bid_volume': float(ticker.get('bidVolume', 0)),
                                'ask_volume': float(ticker.get('askVolume', 0)),
                            }
                            
                            self._last_ws_update = time.time()
                            yield result
                            
                        except Exception as e:
                            logger.error(f"Error fetching ticker for {pair}: {e}")
                    
                    # Wait before next update
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error in book ticker monitoring: {e}")
                    await asyncio.sleep(1)
                    
        except Exception as e:
            logger.error(f"Failed to watch book tickers: {e}")
            raise
    
    async def place_order(self, pair: str, side: str, order_type: str, 
                         amount: float, price: Optional[float] = None, 
                         params: Optional[Dict] = None) -> OrderResult:
        """Place an order on Binance."""
        if not self.rest_client:
            return OrderResult(False, error="REST client not initialized")
        
        try:
            # Validate order parameters
            if pair not in self.symbol_rules:
                return OrderResult(False, error=f"Symbol {pair} not found in rules")
            
            rule = self.symbol_rules[pair]
            
            # Round price and quantity
            from .filters import round_price, round_qty
            if price:
                price = float(round_price(rule, price))
            amount = float(round_qty(rule, amount))
            
            # Validate parameters
            is_valid, error_msg = rule.validate_order_params(side, price or 0, amount)
            if not is_valid:
                return OrderResult(False, error=error_msg)
            
            # Prepare order parameters
            order_params = {
                'symbol': pair,
                'side': side.upper(),
                'type': order_type.upper(),
                'quantity': amount,
            }
            
            if price:
                order_params['price'] = price
            
            if params:
                order_params.update(params)
            
            # Place order
            logger.info(f"Placing order: {order_params}")
            result = await self.rest_client.create_order(**order_params)
            
            # Parse result
            order_id = result.get('id')
            filled_qty = float(result.get('filled', 0))
            avg_price = float(result.get('average', 0))
            
            logger.info(f"Order placed successfully: {order_id}, filled: {filled_qty}, avg_price: {avg_price}")
            
            return OrderResult(
                success=True,
                order_id=order_id,
                filled_qty=filled_qty,
                avg_price=avg_price
            )
            
        except Exception as e:
            error_msg = f"Failed to place order: {e}"
            logger.error(error_msg)
            return OrderResult(False, error=error_msg)
    
    async def fetch_balances(self) -> Dict[str, Balance]:
        """Fetch account balances."""
        if not self.rest_client:
            raise RuntimeError("REST client not initialized")
        
        try:
            balances_data = await self.rest_client.fetch_balance()
            balances = {}
            
            for asset, balance_info in balances_data['total'].items():
                if float(balance_info) > 0:
                    free = float(balances_data['free'].get(asset, 0))
                    total = float(balance_info)
                    balances[asset] = Balance(asset, free, total)
            
            logger.info(f"Fetched balances for {len(balances)} assets")
            return balances
            
        except Exception as e:
            logger.error(f"Failed to fetch balances: {e}")
            raise
    
    async def fetch_order_book(self, symbol: str, limit: int = 10) -> Optional[Dict[str, Any]]:
        """Fetch order book for a symbol."""
        if not self.rest_client:
            return None
        
        try:
            order_book = await self.rest_client.fetch_order_book(symbol, limit)
            return order_book
        except Exception as e:
            logger.error(f"Failed to fetch order book for {symbol}: {e}")
            return None
    
    def get_symbol_rule(self, symbol: str) -> Optional[SymbolRule]:
        """Get symbol rule for a given symbol."""
        return self.symbol_rules.get(symbol)
    
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected
    
    def get_last_ws_update(self) -> float:
        """Get timestamp of last WebSocket update."""
        return self._last_ws_update
    
    async def health_check(self) -> bool:
        """Perform health check."""
        try:
            if not self.rest_client:
                return False
            
            # Try to fetch server time
            await self.rest_client.fetch_time()
            return True
        except Exception:
            return False
