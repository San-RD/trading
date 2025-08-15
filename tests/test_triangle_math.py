"""Test triangle discovery and edge calculation."""

import pytest
from decimal import Decimal

from src.core.triangle import Triangle, find_triangles, calculate_triangle_edge
from src.exchange.filters import SymbolRule


class TestTriangle:
    """Test Triangle class."""
    
    def test_triangle_creation(self):
        """Test triangle creation and properties."""
        triangle = Triangle("USDT", "ETH", "BTC", "ETHUSDT", "ETHBTC", "BTCUSDT")
        
        assert triangle.asset_a == "USDT"
        assert triangle.asset_b == "ETH"
        assert triangle.asset_c == "BTC"
        assert triangle.pair_ab == "ETHUSDT"
        assert triangle.pair_bc == "ETHBTC"
        assert triangle.pair_ca == "BTCUSDT"
        assert triangle.path_abc == ["ETHUSDT", "ETHBTC", "BTCUSDT"]
        assert triangle.path_acb == ["BTCUSDT", "ETHBTC", "ETHUSDT"]
    
    def test_get_pairs(self):
        """Test getting all pairs from triangle."""
        triangle = Triangle("USDT", "ETH", "BTC", "ETHUSDT", "ETHBTC", "BTCUSDT")
        pairs = triangle.get_pairs()
        
        assert len(pairs) == 3
        assert "ETHUSDT" in pairs
        assert "ETHBTC" in pairs
        assert "BTCUSDT" in pairs
    
    def test_get_assets(self):
        """Test getting all assets from triangle."""
        triangle = Triangle("USDT", "ETH", "BTC", "ETHUSDT", "ETHBTC", "BTCUSDT")
        assets = triangle.get_assets()
        
        assert len(assets) == 3
        assert "USDT" in assets
        assert "ETH" in assets
        assert "BTC" in assets


class TestTriangleDiscovery:
    """Test triangle discovery logic."""
    
    def test_find_triangles_simple(self):
        """Test finding triangles with simple market data."""
        # Create mock symbol rules
        symbol_rules = {
            "ETHUSDT": SymbolRule("ETHUSDT", {
                "baseAsset": "ETH",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "isSpotTradingAllowed": True
            }),
            "ETHBTC": SymbolRule("ETHBTC", {
                "baseAsset": "ETH",
                "quoteAsset": "BTC",
                "status": "TRADING",
                "isSpotTradingAllowed": True
            }),
            "BTCUSDT": SymbolRule("BTCUSDT", {
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "isSpotTradingAllowed": True
            })
        }
        
        triangles = find_triangles(symbol_rules, ["USDT", "BTC"])
        
        assert len(triangles) == 1
        triangle = triangles[0]
        assert triangle.asset_a == "USDT"
        assert triangle.asset_b == "ETH"
        assert triangle.asset_c == "BTC"
    
    def test_find_triangles_with_exclusions(self):
        """Test finding triangles with asset exclusions."""
        symbol_rules = {
            "ETHUSDT": SymbolRule("ETHUSDT", {
                "baseAsset": "ETH",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "isSpotTradingAllowed": True
            }),
            "ETHBTC": SymbolRule("ETHBTC", {
                "baseAsset": "ETH",
                "quoteAsset": "BTC",
                "status": "TRADING",
                "isSpotTradingAllowed": True
            }),
            "BTCUSDT": SymbolRule("BTCUSDT", {
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "isSpotTradingAllowed": True
            }),
            "BUSDUSDT": SymbolRule("BUSDUSDT", {
                "baseAsset": "BUSD",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "isSpotTradingAllowed": True
            })
        }
        
        triangles = find_triangles(symbol_rules, ["USDT", "BTC"], exclude_assets=["BUSD"])
        
        assert len(triangles) == 1
        # Should not include BUSD in any triangle
        for triangle in triangles:
            assert "BUSD" not in triangle.get_assets()


class TestEdgeCalculation:
    """Test edge calculation logic."""
    
    def test_calculate_triangle_edge_simple(self):
        """Test simple edge calculation."""
        triangle = Triangle("USDT", "ETH", "BTC", "ETHUSDT", "ETHBTC", "BTCUSDT")
        
        # Mock quotes
        quotes = {
            "ETHUSDT": {"bid": 2000.0, "ask": 2001.0},
            "ETHBTC": {"bid": 0.05, "ask": 0.0501},
            "BTCUSDT": {"bid": 40000.0, "ask": 40001.0}
        }
        
        # Mock symbol rules
        symbol_rules = {
            "ETHUSDT": SymbolRule("ETHUSDT", {
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
                "isSpotTradingAllowed": True
            }),
            "ETHBTC": SymbolRule("ETHBTC", {
                "baseAsset": "ETH",
                "quoteAsset": "BTC",
                "pricePrecision": 6,
                "quantityPrecision": 6,
                "minQty": "0.001",
                "maxQty": "1000",
                "stepSize": "0.001",
                "minNotional": "0.001",
                "maxNotional": "1000",
                "minPrice": "0.000001",
                "maxPrice": "1000",
                "tickSize": "0.000001",
                "status": "TRADING",
                "isSpotTradingAllowed": True
            }),
            "BTCUSDT": SymbolRule("BTCUSDT", {
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "pricePrecision": 2,
                "quantityPrecision": 6,
                "minQty": "0.000001",
                "maxQty": "1000",
                "stepSize": "0.000001",
                "minNotional": "10",
                "maxNotional": "1000000",
                "minPrice": "0.01",
                "maxPrice": "1000000",
                "tickSize": "0.01",
                "status": "TRADING",
                "isSpotTradingAllowed": True
            })
        }
        
        edge_bps, profit, details = calculate_triangle_edge(
            triangle, quotes, 10000, symbol_rules
        )
        
        # Should find some edge (positive or negative)
        assert isinstance(edge_bps, float)
        assert isinstance(profit, float)
        assert "direction" in details
        assert "path" in details
        assert "legs" in details


if __name__ == "__main__":
    pytest.main([__file__])
