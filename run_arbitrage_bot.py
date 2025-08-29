#!/usr/bin/env python3
"""
Multi-Strategy Arbitrage Bot Runner
Runs both ETH and BTC spot↔perp strategies simultaneously
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
from src.config import Config
from src.strategies.strategy_factory import StrategyFactory

async def main():
    """Main entry point for multi-strategy arbitrage bot."""
    try:
        # Load environment variables
        load_dotenv()
        print("✅ Loaded environment variables from .env file")
        
        # Load configuration
        config = Config.load_from_file("config.yaml")
        print("✅ Loaded configuration from config.yaml")
        
        # Get enabled routes
        enabled_routes = StrategyFactory.get_enabled_routes(config)
        if not enabled_routes:
            print("❌ No enabled routes found in configuration")
            return
        
        print("🚀 Starting Multi-Strategy Arbitrage Bot...")
        print("=" * 60)
        print("📊 Running ALL enabled strategies simultaneously:")
        for route in enabled_routes:
            print(f"   • {route.left['symbol']}: {route.left['ex']} {route.left['type']} ↔ {route.right['ex']} {route.right['type']}")
        print("=" * 60)
        
        # Create and start strategies for each route
        strategy_tasks = []
        for route in enabled_routes:
            try:
                strategy = StrategyFactory.create_strategy(route, config)
                if strategy:
                    print(f"✅ Created strategy for route: {route.name}")
                    # Start strategy in background
                    task = asyncio.create_task(strategy.start())
                    strategy_tasks.append(task)
                else:
                    print(f"❌ Failed to create strategy for route: {route.name}")
                    
            except Exception as e:
                print(f"❌ Error creating strategy for route {route.name}: {e}")
        
        if not strategy_tasks:
            print("❌ No strategies were successfully created")
            return
        
        print(f"🎯 Starting {len(strategy_tasks)} strategies...")
        
        # Wait for all strategies to complete
        await asyncio.gather(*strategy_tasks, return_exceptions=True)
        
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
