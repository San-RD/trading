#!/usr/bin/env python3
"""
BTC Spot↔Perp Arbitrage Strategy

This script runs ONLY the BTC/USDC spot↔perp strategy:
- Binance BTC/USDC spot ↔ Hyperliquid BTC-PERP perpetual
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.strategies.spot_perp.runner import SpotPerpRunner
from src.config import Config, RouteConfig


async def main():
    """Main entry point for BTC spot↔perp strategy."""
    try:
        # Load configuration from file
        config = Config.load_from_file("config.yaml")
        
        # Create BTC/USDC route configuration
        route = RouteConfig(
            name="BTC_binance_spot__hl_perp",
            enabled=True,
            strategy_type="spot_perp",
            left={"ex": "binance", "type": "spot", "symbol": "BTC/USDC"},
            right={"ex": "hyperliquid", "type": "perp", "symbol": "BTC-PERP"}
        )
        
        # Create and start the strategy runner with the route
        runner = SpotPerpRunner(config, route)
        
        print("🚀 Starting BTC Spot↔Perp Arbitrage Strategy...")
        print(f"📊 Strategy: Binance BTC/USDC Spot ↔ Hyperliquid BTC-PERP")
        print(f"💰 Min Edge: {config.detector.min_edge_bps} bps")
        print(f"🔒 Risk Limit: ${config.risk.daily_notional_limit} daily notional")
        print(f"🪙 Trading Pair: {route.left['symbol']} ↔ {route.right['symbol']}")
        print("=" * 60)
        
        # Start the strategy
        await runner.start()
        
    except KeyboardInterrupt:
        print("\n⏹️  BTC strategy interrupted by user")
    except Exception as e:
        print(f"❌ Error running BTC strategy: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Run the BTC strategy
    asyncio.run(main())
