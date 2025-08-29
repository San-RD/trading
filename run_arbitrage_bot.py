
#!/usr/bin/env python3
"""
Main Arbitrage Bot Runner
Runs multiple arbitrage strategies in parallel based on configuration.
"""

import asyncio
import logging
import sys
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
sys.path.append(str(Path(__file__).parent / "src"))

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
