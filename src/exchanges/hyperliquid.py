"""Hyperliquid exchange integration for perpetual futures trading."""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Any, AsyncGenerator
from decimal import Decimal
import json
import websockets
import aiohttp

from .base import BaseExchange, Quote, OrderBook, Balance, OrderResult

logger = logging.getLogger(__name__)


class HyperliquidExchange(BaseExchange):
    """Hyperliquid exchange implementation for perpetual futures."""

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        
        # Hyperliquid specific configuration
        self.base_url = "https://api.hyperliquid.xyz"
        self.ws_url = "wss://api.hyperliquid.xyz/ws"
        self.chain = config.get('hyperliquid', {}).get('chain', 'arbitrum')
        
        # Wallet credentials
        hyperliquid_config = config.get('hyperliquid', {})
        self.wallet_address = hyperliquid_config.get('wallet_address', '')
        self.private_key = hyperliquid_config.get('private_key', '')
        self.initial_capital = hyperliquid_config.get('initial_capital_usdc', 50.0)
        
        # WebSocket connection
        self.ws: Optional[websockets.WebSocketServerProtocol] = None
        self.ws_connected = False
        
        # REST client
        self.http_session: Optional[aiohttp.ClientSession] = None
        
        # Market data cache
        self._orderbooks: Dict[str, OrderBook] = {}
        self._tickers: Dict[str, Quote] = {}
        self._last_update = 0
        
        # Trading state
        self._connected = False
        self._markets_loaded = False
        
        # Validate wallet credentials
        if not self.wallet_address or not self.private_key:
            logger.error("❌ Hyperliquid wallet credentials not configured!")
            logger.error("   Please check your config.yaml file")
            logger.error("   Required: wallet_address and private_key in hyperliquid section")
            raise ValueError("Hyperliquid credentials not configured")
        else:
            logger.info(f"✅ Hyperliquid configured with wallet: {self.wallet_address[:8]}...{self.wallet_address[-6:]}")
            logger.info(f"✅ Private key loaded: {self.private_key[:8]}...{self.private_key[-6:]}")
            logger.info(f"✅ Initial capital: ${self.initial_capital}")

    async def connect(self, symbols: List[str] = None) -> bool:
        """Connect to Hyperliquid exchange."""
        try:
            logger.info("🚀 Starting Hyperliquid connection process...")
            
            if self._connected:
                logger.info("✅ Already connected to Hyperliquid")
                return True
            
            if symbols is None:
                symbols = ["ETH-PERP", "BTC-PERP"]  # Default symbols
            
            logger.info(f"📡 Connecting to Hyperliquid with symbols: {symbols}")
            
            # Initialize HTTP session
            if not self.http_session:
                logger.info("🌐 Initializing HTTP session...")
                self.http_session = aiohttp.ClientSession()
                logger.info("✅ HTTP session initialized")
            
            # Load markets first
            logger.info("📊 Loading Hyperliquid markets...")
            await self.load_markets()
            logger.info("✅ Markets loaded")
            
            # Connect WebSocket
            logger.info("🔌 Connecting to WebSocket...")
            await self._connect_websocket()
            logger.info("✅ WebSocket connection completed")
            
            # Wait for WebSocket to be fully ready
            logger.info("⏳ Waiting for WebSocket to be fully ready...")
            await asyncio.sleep(1.0)  # Give WebSocket time to stabilize
            logger.info("⏰ WebSocket stabilization wait completed")
            
            # Check WebSocket state before subscribing
            logger.info(f"🔍 Checking WebSocket state: ws_connected={self.ws_connected}, ws={self.ws is not None}")
            if not self.ws_connected or not self.ws:
                logger.error(f"❌ WebSocket not ready after connection! ws_connected: {self.ws_connected}, ws: {self.ws is not None}")
                return False
            
            logger.info("✅ WebSocket is ready, proceeding with subscriptions...")
            
            # Store symbols for later subscription (don't subscribe yet)
            self._symbols_to_subscribe = symbols
            logger.info(f"💾 Stored symbols for later subscription: {symbols}")
            
            self._connected = True
            logger.info(f"🎉 Hyperliquid connected successfully with symbols {symbols}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Hyperliquid: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def disconnect(self) -> None:
        """Disconnect from Hyperliquid exchange."""
        try:
            if self.ws:
                await self.ws.close()
                self.ws = None
                self.ws_connected = False
            
            if self.http_session:
                await self.http_session.close()
                self.http_session = None
            
            self._connected = False
            logger.info("Hyperliquid disconnected")
            
        except Exception as e:
            logger.error(f"Error disconnecting from Hyperliquid: {e}")

    async def load_markets(self) -> Dict[str, Any]:
        """Load Hyperliquid markets and trading rules."""
        try:
            # Initialize markets dict if not exists
            if not hasattr(self, 'markets'):
                self.markets = {}
            
            # Use POST method with proper payload for Hyperliquid API
            payload = {"type": "meta"}
            
            async with self.http_session.post(
                f"{self.base_url}/info",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Hyperliquid meta info: {data.get('chainName', 'unknown')}")
                    
                    # Store market info
                    for market in data.get("universe", []):
                        symbol = market.get("name", "")
                        if symbol:
                            # Get precision from the market data
                            sz_decimals = market.get("szDecimals", 0.001)
                            px_decimals = market.get("pxDecimals", 0.01)
                            
                            self.markets[symbol] = {
                                "symbol": symbol,
                                "base": market.get("base", ""),
                                "quote": "USDC",  # Hyperliquid uses USDC as quote
                                "type": "perp",
                                "limits": {
                                    "amount": {
                                        "min": sz_decimals,
                                        "max": float('inf')
                                    },
                                    "price": {
                                        "min": px_decimals,
                                        "max": float('inf')
                                    },
                                    "cost": {
                                        "min": 1.0,  # $1 minimum notional
                                        "max": float('inf')
                                    }
                                },
                                "precision": {
                                    "amount": sz_decimals,
                                    "price": px_decimals
                                }
                            }
                    
                    self._markets_loaded = True
                    logger.info(f"Loaded {len(self.markets)} Hyperliquid markets")
                    return self.markets
                else:
                    logger.error(f"Failed to fetch markets: {response.status}")
                    # Fallback: create basic market info for ETH and BTC
                    self._create_fallback_markets()
                    return self.markets
            
        except Exception as e:
            logger.error(f"Failed to load Hyperliquid markets: {e}")
            # Initialize empty markets dict as fallback
            if not hasattr(self, 'markets'):
                self.markets = {}
            # Create fallback markets
            self._create_fallback_markets()
            return {}
    
    def _create_fallback_markets(self):
        """Create fallback market info for ETH and BTC."""
        fallback_markets = {
            "ETH": {
                "symbol": "ETH",
                "base": "ETH",
                "quote": "USDC",
                "type": "perp",
                "limits": {
                    "amount": {"min": 0.001, "max": float('inf')},
                    "price": {"min": 0.01, "max": float('inf')},
                    "cost": {"min": 1.0, "max": float('inf')}
                },
                "precision": {"amount": 0.001, "price": 0.01}
            },
            "BTC": {
                "symbol": "BTC",
                "base": "BTC",
                "quote": "USDC",
                "type": "perp",
                "limits": {
                    "amount": {"min": 0.001, "max": float('inf')},
                    "price": {"min": 0.01, "max": float('inf')},
                    "cost": {"min": 1.0, "max": float('inf')}
                },
                "precision": {"amount": 0.001, "price": 0.01}
            }
        }
        
        for symbol, market_info in fallback_markets.items():
            self.markets[symbol] = market_info
        
        logger.info("Created fallback markets for ETH and BTC")

    async def _connect_websocket(self):
        """Connect to Hyperliquid WebSocket with robust connection handling."""
        try:
            logger.info("🔌 Starting WebSocket connection to Hyperliquid...")
            logger.info(f"🌐 WebSocket URL: {self.ws_url}")
            
            # Check if we already have a WebSocket
            if self.ws:
                logger.info("⚠️  WebSocket already exists, closing old connection...")
                try:
                    await self.ws.close()
                except Exception as e:
                    logger.warning(f"Warning closing old WebSocket: {e}")
                self.ws = None
                self.ws_connected = False
            
            logger.info("🔄 Creating new WebSocket connection...")
            
            # Create WebSocket connection with better parameters
            try:
                self.ws = await websockets.connect(
                    self.ws_url,
                    ping_interval=20,  # More frequent pings
                    ping_timeout=10,
                    close_timeout=10,
                    max_size=2**23,  # 8MB max message size
                    compression=None  # Disable compression for stability
                )
                logger.info("✅ WebSocket connection created successfully")
            except Exception as e:
                logger.error(f"❌ Failed to create WebSocket connection: {e}")
                raise
            
            # Test the connection with multiple pings
            logger.info("🧪 Testing WebSocket connection...")
            try:
                for i in range(3):
                    await self.ws.ping()
                    logger.info(f"✅ WebSocket ping {i+1} successful")
                    await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"❌ WebSocket ping failed: {e}")
                raise
            
            # Mark as connected
            self.ws_connected = True
            logger.info("✅ WebSocket connection established and marked as connected")
            
            # Don't start duplicate WebSocket listener - let watch_quotes handle it
            logger.info("ℹ️  WebSocket ready for use by watch_quotes method")
            
        except Exception as e:
            logger.error(f"❌ WebSocket connection failed: {e}")
            self.ws_connected = False
            if self.ws:
                try:
                    await self.ws.close()
                except:
                    pass
                self.ws = None
            raise

    async def start_subscriptions(self) -> bool:
        """Start market data subscriptions after connection is stable."""
        try:
            if not hasattr(self, '_symbols_to_subscribe') or not self._symbols_to_subscribe:
                logger.warning("No symbols to subscribe to")
                return False
                
            if not self.ws_connected or not self.ws:
                logger.error("WebSocket not ready for subscriptions")
                return False
                
            logger.info("🚀 Starting market data subscriptions...")
            await self._subscribe_market_data(self._symbols_to_subscribe)
            return True
            
        except Exception as e:
            logger.error(f"Failed to start subscriptions: {e}")
            return False

    async def _subscribe_market_data(self, symbols: List[str]):
        """Subscribe to market data for given symbols using Hyperliquid's API format."""
        try:
            logger.info(f"🚀 Starting market data subscriptions for {len(symbols)} symbols...")
            
            # Check WebSocket state
            if not self.ws_connected:
                logger.error(f"❌ WebSocket not connected!")
                return
            
            if not self.ws:
                logger.error(f"❌ WebSocket object is None!")
                return
                
            for symbol in symbols:
                # Clean symbol name (remove -PERP suffix for subscription)
                clean_symbol = symbol.replace("-PERP", "")
                
                try:
                    # Subscribe to L2 orderbook updates
                    orderbook_sub = {
                        "method": "subscribe",
                        "subscription": {
                            "type": "l2Book",
                            "coin": clean_symbol
                        }
                    }
                    
                    await self.ws.send(json.dumps(orderbook_sub))
                    logger.debug(f"📤 Sent l2Book subscription for {clean_symbol}")
                    
                    # Wait for subscription response
                    await asyncio.sleep(0.2)
                    
                    # Subscribe to all mid prices
                    mids_sub = {
                        "method": "subscribe",
                        "subscription": {
                            "type": "allMids",
                            "dex": "hyperliquid"
                        }
                    }
                    
                    await self.ws.send(json.dumps(mids_sub))
                    logger.debug(f"📤 Sent allMids subscription")
                    
                    # Wait for subscription response
                    await asyncio.sleep(0.2)
                    
                except Exception as e:
                    logger.error(f"❌ Failed to subscribe to {clean_symbol}: {e}")
                    continue
                
            logger.info(f"✅ Sent all subscription messages for {symbols}")
            
        except Exception as e:
            logger.error(f"❌ Error in subscription method: {e}")
            import traceback
            traceback.print_exc()
            raise

    async def watch_quotes(self, symbols: List[str]) -> AsyncGenerator[Quote, None]:
        """Watch real-time quotes for given symbols with robust reconnection."""
        logger.info(f"🔍 Starting quote monitoring for symbols: {symbols}")
        
        max_reconnect_attempts = 5
        reconnect_delay = 2.0
        
        for attempt in range(max_reconnect_attempts):
            try:
                if not self.ws_connected:
                    logger.warning(f"⚠️  WebSocket not connected, attempting to reconnect (attempt {attempt + 1}/{max_reconnect_attempts})")
                    await self._reconnect_websocket()
                    if not self.ws_connected:
                        logger.error(f"❌ Failed to reconnect WebSocket on attempt {attempt + 1}")
                        if attempt < max_reconnect_attempts - 1:
                            await asyncio.sleep(reconnect_delay)
                            continue
                        else:
                            logger.error("❌ Max reconnection attempts reached")
                            return
                
                logger.info(f"✅ WebSocket connected, starting to listen for messages...")
                
                # Resubscribe to market data after reconnection
                if attempt > 0:
                    logger.info("🔄 Resubscribing to market data after reconnection...")
                    await self._subscribe_market_data(symbols)
                
                logger.info(f"🎧 Starting WebSocket message monitoring for symbols: {symbols}")
                
                # Add a ping to test connection
                try:
                    await self.ws.ping()
                    logger.debug("🏓 WebSocket ping successful")
                except Exception as e:
                    logger.warning(f"⚠️  WebSocket ping failed: {e}")
                
                # Wait a moment for the WebSocket to stabilize
                await asyncio.sleep(0.5)
                
                logger.debug("🚀 Starting message loop...")
                
                async for message in self.ws:
                    try:
                        data = json.loads(message)
                        
                        # Check for ping/pong messages
                        if isinstance(data, str) and data == "pong":
                            logger.debug("🏓 Received pong from Hyperliquid")
                            continue
                        
                        # Handle different message types based on Hyperliquid's documented format
                        if "channel" in data:
                            channel = data["channel"]
                            
                            if channel == "l2Book":
                                # Handle orderbook updates
                                logger.debug(f"📊 Processing l2Book update for {data.get('data', {}).get('coin', 'unknown')}")
                                await self._handle_orderbook_update(data["data"])
                            elif channel == "allMids":
                                # Handle mid-price updates
                                logger.debug(f"📈 Processing allMids update")
                                await self._handle_mids_update(data["data"])
                            elif channel == "subscriptionResponse":
                                # Handle subscription confirmation
                                logger.debug(f"✅ Subscription confirmed")
                        
                        # Also check for other message formats
                        elif "method" in data:
                            if data["method"] == "notify":
                                logger.debug(f"📢 Processing notify message")
                        
                        # Check if we have valid quotes to yield
                        for symbol in symbols:
                            clean_symbol = symbol.replace("-PERP", "")
                            if clean_symbol in self._tickers:
                                quote = self._tickers[clean_symbol]
                                logger.debug(f"✅ Yielding quote for {symbol}: bid=${quote.bid:.4f} ask=${quote.ask:.4f}")
                                yield quote
                                
                    except json.JSONDecodeError as e:
                        logger.warning(f"⚠️  Failed to parse WebSocket message: {e}")
                        continue
                    except Exception as e:
                        logger.error(f"❌ Error processing WebSocket message: {e}")
                        
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"⚠️  WebSocket connection closed (attempt {attempt + 1}): {e}")
                self.ws_connected = False
                if attempt < max_reconnect_attempts - 1:
                    logger.info(f"🔄 Attempting to reconnect in {reconnect_delay} seconds...")
                    await asyncio.sleep(reconnect_delay)
                    continue
                else:
                    logger.error("❌ Max reconnection attempts reached")
                    break
                    
            except Exception as e:
                logger.error(f"❌ WebSocket error in watch_quotes (attempt {attempt + 1}): {e}")
                import traceback
                traceback.print_exc()
                if attempt < max_reconnect_attempts - 1:
                    logger.info(f"🔄 Attempting to reconnect in {reconnect_delay} seconds...")
                    await asyncio.sleep(reconnect_delay)
                    continue
                else:
                    logger.error("❌ Max reconnection attempts reached")
                    break
                    
        logger.error("❌ WebSocket monitoring failed after all reconnection attempts")
        await self._reconnect_websocket()

    async def _handle_mids_update(self, data: Dict):
        """Handle mid-price updates from Hyperliquid WebSocket using AllMids format."""
        try:
            logger.info(f"🔍 Processing allMids update with data type: {type(data)}")
            logger.info(f"📊 Mids data structure: {json.dumps(data, indent=2)}")
            
            # AllMids format: { mids: Record<string, string> }
            if isinstance(data, dict) and "mids" in data:
                mids = data["mids"]
                logger.info(f"📈 Received mids for {len(mids)} coins")
                
                for coin, mid_price_str in mids.items():
                    try:
                        mid_price = float(mid_price_str)
                        logger.info(f"📊 Coin: {coin}, Mid: ${mid_price:.4f}")
                        
                        # Update quote if we have orderbook data
                        await self._update_quote_from_mid(coin, mid_price)
                        
                    except (ValueError, TypeError) as e:
                        logger.warning(f"⚠️ Invalid mid price for {coin}: {mid_price_str}, error: {e}")
                        
            elif isinstance(data, list):
                # Alternative format: [{"coin": "ETH", "mid": "4340.0"}]
                logger.info(f"📈 Received mids list with {len(data)} items")
                
                for coin_data in data:
                    if isinstance(coin_data, dict):
                        coin = coin_data.get("coin")
                        mid_price_str = coin_data.get("mid")
                        
                        if coin and mid_price_str:
                            try:
                                mid_price = float(mid_price_str)
                                logger.info(f"📊 Coin: {coin}, Mid: ${mid_price:.4f}")
                                await self._update_quote_from_mid(coin, mid_price)
                            except (ValueError, TypeError) as e:
                                logger.warning(f"⚠️ Invalid mid price for {coin}: {mid_price_str}, error: {e}")
                                
            else:
                logger.warning(f"⚠️ Unexpected mids data format: {type(data)} - {data}")
            
        except Exception as e:
            logger.error(f"❌ Error handling mids update: {e}")
            logger.error(f"📊 Data that caused error: {data}")
            import traceback
            traceback.print_exc()

    async def _update_quote_from_mid(self, coin: str, mid_price: float):
        """Update quote from mid price data."""
        try:
            # Convert to proper format and add -PERP suffix for consistency
            perp_symbol = f"{coin}-PERP"
            
            # Get the orderbook to extract bid/ask
            orderbook = self._orderbooks.get(perp_symbol)
            if orderbook and orderbook.bids and orderbook.asks:
                best_bid = orderbook.bids[0][0]
                best_ask = orderbook.asks[0][0]
                best_bid_size = orderbook.bids[0][1]
                best_ask_size = orderbook.asks[0][1]
                
                # Create or update quote
                self._tickers[coin] = Quote(
                    venue=self.name,
                    symbol=perp_symbol,
                    bid=best_bid,
                    ask=best_ask,
                    bid_size=best_bid_size,
                    ask_size=best_ask_size,
                    ts_exchange=int(time.time() * 1000),
                    ts_local=int(time.time() * 1000)
                )
                
                logger.info(f"✅ Updated {perp_symbol} quote from mids: bid=${best_bid:.4f} ask=${best_ask:.4f} mid=${mid_price:.4f}")
            else:
                logger.info(f"📊 Received mid price for {coin}: ${mid_price:.4f} (waiting for orderbook)")
                
        except Exception as e:
            logger.error(f"❌ Error updating quote from mid: {e}")

    async def _handle_orderbook_update(self, data: Dict):
        """Handle orderbook update from Hyperliquid WebSocket using WsBook format."""
        try:
            # WsBook format: { coin: string; levels: [Array<WsLevel>, Array<WsLevel>] }
            symbol = data.get("coin", "")
            levels = data.get("levels", [])
            
            if not symbol or not levels or len(levels) < 2:
                logger.warning(f"⚠️ Invalid l2Book data: coin={symbol}, levels={levels}")
                return
            
            # Convert to proper format and add -PERP suffix for consistency
            perp_symbol = f"{symbol}-PERP"
            
            # Extract bids and asks from the levels array
            # levels[0] = bids, levels[1] = asks (based on WsBook format)
            # Each level is an object with "px" (price) and "sz" (size) keys
            bids = []
            asks = []
            
            if len(levels) >= 1 and isinstance(levels[0], list):
                for level in levels[0]:  # Bids
                    if isinstance(level, dict) and "px" in level and "sz" in level:
                        try:
                            price = float(level["px"])
                            size = float(level["sz"])
                            bids.append((price, size))
                        except (ValueError, TypeError) as e:
                            logger.warning(f"⚠️ Invalid bid level: {level}, error: {e}")
            
            if len(levels) >= 2 and isinstance(levels[1], list):
                for level in levels[1]:  # Asks
                    if isinstance(level, dict) and "px" in level and "sz" in level:
                        try:
                            price = float(level["px"])
                            size = float(level["sz"])
                            asks.append((price, size))
                        except (ValueError, TypeError) as e:
                            logger.warning(f"⚠️ Invalid ask level: {level}, error: {e}")
            
            # Sort by price (bids descending, asks ascending)
            bids.sort(key=lambda x: x[0], reverse=True)
            asks.sort(key=lambda x: x[0])
            
            if bids and asks:
                self._orderbooks[perp_symbol] = OrderBook(
                    venue=self.name,
                    symbol=perp_symbol,
                    bids=bids,
                    asks=asks,
                    ts_exchange=int(time.time() * 1000),
                    ts_local=int(time.time() * 1000)
                )
                
                # Update ticker with best bid/ask
                best_bid = bids[0][0]
                best_ask = asks[0][0]
                best_bid_size = bids[0][1]
                best_ask_size = asks[0][1]
                
                self._tickers[symbol] = Quote(
                    venue=self.name,
                    symbol=perp_symbol,
                    bid=best_bid,
                    ask=best_ask,
                    bid_size=best_bid_size,
                    ask_size=best_ask_size,
                    ts_exchange=int(time.time() * 1000),
                    ts_local=int(time.time() * 1000)
                )
                
                logger.info(f"✅ Updated {perp_symbol} quote: bid=${best_bid:.4f} ask=${best_ask:.4f}")
            else:
                logger.warning(f"⚠️ No valid bid/ask data for {perp_symbol}")
            
        except Exception as e:
            logger.error(f"❌ Error handling orderbook update: {e}")
            import traceback
            traceback.print_exc()

    async def fetch_order_book(self, symbol: str, limit: int = 10) -> Optional[OrderBook]:
        """Fetch order book for a symbol."""
        try:
            # Try to get from cache first
            if symbol in self._orderbooks:
                return self._orderbooks[symbol]
            
            # Fallback to REST API
            async with self.http_session.get(f"{self.base_url}/orderbook?coin={symbol}") as response:
                data = await response.json()
                
                bids = [(float(level[0]), float(level[1])) for level in data.get("bids", [])[:limit]]
                asks = [(float(level[0]), float(level[1])) for level in data.get("asks", [])[:limit]]
                
                orderbook = OrderBook(
                    venue=self.name,
                    symbol=symbol,
                    bids=bids,
                    asks=asks,
                    ts_exchange=int(time.time() * 1000),
                    ts_local=int(time.time() * 1000)
                )
                
                self._orderbooks[symbol] = orderbook
                return orderbook
                
        except Exception as e:
            logger.error(f"Failed to fetch orderbook for {symbol}: {e}")
            return None

    async def place_order(self, symbol: str, side: str, order_type: str,
                         amount: float, price: Optional[float] = None,
                         params: Optional[Dict] = None) -> OrderResult:
        """Place an order on Hyperliquid (perpetual futures)."""
        try:
            # For now, return a mock result since we need API keys for real trading
            # In production, this would make the actual API call to Hyperliquid
            
            logger.info(f"Placing {side} {amount} {symbol} at {price} on Hyperliquid")
            
            return OrderResult(
                success=True,
                order_id=f"hl_{int(time.time() * 1000)}",
                filled_qty=amount,
                avg_price=price or 0.0,
                fee_asset="USDC",
                fee_amount=0.0,
                latency_ms=50
            )
            
        except Exception as e:
            logger.error(f"Failed to place order on Hyperliquid: {e}")
            return OrderResult(
                success=False,
                error=str(e)
            )

    async def create_order_perp(self, symbol: str, side: str, amount_base: float, 
                               price: float, tif: str = "IOC", reduce_only: bool = False) -> OrderResult:
        """Create a perpetual futures order on Hyperliquid."""
        try:
            # Convert to Hyperliquid format according to official API spec
            order_params = {
                "coin": symbol,
                "is_buy": side.lower() == "buy",
                "sz": str(amount_base),
                "limit_px": str(price),
                "reduce_only": reduce_only
            }
            
            # For IOC orders, set immediate execution
            if tif == "IOC":
                order_params["time_in_force"] = "Ioc"
            
            # Add required fields for Hyperliquid API
            if self.wallet_address and self.private_key:
                # TODO: Implement real order signing and submission
                # This would require:
                # 1. Creating the order request
                # 2. Signing with private key
                # 3. Submitting to /exchange endpoint
                logger.info(f"Real order would be submitted: {order_params}")
            
            logger.info(f"Creating perp order: {order_params}")
            
            # Mock execution for now
            return OrderResult(
                success=True,
                order_id=f"hl_perp_{int(time.time() * 1000)}",
                filled_qty=amount_base,
                avg_price=price,
                fee_asset="USDC",
                fee_amount=0.0,
                latency_ms=75
            )
            
        except Exception as e:
            logger.error(f"Failed to create perp order: {e}")
            return OrderResult(
                success=False,
                error=str(e)
            )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel a specific order."""
        try:
            logger.info(f"Cancelling order {order_id} for {symbol} on Hyperliquid")
            # Mock implementation for now
            # In production, this would call Hyperliquid API
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def cancel_all(self, symbol: str) -> bool:
        """Cancel all orders for a symbol."""
        try:
            logger.info(f"Cancelling all orders for {symbol} on Hyperliquid")
            # Mock implementation
            return True
        except Exception as e:
            logger.error(f"Failed to cancel orders: {e}")
            return False

    async def fetch_balances(self) -> Dict[str, Balance]:
        """Fetch account balances (USDC margin)."""
        try:
            if self.wallet_address and self.private_key and self.http_session:
                # Use the real Hyperliquid API endpoint
                logger.info(f"💰 Fetching real balance for wallet: {self.wallet_address}")
                
                # Call the clearinghouseState endpoint
                payload = {
                    "type": "clearinghouseState",
                    "user": self.wallet_address
                }
                
                async with self.http_session.post(
                    f"{self.base_url}/info",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Extract the withdrawable amount (USDC balance)
                        withdrawable = float(data.get("withdrawable", 0))
                        account_value = float(data.get("marginSummary", {}).get("accountValue", 0))
                        
                        logger.info(f"Real balance fetched: ${withdrawable:.2f} USDC")
                        
                        return {
                            "USDC": Balance(
                                asset="USDC",
                                free=withdrawable,
                                total=account_value,
                                ts=int(time.time() * 1000)
                            )
                        }
                    else:
                        logger.error(f"Failed to fetch balance: {response.status}")
                        # Fallback to configured capital
                        return {
                            "USDC": Balance(
                                asset="USDC",
                                free=self.initial_capital,
                                total=self.initial_capital,
                                ts=int(time.time() * 1000)
                            )
                        }
            else:
                # Mock balance for testing
                return {
                    "USDC": Balance(
                        asset="USDC",
                        free=50.0,
                        total=50.0,
                        ts=int(time.time() * 1000)
                    )
                }
        except Exception as e:
            logger.error(f"Failed to fetch balances: {e}")
            # Fallback to configured capital
            return {
                "USDC": Balance(
                    asset="USDC",
                    free=self.initial_capital,
                    total=self.initial_capital,
                    ts=int(time.time() * 1000)
                )
            }

    async def fetch_positions(self, symbol: str) -> Dict[str, Any]:
        """Fetch positions for a symbol."""
        try:
            if self.wallet_address and self.http_session:
                # Use the real Hyperliquid API endpoint
                payload = {
                    "type": "clearinghouseState",
                    "user": self.wallet_address
                }
                
                async with self.http_session.post(
                    f"{self.base_url}/info",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Look for the specific symbol position
                        symbol_positions = []
                        for asset_pos in data.get("assetPositions", []):
                            if asset_pos.get("position", {}).get("coin") == symbol.replace("-PERP", ""):
                                pos = asset_pos["position"]
                                symbol_positions.append({
                                    "size": float(pos.get("szi", 0)),
                                    "entry_price": float(pos.get("entryPx", 0)),
                                    "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
                                    "realized_pnl": 0.0,  # Not available in this endpoint
                                    "position_value": float(pos.get("positionValue", 0)),
                                    "leverage": pos.get("leverage", {}).get("value", 0)
                                })
                        
                        if symbol_positions:
                            return symbol_positions[0]  # Return first position
                        else:
                            return {
                                "size": 0.0,
                                "entry_price": 0.0,
                                "unrealized_pnl": 0.0,
                                "realized_pnl": 0.0,
                                "position_value": 0.0,
                                "leverage": 0
                            }
                    else:
                        logger.error(f"Failed to fetch positions: {response.status}")
                        return self._get_mock_position()
            else:
                return self._get_mock_position()
                
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return self._get_mock_position()
    
    def _get_mock_position(self) -> Dict[str, Any]:
        """Get mock position data for testing."""
        return {
            "size": 0.0,
            "entry_price": 0.0,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "position_value": 0.0,
            "leverage": 0
        }

    async def fetch_funding_rate(self, symbol: str) -> Optional[float]:
        """Fetch current funding rate for a symbol."""
        try:
            if not self.http_session:
                return None
                
            # Fetch funding rate from Hyperliquid API
            # This would be available in the meta info or a separate endpoint
            # For now, return a mock value
            logger.info(f"Fetching funding rate for {symbol}")
            
            # TODO: Implement real funding rate fetching
            # This would typically be in the meta info or a separate endpoint
            return 0.0001  # 0.01% per 8h (mock value)
            
        except Exception as e:
            logger.error(f"Failed to fetch funding rate for {symbol}: {e}")
            return None

    async def test_connectivity(self) -> bool:
        """Test basic network connectivity to Hyperliquid."""
        try:
            if not self.http_session:
                return False
                
            # Simple ping test
            async with self.http_session.get(
                f"{self.base_url}/ping",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                return response.status == 200
                
        except Exception as e:
            logger.warning(f"Connectivity test failed: {e}")
            return False

    async def health_check(self) -> bool:
        """Perform health check."""
        try:
            if not self.ws_connected:
                return False
            
            # Check if we can fetch basic market data
            test_symbol = list(self.markets.keys())[0] if self.markets else None
            if test_symbol:
                orderbook = await self.fetch_order_book(test_symbol, limit=1)
                return orderbook is not None
            
            return False
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def fetch_initial_quotes(self, symbols: List[str]) -> None:
        """Fetch initial quotes from REST API as fallback."""
        try:
            logger.info(f"🔍 Fetching initial quotes for symbols: {symbols}")
            
            for symbol in symbols:
                clean_symbol = symbol.replace("-PERP", "")
                logger.info(f"📡 Fetching {clean_symbol} from REST API...")
                
                # Use the correct Hyperliquid API format
                payload = {
                    "type": "meta"
                }
                
                logger.info(f"📤 REST API payload: {json.dumps(payload)}")
                logger.info(f"🌐 REST API URL: {self.base_url}/info")
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/info",
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        logger.info(f"📥 REST API response status: {response.status}")
                        
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"📊 REST API response data: {json.dumps(data, indent=2)}")
                            
                            # Look for the specific coin in the meta response
                            if "universe" in data:
                                for coin_info in data["universe"]:
                                    if coin_info.get("name") == clean_symbol:
                                        logger.info(f"✅ Found {clean_symbol} in universe")
                                        
                                        # Try to get orderbook for this coin
                                        orderbook_payload = {
                                            "type": "orderBook",
                                            "coin": clean_symbol
                                        }
                                        
                                        logger.info(f"📤 Orderbook payload: {json.dumps(orderbook_payload)}")
                                        
                                        async with session.post(
                                            f"{self.base_url}/info",
                                            json=orderbook_payload,
                                            timeout=aiohttp.ClientTimeout(total=10)
                                        ) as ob_response:
                                            if ob_response.status == 200:
                                                ob_data = await ob_response.json()
                                                logger.info(f"📊 Orderbook response: {json.dumps(ob_data, indent=2)}")
                                                
                                                if "data" in ob_data and "bids" in ob_data["data"] and "asks" in ob_data["data"]:
                                                    bids = ob_data["data"]["bids"]
                                                    asks = ob_data["data"]["asks"]
                                                    
                                                    logger.info(f"📈 Found {len(bids)} bids and {len(asks)} asks")
                                                    
                                                    if bids and asks:
                                                        best_bid = float(bids[0][0])
                                                        best_ask = float(asks[0][0])
                                                        best_bid_size = float(bids[0][1])
                                                        best_ask_size = float(asks[0][1])
                                                        
                                                        # Create quote
                                                        quote = Quote(
                                                            venue=self.name,
                                                            symbol=symbol,
                                                            bid=best_bid,
                                                            ask=best_ask,
                                                            bid_size=best_bid_size,
                                                            ask_size=best_ask_size,
                                                            ts_exchange=int(time.time() * 1000),
                                                            ts_local=int(time.time() * 1000)
                                                        )
                                                        
                                                        # Store in tickers
                                                        if not hasattr(self, '_tickers'):
                                                            self._tickers = {}
                                                        self._tickers[clean_symbol] = quote
                                                        
                                                        logger.info(f"✅ Created initial quote for {symbol}: bid=${best_bid:.4f} ask=${best_ask:.4f}")
                                                        break
                                                    else:
                                                        logger.warning(f"⚠️ No bid/ask data found for {clean_symbol}")
                                                else:
                                                    logger.warning(f"⚠️ Unexpected orderbook response format for {clean_symbol}")
                                            else:
                                                ob_text = await ob_response.text()
                                                logger.error(f"❌ Orderbook API error {ob_response.status}: {ob_text}")
                                        break
                                else:
                                    logger.warning(f"⚠️ {clean_symbol} not found in universe")
                            else:
                                logger.warning(f"⚠️ No universe data in meta response")
                        else:
                            response_text = await response.text()
                            logger.error(f"❌ REST API error {response.status}: {response_text}")
                                    
        except Exception as e:
            logger.error(f"❌ Error fetching initial quotes: {e}")
            import traceback
            traceback.print_exc()

    async def _reconnect_websocket(self):
        """Reconnect to WebSocket."""
        try:
            logger.info("Attempting to reconnect to Hyperliquid WebSocket...")
            
            if hasattr(self, 'ws') and self.ws:
                await self.ws.close()
            
            self.ws_connected = False
            await asyncio.sleep(1)  # Wait before reconnecting
            
            await self._connect_websocket()
            
            # Resubscribe to market data
            if hasattr(self, 'markets'):
                symbols = list(self.markets.keys())
                await self._subscribe_market_data(symbols)
                
            logger.info("Successfully reconnected to Hyperliquid WebSocket")
            
        except Exception as e:
            logger.error(f"WebSocket reconnection failed: {e}")
            self.ws_connected = False

    def normalize_symbol(self, symbol: str) -> str:
        """Convert CCXT symbol format to Hyperliquid format."""
        # Convert ETH/USDC -> ETH-PERP
        if "/" in symbol:
            base = symbol.split("/")[0]
            return f"{base}-PERP"
        return symbol

    def price_to_precision(self, price: float, symbol: str) -> float:
        """Round price to exchange precision."""
        normalized_symbol = self.normalize_symbol(symbol)
        if normalized_symbol not in self.markets:
            return price
        
        precision = self.markets[normalized_symbol]["precision"]["price"]
        return round(price / precision) * precision

    def amount_to_precision(self, amount: float, symbol: str) -> float:
        """Round amount to exchange precision."""
        normalized_symbol = self.normalize_symbol(symbol)
        if normalized_symbol not in self.markets:
            return amount
        
        precision = self.markets[normalized_symbol]["precision"]["amount"]
        return round(amount / precision) * precision

    def get_taker_fee_bps(self) -> float:
        """Get taker fee in basis points."""
        return self.config.get('fees', {}).get('taker_bps', {}).get('hyperliquid', 3.0)

    def get_maker_fee_bps(self) -> float:
        """Get maker fee in basis points."""
        return self.config.get('fees', {}).get('maker_bps', {}).get('hyperliquid', 2.0)
    
    def is_connected(self) -> bool:
        """Check if exchange is connected."""
        return self._connected and self.ws_connected

    async def _get_asset_ids(self):
        """Get the correct asset IDs from Hyperliquid's meta endpoint."""
        try:
            logger.info("🔍 Fetching asset IDs from Hyperliquid meta endpoint...")
            
            # First get the meta data to find asset IDs
            meta_payload = {"type": "meta"}
            async with self.http_session.post(f"{self.base_url}/info", json=meta_payload) as response:
                if response.status == 200:
                    meta_data = await response.json()
                    logger.info(f"✅ Meta data received: {json.dumps(meta_data, indent=2)}")
                    
                    # Extract asset IDs for ETH and BTC
                    if "universe" in meta_data:
                        universe = meta_data["universe"]
                        asset_ids = {}
                        
                        for asset in universe:
                            if "name" in asset and "chain" in asset:
                                symbol = asset["name"]
                                asset_id = asset["chain"]
                                asset_ids[symbol] = asset_id
                                logger.info(f"📊 Found asset: {symbol} -> ID: {asset_id}")
                        
                        return asset_ids
                    else:
                        logger.warning("⚠️  No 'universe' found in meta data")
                        return {}
                else:
                    logger.error(f"❌ Meta endpoint failed: {response.status}")
                    return {}
                    
        except Exception as e:
            logger.error(f"❌ Failed to get asset IDs: {e}")
            return {}

    async def test_websocket_connection(self):
        """Test basic WebSocket connectivity with a simple ping."""
        try:
            if not self.ws_connected or not self.ws:
                logger.error("❌ WebSocket not connected for ping test")
                return False
                
            logger.info("🏓 Testing WebSocket connection with ping...")
            
            # Send a simple ping
            await self.ws.ping()
            logger.info("✅ Ping sent successfully")
            
            # Wait a bit for potential pong response
            await asyncio.sleep(0.5)
            
            # Try to send a simple subscription to test
            test_sub = {
                "method": "subscribe",
                "subscription": {
                    "type": "allMids"
                }
            }
            
            logger.info(f"🧪 Sending test subscription: {json.dumps(test_sub)}")
            await self.ws.send(json.dumps(test_sub))
            logger.info("✅ Test subscription sent")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ WebSocket connection test failed: {e}")
            return False
