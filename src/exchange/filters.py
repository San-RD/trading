"""Trading filters and precision handling for exchanges."""

from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Dict, Any


class SymbolRule:
    """Trading rules for a specific symbol."""
    
    def __init__(self, symbol: str, rules: Dict[str, Any]):
        self.symbol = symbol
        self.base_asset = rules.get("baseAsset", "")
        self.quote_asset = rules.get("quoteAsset", "")
        
        # Precision rules
        self.price_precision = rules.get("pricePrecision", 8)
        self.quantity_precision = rules.get("quantityPrecision", 8)
        
        # Lot size rules
        self.min_qty = Decimal(str(rules.get("minQty", "0")))
        self.max_qty = Decimal(str(rules.get("maxQty", "999999")))
        self.step_size = Decimal(str(rules.get("stepSize", "0.00000001")))
        
        # Notional rules
        self.min_notional = Decimal(str(rules.get("minNotional", "0")))
        self.max_notional = Decimal(str(rules.get("maxNotional", "999999")))
        
        # Price filter
        self.min_price = Decimal(str(rules.get("minPrice", "0")))
        self.max_price = Decimal(str(rules.get("maxPrice", "999999")))
        self.tick_size = Decimal(str(rules.get("tickSize", "0.00000001")))
        
        # Status
        self.status = rules.get("status", "TRADING")
        self.is_spot_trading_allowed = rules.get("isSpotTradingAllowed", True)
        self.is_margin_trading_allowed = rules.get("isMarginTradingAllowed", False)
    
    def is_active(self) -> bool:
        """Check if symbol is active for trading."""
        return (
            self.status == "TRADING" and
            self.is_spot_trading_allowed
        )
    
    def __repr__(self) -> str:
        return f"SymbolRule({self.symbol}, precision={self.price_precision}/{self.quantity_precision})"


def round_price(rule: SymbolRule, price: float) -> Decimal:
    """Round price according to tick size and precision."""
    price_decimal = Decimal(str(price))
    
    # Round to tick size
    tick_size = rule.tick_size
    rounded = (price_decimal / tick_size).quantize(Decimal("1"), ROUND_DOWN) * tick_size
    
    # Apply precision limit
    precision = Decimal("10") ** (-rule.price_precision)
    rounded = rounded.quantize(precision, ROUND_DOWN)
    
    return rounded


def round_qty(rule: SymbolRule, qty: float) -> Decimal:
    """Round quantity according to step size and precision."""
    qty_decimal = Decimal(str(qty))
    
    # Round to step size
    step_size = rule.step_size
    rounded = (qty_decimal / step_size).quantize(Decimal("1"), ROUND_DOWN) * step_size
    
    # Apply precision limit
    precision = Decimal("10") ** (-rule.quantity_precision)
    rounded = rounded.quantize(precision, ROUND_DOWN)
    
    return rounded


def enforce_min_notional(rule: SymbolRule, price: float, qty: float) -> bool:
    """Check if price * qty meets minimum notional requirement."""
    price_decimal = Decimal(str(price))
    qty_decimal = Decimal(str(qty))
    
    notional = price_decimal * qty_decimal
    return notional >= rule.min_notional


def validate_order_params(rule: SymbolRule, side: str, price: float, qty: float) -> tuple[bool, str]:
    """Validate all order parameters against symbol rules."""
    # Check if symbol is active
    if not rule.is_active():
        return False, f"Symbol {rule.symbol} is not active for trading"
    
    # Check price range
    if price < rule.min_price or price > rule.max_price:
        return False, f"Price {price} is outside allowed range [{rule.min_price}, {rule.max_price}]"
    
    # Check quantity range
    if qty < rule.min_qty or qty > rule.max_qty:
        return False, f"Quantity {qty} is outside allowed range [{rule.min_qty}, {rule.max_qty}]"
    
    # Check step size
    step_size = rule.step_size
    if qty % step_size != 0:
        return False, f"Quantity {qty} is not a multiple of step size {step_size}"
    
    # Check minimum notional
    if not enforce_min_notional(rule, price, qty):
        return False, f"Notional {price * qty} is below minimum {rule.min_notional}"
    
    return True, "OK"
