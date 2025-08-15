#!/usr/bin/env python3
"""
Live ETH/USDT Trading Runner for Cross-Exchange Arbitrage Bot

This script runs live trading with ETH/USDT pair only:
- Live trading mode (REAL MONEY)
- ETH/USDT pair only
- Conservative risk controls
- Enhanced safety checks
- Real-time monitoring

⚠️  WARNING: This will use REAL MONEY! ⚠️

Usage: python run_live_eth.py
"""

import asyncio
import signal
import sys
import time
from datetime import datetime
from loguru import logger

from src.main import CrossExchangeArbBot
from src.config import Config


class LiveETHTradingRunner:
    """Manages the live ETH/USDT trading execution."""
    
    def __init__(self):
        self.bot = None
        self.running = False
        self.start_time = None
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle interrupt signals."""
        logger.info(f"Received signal {signum}, stopping live trading...")
        self.running = False
    
    async def run_live_trading(self):
        """Run the live ETH/USDT trading."""
        try:
            logger.warning("🚨 LIVE TRADING MODE - REAL MONEY WILL BE USED! 🚨")
            logger.info("=" * 70)
            logger.info("LIVE TRADING CONFIRMATION REQUIRED:")
            logger.info("  Mode: LIVE TRADING (REAL MONEY)")
            logger.info("  Pair: ETH/USDT ONLY")
            logger.info("  Duration: 8 hours maximum")
            logger.info("  Position size: $200 max per leg")
            logger.info("  Spread threshold: 0.35% gross, 0.25% net")
            logger.info("  Max trades: 10 per session")
            logger.info("  Risk profile: Conservative but live")
            logger.info("  Exchanges: Binance ↔ OKX")
            logger.info("=" * 70)
            
            # Final confirmation
            confirm = input("\n🚨 Type 'LIVE' to confirm live trading with real money: ")
            if confirm != "LIVE":
                logger.info("❌ Live trading cancelled by user")
                return
            
            logger.info("✅ Live trading confirmed!")
            logger.info("🚀 Starting Live ETH/USDT Trading Bot...")
            
            # Load configuration
            config = Config.load_from_file("config.yaml")
            
            # Verify live trading settings
            if config.exchanges.accounts["binance"].sandbox:
                logger.error("❌ Binance is in sandbox mode! Cannot trade live!")
                return
            
            if config.exchanges.accounts["okx"].sandbox:
                logger.error("❌ OKX is in sandbox mode! Cannot trade live!")
                return
            
            # Initialize bot
            self.bot = CrossExchangeArbBot("config.yaml")
            self.start_time = time.time()
            self.running = True
            
            # Start the bot
            await self.bot.start()
            
            # Monitor live trading session
            await self._monitor_live_session()
            
        except Exception as e:
            logger.error(f"❌ Live trading failed: {e}")
            raise
        finally:
            await self._cleanup()
    
    async def _monitor_live_session(self):
        """Monitor the live trading session."""
        logger.info("📊 Monitoring live ETH/USDT trading session...")
        
        while self.running:
            try:
                # Check if session should continue
                if not self.bot.session_manager.should_continue_session():
                    logger.info("⏰ Session ended naturally")
                    break
                
                # Log status every 2 minutes for live trading
                if int(time.time()) % 120 == 0:
                    self.bot.session_manager.log_session_status()
                    
                    # Additional live trading status
                    elapsed_hours = (time.time() - self.start_time) / 3600
                    logger.info(f"⏱️  Live trading session: {elapsed_hours:.1f} hours elapsed")
                
                # Check for manual stop conditions
                elapsed_hours = (time.time() - self.start_time) / 3600
                if elapsed_hours >= 8.0:  # Stop after 8 hours max
                    logger.info("⏰ Maximum live trading duration reached")
                    break
                
                await asyncio.sleep(30)  # Check every 30 seconds for live trading
                
            except Exception as e:
                logger.error(f"Error in live session monitor: {e}")
                break
    
    async def _cleanup(self):
        """Clean up after live trading."""
        try:
            if self.bot:
                await self.bot.stop()
            
            # Calculate final statistics
            if self.bot and self.bot.session_manager:
                summary = self.bot.session_manager.get_session_summary()
                
                logger.info("🎯 Live ETH/USDT Trading Session Complete!")
                logger.info("=" * 70)
                logger.info("Final Live Trading Results:")
                logger.info(f"  Duration: {summary['session_duration_hours']:.1f} hours")
                logger.info(f"  Total trades: {summary['total_trades']}")
                logger.info(f"  Success rate: {summary['success_rate_pct']:.1f}%")
                logger.info(f"  Total PnL: ${summary['total_pnl']:.4f}")
                logger.info(f"  Average PnL per trade: ${summary['avg_pnl_per_trade']:.4f}")
                logger.info(f"  Opportunities detected: {summary['total_opportunities']}")
                logger.info("=" * 70)
                logger.info("💰 REAL MONEY WAS TRADED!")
                logger.info("📊 Check your exchange accounts for actual positions")
                
                # Export results
                csv_file = await self.bot.session_manager.export_results_csv()
                if csv_file:
                    logger.info(f"📊 Live trading results exported to: {csv_file}")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


async def main():
    """Main entry point."""
    runner = LiveETHTradingRunner()
    
    try:
        await runner.run_live_trading()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Live trading error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Configure logging for live trading
    logger.remove()
    logger.add(
        sys.stdout,
        format="<red>{time:HH:mm:ss}</red> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        "live_trading_eth.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="1 day"
    )
    
    # Run the live ETH/USDT trading bot
    asyncio.run(main())
