#!/usr/bin/env python3
"""
Check real Hyperliquid balance using wallet credentials.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def check_hyperliquid_balance():
    """Check real Hyperliquid balance."""
    print("🔍 Checking your real Hyperliquid balance...")
    
    try:
        from src.exchanges.hyperliquid import HyperliquidExchange
        
        # Your wallet configuration
        config = {
            'hyperliquid': {
                'wallet_address': '0x0D1F99f16c7D5047e8ECA4D50CC68C682dd53597',
                'private_key': '0x862fdec89b3bee9c9eddbca0eaceb23162d8787c',
                'chain': 'arbitrum',
                'initial_capital_usdc': 50.0
            }
        }
        
        # Create Hyperliquid exchange instance
        hl = HyperliquidExchange('hyperliquid', config)
        print(f"✅ Connected to Hyperliquid with wallet: {hl.wallet_address[:8]}...{hl.wallet_address[-6:]}")
        
        # Try to connect and fetch real balance
        print("\n📡 Connecting to Hyperliquid...")
        connected = await hl.connect(['ETH-PERP'])
        
        if connected:
            print("✅ Successfully connected to Hyperliquid")
            
            # Fetch real balance
            print("\n💰 Fetching your real balance...")
            balances = await hl.fetch_balances()
            
            if 'USDC' in balances:
                usdc_balance = balances['USDC']
                print(f"\n🎯 **Your Real Hyperliquid Balance:**")
                print(f"   💵 USDC: ${usdc_balance.free:.2f}")
                print(f"   📊 Total: ${usdc_balance.total:.2f}")
                print(f"   ⏰ Last Updated: {usdc_balance.ts}")
                
                # Check if it matches expected
                expected = 50.0
                actual = usdc_balance.free
                if abs(actual - expected) < 0.01:
                    print(f"\n✅ Balance matches expected: ${expected}")
                else:
                    print(f"\n⚠️  Balance differs from expected:")
                    print(f"   Expected: ${expected}")
                    print(f"   Actual: ${actual}")
                    print(f"   Difference: ${actual - expected:.2f}")
            else:
                print("❌ No USDC balance found")
                
            # Try to fetch positions
            print("\n📈 Fetching positions...")
            positions = await hl.fetch_positions('ETH-PERP')
            if positions:
                print(f"   ETH-PERP Position: {positions}")
            else:
                print("   No open positions")
                
            # Try to fetch funding rate
            print("\n📊 Fetching funding rate...")
            funding_rate = await hl.fetch_funding_rate('ETH-PERP')
            if funding_rate:
                print(f"   ETH-PERP Funding Rate: {funding_rate:.6f} ({funding_rate*100:.4f}%)")
            else:
                print("   Could not fetch funding rate")
                
        else:
            print("❌ Failed to connect to Hyperliquid")
            print("   This might be due to:")
            print("   - Network connectivity issues")
            print("   - API rate limits")
            print("   - Wallet authentication issues")
            
        # Clean up
        await hl.disconnect()
        
    except Exception as e:
        print(f"❌ Error checking balance: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

async def main():
    """Main function."""
    print("🚀 Hyperliquid Balance Checker")
    print("=" * 40)
    
    success = await check_hyperliquid_balance()
    
    if success:
        print("\n✅ Balance check completed!")
    else:
        print("\n❌ Balance check failed!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
