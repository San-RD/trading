#!/usr/bin/env python3
"""Kraken exchange integration for cross-exchange arbitrage using krakenex API."""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Any, AsyncGenerator
from decimal import Decimal

# Kraken API
import krakenex
from pykrakenapi import KrakenAPI

from .base import BaseExchange, Quote, OrderBook, Balance, OrderResult

logger = logging.getLogger(__name__)


class KrakenExchange(BaseExchange):
    """Kraken exchange implementation using krakenex API."""

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        
        # Get Kraken account configuration
        acct = self.config["exchanges"]["accounts"]["kraken"]
        
        # Initialize Kraken API
        self.api = krakenex.API(
            key=acct["key"],
            secret=acct["secret"]
        )
        
        # Initialize KrakenAPI wrapper for easier data access
        self.kraken_api = KrakenAPI(self.api)
        
        # Set trading mode
        self.sandbox = acct.get("sandbox", False)
        if self.sandbox:
            logger.info("Using Kraken sandbox mode")
            # Note: Kraken sandbox is limited, may need to use testnet
        
        self._connected = False
        self._last_update = 0
        self._markets_loaded = False

    async def connect(self, symbols: list[str]) -> bool:
        """Connect to Kraken exchange."""
        try:
            logger.info("🔍 Kraken connecting using krakenex API...")
            
            # Test connection by getting server time
            try:
                server_time = self.api.query_public('Time')
                if server_time['error']:
                    logger.error(f"Kraken server time error: {server_time['error']}")
                    return False
                logger.info(f"✅ Kraken server time: {server_time['result']}")
            except Exception as e:
                logger.error(f"Failed to get Kraken server time: {e}")
                return False
            
            # Test account access
            try:
                account_balance = self.api.query_private('Balance')
                if account_balance['error']:
                    logger.error(f"Kraken balance error: {account_balance['error']}")
                    return False
                logger.info("✅ Kraken account access verified")
            except Exception as e:
                logger.error(f"Failed to access Kraken account: {e}")
                return False
            
            # Validate symbols
            for symbol in symbols:
                try:
                    # Convert CCXT format to Kraken format
                    kraken_symbol = self._convert_symbol_format(symbol)
                    
                    # Test if symbol exists by getting ticker
                    ticker_result = self.api.query_public('Ticker', {'pair': kraken_symbol})
                    if ticker_result['error']:
                        logger.warning(f"Kraken symbol not found: {symbol} -> {kraken_symbol}, but continuing...")
                        continue
                    logger.info(f"✅ Kraken symbol validated: {symbol} -> {kraken_symbol}")
                except Exception as e:
                    logger.warning(f"Failed to validate Kraken symbol {symbol}: {e}, but continuing...")
                    continue
            
            self._connected = True
            self._markets_loaded = True
            
            # Log connection details
            mode = "SANDBOX" if self.sandbox else "LIVE"
            logger.info(f"✅ Kraken connected with symbols {symbols} in {mode} mode")
            logger.info(f"  Using krakenex API")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Kraken: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from Kraken exchange."""
        try:
            self._connected = False
            self._markets_loaded = False
            logger.info("Kraken disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting from Kraken: {e}")

    def is_connected(self) -> bool:
        """Check if exchange is connected."""
        return self._connected

    async def load_markets(self) -> Dict[str, Any]:
        """Load exchange markets and trading rules."""
        try:
            # Get asset pairs info
            pairs_info = self.api.query_public('AssetPairs')
            if pairs_info['error']:
                logger.error(f"Failed to get Kraken asset pairs: {pairs_info['error']}")
                return {}
            
            markets = {}
            pairs_data = pairs_info['result']
            
            # Load ALL active pairs, not just USDC
            for pair_name, pair_data in pairs_data.items():
                if pair_data.get('status') == 'online':
                    # Convert Kraken asset names to standard format
                    base_asset = pair_data['base']
                    quote_asset = pair_data['quote']
                    
                    # Remove Kraken prefixes: X for crypto, Z for fiat
                    if base_asset.startswith('X'):
                        base_asset = base_asset[1:]  # XETH -> ETH
                    if quote_asset.startswith('Z'):
                        quote_asset = quote_asset[1:]  # ZUSD -> USD
                    
                    # Convert to CCXT format
                    ccxt_symbol = f"{base_asset}/{quote_asset}"
                    
                    markets[ccxt_symbol] = {
                        'id': pair_name,
                        'symbol': ccxt_symbol,
                        'base': base_asset,
                        'quote': quote_asset,
                        'active': True,
                        'precision': {
                            'amount': int(pair_data.get('lot_decimals', 8)),
                            'price': int(pair_data.get('pair_decimals', 8))
                        },
                        'limits': {
                            'amount': {
                                'min': float(pair_data.get('lot_min', 0)),
                                'max': None
                            },
                            'price': {
                                'min': float(pair_data.get('tick_size', 0.01)),
                                'max': None
                            }
                        }
                    }
            
            logger.info(f"Kraken markets loaded: {len(markets)} pairs")
            return markets
            
        except Exception as e:
            logger.error(f"Failed to load Kraken markets: {e}")
            return {}

    async def watch_quotes(self, symbols: List[str]) -> AsyncGenerator[Quote, None]:
        """Watch real-time quotes using Kraken WebSocket v2 API."""
        import websockets
        import json
        
        try:
            # WebSocket v2 endpoint
            ws_url = "wss://ws.kraken.com/v2"
            
            async with websockets.connect(ws_url) as websocket:
                self._ws_connected = True
                logger.info(f"Connected to Kraken WebSocket v2")
                
                # Subscribe to ticker feeds for all symbols
                for symbol in symbols:
                    # For WebSocket v2, use the symbol directly as documented
                    # Documentation shows: "symbol": ["ALGO/USD"] format
                    logger.info(f"🔍 Subscribing to symbol: {symbol}")
                    
                    # WebSocket v2 subscription message
                    subscribe_msg = {
                        "method": "subscribe",
                        "params": {
                            "channel": "ticker",
                            "symbol": [symbol],  # Use symbol directly: ["ETH/USDC"]
                            "snapshot": True,   # Request initial snapshot
                            "event_trigger": "bbo"  # Update on best bid/offer changes
                        }
                    }
                    
                    logger.info(f"📡 Sending subscription: {subscribe_msg}")
                    await websocket.send(json.dumps(subscribe_msg))
                    logger.info(f"✅ Subscribed to {symbol} ticker feed")
                
                # Listen for incoming messages
                while self._connected:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                        data = json.loads(message)
                        
                        # Debug: Log all incoming messages
                        logger.debug(f"Kraken WebSocket message: {data}")
                        
                        # Handle different message types
                        if 'channel' in data and data['channel'] == 'ticker':
                            ticker_data = data.get('data', [])
                            
                            if ticker_data and len(ticker_data) > 0:
                                # Extract ticker data from the documented format
                                ticker = ticker_data[0]  # First element contains the ticker
                                
                                # Extract bid/ask from documented format
                                bid = float(ticker.get('bid', 0))
                                ask = float(ticker.get('ask', 0))

                                symbol = ticker.get('symbol', '')
                                
                                if bid > 0 and ask > 0 and symbol:
                                    quote = Quote(
                                        symbol=symbol,
                                        bid=bid,
                                        ask=ask,
                                        last=ask,
                                        ts_exchange=int(time.time() * 1000)
                                    )
                                    
                                    self._last_update = quote.ts_exchange
                                    yield quote
                        
                        elif 'method' in data and data['method'] == 'pong':
                            # Handle ping/pong for connection health
                            continue
                            
                        elif 'error' in data:
                            logger.warning(f"Kraken WebSocket error: {data['error']}")
                            
                        elif 'method' in data and data['method'] == 'subscribe':
                            # Handle subscription confirmation
                            if data.get('success'):
                                logger.info(f"✅ Kraken WebSocket subscription successful: {data.get('result', {}).get('symbol', 'unknown')}")
                            else:
                                logger.error(f"❌ Kraken WebSocket subscription failed: {data.get('error', 'unknown error')}")
                            
                        elif 'method' in data and data['method'] == 'unsubscribe':
                            # Handle unsubscription confirmation
                            logger.info(f"Kraken WebSocket unsubscription confirmed: {data}")
                            
                    except asyncio.TimeoutError:
                        # Send ping to keep connection alive
                        ping_msg = {"method": "ping"}
                        await websocket.send(json.dumps(ping_msg))
                        continue
                        
                    except Exception as e:
                        logger.error(f"Error processing WebSocket message: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Kraken WebSocket connection failed: {e}")
            self._ws_connected = False
            # Fallback to REST API if WebSocket fails
            logger.info("Falling back to REST API polling")
            async for quote in self._fallback_rest_quotes(symbols):
                yield quote

    async def _fallback_rest_quotes(self, symbols: List[str]) -> AsyncGenerator[Quote, None]:
        """Fallback REST API polling if WebSocket fails."""
        try:
            while self._connected:
                for symbol in symbols:
                    try:
                        # Convert symbol format
                        kraken_symbol = self._convert_symbol_format(symbol)
                        
                        # Get ticker data
                        ticker_result = self.api.query_public('Ticker', {'pair': kraken_symbol})
                        
                        if not ticker_result['error']:
                            ticker_data = ticker_result['result'][kraken_symbol]
                            
                            # Extract bid/ask from Kraken ticker format
                            bid = float(ticker_data.get('b', [0])[0])
                            ask = float(ticker_data.get('a', [0])[0])

                            
                            if bid > 0 and ask > 0:
                                quote = Quote(
                                    symbol=symbol,
                                    bid=bid,
                                    ask=ask,
                                    last=ask,
                                    ts_exchange=int(time.time() * 1000)
                                )
                                
                                self._last_update = quote.ts_exchange
                                yield quote
                            
                    except Exception as e:
                        logger.warning(f"Error getting ticker for {symbol}: {e}")
                        await asyncio.sleep(1)
                        
                await asyncio.sleep(1)  # Poll every second
                
        except Exception as e:
            logger.error(f"Failed to watch quotes: {e}")
            raise

    async def fetch_order_book(self, symbol: str, limit: int = 10) -> Optional[OrderBook]:
        """Fetch order book for a symbol."""
        try:
            # Convert symbol format
            kraken_symbol = self._convert_symbol_format(symbol)
            
            # Get order book
            order_book_result = self.api.query_public('Depth', {
                'pair': kraken_symbol,
                'count': limit
            })
            
            if not order_book_result['error']:
                order_book_data = order_book_result['result'][kraken_symbol]
                
                # Extract bids and asks
                bids = []
                asks = []
                
                for bid in order_book_data.get('bids', [])[:limit]:
                    if len(bid) >= 2:
                        bids.append([float(bid[0]), float(bid[1])])
                
                for ask in order_book_data.get('asks', [])[:limit]:
                    if len(ask) >= 2:
                        asks.append([float(ask[0]), float(ask[1])])
                
                return OrderBook(
                    symbol=symbol,
                    bids=bids,
                    asks=asks,
                    ts_exchange=int(time.time() * 1000)
                )
            else:
                logger.error(f"Failed to fetch order book for {symbol}: {order_book_result['error']}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to fetch order book for {symbol}: {e}")
            return None

    async def place_order(self, symbol: str, side: str, order_type: str,
                         amount: float, price: Optional[float] = None,
                         params: Optional[Dict] = None) -> OrderResult:
        """Place an order on Kraken."""
        try:
            logger.info(f"🔍 Kraken place_order called: {symbol} {side} {amount} {order_type}")
            
            # Convert symbol format
            kraken_symbol = self._convert_symbol_format(symbol)
            logger.info(f"  Converted symbol: {symbol} -> {kraken_symbol}")
            
            # Convert order type
            if order_type == 'market':
                kraken_order_type = 'market'
            elif order_type == 'limit':
                kraken_order_type = 'limit'
            else:
                kraken_order_type = order_type
            
            # Convert side
            if side == 'buy':
                kraken_side = 'buy'
            elif side == 'sell':
                kraken_side = 'sell'
            else:
                kraken_side = side
            
            # Prepare order data
            # Round amount to meet Kraken's lot precision requirements (8 decimal places)
            rounded_amount = round(amount, 8)
            order_data = {
                'pair': kraken_symbol,
                'type': kraken_side,
                'ordertype': kraken_order_type,
                'volume': str(rounded_amount)
            }
            logger.info(f"  Amount rounded: {amount} -> {rounded_amount}")
            
            # Add price for limit orders
            if price and kraken_order_type == 'limit':
                # Round price to meet Kraken's tick size requirements
                # Kraken ETH/USDC has tick_size: 0.01, so round to 2 decimal places
                rounded_price = round(price, 2)
                order_data['price'] = str(rounded_price)
                logger.info(f"  Price rounded: {price} -> {rounded_price}")
            
            # Add any additional parameters
            if params:
                order_data.update(params)
            
            logger.info(f"🔍 Kraken place_order:")
            logger.info(f"  Symbol: {kraken_symbol}")
            logger.info(f"  Order data: {order_data}")
            
            # Place order
            logger.info(f"  📡 Sending order to Kraken API...")
            result = self.api.query_private('AddOrder', order_data)
            
            logger.info(f"Kraken API response: {result}")
            
            # Validate response structure
            if not isinstance(result, dict):
                error_msg = f"Invalid response type: {type(result)}, expected dict"
                logger.error(f"❌ {error_msg}")
                return OrderResult(False, error=error_msg)
            
            if 'error' not in result:
                error_msg = f"Missing 'error' field in response: {result}"
                logger.error(f"❌ {error_msg}")
                return OrderResult(False, error=error_msg)
            
            if result['error']:
                # Error from Kraken
                error_msg = str(result['error'])
                logger.error(f"❌ Kraken API error: {error_msg}")
                return OrderResult(False, error=error_msg)
            
            # Check for result field
            if 'result' not in result:
                error_msg = f"Missing 'result' field in response: {result}"
                logger.error(f"❌ {error_msg}")
                return OrderResult(False, error=error_msg)
            
            order_info = result['result']
            logger.info(f"  Order info: {order_info}")
            
            # Validate order_info structure
            if not isinstance(order_info, dict):
                error_msg = f"Invalid order_info type: {type(order_info)}, expected dict"
                logger.error(f"❌ {error_msg}")
                return OrderResult(False, error=error_msg)
            
            # Get order ID
            if 'txid' not in order_info:
                error_msg = f"Missing 'txid' field in order_info: {order_info}"
                logger.error(f"❌ {error_msg}")
                return OrderResult(False, error=error_msg)
            
            txid = order_info['txid']
            if not isinstance(txid, list) or len(txid) == 0:
                error_msg = f"Invalid 'txid' format: {txid}, expected non-empty list"
                logger.error(f"❌ {error_msg}")
                return OrderResult(False, error=error_msg)
            
            order_id = txid[0]
            if not order_id:
                error_msg = f"Empty order ID in txid: {txid}"
                logger.error(f"❌ {error_msg}")
                return OrderResult(False, error=error_msg)
            
            logger.info(f"✅ Kraken order placed successfully: {order_id}")
            
            return OrderResult(
                success=True,
                order_id=order_id,
                filled_qty=amount,
                avg_price=price or 0.0,
                fee_asset='',
                fee_amount=0.0
            )
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Exception in Kraken place_order: {error_msg}")
            import traceback
            logger.error(f"  Traceback: {traceback.format_exc()}")
            return OrderResult(False, error=error_msg)

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order."""
        try:
            # Cancel order
            result = self.api.query_private('CancelOrder', {'txid': order_id})
            
            if not result['error']:
                return True
            else:
                logger.error(f"Failed to cancel order {order_id} on Kraken: {result['error']}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id} on Kraken: {e}")
            return False

    async def fetch_balances(self) -> Dict[str, Balance]:
        """Fetch account balances."""
        try:
            # Get account balance
            result = self.api.query_private('Balance')
            
            if not result['error']:
                balances = {}
                balance_data = result['result']
                
                for asset, amount in balance_data.items():
                    total = float(amount)
                    if total > 0:
                        # Normalize asset names by removing Kraken prefixes
                        normalized_asset = asset
                        if asset.startswith('X'):
                            normalized_asset = asset[1:]  # XETH -> ETH
                        elif asset.startswith('Z'):
                            normalized_asset = asset[1:]  # ZUSD -> USD
                        
                        balances[normalized_asset] = Balance(
                            asset=normalized_asset,
                            free=total,
                            total=total,
                            ts=int(time.time() * 1000)
                        )
                        
                        # Log the normalization for debugging
                        if asset != normalized_asset:
                            logger.debug(f"Balance asset normalized: {asset} -> {normalized_asset}")
                
                logger.info(f"Kraken balances loaded: {list(balances.keys())}")
                return balances
            else:
                logger.error(f"Kraken balance API error: {result['error']}")
                return {}
            
        except Exception as e:
            logger.error(f"Failed to fetch balances from Kraken: {e}")
            return {}

    async def check_account_config(self) -> Dict[str, Any]:
        """Check account configuration."""
        try:
            # Get account balance as a simple check
            balance = self.api.query_private('Balance')
            return {
                'balance_accessible': not bool(balance['error']),
                'balance_count': len(balance.get('result', {})) if not balance['error'] else 0
            }
        except Exception as e:
            logger.error(f"Failed to get Kraken account config: {e}")
            return {"error": str(e)}

    async def health_check(self) -> bool:
        """Perform health check."""
        try:
            # Check if we can get a simple ticker
            test_symbol = "ETH/USDC"
            kraken_symbol = self._convert_symbol_format(test_symbol)
            
            result = self.api.query_public('Ticker', {'pair': kraken_symbol})
            if not result['error']:
                return True
            else:
                logger.warning(f"Kraken health check failed: {result['error']}")
                return False
                
        except Exception as e:
            logger.error(f"Kraken health check error: {e}")
            return False

    def get_taker_fee_bps(self) -> float:
        """Get taker fee in basis points."""
        return self.config.get('taker_fee_bps', 26.0)  # Kraken default: 0.26%

    def get_maker_fee_bps(self) -> float:
        """Get maker fee in basis points."""
        return self.config.get('maker_fee_bps', 16.0)  # Kraken default: 0.16%

    def _convert_symbol_format(self, ccxt_symbol: str) -> str:
        """Convert CCXT symbol format to Kraken format."""
        # CCXT: ETH/USDC -> Kraken: ETHUSDC
        return ccxt_symbol.replace('/', '')

    def _get_websocket_symbol(self, ccxt_symbol: str) -> Optional[str]:
        """Get Kraken's internal WebSocket symbol format."""
        try:
            # Load markets if not already loaded
            if not hasattr(self, '_websocket_symbols'):
                self._websocket_symbols = {}
                
                # Get asset pairs info for WebSocket symbols
                pairs_info = self.api.query_public('AssetPairs')
                if not pairs_info['error']:
                    logger.info(f"🔍 Loading Kraken asset pairs for WebSocket...")
                    for pair_name, pair_data in pairs_info['result'].items():
                        if pair_data.get('status') == 'online':
                            # Convert to CCXT format for matching
                            base_asset = pair_data['base']
                            quote_asset = pair_data['quote']
                            
                            # Remove Kraken prefixes for matching
                            clean_base = base_asset[1:] if base_asset.startswith('X') else base_asset
                            clean_quote = quote_asset[1:] if quote_asset.startswith('Z') else quote_asset
                            
                            ccxt_format = f"{clean_base}/{clean_quote}"
                            self._websocket_symbols[ccxt_format] = pair_name
                            
                            # Debug: Log some key pairs
                            if ccxt_format in ['ETH/USDC', 'ETH/USDT', 'BTC/USD']:
                                logger.info(f"  📊 {ccxt_format} -> {pair_name} (base: {base_asset}, quote: {quote_asset})")
                    
                    logger.info(f"✅ Loaded {len(self._websocket_symbols)} WebSocket symbols")
                else:
                    logger.error(f"Failed to get asset pairs: {pairs_info['error']}")
            
            # Return the internal Kraken symbol
            result = self._websocket_symbols.get(ccxt_symbol)
            logger.info(f"🔍 WebSocket symbol lookup: {ccxt_symbol} -> {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to get WebSocket symbol for {ccxt_symbol}: {e}")
            return None

    def is_websocket_connected(self) -> bool:
        """Check if WebSocket connection is active."""
        return hasattr(self, '_ws_connected') and self._ws_connected

    def get_connection_status(self) -> Dict[str, Any]:
        """Get detailed connection status."""
        return {
            'name': self.name,
            'connected': self._connected,
            'websocket_active': self.is_websocket_connected(),
            'last_update': self._last_update,
            'last_update_age_ms': int(time.time() * 1000) - self._last_update if self._last_update > 0 else 0
        }

    def get_last_update(self) -> int:
        """Get timestamp of last update."""
        return self._last_update

    def is_connected(self) -> bool:
        """Check if exchange is connected."""
        return self._connected
