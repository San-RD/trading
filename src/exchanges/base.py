"""Base exchange interface for cross-exchange arbitrage."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, AsyncGenerator
from decimal import Decimal
from dataclasses import dataclass


@dataclass
class Quote:
    """Market quote data."""
    venue: str
    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    ts_exchange: int
    ts_local: int

    @property
    def spread_bps(self) -> float:
        """Calculate spread in basis points."""
        if self.bid <= 0 or self.ask <= 0:
            return float('inf')
        return ((self.ask - self.bid) / self.bid) * 10000

    @property
    def mid_price(self) -> float:
        """Calculate mid price."""
        return (self.bid + self.ask) / 2


@dataclass
class OrderBook:
    """Order book data."""
    venue: str
    symbol: str
    bids: List[tuple[float, float]]  # (price, size)
    asks: List[tuple[float, float]]  # (price, size)
    ts_exchange: int
    ts_local: int


@dataclass
class Balance:
    """Account balance."""
    asset: str
    free: float
    total: float
    ts: int


@dataclass
class OrderResult:
    """Order execution result."""
    success: bool
    order_id: Optional[str] = None
    filled_qty: float = 0.0
    avg_price: float = 0.0
    fee_asset: str = ""
    fee_amount: float = 0.0
    error: Optional[str] = None
    latency_ms: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class BaseExchange(ABC):
    """Base exchange interface."""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self._connected = False
        self._last_update = 0

    @abstractmethod
    async def connect(self, symbols: List[str]) -> bool:
        """Connect to the exchange."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the exchange."""
        pass

    @abstractmethod
    async def load_markets(self) -> Dict[str, Any]:
        """Load exchange markets and trading rules."""
        pass

    @abstractmethod
    async def watch_quotes(self, symbols: List[str]) -> AsyncGenerator[Quote, None]:
        """Watch real-time quotes for given symbols."""
        pass

    @abstractmethod
    async def fetch_order_book(self, symbol: str, limit: int = 10) -> Optional[OrderBook]:
        """Fetch order book for a symbol."""
        pass

    @abstractmethod
    async def place_order(self, symbol: str, side: str, order_type: str,
                         amount: float, price: Optional[float] = None,
                         params: Optional[Dict] = None) -> OrderResult:
        """Place an order on the exchange."""
        pass

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order."""
        pass

    @abstractmethod
    async def fetch_balances(self) -> Dict[str, Balance]:
        """Fetch account balances."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Perform health check."""
        pass
    def is_connected(self) -> bool:
        """Check if exchange is connected."""
        return self._connected

    def get_last_update(self) -> int:
        """Get timestamp of last update."""
        return self._last_update

    def get_taker_fee_bps(self) -> float:
        """Get taker fee in basis points."""
        return self.config.get('taker_fee_bps', 10.0)

    def get_maker_fee_bps(self) -> float:
        """Get maker fee in basis points."""
        return self.config.get('maker_fee_bps', 8.0)

