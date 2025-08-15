"""Trading filters and precision handling for exchanges."""

from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal, ROUND_DOWN, ROUND_UP


@dataclass
class SymbolRule:
    """Trading rules for a symbol."""
    symbol: str
    base_asset: str
    quote_asset: str
    price_precision: int
    quantity_precision: int
    min_qty: float
    max_qty: float
    step_size: float
    min_notional: float
    max_notional: float
    min_price: float
    max_price: float
    tick_size: float
    status: str
    is_spot_trading_allowed: bool
    is_margin_trading_allowed: bool

    @classmethod
    def from_exchange_info(cls, symbol: str, info: Dict[str, Any]) -> "SymbolRule":
        """Create SymbolRule from exchange info."""
        return cls(
            symbol=symbol,
            base_asset=info.get('baseAsset', ''),
            quote_asset=info.get('quoteAsset', ''),
            price_precision=info.get('pricePrecision', 8),
            quantity_precision=info.get('quantityPrecision', 8),
            min_qty=float(info.get('minQty', '0')),
            max_qty=float(info.get('maxQty', '999999')),
            step_size=float(info.get('stepSize', '0.00000001')),
            min_notional=float(info.get('minNotional', '0')),
            max_notional=float(info.get('maxNotional', '999999')),
            min_price=float(info.get('minPrice', '0')),
            max_price=float(info.get('maxPrice', '999999')),
            tick_size=float(info.get('tickSize', '0.00000001')),
            status=info.get('status', 'INACTIVE'),
            is_spot_trading_allowed=info.get('isSpotTradingAllowed', False),
            is_margin_trading_allowed=info.get('isMarginTradingAllowed', False)
        )

    def round_price(self, price: float) -> float:
        """Round price to exchange precision."""
        if self.tick_size <= 0:
            return price
        
        # Round down to nearest tick size
        ticks = int(Decimal(str(price)) / Decimal(str(self.tick_size)))
        return float(ticks * Decimal(str(self.tick_size)))

    def round_qty(self, qty: float) -> float:
        """Round quantity to exchange precision."""
        if self.step_size <= 0:
            return qty
        
        # Round down to nearest step size
        steps = int(Decimal(str(qty)) / Decimal(str(self.step_size)))
        return float(steps * Decimal(str(self.step_size)))

    def enforce_min_notional(self, price: float, qty: float) -> Tuple[float, float]:
        """Enforce minimum notional by adjusting quantity if needed."""
        notional = price * qty
        
        if notional >= self.min_notional:
            return price, qty
        
        # Calculate minimum quantity needed
        min_qty = self.min_notional / price
        min_qty = self.round_qty(min_qty)
        
        # Ensure we don't exceed max quantity
        if min_qty > self.max_qty:
            raise ValueError(f"Minimum notional {self.min_notional} requires quantity {min_qty} > max {self.max_qty}")
        
        return price, min_qty

    def validate_order_params(self, side: str, price: float, qty: float) -> Tuple[bool, Optional[str]]:
        """Validate order parameters."""
        # Check quantity bounds
        if qty < self.min_qty:
            return False, f"Quantity {qty} < min {self.min_qty}"
        if qty > self.max_qty:
            return False, f"Quantity {qty} > max {self.max_qty}"
        
        # Check price bounds
        if price < self.min_price:
            return False, f"Price {price} < min {self.min_price}"
        if price > self.max_price:
            return False, f"Price {price} > max {self.max_price}"
        
        # Check notional
        notional = price * qty
        if notional < self.min_notional:
            return False, f"Notional {notional} < min {self.min_notional}"
        if notional > self.max_notional:
            return False, f"Notional {notional} > max {self.max_notional}"
        
        # Check step size
        if self.step_size > 0:
            remainder = qty % self.step_size
            if abs(remainder) > 1e-10:  # Small tolerance for floating point
                return False, f"Quantity {qty} not multiple of step size {self.step_size}"
        
        # Check tick size
        if self.tick_size > 0:
            remainder = price % self.tick_size
            if abs(remainder) > 1e-10:  # Small tolerance for floating point
                return False, f"Price {price} not multiple of tick size {self.tick_size}"
        
        return True, None


def round_price(rule: SymbolRule, price: float) -> float:
    """Round price according to symbol rule."""
    return rule.round_price(price)


def round_qty(rule: SymbolRule, qty: float) -> float:
    """Round quantity according to symbol rule."""
    return rule.round_qty(qty)


def enforce_min_notional(rule: SymbolRule, price: float, qty: float) -> Tuple[float, float]:
    """Enforce minimum notional according to symbol rule."""
    return rule.enforce_min_notional(price, qty)


def validate_order_params(rule: SymbolRule, side: str, price: float, qty: float) -> Tuple[bool, Optional[str]]:
    """Validate order parameters according to symbol rule."""
    return rule.validate_order_params(side, price, qty)


def get_taker_fee_bps(exchange: str, config: Dict[str, Any]) -> float:
    """Get taker fee in basis points for an exchange."""
    fees = config.get('fees', {}).get('taker_bps', {})
    return fees.get(exchange, fees.get('default', 10.0))


def get_maker_fee_bps(exchange: str, config: Dict[str, Any]) -> float:
    """Get maker fee in basis points for an exchange."""
    fees = config.get('fees', {}).get('maker_bps', {})
    return fees.get(exchange, fees.get('default', 8.0))
