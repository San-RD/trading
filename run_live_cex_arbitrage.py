#!/usr/bin/env python3
"""
Live CEX↔CEX Arbitrage Bot Runner
Binance ↔ OKX with ETH/USDT pair

Capital: $100 total ($25 per exchange, $25 per leg)
Session: 2 hours
Risk: 1% max daily loss, 0.3% max per trade loss
Spread: 0.50% gross, ≥0.35% net after fees & slippage

⚠️  WARNING: This will use REAL MONEY! ⚠️

Usage: python run_live_cex_arbitrage.py
"""

import asyncio
import signal
import sys
import time
from datetime import datetime
from loguru import logger

from src.main import CrossExchangeArbBot
from src.config import Config


class LiveCEXArbitrageRunner:
    """Manages the live CEX↔CEX arbitrage execution."""
    
    def __init__(self):
        self.bot = None
        self.running = False
        self.start_time = None
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle interrupt signals."""
        logger.info(f"Received signal {signum}, stopping live arbitrage...")
        self.running = False
    
    async def run_live_arbitrage(self):
        """Run the live CEX↔CEX arbitrage."""
        try:
            logger.warning("🚨 LIVE CEX ARBITRAGE MODE - REAL MONEY WILL BE USED! 🚨")
            logger.info("=" * 80)
            logger.info("LIVE CEX ARBITRAGE CONFIRMATION REQUIRED:")
            logger.info("  Mode: LIVE CEX↔CEX ARBITRAGE (REAL MONEY)")
            logger.info("  Pair: ETH/USDT ONLY")
            logger.info("  Exchanges: Binance ↔ OKX")
            logger.info("  Capital: $100 total ($25 per exchange)")
            logger.info("  Position Size: $25 max per leg")
            logger.info("  Session Duration: 2 hours maximum")
            logger.info("  Spread Threshold: 0.50% gross, ≥0.35% net")
            logger.info("  Risk Profile: 1% max daily loss, 0.3% max per trade")
            logger.info("  Rebalancing: Auto 50% USDC / 50% ETH on each exchange")
            logger.info("=" * 80)
            
            # Final confirmation
            confirm = input("\n🚨 Type 'LIVE CEX' to confirm live arbitrage with real money: ")
            if confirm != "LIVE CEX":
                logger.info("❌ Live arbitrage cancelled by user")
                return
            
            logger.info("✅ Live CEX arbitrage confirmed!")
            logger.info("🚀 Starting Live CEX↔CEX Arbitrage Bot...")
            
            # Load configuration
            config = Config.load_from_file("config.yaml")
            
            # Verify live trading settings
            if config.exchanges.accounts["binance"].sandbox:
                logger.error("❌ Binance is in sandbox mode! Cannot trade live!")
                return
            
            if config.exchanges.accounts["okx"].sandbox:
                logger.error("❌ OKX is in sandbox mode! Cannot trade live!")
                return
            
            # Verify capital allocation
            logger.info("💰 Verifying capital allocation requirements...")
            logger.info("  Binance: $25 USDC + $25 ETH")
            logger.info("  OKX: $25 USDC + $25 ETH")
            logger.info("  Total: $100 capital")
            logger.info("  Position size: $25 per leg")
            
            # Initialize bot
            self.bot = CrossExchangeArbBot("config.yaml")
            self.start_time = time.time()
            self.running = True
            
            # Start the bot
            await self.bot.start()
            
            # Monitor live arbitrage session
            await self._monitor_live_session()
            
        except Exception as e:
            logger.error(f"❌ Live arbitrage failed: {e}")
            raise
        finally:
            await self._cleanup()
    
    async def _monitor_live_session(self):
        """Monitor the live arbitrage session."""
        logger.info("📊 Monitoring live CEX↔CEX arbitrage session...")
        
        while self.running:
            try:
                # Check if session should continue
                if not self.bot.session_manager.should_continue_session():
                    logger.info("⏰ Session ended naturally")
                    break
                
                # Log status every minute for live arbitrage
                if int(time.time()) % 60 == 0:
                    self.bot.session_manager.log_session_status()
                    
                    # Additional live arbitrage status
                    elapsed_hours = (time.time() - self.start_time) / 3600
                    logger.info(f"⏱️  Live arbitrage session: {elapsed_hours:.2f} hours elapsed")
                    
                    # Log current capital status
                    logger.info("💰 Current Capital Status:")
                    logger.info("  Position size limit: $25 per leg")
                    logger.info("  Max daily loss: $1 (1% of $100)")
                    logger.info("  Max per trade loss: $0.075 (0.3% of $25)")
                
                # Check for manual stop conditions
                elapsed_hours = (time.time() - self.start_time) / 3600
                if elapsed_hours >= 2.0:  # Stop after 2 hours max
                    logger.info("⏰ Maximum arbitrage session duration reached (2 hours)")
                    break
                
                await asyncio.sleep(30)  # Check every 30 seconds for live arbitrage
                
            except Exception as e:
                logger.error(f"Error in live session monitor: {e}")
                break
    
    async def _cleanup(self):
        """Clean up after live arbitrage."""
        try:
            if self.bot:
                await self.bot.stop()
            
            # Calculate final statistics
            if self.bot and self.bot.session_manager:
                summary = self.bot.session_manager.get_session_summary()
                
                logger.info("🎯 Live CEX↔CEX Arbitrage Session Complete!")
                logger.info("=" * 80)
                logger.info("Final Live Arbitrage Results:")
                logger.info(f"  Duration: {summary['session_duration_hours']:.2f} hours")
                logger.info(f"  Total trades: {summary['total_trades']}")
                logger.info(f"  Success rate: {summary['success_rate_pct']:.1f}%")
                logger.info(f"  Total PnL: ${summary['total_pnl']:.4f}")
                logger.info(f"  Average PnL per trade: ${summary['avg_pnl_per_trade']:.4f}")
                logger.info(f"  Opportunities detected: {summary['total_opportunities']}")
                logger.info("=" * 80)
                logger.info("💰 REAL MONEY WAS TRADED!")
                logger.info("📊 Check your exchange accounts for actual positions")
                logger.info("🔄 Verify 50% USDC / 50% ETH ratio on both exchanges")
                
                # Export results
                csv_file = await self.bot.session_manager.export_results_csv()
                if csv_file:
                    logger.info(f"📊 Live arbitrage results exported to: {csv_file}")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


async def main():
    """Main entry point."""
    runner = LiveCEXArbitrageRunner()
    
    try:
        await runner.run_live_arbitrage()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Live arbitrage error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Configure logging for live arbitrage
    logger.remove()
    logger.add(
        sys.stdout,
        format="<red>{time:HH:mm:ss}</red> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        "live_cex_arbitrage.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="1 day"
    )
    
    # Run the live CEX↔CEX arbitrage bot
    asyncio.run(main())
