"""Data models for cross-exchange arbitrage bot."""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class Opportunity:
    """Arbitrage opportunity model."""
    id: Optional[int] = None
    timestamp: Optional[datetime] = None
    symbol: str = ""
    direction: str = ""
    edge_bps: float = 0.0
    notional: float = 0.0
    expected_profit: float = 0.0
    metadata: Optional[str] = None


@dataclass
class Order:
    """Order model."""
    id: Optional[int] = None
    order_id: str = ""
    venue: str = ""
    symbol: str = ""
    side: str = ""
    price: float = 0.0
    qty: float = 0.0
    status: str = ""
    ts_sent: Optional[int] = None
    ts_filled: Optional[int] = None
    metadata: Optional[str] = None


@dataclass
class Fill:
    """Fill model."""
    id: Optional[int] = None
    order_id: int = 0
    price: float = 0.0
    qty: float = 0.0
    fee_asset: str = ""
    fee: float = 0.0
    ts: Optional[int] = None


@dataclass
class Trade:
    """Trade model."""
    id: Optional[int] = None
    symbol: str = ""
    direction: str = ""
    pnl_usdt: float = 0.0
    edge_bps: float = 0.0
    latency_ms_total: int = 0
    mode: str = ""
    notes: Optional[str] = None
    ts: Optional[int] = None


@dataclass
class BalanceSnapshot:
    """Balance snapshot model."""
    id: Optional[int] = None
    venue: str = ""
    asset: str = ""
    free: float = 0.0
    total: float = 0.0
    ts: Optional[int] = None
