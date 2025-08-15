"""Sample market data for testing the trading bot."""

# Sample quotes for testing triangle calculations
SAMPLE_QUOTES = {
    "ETHUSDT": {
        "bid": 2000.0,
        "ask": 2001.0,
        "ts": 1640995200000,
        "bid_volume": 10.5,
        "ask_volume": 8.2
    },
    "ETHBTC": {
        "bid": 0.05,
        "ask": 0.0501,
        "ts": 1640995200000,
        "bid_volume": 100.0,
        "ask_volume": 95.0
    },
    "BTCUSDT": {
        "bid": 40000.0,
        "ask": 40001.0,
        "ts": 1640995200000,
        "bid_volume": 2.5,
        "ask_volume": 2.3
    },
    "ADAUSDT": {
        "bid": 1.20,
        "ask": 1.201,
        "ts": 1640995200000,
        "bid_volume": 10000.0,
        "ask_volume": 9500.0
    },
    "ADABTC": {
        "bid": 0.00003,
        "ask": 0.0000301,
        "ts": 1640995200000,
        "bid_volume": 500000.0,
        "ask_volume": 480000.0
    }
}

# Sample symbol rules for testing
SAMPLE_SYMBOL_RULES = {
    "ETHUSDT": {
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
    },
    "ETHBTC": {
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
        "isSpotTradingAllowed": True,
        "isMarginTradingAllowed": False
    },
    "BTCUSDT": {
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
        "isSpotTradingAllowed": True,
        "isMarginTradingAllowed": False
    }
}

# Sample profitable triangle for testing
SAMPLE_TRIANGLE = {
    "asset_a": "USDT",
    "asset_b": "ETH", 
    "asset_c": "BTC",
    "pair_ab": "ETHUSDT",
    "pair_bc": "ETHBTC",
    "pair_ca": "BTCUSDT",
    "expected_edge_bps": 12.5,
    "expected_profit": 0.125
}

# Sample execution result for testing
SAMPLE_EXECUTION_RESULT = {
    "success": True,
    "opportunity": SAMPLE_TRIANGLE,
    "orders": [
        {
            "pair": "ETHUSDT",
            "side": "buy",
            "price": 2001.0,
            "quantity": 0.005,
            "status": "filled",
            "order_id": "test_order_1",
            "filled_qty": 0.005,
            "avg_price": 2001.0,
            "timestamp": 1640995200
        },
        {
            "pair": "ETHBTC",
            "side": "sell",
            "price": 0.05,
            "quantity": 0.005,
            "status": "filled",
            "order_id": "test_order_2",
            "filled_qty": 0.005,
            "avg_price": 0.05,
            "timestamp": 1640995200
        },
        {
            "pair": "BTCUSDT",
            "side": "sell",
            "price": 40000.0,
            "quantity": 0.00025,
            "status": "filled",
            "order_id": "test_order_3",
            "filled_qty": 0.00025,
            "avg_price": 40000.0,
            "timestamp": 1640995200
        }
    ],
    "realized_pnl": 0.125,
    "execution_time_ms": 45.2,
    "error": None
}
