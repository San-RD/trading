#!/usr/bin/env python3
"""
Live CEX<->CEX Arbitrage Bot Runner
Dynamically configured from config.yaml

WARNING: This will use REAL MONEY!

Usage: python run_live_cex_arbitrage.py [--yes]
"""

import asyncio
import signal
import sys
import time
import os
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
        self.config = None
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle interrupt signals."""
        logger.info(f"Received signal {signum}, stopping live arbitrage...")
        self.running = False
    
    def _get_capital_info(self):
        """Get capital information from config."""
        if not self.config:
            return {}
        
        # Calculate total capital based on notional limits
        daily_limit = getattr(self.config.risk, 'daily_notional_limit', 1000.0)
        max_trades = self.config.risk.max_trades_per_day
        avg_trade_size = daily_limit / max_trades if max_trades > 0 else daily_limit
        
        return {
            'daily_limit': daily_limit,
            'max_trades': max_trades,
            'avg_trade_size': avg_trade_size,
            'max_loss_pct': getattr(self.config.risk, 'max_daily_loss_pct', 1.0),
            'max_trade_loss_pct': self.config.risk.max_loss_per_trade_pct
        }
    
    def _get_session_info(self):
        """Get session information from config."""
        if not self.config:
            return {}
        
        return {
            'max_duration_min': getattr(self.config.session, 'max_duration_min', 90),
            'max_trades': getattr(self.config.session, 'max_trades', 10),
            'auto_stop': self.config.session.auto_stop,
            'target_pairs': self.config.session.target_pairs
        }
    
    def _get_detection_info(self):
        """Get detection parameters from config."""
        if not self.config:
            return {}
        
        # Safely get realistic_trading config
        realistic_config = getattr(self.config, 'realistic_trading', None)
        min_net_edge = 0.0
        if realistic_config:
            min_net_edge = getattr(realistic_config, 'min_net_edge_after_slippage', 0.0)
        
        return {
            'min_edge_bps': self.config.detector.min_edge_bps,
            'max_spread_bps': self.config.detector.max_spread_bps,
            'max_notional': getattr(self.config.detector, 'max_notional_usdt', 25.0),
            'min_net_edge': min_net_edge
        }
    
    async def run_live_arbitrage(self):
        """Run the live CEX↔CEX arbitrage."""
        try:
            # Load configuration first
            self.config = Config.load_from_file("config.yaml")
            
            # Get dynamic configuration values
            capital_info = self._get_capital_info()
            session_info = self._get_session_info()
            detection_info = self._get_detection_info()
            
            logger.warning("LIVE CEX ARBITRAGE MODE - REAL MONEY WILL BE USED!")
            logger.info("=" * 80)
            logger.info("LIVE CEX ARBITRAGE CONFIRMATION REQUIRED:")
            logger.info("  Mode: LIVE CEX<->CEX ARBITRAGE (REAL MONEY)")
            logger.info(f"  Pairs: {', '.join(session_info.get('target_pairs', ['ETH/USDC']))}")
            logger.info("  Exchanges: Binance <-> OKX")
            logger.info(f"  Daily Notional Limit: ${capital_info.get('daily_limit', 0):,.0f}")
            logger.info(f"  Max Trades Per Day: {capital_info.get('max_trades', 0)}")
            logger.info(f"  Max Position Size: ${detection_info.get('max_notional', 0)} per leg")
            logger.info(f"  Session Duration: {session_info.get('max_duration_min', 0)} minutes maximum")
            logger.info(f"  Min Edge Required: {detection_info.get('min_edge_bps', 0)} bps (0.{detection_info.get('min_edge_bps', 0)/100:.2f}%)")
            logger.info(f"  Max Spread Ignore: {detection_info.get('max_spread_bps', 0)} bps (ignore markets wider than {detection_info.get('max_spread_bps', 0)/100:.2f}%)")
            if detection_info.get('min_net_edge', 0) > 0:
                logger.info(f"  Net Edge After Slippage: {detection_info.get('min_net_edge', 0)} bps minimum")
            elif detection_info.get('min_net_edge', 0) < 0:
                logger.info(f"  Net Edge After Slippage: {detection_info.get('min_net_edge', 0)} bps (allows small losses)")
            logger.info(f"  Risk Profile: {capital_info.get('max_loss_pct', 0)}% max daily loss, {capital_info.get('max_trade_loss_pct', 0)}% max per trade")
            logger.info("=" * 80)
            
            # Final confirmation
            if "--yes" in sys.argv or os.environ.get("LIVE_CEX_CONFIRM") == "1":
                confirm = "LIVE CEX"
            else:
                confirm = input("\nType 'LIVE CEX' to confirm live arbitrage with real money: ")
            if confirm != "LIVE CEX":
                logger.info("Live arbitrage cancelled by user")
                return
            
            logger.info("Live CEX arbitrage confirmed!")
            logger.info("Starting Live CEX<->CEX Arbitrage Bot...")
            
            # Verify live trading settings
            if self.config.exchanges.accounts["binance"].sandbox:
                logger.error("Binance is in sandbox mode! Cannot trade live!")
                return
            
            if self.config.exchanges.accounts["okx"].sandbox:
                logger.error("OKX is in sandbox mode! Cannot trade live!")
                return
            
            # Verify capital allocation
            logger.info("Verifying capital allocation requirements...")
            max_notional = detection_info.get('max_notional', 0)
            logger.info(f"  Binance: ${max_notional} USDC + ${max_notional} ETH")
            logger.info(f"  OKX: ${max_notional} USDC + ${max_notional} ETH")
            logger.info(f"  Daily limit: ${capital_info.get('daily_limit', 0):,.0f} total notional")
            logger.info(f"  Position size: ${max_notional} per leg")
            
            # Initialize bot
            self.bot = CrossExchangeArbBot("config.yaml")
            self.start_time = time.time()
            self.running = True
            
            # Start the bot
            await self.bot.start()
            
            # Monitor live arbitrage session
            await self._monitor_live_session()
            
        except Exception as e:
            logger.error(f"Live arbitrage failed: {e}")
            raise
        finally:
            await self._cleanup()
    
    async def _monitor_live_session(self):
        """Monitor the live arbitrage session."""
        logger.info("Monitoring live CEX<->CEX arbitrage session...")
        
        while self.running:
            try:
                # Check if session should continue
                if not self.bot.session_manager.should_continue_session():
                    logger.info("Session ended naturally")
                    break
                
                # Log status every minute for live arbitrage
                if int(time.time()) % 60 == 0:
                    self.bot.session_manager.log_session_status()
                    
                    # Additional live arbitrage status
                    elapsed_hours = (time.time() - self.start_time) / 3600
                    logger.info(f"Live arbitrage session: {elapsed_hours:.2f} hours elapsed")
                    
                    # Log current capital status from config
                    capital_info = self._get_capital_info()
                    detection_info = self._get_detection_info()
                    
                    logger.info("Current Capital Status:")
                    logger.info(f"  Position size limit: ${detection_info.get('max_notional', 0)} per leg")
                    max_daily_loss = (capital_info.get('daily_limit', 0) * capital_info.get('max_loss_pct', 0) / 100)
                    logger.info(f"  Max daily loss: ${max_daily_loss:.2f} ({capital_info.get('max_loss_pct', 0)}% of ${capital_info.get('daily_limit', 0):,.0f})")
                    max_trade_loss = (detection_info.get('max_notional', 0) * capital_info.get('max_trade_loss_pct', 0) / 100)
                    logger.info(f"  Max per trade loss: ${max_trade_loss:.4f} ({capital_info.get('max_trade_loss_pct', 0)}% of ${detection_info.get('max_notional', 0)})")
                
                # Check for manual stop conditions from config
                session_info = self._get_session_info()
                elapsed_minutes = (time.time() - self.start_time) / 60
                max_duration = session_info.get('max_duration_min', 0)
                
                if max_duration > 0 and elapsed_minutes >= max_duration:
                    logger.info(f"Maximum arbitrage session duration reached ({max_duration} minutes)")
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
                
                logger.info("Live CEX<->CEX Arbitrage Session Complete!")
                logger.info("=" * 80)
                logger.info("Final Live Arbitrage Results:")
                logger.info(f"  Duration: {summary['session_duration_hours']:.2f} hours")
                logger.info(f"  Total trades: {summary['total_trades']}")
                logger.info(f"  Success rate: {summary['success_rate_pct']:.1f}%")
                logger.info(f"  Total PnL: ${summary['total_pnl']:.4f}")
                logger.info(f"  Average PnL per trade: ${summary['avg_pnl_per_trade']:.4f}")
                logger.info(f"  Opportunities detected: {summary['total_opportunities']}")
                logger.info("=" * 80)
                logger.info("REAL MONEY WAS TRADED!")
                logger.info("Check your exchange accounts for actual positions")
                
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
        format="{time:HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="INFO"
    )
    logger.add(
        "live_cex_arbitrage.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="1 day"
    )
    
    # Run the live CEX<->CEX arbitrage bot
    asyncio.run(main())
