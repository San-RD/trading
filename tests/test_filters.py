"""Test trading filters and precision handling."""

import pytest
from decimal import Decimal

from src.exchanges.filters import SymbolRule, round_price, round_qty, enforce_min_notional, validate_order_params


class TestSymbolRule:
    """Test SymbolRule class."""
    
    def test_symbol_rule_creation(self):
        """Test symbol rule creation."""
        rules = {
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "pricePrecision": 2,
            "quantityPrecision": 6,
            "minQty": "0.001",
            "maxQty": "1000",
            "stepSize": "0.001",
            "minNotional": "10",
            "maxNotional": "1000000",
            "minPrice": "0.01",
            "maxPrice": "1000000",
            "tickSize": "0.01",
            "status": "TRADING",
            "isSpotTradingAllowed": True,
            "isMarginTradingAllowed": False
        }
        
        rule = SymbolRule("ETHUSDT", rules)
        
        assert rule.symbol == "ETHUSDT"
        assert rule.base_asset == "ETH"
        assert rule.quote_asset == "USDT"
        assert rule.price_precision == 2
        assert rule.quantity_precision == 6
        assert rule.min_qty == Decimal("0.001")
        assert rule.max_qty == Decimal("1000")
        assert rule.step_size == Decimal("0.001")
        assert rule.min_notional == Decimal("10")
        assert rule.max_notional == Decimal("1000000")
        assert rule.min_price == Decimal("0.01")
        assert rule.max_price == Decimal("1000000")
        assert rule.tick_size == Decimal("0.01")
        assert rule.status == "TRADING"
        assert rule.is_spot_trading_allowed is True
        assert rule.is_margin_trading_allowed is False
    
    def test_is_active(self):
        """Test active status checking."""
        # Active rule
        active_rules = {
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "status": "TRADING",
            "isSpotTradingAllowed": True
        }
        rule = SymbolRule("ETHUSDT", active_rules)
        assert rule.is_active() is True
        
        # Inactive rule
        inactive_rules = {
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "status": "BREAK",
            "isSpotTradingAllowed": True
        }
        rule = SymbolRule("ETHUSDT", inactive_rules)
        assert rule.is_active() is False


class TestPriceRounding:
    """Test price rounding functionality."""
    
    def test_round_price_basic(self):
        """Test basic price rounding."""
        rules = {
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "tickSize": "0.01"
        }
        rule = SymbolRule("ETHUSDT", rules)
        
        # Test rounding down
        rounded = round_price(rule, 123.456)
        assert rounded == Decimal("123.45")
        
        # Test rounding to tick size
        rounded = round_price(rule, 123.457)
        assert rounded == Decimal("123.45")
    
    def test_round_price_precision(self):
        """Test price rounding with precision limits."""
        rules = {
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "pricePrecision": 2,
            "tickSize": "0.01"
        }
        rule = SymbolRule("ETHUSDT", rules)
        
        rounded = round_price(rule, 123.456789)
        assert rounded == Decimal("123.45")


class TestQuantityRounding:
    """Test quantity rounding functionality."""
    
    def test_round_qty_basic(self):
        """Test basic quantity rounding."""
        rules = {
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "stepSize": "0.001"
        }
        rule = SymbolRule("ETHUSDT", rules)
        
        # Test rounding down
        rounded = round_qty(rule, 1.2345)
        assert rounded == Decimal("1.234")
        
        # Test rounding to step size
        rounded = round_qty(rule, 1.2347)
        assert rounded == Decimal("1.234")
    
    def test_round_qty_precision(self):
        """Test quantity rounding with precision limits."""
        rules = {
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "quantityPrecision": 6,
            "stepSize": "0.001"
        }
        rule = SymbolRule("ETHUSDT", rules)
        
        rounded = round_qty(rule, 1.23456789)
        assert rounded == Decimal("1.234")


class TestMinNotional:
    """Test minimum notional validation."""
    
    def test_enforce_min_notional(self):
        """Test minimum notional enforcement."""
        rules = {
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "minNotional": "10"
        }
        rule = SymbolRule("ETHUSDT", rules)
        
        # Valid notional
        assert enforce_min_notional(rule, 2000.0, 0.01) is True  # 20 USDT
        
        # Invalid notional
        assert enforce_min_notional(rule, 2000.0, 0.001) is False  # 2 USDT


class TestOrderValidation:
    """Test order parameter validation."""
    
    def test_validate_order_params_valid(self):
        """Test valid order parameters."""
        rules = {
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "status": "TRADING",
            "isSpotTradingAllowed": True,
            "minPrice": "0.01",
            "maxPrice": "1000000",
            "minQty": "0.001",
            "maxQty": "1000",
            "stepSize": "0.001",
            "minNotional": "10"
        }
        rule = SymbolRule("ETHUSDT", rules)
        
        is_valid, message = validate_order_params(rule, "buy", 2000.0, 0.01)
        assert is_valid is True
        assert message == "OK"
    
    def test_validate_order_params_inactive(self):
        """Test validation with inactive symbol."""
        rules = {
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "status": "BREAK",
            "isSpotTradingAllowed": True
        }
        rule = SymbolRule("ETHUSDT", rules)
        
        is_valid, message = validate_order_params(rule, "buy", 2000.0, 0.01)
        assert is_valid is False
        assert "not active" in message
    
    def test_validate_order_params_price_range(self):
        """Test price range validation."""
        rules = {
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "status": "TRADING",
            "isSpotTradingAllowed": True,
            "minPrice": "1000",
            "maxPrice": "5000",
            "minQty": "0.001",
            "maxQty": "1000",
            "stepSize": "0.001",
            "minNotional": "10"
        }
        rule = SymbolRule("ETHUSDT", rules)
        
        # Price too low
        is_valid, message = validate_order_params(rule, "buy", 500.0, 0.01)
        assert is_valid is False
        assert "outside allowed range" in message
        
        # Price too high
        is_valid, message = validate_order_params(rule, "buy", 10000.0, 0.01)
        assert is_valid is False
        assert "outside allowed range" in message
    
    def test_validate_order_params_quantity_range(self):
        """Test quantity range validation."""
        rules = {
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "status": "TRADING",
            "isSpotTradingAllowed": True,
            "minPrice": "0.01",
            "maxPrice": "1000000",
            "minQty": "0.01",
            "maxQty": "10",
            "stepSize": "0.01",
            "minNotional": "10"
        }
        rule = SymbolRule("ETHUSDT", rules)
        
        # Quantity too low
        is_valid, message = validate_order_params(rule, "buy", 2000.0, 0.001)
        assert is_valid is False
        assert "outside allowed range" in message
        
        # Quantity too high
        is_valid, message = validate_order_params(rule, "buy", 2000.0, 100.0)
        assert is_valid is False
        assert "outside allowed range" in message
    
    def test_validate_order_params_step_size(self):
        """Test step size validation."""
        rules = {
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "status": "TRADING",
            "isSpotTradingAllowed": True,
            "minPrice": "0.01",
            "maxPrice": "1000000",
            "minQty": "0.001",
            "maxQty": "1000",
            "stepSize": "0.01",
            "minNotional": "10"
        }
        rule = SymbolRule("ETHUSDT", rules)
        
        # Invalid step size
        is_valid, message = validate_order_params(rule, "buy", 2000.0, 0.015)
        assert is_valid is False
        assert "not a multiple of step size" in message


if __name__ == "__main__":
    pytest.main([__file__])
