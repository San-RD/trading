#!/usr/bin/env python3
"""
Main entry point for the arbitrage bot with parallel strategy support.
Supports multiple routes and strategy types without touching existing code.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def main():
    """Main entry point for the arbitrage bot."""
    try:
        from src.strategies.orchestrator import StrategyOrchestrator
        from src.config import Config
        
        print("🚀 Starting Arbitrage Bot with Parallel Strategy Support...")
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
