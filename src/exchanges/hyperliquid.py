"""Hyperliquid exchange integration using official Python SDK"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any, AsyncGenerator
from decimal import Decimal
import aiohttp
import websockets
from loguru import logger

from .base import BaseExchange, Quote, OrderBook, OrderType, OrderSide, Balance, OrderResult

from hyperliquid.exchange import Exchange as Hyperliquid
from hyperliquid.exchange import OrderRequest, CancelRequest
from eth_account import Account
HYPERLIQUID_SDK_AVAILABLE = True


class HyperliquidExchange(BaseExchange):
    """Hyperliquid exchange adapter using official Python SDK"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        
        # Asset mapping (ETH=0, BTC=1)
        self.asset_map = {
            'ETH': 0,
            'BTC': 1
        }
        
        # WebSocket connection
        self.ws = None
        self.ws_connected = False
        self.quotes = {}
        self.orderbooks = {}
        
        # Nonce management
        self.last_nonce = int(time.time() * 1000)
        
        # Initialize Hyperliquid SDK
        try:
            # Extract wallet address and private key from config
            wallet_address = config.get('hyperliquid', {}).get('wallet_address')
            private_key = config.get('hyperliquid', {}).get('private_key')
            
            if not wallet_address or not private_key:
                raise ValueError("Hyperliquid wallet_address and private_key must be provided in config")
            
            logger.info(f"🔑 Initializing Hyperliquid SDK with wallet: {wallet_address[:10]}...")
            
            # Create LocalAccount from private key
            wallet = Account.from_key(private_key)
            
            self.hyperliquid = Hyperliquid(
                wallet=wallet,
                base_url="https://api.hyperliquid.xyz"  # Mainnet API
            )
            logger.info(f"✅ Hyperliquid SDK initialized for wallet: {wallet.address}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Hyperliquid SDK: {e}")
            raise
        
    async def connect(self, symbols: List[str] = None) -> bool:
        """Connect to Hyperliquid WebSocket"""
        try:
            # Test REST API connection first
            await self._test_rest_connection()
            
            # Connect WebSocket
            await self._connect_websocket()
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Hyperliquid: {e}")
            return False
            
    async def _test_rest_connection(self):
        """Test REST API connection"""
        try:
            # Get meta info to test connection
            meta_response = await self._make_rest_request(
                "https://api.hyperliquid.xyz/info",
                {"type": "meta"}
            )
            
            if meta_response and 'universe' in meta_response:
                logger.info(f"✅ REST API connected - found {len(meta_response['universe'])} assets")
                # Update asset mapping from response
                for i, asset in enumerate(meta_response['universe']):
                    if asset['name'] in ['ETH', 'BTC']:
                        self.asset_map[asset['name']] = i
                logger.info(f"📊 Asset mapping: {self.asset_map}")
            else:
                logger.warning("⚠️ REST API response missing universe data")
                
        except Exception as e:
            logger.error(f"❌ REST API test failed: {e}")
            raise
            
    async def _make_rest_request(self, url: str, data: Dict) -> Optional[Dict]:
        """Make REST API request"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"❌ REST API error {response.status}: {await response.text()}")
                        return None
        except Exception as e:
            logger.error(f"❌ REST request failed: {e}")
            return None
            
    async def _connect_websocket(self):
        """Connect to Hyperliquid WebSocket"""
        try:
            self.ws = await websockets.connect(
                "wss://api.hyperliquid.xyz/ws",
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5
            )
            self.ws_connected = True
            logger.info("✅ WebSocket connected to Hyperliquid")
            
        except Exception as e:
            logger.error(f"❌ WebSocket connection failed: {e}")
            raise
            
    async def start_subscriptions(self, symbols: List[str] = None):
        """Start WebSocket subscriptions for specific symbols"""
            
        if not self.ws_connected:
            logger.warning("⚠️ WebSocket not connected - skipping subscriptions")
            return
            
        try:
            # If no symbols specified, subscribe to all supported assets
            if not symbols:
                symbols = ['ETH', 'BTC']
            
            # Subscribe to orderbook updates for specified symbols only
            for symbol in symbols:
                if symbol in self.asset_map:
                    asset_id = self.asset_map[symbol]
                    # Use the correct WebSocket subscription format
                    subscribe_msg = {
                        "method": "subscribe",
                        "subscription": {
                            "type": "l2Book",
                            "coin": symbol
                        }
                    }
                    await self.ws.send(json.dumps(subscribe_msg))
                    logger.info(f"📡 Subscribed to {symbol} orderbook (Asset ID: {asset_id})")
                    
            # Subscribe to all mids for price updates (needed for all strategies)
            mids_msg = {
                "method": "subscribe",
                "subscription": {
                    "type": "allMids"
                }
            }
            await self.ws.send(json.dumps(mids_msg))
            logger.info("📡 Subscribed to all mids")
            
            # Wait for subscriptions to process
            await asyncio.sleep(0.5)
            
            # Start WebSocket listener task
            asyncio.create_task(self._websocket_listener())
            logger.info("🎧 WebSocket listener task started")
            
        except Exception as e:
            logger.error(f"❌ Failed to start subscriptions: {e}")
            
    async def fetch_initial_quotes(self, symbols: List[str]) -> None:
        """Fetch initial quotes from REST API as fallback"""
            
        try:
            logger.info(f"📡 Fetching initial quotes for {symbols}")
            
            for symbol in symbols:
                if symbol.endswith('-PERP'):
                    clean_symbol = symbol.replace('-PERP', '')
                    if clean_symbol in self.asset_map:
                        # Try to get orderbook for this coin
                        orderbook_payload = {
                            "type": "orderBook",
                            "coin": clean_symbol
                        }
                        
                        orderbook_response = await self._make_rest_request(
                            "https://api.hyperliquid.xyz/info",
                            orderbook_payload
                        )
                        
                        if orderbook_response and 'data' in orderbook_response:
                            data = orderbook_response['data']
                            if 'bids' in data and 'asks' in data:
                                bids = data['bids']
                                asks = data['asks']
                                
                                if bids and asks:
                                    best_bid = float(bids[0][0])
                                    best_ask = float(bids[0][1])
                                    
                                    # Create quote
                                    quote = Quote(
                                        symbol=symbol,
                                        bid=best_bid,
                                        ask=best_ask,
                                        last=best_ask,  # Use ask as last price
                                        ts_exchange=int(time.time() * 1000)
                                    )
                                    self.quotes[clean_symbol] = quote
                                    
                                    logger.info(f"✅ Initial quote for {symbol}: bid=${best_bid:.4f} ask=${best_ask:.4f}")
                                    
        except Exception as e:
            logger.error(f"❌ Error fetching initial quotes: {e}")
            
    async def watch_quotes(self, symbols: List[str]) -> AsyncGenerator[Quote, None]:
        """Watch for quote updates via WebSocket"""
        # Wait for WebSocket to be ready
        while not self.ws_connected:
            await asyncio.sleep(0.1)
            
        if not self.ws_connected:
            return
            
        try:
            logger.info(f"🔄 Starting quote monitoring for symbols: {symbols}")
            last_quote_time = {}
            
            while self.ws_connected:
                for symbol in symbols:
                    # Clean symbol (remove -PERP suffix)
                    clean_symbol = symbol.replace('-PERP', '')
                    
                    if clean_symbol not in self.asset_map:
                        logger.warning(f"⚠️ Unknown symbol: {symbol}")
                        continue
                        
                    # Check if we have recent quotes
                    if clean_symbol in self.quotes:
                        quote = self.quotes[clean_symbol]
                        current_time = time.time()
                        quote_time = quote.ts_exchange / 1000
                        age_seconds = current_time - quote_time
                        
                        # Return quote if it's fresh (less than 2 seconds old) or if we haven't seen it recently
                        if age_seconds < 2.0:
                            # Only yield if we haven't seen this quote recently (to avoid spam)
                            last_seen = last_quote_time.get(clean_symbol, 0)
                            if current_time - last_seen >= 1.0:  # Log at most once per second
                                logger.info(f"📊 HL {clean_symbol}-PERP: bid=${quote.bid:.4f} ask=${quote.ask:.4f} (age: {age_seconds:.1f}s)")
                                last_quote_time[clean_symbol] = current_time
                            yield quote
                        else:
                            logger.debug(f"⚠️ Quote for {clean_symbol} is stale: {age_seconds:.1f}s old")
                            
                # Wait for new data
                await asyncio.sleep(0.5)  # Check every 500ms
                
        except Exception as e:
            logger.error(f"❌ Error watching quotes: {e}")
            
    async def fetch_order_book(self, symbol: str, limit: int = 10) -> Optional[OrderBook]:
        """Fetch orderbook for a symbol"""

            
        if not self.ws_connected:
            return None
            
        try:
            # Clean symbol (remove -PERP suffix)
            clean_symbol = symbol.replace('-PERP', '')
            
            if clean_symbol not in self.asset_map:
                logger.warning(f"⚠️ Unknown symbol: {symbol}")
                return None
                
            # Check if we have recent orderbook
            if clean_symbol in self.orderbooks:
                orderbook = self.orderbooks[clean_symbol]
                # Return orderbook if it's fresh (less than 1 second old)
                # orderbook.ts_exchange is in milliseconds, time.time() is in seconds
                if time.time() - (orderbook.ts_exchange / 1000) < 1.0:
                    return orderbook
                    
            # Wait for new data
            await asyncio.sleep(0.1)
            return None
            
        except Exception as e:
            logger.error(f"❌ Error fetching orderbook for {symbol}: {e}")
            return None
            
    async def _websocket_listener(self):
        """WebSocket message listener"""
        if not self.ws_connected:
            return
            
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    await self._handle_websocket_message(data)
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Invalid JSON message: {message}")
                except Exception as e:
                    logger.error(f"❌ Error handling WebSocket message: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("⚠️ WebSocket connection closed")
            self.ws_connected = False
        except Exception as e:
            logger.error(f"❌ WebSocket listener error: {e}")
            
    async def _handle_websocket_message(self, data: Dict):
        """Handle WebSocket message"""
        try:
            # Check for subscription confirmation
            if 'channel' in data and data['channel'] == 'subscribed':
                logger.info(f"✅ WebSocket subscription confirmed")
                return
                
            # Check for error messages
            if 'channel' in data and data['channel'] == 'error':
                logger.error(f"❌ WebSocket error: {data}")
                return
                
            # Handle data messages based on channel
            channel = data.get('channel')
            if channel == 'l2Book':
                await self._handle_orderbook_update(data['data'])
            elif channel == 'allMids':
                await self._handle_mids_update(data['data'])
            elif channel == 'subscriptionResponse':
                pass  # Silent subscription response
            elif channel == 'error':
                logger.error(f"❌ WebSocket error: {data}")
            else:
                pass  # Silent unhandled channels
                
        except Exception as e:
            logger.error(f"❌ Error handling message: {e}")
            
    async def _handle_orderbook_update(self, data: Dict):
        """Handle orderbook update"""
        try:
            coin = data.get('coin')
            if not coin or coin not in self.asset_map:
                return
                
            # Parse orderbook data from the levels array
            bids = []
            asks = []
            
            if 'levels' in data and len(data['levels']) == 2:
                # First array is bids, second is asks
                bids_data = data['levels'][0]  # Bids
                asks_data = data['levels'][1]  # Asks
                
                # Parse bids (each bid has 'px' for price and 'sz' for size)
                for bid in bids_data:
                    if isinstance(bid, dict) and 'px' in bid and 'sz' in bid:
                        try:
                            price = float(bid['px'])
                            size = float(bid['sz'])
                            bids.append([price, size])
                        except (ValueError, TypeError):
                            continue
                
                # Parse asks (each ask has 'px' for price and 'sz' for size)
                for ask in asks_data:
                    if isinstance(ask, dict) and 'px' in ask and 'sz' in ask:
                        try:
                            price = float(ask['px'])
                            size = float(ask['sz'])
                            asks.append([price, size])
                        except (ValueError, TypeError):
                            continue
                            
            if bids and asks:
                # Sort by price
                bids.sort(key=lambda x: x[0], reverse=True)  # Highest bid first
                asks.sort(key=lambda x: x[0])  # Lowest ask first
                
                # Create orderbook
                orderbook = OrderBook(
                    symbol=f"{coin}-PERP",
                    bids=bids[:10],  # Top 10 bids
                    asks=asks[:10],  # Top 10 asks
                    ts_exchange=int(time.time() * 1000)
                )
                
                self.orderbooks[coin] = orderbook
                
                # Create quote from best bid/ask
                if bids and asks:
                    quote = Quote(
                        symbol=f"{coin}-PERP",
                        bid=bids[0][0],
                        ask=asks[0][0],
                        last=asks[0][0],  # Use ask as last price
                        ts_exchange=int(time.time() * 1000)
                    )
                    self.quotes[coin] = quote
                    
                    # Log quote updates (but not too frequently)
                    current_time = time.time()
                    if not hasattr(self, '_last_quote_log') or current_time - getattr(self, '_last_quote_log', 0) >= 2.0:
                        logger.info(f"🔄 HL {coin}-PERP quote updated: bid=${quote.bid:.4f} ask=${quote.ask:.4f}")
                        self._last_quote_log = current_time
                    
                    # Only log significant price changes (>0.1%) to reduce noise
                    if coin in self.quotes:
                        old_quote = self.quotes[coin]
                        old_mid = (old_quote.bid + old_quote.ask) / 2
                        new_mid = (bids[0][0] + asks[0][0]) / 2
                        price_change_pct = abs(new_mid - old_mid) / old_mid * 100
                        
                        if price_change_pct > 0.1:  # Only log if >0.1% change
                            logger.info(f"📊 {coin} price update: ${old_mid:.2f} → ${new_mid:.2f} ({price_change_pct:+.2f}%)")
                    else:
                        # Log first quote
                        logger.info(f"📊 First {coin} quote: bid=${bids[0][0]:.2f} ask=${asks[0][0]:.2f}")
                
        except Exception as e:
            logger.error(f"❌ Error handling orderbook update: {e}")
            import traceback
            traceback.print_exc()
            
    async def _handle_mids_update(self, data: Dict):
        """Handle mids update"""
        try:
            if 'mids' in data:
                mids = data['mids']
                # Extract ETH and BTC mid prices
                for coin, mid_str in mids.items():
                    if coin in ['ETH', 'BTC']:
                        try:
                            mid = float(mid_str)
                            # Update quote with mid price if it exists
                            if coin in self.quotes:
                                self.quotes[coin].last = mid
                        except (ValueError, TypeError):
                            continue
                                
        except Exception as e:
            logger.error(f"❌ Error handling mids update: {e}")
            
    async def place_order(self, symbol: str, side: str, order_type: str,
                         amount: float, price: Optional[float] = None,
                         params: Optional[Dict] = None) -> OrderResult:
        """Place an order using Hyperliquid SDK"""

            
        try:
            # Clean symbol and get asset ID
            clean_symbol = symbol.replace('-PERP', '')
            if clean_symbol not in self.asset_map:
                raise ValueError(f"Unknown symbol: {symbol}")
                
            asset_id = self.asset_map[clean_symbol]
            
            # Generate unique nonce
            nonce = self._generate_nonce()
            
            # Create order request
            order_request = OrderRequest(
                coin=clean_symbol,
                is_buy=side.lower() == "buy",
                sz=str(amount),
                limit_px=str(price) if price else None,
                reduce_only=False,
                cloid=f"0x{nonce:032x}"  # Use nonce as client order ID
            )
            
            # Place order
            response = await self.hyperliquid.order(order_request)
            
            logger.info(f"✅ Order placed: {side} {amount} {symbol} @ {price}")
            return OrderResult(
                success=True,
                order_id=response.get('oid', str(nonce)),
                filled_qty=amount,
                avg_price=price or 0.0,
                fee_asset="USDC",
                fee_amount=0.0,
                latency_ms=75
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to create order: {e}")
            return OrderResult(
                success=False,
                error=str(e)
            )
            
    def _generate_nonce(self) -> int:
        """Generate unique nonce for orders"""
        current_time = int(time.time() * 1000)
        if current_time <= self.last_nonce:
            current_time = self.last_nonce + 1
        self.last_nonce = current_time
        return current_time
        
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order"""

            
        try:
            # Clean symbol and get asset ID
            clean_symbol = symbol.replace('-PERP', '')
            if clean_symbol not in self.asset_map:
                logger.warning(f"⚠️ Unknown symbol: {symbol}")
                return False
                
            asset_id = self.asset_map[clean_symbol]
            
            # Create cancel request
            cancel_request = CancelRequest(
                coin=clean_symbol,
                oid=int(order_id) if order_id.isdigit() else 0
            )
            
            # Cancel order
            response = await self.hyperliquid.cancel(cancel_request)
            
            logger.info(f"✅ Order cancelled: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to cancel order: {e}")
            return False
            
    async def fetch_balances(self) -> Dict[str, Balance]:
        """Fetch account balances"""

            
        try:
            # Get account info from Hyperliquid
            account_info = await self.hyperliquid.get_account_info()
            
            balance = {}
            if 'marginSummary' in account_info:
                margin = account_info['marginSummary']
                usdc_value = float(margin.get('accountValue', 0))
                balance['USDC'] = Balance(
                    asset="USDC",
                    free=usdc_value,
                    total=usdc_value,
                    ts=int(time.time() * 1000)
                )
                
            logger.debug(f"💰 Balance: {balance}")
            return balance
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch balance: {e}")
            return {}
            
    async def load_markets(self) -> Dict[str, Any]:
        """Load exchange markets and trading rules"""

            
        try:
            # Get meta info from Hyperliquid
            meta_response = await self._make_rest_request(
                "https://api.hyperliquid.xyz/info",
                {"type": "meta"}
            )
            
            markets = {}
            if meta_response and 'universe' in meta_response:
                for asset in meta_response['universe']:
                    if asset['name'] in ['ETH', 'BTC']:
                        symbol = f"{asset['name']}-PERP"
                        markets[symbol] = {
                            "symbol": symbol,
                            "base": asset['name'],
                            "quote": "USDC",
                            "type": "perp",
                            "precision": {
                                "amount": asset.get('szDecimals', 0.001),
                                "price": asset.get('pxDecimals', 0.01)
                            }
                        }
                        
            logger.info(f"📊 Loaded {len(markets)} Hyperliquid markets")
            return markets
            
        except Exception as e:
            logger.error(f"❌ Failed to load markets: {e}")
            return {}
            
    async def disconnect(self) -> None:
        """Disconnect from Hyperliquid"""
        if self.ws and self.ws_connected:
            await self.ws.close()
            self.ws_connected = False
            logger.info("🔌 Hyperliquid WebSocket closed")
            
    async def health_check(self) -> bool:
        """Perform health check"""

            
        try:
            if not self.ws_connected:
                return False
                
            # Test WebSocket connection
            await self.ws.ping()
            return True
            
        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
            return False
            
    def price_to_precision(self, symbol: str, price: float) -> str:
        """Convert price to exchange precision"""
        # Hyperliquid typically uses 4 decimal places for prices
        return f"{price:.4f}"
        
    def amount_to_precision(self, symbol: str, amount: float) -> str:
        """Convert amount to exchange precision"""
        # Hyperliquid typically uses 4 decimal places for amounts
        return f"{amount:.4f}"
        
    async def close(self):
        """Close connections"""
        await self.disconnect()
