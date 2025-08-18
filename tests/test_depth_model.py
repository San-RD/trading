"""Test depth model functionality."""

import pytest
from decimal import Decimal
from src.exchanges.depth_model import DepthModel, DepthLevel


class TestDepthLevel:
    """Test DepthLevel class."""
    
    def test_depth_level_creation(self):
        """Test depth level creation."""
        level = DepthLevel(100.0, 1.5)
        
        assert level.price == Decimal("100.0")
        assert level.quantity == Decimal("1.5")
    
    def test_depth_level_repr(self):
        """Test depth level string representation."""
        level = DepthLevel(100.0, 1.5)
        repr_str = repr(level)
        
        assert "DepthLevel" in repr_str
        assert "100.0" in repr_str
        assert "1.5" in repr_str


class TestDepthModel:
    """Test DepthModel class."""
    
    def test_depth_model_creation(self):
        """Test depth model creation."""
        model = DepthModel(enabled=True, levels=5)
        
        assert model.enabled is True
        assert model.levels == 5
        assert len(model._depth_cache) == 0
    
    def test_depth_model_disabled(self):
        """Test depth model when disabled."""
        model = DepthModel(enabled=False, levels=5)
        
        # Should return None for all operations
        assert model.get_effective_price("BTCUSDT", "buy", 1.0) is None
        assert model.estimate_slippage_bps("BTCUSDT", "buy", 1.0) == 0.0
        assert model.is_data_fresh("BTCUSDT") is False
    
    def test_update_depth(self):
        """Test depth data update."""
        model = DepthModel(enabled=True, levels=3)
        
        bids = [(100.0, 1.0), (99.0, 2.0), (98.0, 3.0)]
        asks = [(101.0, 1.0), (102.0, 2.0), (103.0, 3.0)]
        
        model.update_depth("BTCUSDT", bids, asks)
        
        assert "BTCUSDT" in model._depth_cache
        assert len(model._depth_cache["BTCUSDT"]["bids"]) == 3
        assert len(model._depth_cache["BTCUSDT"]["asks"]) == 3
        
        # Check bid levels
        bid_levels = model._depth_cache["BTCUSDT"]["bids"]
        assert bid_levels[0].price == Decimal("100.0")
        assert bid_levels[0].quantity == Decimal("1.0")
        assert bid_levels[1].price == Decimal("99.0")
        assert bid_levels[1].quantity == Decimal("2.0")
        
        # Check ask levels
        ask_levels = model._depth_cache["BTCUSDT"]["asks"]
        assert ask_levels[0].price == Decimal("101.0")
        assert ask_levels[0].quantity == Decimal("1.0")
        assert ask_levels[1].price == Decimal("102.0")
        assert ask_levels[1].quantity == Decimal("2.0")
    
    def test_get_effective_price_buy(self):
        """Test effective price calculation for buy orders."""
        model = DepthModel(enabled=True, levels=3)
        
        # Setup depth data
        bids = [(100.0, 1.0), (99.0, 2.0), (98.0, 3.0)]
        asks = [(101.0, 1.0), (102.0, 2.0), (103.0, 3.0)]
        model.update_depth("BTCUSDT", bids, asks)
        
        # Test small quantity (should fit in first level)
        effective_price = model.get_effective_price("BTCUSDT", "buy", 0.5)
        assert effective_price == 101.0
        
        # Test larger quantity (should span multiple levels)
        effective_price = model.get_effective_price("BTCUSDT", "buy", 2.5)
        expected_price = (101.0 * 1.0 + 102.0 * 1.5) / 2.5
        assert abs(effective_price - expected_price) < 0.01
    
    def test_get_effective_price_sell(self):
        """Test effective price calculation for sell orders."""
        model = DepthModel(enabled=True, levels=3)
        
        # Setup depth data
        bids = [(100.0, 1.0), (99.0, 2.0), (98.0, 3.0)]
        asks = [(101.0, 1.0), (102.0, 2.0), (103.0, 3.0)]
        model.update_depth("BTCUSDT", bids, asks)
        
        # Test small quantity (should fit in first level)
        effective_price = model.get_effective_price("BTCUSDT", "sell", 0.5)
        assert effective_price == 100.0
        
        # Test larger quantity (should span multiple levels)
        effective_price = model.get_effective_price("BTCUSDT", "sell", 2.5)
        expected_price = (100.0 * 1.0 + 99.0 * 1.5) / 2.5
        assert abs(effective_price - expected_price) < 0.01
    
    def test_get_effective_price_insufficient_depth(self):
        """Test effective price with insufficient depth."""
        model = DepthModel(enabled=True, levels=2)
        
        # Setup limited depth data
        bids = [(100.0, 1.0), (99.0, 1.0)]
        asks = [(101.0, 1.0), (102.0, 1.0)]
        model.update_depth("BTCUSDT", bids, asks)
        
        # Try to get price for quantity larger than available depth
        effective_price = model.get_effective_price("BTCUSDT", "buy", 5.0)
        assert effective_price is None
    
    def test_estimate_slippage_bps(self):
        """Test slippage estimation."""
        model = DepthModel(enabled=True, levels=3)
        
        # Setup depth data
        bids = [(100.0, 1.0), (99.0, 2.0), (98.0, 3.0)]
        asks = [(101.0, 1.0), (102.0, 2.0), (103.0, 3.0)]
        model.update_depth("BTCUSDT", bids, asks)
        
        # Test buy slippage
        slippage = model.estimate_slippage_bps("BTCUSDT", "buy", 2.5)
        assert slippage > 0  # Should have positive slippage
        
        # Test sell slippage
        slippage = model.estimate_slippage_bps("BTCUSDT", "sell", 2.5)
        assert slippage > 0  # Should have positive slippage
    
    def test_is_data_fresh(self):
        """Test data freshness checking."""
        model = DepthModel(enabled=True, levels=3)
        
        # Initially no data
        assert model.is_data_fresh("BTCUSDT") is False
        
        # Update data
        bids = [(100.0, 1.0)]
        asks = [(101.0, 1.0)]
        model.update_depth("BTCUSDT", bids, asks)
        
        # Should be fresh immediately after update
        assert model.is_data_fresh("BTCUSDT") is True
    
    def test_get_depth_summary(self):
        """Test depth summary generation."""
        model = DepthModel(enabled=True, levels=3)
        
        # Setup depth data
        bids = [(100.0, 1.0), (99.0, 2.0)]
        asks = [(101.0, 1.0), (102.0, 2.0)]
        model.update_depth("BTCUSDT", bids, asks)
        
        summary = model.get_depth_summary("BTCUSDT")
        
        assert summary is not None
        assert summary["symbol"] == "BTCUSDT"
        assert summary["bid_levels"] == 2
        assert summary["ask_levels"] == 2
        assert summary["total_bid_qty"] == 3.0
        assert summary["total_ask_qty"] == 3.0
        assert summary["spread_bps"] is not None
        assert summary["last_update"] > 0
    
    def test_get_depth_summary_no_data(self):
        """Test depth summary when no data available."""
        model = DepthModel(enabled=True, levels=3)
        
        summary = model.get_depth_summary("BTCUSDT")
        assert summary is None


if __name__ == "__main__":
    pytest.main([__file__])
