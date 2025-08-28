#!/usr/bin/env python3
"""
Live CEX<->CEX Arbitrage Bot Runner
Dynamically configured from config.yaml

WARNING: This will use REAL MONEY!

Usage: 
  python run_live_cex_arbitrage.py [--yes]     # Start live trading
  python run_live_cex_arbitrage.py --show-config  # Show current configuration
"""

import asyncio
import signal
import sys
import time
import os
from datetime import datetime
from loguru import logger

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

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
    
    def _load_config(self):
        """Load configuration from config.yaml."""
        try:
            # Get the directory where this script is located
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, "config.yaml")
            
            logger.info(f"Loading config from: {config_path}")
            self.config = Config.load_from_file(config_path)
            
            # Display current configuration from config.yaml
            self._show_config()
            
        except FileNotFoundError as e:
            logger.error(f"Config file not found: {e}")
            logger.error(f"Make sure config.yaml exists in: {script_dir}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            sys.exit(1)
    
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
            'max_notional': self.config.detector.max_notional_usdc,
            'min_notional': self.config.detector.min_notional_usdc,
            'min_net_edge': min_net_edge,
            'min_book_age_ms': getattr(self.config.detector, 'min_book_bbo_age_ms', 500),
            'slippage_model': getattr(self.config.detector, 'slippage_model', 'depth_aware')
        }
    
    def _get_exchange_info(self):
        """Get exchange information from config."""
        if not self.config:
            return {}
        
        return {
            'left_exchange': self.config.exchanges.left,
            'right_exchange': self.config.exchanges.right,
            'binance_sandbox': self.config.exchanges.accounts["binance"].sandbox,
            'kraken_sandbox': self.config.exchanges.accounts["kraken"].sandbox
        }
    
    def _get_fee_info(self):
        """Get fee information from config."""
        if not self.config:
            return {}
        
        return {
            'binance_taker': self.config.get_taker_fee_bps("binance"),
            'binance_maker': self.config.get_maker_fee_bps("binance"),
            'kraken_taker': self.config.get_taker_fee_bps("kraken"),
            'kraken_maker': self.config.get_maker_fee_bps("kraken")
        }
    
    def _display_current_configuration(self):
        """Display the current configuration before asking for confirmation."""
        logger.info("=" * 80)
        logger.info("CURRENT CONFIGURATION FROM config.yaml:")
        logger.info("=" * 80)
        
        # Exchange info
        exchange_info = self._get_exchange_info()
        logger.info(f"EXCHANGES:")
        logger.info(f"  Left: {exchange_info.get('left_exchange', 'N/A')}")
        logger.info(f"  Right: {exchange_info.get('right_exchange', 'N/A')}")
        logger.info(f"  Binance Sandbox: {exchange_info.get('binance_sandbox', 'N/A')}")
        logger.info(f"  Kraken Sandbox: {exchange_info.get('kraken_sandbox', 'N/A')}")
        
        # Fee info
        fee_info = self._get_fee_info()
        logger.info(f"FEES (basis points):")
        logger.info(f"  Binance: Taker {fee_info.get('binance_taker', 'N/A')} | Maker {fee_info.get('binance_maker', 'N/A')}")
        logger.info(f"  Kraken: Taker {fee_info.get('kraken_taker', 'N/A')} | Maker {fee_info.get('kraken_maker', 'N/A')}")
        
        # Session info
        session_info = self._get_session_info()
        logger.info(f"SESSION:")
        logger.info(f"  Target Pairs: {', '.join(session_info.get('target_pairs', ['N/A']))}")
        logger.info(f"  Max Duration: {session_info.get('max_duration_min', 'N/A')} minutes")
        logger.info(f"  Max Trades: {session_info.get('max_trades', 'N/A')}")
        logger.info(f"  Auto Stop: {session_info.get('auto_stop', 'N/A')}")
        
        # Detection info
        detection_info = self._get_detection_info()
        logger.info(f"DETECTION:")
        logger.info(f"  Min Edge: {detection_info.get('min_edge_bps', 'N/A')} bps (0.{detection_info.get('min_edge_bps', 0)/100:.2f}%)")
        logger.info(f"  Max Spread: {detection_info.get('max_spread_bps', 'N/A')} bps")
        logger.info(f"  Min Book Age: {detection_info.get('min_book_age_ms', 'N/A')} ms")
        logger.info(f"  Slippage Model: {detection_info.get('slippage_model', 'N/A')}")
        logger.info(f"  Position Size: ${detection_info.get('min_notional', 'N/A')} - ${detection_info.get('max_notional', 'N/A')} per leg")
        
        # Capital info
        capital_info = self._get_capital_info()
        logger.info(f"RISK MANAGEMENT:")
        logger.info(f"  Daily Notional Limit: ${capital_info.get('daily_limit', 'N/A'):,.0f}")
        logger.info(f"  Max Trades Per Day: {capital_info.get('max_trades', 'N/A')}")
        logger.info(f"  Max Daily Loss: {capital_info.get('max_loss_pct', 'N/A')}%")
        logger.info(f"  Max Per Trade Loss: {capital_info.get('max_trade_loss_pct', 'N/A')}%")
        
        # Realistic trading
        if hasattr(self.config, 'realistic_trading') and self.config.realistic_trading:
            realistic = self.config.realistic_trading
            logger.info(f"REALISTIC TRADING:")
            logger.info(f"  Min Net Edge After Slippage: {getattr(realistic, 'min_net_edge_after_slippage', 'N/A')} bps")
            logger.info(f"  Slippage Method: {getattr(realistic, 'slippage_estimation_method', 'N/A')}")
            logger.info(f"  Partial Fill Handling: {getattr(realistic, 'partial_fill_handling', 'N/A')}")
        
        logger.info("=" * 80)
    
    async def run_live_arbitrage(self):
        """Run the live CEX↔CEX arbitrage."""
        try:
            # Load configuration first
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, "config.yaml")
            self.config = Config.load_from_file(config_path)
            
            # Display current configuration from config.yaml
            self._display_current_configuration()
            
            logger.warning("LIVE CEX ARBITRAGE MODE - REAL MONEY WILL BE USED!")
            logger.info("=" * 80)
            logger.info("LIVE CEX ARBITRAGE CONFIRMATION REQUIRED:")
            logger.info("  Mode: LIVE CEX<->CEX ARBITRAGE (REAL MONEY)")
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
            
            if self.config.exchanges.accounts["kraken"].sandbox:
                logger.error("Kraken is in sandbox mode! Cannot trade live!")
                return
            
            # Verify capital allocation
            logger.info("Verifying capital allocation requirements...")
            detection_info = self._get_detection_info()
            capital_info = self._get_capital_info()
            max_notional = detection_info.get('max_notional', 0)
            min_notional = detection_info.get('min_notional', 0)
            logger.info(f"  Binance: ${max_notional} USDC + ${max_notional} ETH")
            logger.info(f"  Kraken: ${max_notional} USDC + ${max_notional} ETH")
            logger.info(f"  Daily limit: ${capital_info.get('daily_limit', 0):,.0f} total notional")
            logger.info(f"  Position size: ${max_notional} per leg")
            logger.info(f"  Min trade size: ${min_notional} per leg")
            
            # Initialize bot
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, "config.yaml")
            self.bot = CrossExchangeArbBot(config_path)
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
                logger.info(f"  Total PnL: ${summary.get('total_pnl', 0):.4f}")
                logger.info(f"  Average PnL per trade: ${summary.get('avg_pnl_per_trade', 0):.4f}")
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

    def show_configuration(self):
        """Show current configuration without starting the bot."""
        try:
            # Load configuration
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, "config.yaml")
            self.config = Config.load_from_file(config_path)
            
            # Display current configuration
            self._display_current_configuration()
            
            logger.info("Configuration loaded successfully!")
            logger.info("Use --yes flag to start live trading, or run without flags to confirm manually.")
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise


def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "--show-config":
        # Show configuration only
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, "config.yaml")
            config = Config.load_from_file(config_path)
            logger.info(f"Config loaded from: {config_path}")
            logger.info("Configuration loaded successfully!")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            sys.exit(1)
        return
    
    # Run live arbitrage
    runner = LiveCEXArbitrageRunner()
    asyncio.run(runner.run_live_arbitrage())


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
    main()
