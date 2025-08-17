#!/usr/bin/env python3
"""Test OKX connection to debug the issue."""

import asyncio
import sys
from src.exchanges.okx import OKXExchange
from src.config import get_config

async def test_okx_connection():
    """Test OKX exchange connection."""
    try:
        print("🔧 Testing OKX Exchange Connection...")
        
        # Load config
        config = get_config()
        print(f"✅ Config loaded: {config.exchanges.left} ↔ {config.exchanges.right}")
        
        # Create exchange
        exchange = OKXExchange(config)
        print(f"✅ Exchange created: {exchange.name}")
        print(f"✅ REST client: {exchange.rest_client is not None}")
        print(f"✅ WS client: {exchange.ws_client is not None}")
        
        # Test connection
        print("\n🔌 Testing connection...")
        await exchange.connect()
        print(f"✅ Connected: {exchange.is_connected()}")
        
        # Test markets loading
        print("\n📊 Testing markets loading...")
        markets = await exchange.load_markets()
        print(f"✅ Markets loaded: {len(markets)} symbols")
        print(f"✅ Symbol rules: {len(exchange.symbol_rules)} rules")
        
        # Test health check
        print("\n🏥 Testing health check...")
        health = await exchange.health_check()
        print(f"✅ Health check: {health}")
        
        # Test quote watching (briefly)
        print("\n📈 Testing quote watching...")
        symbols = ["ETH/USDC"]
        quote_count = 0
        async for quote in exchange.watch_quotes(symbols):
            print(f"✅ Quote received: {quote.symbol} {quote.bid}/{quote.ask}")
            quote_count += 1
            if quote_count >= 2:  # Just get 2 quotes
                break
        
        print(f"✅ Quote monitoring working: {quote_count} quotes received")
        
        # Cleanup
        await exchange.disconnect()
        print(f"✅ Disconnected: {exchange.is_connected()}")
        
        print("\n🎉 All OKX tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_okx_connection())
    sys.exit(0 if success else 1)
