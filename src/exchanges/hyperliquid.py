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

    async def connect(self, symbols: List[str]) -> bool:
        """Connect to Hyperliquid exchange."""
        try:
            # Initialize HTTP session
            self.http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
            
            # Load markets
            await self.load_markets()
            
            # Connect WebSocket
            await self._connect_websocket()
            
            # Subscribe to market data
            await self._subscribe_market_data(symbols)
            
            self._connected = True
            logger.info(f"Hyperliquid connected with symbols {symbols}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Hyperliquid: {e}")
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
        """Connect to Hyperliquid WebSocket."""
        try:
            self.ws = await websockets.connect(self.ws_url)
            self.ws_connected = True
            logger.info("Hyperliquid WebSocket connected")
        except Exception as e:
            logger.error(f"Failed to connect to Hyperliquid WebSocket: {e}")
            raise

    async def _subscribe_market_data(self, symbols: List[str]):
        """Subscribe to market data for given symbols."""
        try:
            for symbol in symbols:
                # Clean symbol name (remove -PERP suffix for subscription)
                clean_symbol = symbol.replace("-PERP", "")
                
                # Subscribe to orderbook updates
                orderbook_sub = {
                    "method": "subscribe",
                    "subscription": {
                        "type": "orderbook",
                        "coin": clean_symbol
                    }
                }
                await self.ws.send(json.dumps(orderbook_sub))
                
                # Subscribe to ticker updates
                ticker_sub = {
                    "method": "subscribe", 
                    "subscription": {
                        "type": "ticker",
                        "coin": clean_symbol
                    }
                }
                await self.ws.send(json.dumps(ticker_sub))
                
                # Subscribe to trades
                trades_sub = {
                    "method": "subscribe",
                    "subscription": {
                        "type": "trades",
                        "coin": clean_symbol
                    }
                }
                await self.ws.send(json.dumps(trades_sub))
                
            logger.info(f"Subscribed to market data for {symbols}")
            
        except Exception as e:
            logger.error(f"Failed to subscribe to market data: {e}")
            raise

    async def watch_quotes(self, symbols: List[str]) -> AsyncGenerator[Quote, None]:
        """Watch real-time quotes for given symbols."""
        if not self.ws_connected:
            logger.error("WebSocket not connected")
            return
        
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    
                    # Handle different message types
                    if "data" in data:
                        # Handle orderbook update
                        if data.get("channel") == "orderbook":
                            await self._handle_orderbook_update(data["data"])
                        elif data.get("channel") == "ticker":
                            await self._handle_ticker_update(data["data"])
                    
                    # Yield updated quotes for requested symbols
                    for symbol in symbols:
                        clean_symbol = symbol.replace("-PERP", "")
                        if clean_symbol in self._tickers:
                            yield self._tickers[clean_symbol]
                            
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logger.error(f"Error processing WebSocket message: {e}")
                    
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            # Attempt reconnection
            await self._reconnect_websocket()

    async def _handle_orderbook_update(self, data: Dict):
        """Handle orderbook update from WebSocket."""
        try:
            symbol = data.get("coin", "")
            if not symbol:
                return
            
            # Convert to proper format and add -PERP suffix for consistency
            perp_symbol = f"{symbol}-PERP"
            
            bids = [(float(level[0]), float(level[1])) for level in data.get("bids", [])]
            asks = [(float(level[0]), float(level[1])) for level in data.get("asks", [])]
            
            self._orderbooks[perp_symbol] = OrderBook(
                venue=self.name,
                symbol=perp_symbol,
                bids=bids,
                asks=asks,
                ts_exchange=int(time.time() * 1000),
                ts_local=int(time.time() * 1000)
            )
            
        except Exception as e:
            logger.error(f"Error handling orderbook update: {e}")

    async def _handle_ticker_update(self, data: Dict):
        """Handle ticker update from WebSocket."""
        try:
            symbol = data.get("coin", "")
            if not symbol:
                return
            
            # Convert to proper format and add -PERP suffix for consistency
            perp_symbol = f"{symbol}-PERP"
            
            # Extract best bid/ask from orderbook
            orderbook = self._orderbooks.get(perp_symbol)
            if orderbook and orderbook.bids and orderbook.asks:
                best_bid = orderbook.bids[0][0]
                best_ask = orderbook.asks[0][0]
                best_bid_size = orderbook.bids[0][1]
                best_ask_size = orderbook.asks[0][1]
                
                self._tickers[perp_symbol] = Quote(
                    venue=self.name,
                    symbol=perp_symbol,
                    bid=best_bid,
                    ask=best_ask,
                    bid_size=best_bid_size,
                    ask_size=best_ask_size,
                    ts_exchange=int(time.time() * 1000),
                    ts_local=int(time.time() * 1000)
                )
                
        except Exception as e:
            logger.error(f"Error handling ticker update: {e}")

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

    async def _reconnect_websocket(self):
        """Reconnect WebSocket on error."""
        try:
            logger.info("Attempting WebSocket reconnection...")
            await self._connect_websocket()
            if hasattr(self, 'markets') and self.markets:
                await self._subscribe_market_data(list(self.markets.keys()))
            else:
                logger.warning("No markets loaded, skipping market data subscription")
        except Exception as e:
            logger.error(f"WebSocket reconnection failed: {e}")

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
