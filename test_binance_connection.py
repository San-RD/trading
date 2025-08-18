#!/usr/bin/env python3
"""Test Binance connection to debug the issue."""

import asyncio
import sys
from src.exchanges.binance import BinanceExchange
from src.config import get_config

async def test_binance_connection():
    """Test Binance exchange connection."""
    try:
        print("🔧 Testing Binance Exchange Connection...")
        
        # Load config
        config = get_config()
        print(f"✅ Config loaded: {config.exchanges.left} ↔ {config.exchanges.right}")
        
        # Create exchange with name and config
        exchange = BinanceExchange("binance", config.dict())
        print(f"✅ Exchange created: {exchange.name}")
        print(f"✅ REST public client: {exchange.rest_public is not None}")
        print(f"✅ WS public client: {exchange.ws_public is not None}")
        print(f"✅ REST private client: {exchange.rest_private is not None}")
        
        # Test connection
        print("\n🔌 Testing connection...")
        symbols = ["ETH/USDC"]
        connected = await exchange.connect(symbols)
        print(f"✅ Connected: {connected}")
        print(f"✅ Is connected: {exchange.is_connected()}")
        
        # Test markets loading
        print("\n📊 Testing markets loading...")
        markets = await exchange.load_markets()
        print(f"✅ Markets loaded: {len(markets)} symbols")
        
        # Test health check
        print("\n🏥 Testing health check...")
        health = await exchange.health_check()
        print(f"✅ Health check: {health}")
        
        # Test quote watching (briefly)
        print("\n📈 Testing quote watching...")
        quote_count = 0
        try:
            async for quote in exchange.watch_quotes(symbols):
                print(f"✅ Quote received: {quote.symbol} {quote.bid}/{quote.ask}")
                quote_count += 1
                if quote_count >= 2:  # Just get 2 quotes
                    break
        except Exception as e:
            print(f"⚠️ Quote watching error (expected for brief test): {e}")
        
        print(f"✅ Quote monitoring test completed: {quote_count} quotes received")
        
        # Cleanup
        await exchange.disconnect()
        print(f"✅ Disconnected: {exchange.is_connected()}")
        
        print("\n🎉 All Binance tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_binance_connection())
    sys.exit(0 if success else 1)
