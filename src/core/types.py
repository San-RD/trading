#!/usr/bin/env python3
"""
Shared types and data structures for the arbitrage bot.
This file breaks circular imports between modules.
"""

import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class ArbitrageDirection(Enum):
    """Direction of arbitrage trade."""
    LEFT_TO_RIGHT = "left_to_right"  # Buy on left, sell on right
    RIGHT_TO_LEFT = "right_to_left"  # Buy on right, sell on left


@dataclass
class ArbitrageOpportunity:
    """Detected arbitrage opportunity."""
    symbol: str
    direction: ArbitrageDirection
    left_exchange: str
    right_exchange: str
    
    # Prices
    buy_price: float
    sell_price: float
    
    # Quantities and sizing
    trade_size: float
    net_edge_bps: float
    spread_bps: float
    
    # Timestamps
    timestamp: int = 0
    
    # Optional fields with defaults
    notional_value: float = 0.0
    expected_profit_usdt: float = 0.0
    quotes_age_ms: int = 0
    confidence_score: float = 1.0
    expires_at: int = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        """Set default values after initialization."""
        if self.metadata is None:
            self.metadata = {}
        if self.notional_value == 0.0:
            self.notional_value = self.trade_size * self.buy_price
        if self.expected_profit_usdt == 0.0:
            self.expected_profit_usdt = self.notional_value * self.net_edge_bps / 10000
        if self.timestamp == 0:
            self.timestamp = int(time.time() * 1000)
        if self.expires_at == 0:
            self.expires_at = self.timestamp + 5000  # 5 second expiry


@dataclass
class ExecutionResult:
    """Result of trade execution."""
    success: bool
    opportunity: ArbitrageOpportunity
    left_order: Any  # OrderResult
    right_order: Any  # OrderResult
    execution_time_ms: int
    realized_pnl: float
    error: Optional[str] = None
