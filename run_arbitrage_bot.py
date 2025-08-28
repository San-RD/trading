#!/usr/bin/env python3
"""
Multi-Strategy Arbitrage Bot Orchestrator

This script runs ALL enabled strategies simultaneously:
- ETH/USDC: Binance spot ↔ Hyperliquid perp
- BTC/USDC: Binance spot ↔ Hyperliquid perp

For single strategies, use:
- run_eth_spot_perp.py    # ETH/USDC only
- run_btc_spot_perp.py    # BTC/USDC only
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def main():
    """Main entry point for the multi-strategy arbitrage bot."""
    try:
        from src.strategies.orchestrator import StrategyOrchestrator
        from src.config import Config
        
        print("🚀 Starting Multi-Strategy Arbitrage Bot...")
        print("=" * 60)
        print("📊 Running ALL enabled strategies simultaneously:")
        print("   • ETH/USDC: Binance Spot ↔ Hyperliquid Perp")
        print("   • BTC/USDC: Binance Spot ↔ Hyperliquid Perp")
        print("=" * 60)
        
        # Load configuration
        config = Config.load_from_file("config.yaml")
        
        # Create and start orchestrator
        orchestrator = StrategyOrchestrator(config)
        
        # Start the bot
        await orchestrator.start()
        
    except KeyboardInterrupt:
        print("\n🛑 Shutdown requested by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
