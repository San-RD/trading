#!/usr/bin/env python3
"""
Conservative Paper Trading Test Runner for Cross-Exchange Arbitrage Bot

This script runs a 2-3 hour paper trading test with strict risk controls:
- Maximum $100 per leg per trade
- 0.50% minimum gross spread, 0.35% net after fees & slippage
- Maximum 5 trades per session
- Automatic stop after 3 hours or risk limits
- CSV export of results
- Paper trading mode (no real money)

Usage: python run_paper_test.py
"""

import asyncio
import signal
import sys
import time
from datetime import datetime
from loguru import logger

from src.main import CrossExchangeArbBot
from src.config import Config


class PaperTestRunner:
    """Manages the paper trading test execution."""
    
    def __init__(self):
        self.bot = None
        self.running = False
        self.start_time = None
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle interrupt signals."""
        logger.info(f"Received signal {signum}, stopping paper test...")
        self.running = False
    
    async def run_test(self):
        """Run the paper trading test."""
        try:
            logger.info("🚀 Starting Conservative Paper Trading Test")
            logger.info("=" * 60)
            logger.info("Test Parameters:")
            logger.info("  Mode: PAPER TRADING (simulation)")
            logger.info("  Duration: 2-3 hours")
            logger.info("  Position size: $100 max per leg")
            logger.info("  Spread threshold: 0.50% gross, 0.35% net")
            logger.info("  Max trades: 5 per session")
            logger.info("  Target pairs: SOL/USDT, ETH/USDT")
            logger.info("  Risk profile: Conservative")
            logger.info("  No real money at risk")
            logger.info("=" * 60)
            
            # Load configuration
            config = Config.load_from_file("config.yaml")
            
            # Verify paper trading settings
            if not config.exchanges.accounts["binance"].sandbox:
                logger.warning("⚠️  Binance is NOT in sandbox mode! This will use real API keys")
            
            if not config.exchanges.accounts["okx"].sandbox:
                logger.warning("⚠️  OKX is NOT in sandbox mode! This will use real API keys")
            
            # Initialize bot
            self.bot = CrossExchangeArbBot("config.yaml")
            self.start_time = time.time()
            self.running = True
            
            # Start the bot
            await self.bot.start()
            
            # Monitor session
            await self._monitor_session()
            
        except Exception as e:
            logger.error(f"❌ Paper test failed: {e}")
            raise
        finally:
            await self._cleanup()
    
    async def _monitor_session(self):
        """Monitor the paper trading test session."""
        logger.info("📊 Monitoring paper trading test session...")
        
        while self.running:
            try:
                # Check if session should continue
                if not self.bot.session_manager.should_continue_session():
                    logger.info("⏰ Session ended naturally")
                    break
                
                # Log status every 5 minutes
                if int(time.time()) % 300 == 0:
                    self.bot.session_manager.log_session_status()
                
                # Check for manual stop conditions
                elapsed_hours = (time.time() - self.start_time) / 3600
                if elapsed_hours >= 3.5:  # Stop after 3.5 hours max
                    logger.info("⏰ Maximum test duration reached")
                    break
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in session monitor: {e}")
                break
    
    async def _cleanup(self):
        """Clean up after the test."""
        try:
            if self.bot:
                await self.bot.stop()
            
            # Calculate final statistics
            if self.bot and self.bot.session_manager:
                summary = self.bot.session_manager.get_session_summary()
                
                logger.info("🎯 Paper Trading Test Complete!")
                logger.info("=" * 60)
                logger.info("Final Results:")
                logger.info(f"  Duration: {summary['session_duration_hours']:.1f} hours")
                logger.info(f"  Total trades: {summary['total_trades']}")
                logger.info(f"  Success rate: {summary['success_rate_pct']:.1f}%")
                logger.info(f"  Total PnL: ${summary['total_pnl']:.4f}")
                logger.info(f"  Average PnL per trade: ${summary['avg_pnl_per_trade']:.4f}")
                logger.info(f"  Opportunities detected: {summary['total_opportunities']}")
                logger.info("=" * 60)
                logger.info("📝 Note: This was a paper trading simulation")
                logger.info("📝 No real money was traded or lost")
                
                # Export results
                csv_file = await self.bot.session_manager.export_results_csv()
                if csv_file:
                    logger.info(f"📊 Results exported to: {csv_file}")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


async def main():
    """Main entry point."""
    runner = PaperTestRunner()
    
    try:
        await runner.run_test()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Paper test error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Configure logging
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        "paper_test.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="1 day"
    )
    
    # Run the paper trading test
    asyncio.run(main())
