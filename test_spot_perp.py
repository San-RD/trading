#!/usr/bin/env python3
"""
Test script for the Spot↔Perp arbitrage strategy.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def test_components():
    """Test all the strategy components."""
    print("🧪 Testing Spot↔Perp Strategy Components...")
    
    try:
        # Test 1: Import Hyperliquid exchange
        print("1. Testing Hyperliquid exchange...")
        from src.exchanges.hyperliquid import HyperliquidExchange
        
        config = {
            'hyperliquid': {
                'wallet_address': '0x0D1F99f16c7D5047e8ECA4D50CC68C682dd53597',
                'private_key': '0x862fdec89b3bee9c9eddbca0eaceb23162d8787c',
                'chain': 'arbitrum',
                'initial_capital_usdc': 50.0
            }
        }
        
        hl = HyperliquidExchange('hyperliquid', config)
        print(f"   ✅ Hyperliquid created with wallet: {hl.wallet_address[:8]}...{hl.wallet_address[-6:]}")
        print(f"   ✅ Initial capital: ${hl.initial_capital}")
        
        # Test 2: Import strategy components
        print("2. Testing strategy components...")
        from src.strategies.spot_perp.detector import SpotPerpDetector
        from src.strategies.spot_perp.planner import SpotPerpPlanner
        from src.strategies.spot_perp.runner import SpotPerpRunner
        
        print("   ✅ Detector imported")
        print("   ✅ Planner imported") 
        print("   ✅ Runner imported")
        
        # Test 3: Import Telegram notifier
        print("3. Testing Telegram notifier...")
        from src.notify.telegram_readonly import TelegramReadOnlyNotifier
        
        print("   ✅ Telegram notifier imported")
        
        # Test 4: Test mock balance
        print("4. Testing mock balance...")
        balances = await hl.fetch_balances()
        if 'USDC' in balances:
            print(f"   ✅ USDC balance: ${balances['USDC'].free}")
        else:
            print("   ⚠️  No USDC balance found")
        
        print("\n🎉 All components working! Ready to run strategy.")
        return True
        
    except Exception as e:
        print(f"❌ Error testing components: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function."""
    success = await test_components()
    if success:
        print("\n🚀 Ready to start Spot↔Perp strategy!")
        print("   Run: python run_spot_perp_strategy.py")
    else:
        print("\n❌ Some components failed. Check the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
