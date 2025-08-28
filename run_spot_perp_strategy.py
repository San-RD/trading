#!/usr/bin/env python3
"""
Entry point for the Spot↔Perp arbitrage strategy.

This script runs the new spot↔perp strategy without affecting the existing spot↔spot logic.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.strategies.spot_perp.runner import SpotPerpRunner
from src.config import Config


async def main():
    """Main entry point for the spot↔perp strategy."""
    try:
        # Load configuration from file
        config = Config.load_from_file("config.yaml")
        
        # Create and start the strategy runner
        runner = SpotPerpRunner(config)
        
        print("🚀 Starting Spot↔Perp Arbitrage Strategy...")
        print(f"📊 Strategy: Binance Spot ↔ Hyperliquid Perp")
        print(f"💰 Min Edge: {config.detector.min_edge_bps} bps")
        print(f"🔒 Risk Limit: ${config.risk.daily_notional_limit} daily notional")
        print(f"🪙 Supported Pairs: ETH/USDC, BTC/USDC")
        print("=" * 50)
        
        # Start the strategy
        await runner.start()
        
    except KeyboardInterrupt:
        print("\n⏹️  Strategy interrupted by user")
    except Exception as e:
        print(f"❌ Error running strategy: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Run the strategy
    asyncio.run(main())
