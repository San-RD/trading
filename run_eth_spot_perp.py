#!/usr/bin/env python3
"""
ETH Spot↔Perp Arbitrage Strategy Runner
Runs the ETH/USDC spot↔perp strategy between Binance and Hyperliquid.
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Loaded environment variables from .env file")
except ImportError:
    print("⚠️  python-dotenv not installed. Install with: pip install python-dotenv")
except Exception as e:
    print(f"⚠️  Error loading .env file: {e}")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.strategies.spot_perp.runner import SpotPerpRunner
from src.config import Config, RouteConfig


async def main():
    """Main entry point for ETH spot↔perp strategy."""
    try:
        # Load configuration from file
        config = Config.load_from_file("config.yaml")
        
        # Set up logging based on config
        log_level = getattr(logging, config.logging.level.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Also set loguru level
        from loguru import logger
        logger.remove()  # Remove default handler
        logger.add(sys.stderr, level=log_level, format='{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}')
        
        print(f"🔧 Logging level set to: {config.logging.level.upper()}")
        
        # DEBUG: Show what API keys are actually loaded
        print("🔍 DEBUG: Checking loaded API keys...")
        print(f"   Binance API Key: {config.exchanges.accounts['binance'].key[:20]}...")
        print(f"   Binance Secret: {config.exchanges.accounts['binance'].secret[:20]}...")
        print(f"   Binance Sandbox: {config.exchanges.accounts['binance'].sandbox}")
        print("=" * 60)
        
        # Create ETH/USDC route configuration
        route = RouteConfig(
            name="ETH_binance_spot__hl_perp",
            enabled=True,
            strategy_type="spot_perp",
            left={"ex": "binance", "type": "spot", "symbol": "ETH/USDC"},
            right={"ex": "hyperliquid", "type": "perp", "symbol": "ETH-PERP"}
        )
        
        # Create and start the strategy runner with the route
        runner = SpotPerpRunner(config, route)
        
        print("🚀 Starting ETH Spot↔Perp Arbitrage Strategy...")
        print(f"📊 Strategy: Binance ETH/USDC Spot ↔ Hyperliquid ETH-PERP")
        print(f"💰 Min Edge: {config.detector.min_edge_bps} bps")
        print(f"🔒 Risk Limit: ${config.risk.daily_notional_limit} daily notional")
        print(f"🪙 Trading Pair: {route.left['symbol']} ↔ {route.right['symbol']}")
        print("=" * 60)
        
        # Start the strategy
        await runner.start()
        
    except KeyboardInterrupt:
        print("\n⏹️  ETH strategy interrupted by user")
    except Exception as e:
        print(f"❌ Error running ETH strategy: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Run the ETH strategy
    asyncio.run(main())
