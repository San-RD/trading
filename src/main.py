"""Main entry point for the cross-exchange arbitrage bot."""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
import click
from loguru import logger

# uvloop is not available on Windows
try:
    import uvloop
    UVLOOP_AVAILABLE = True
except ImportError:
    UVLOOP_AVAILABLE = False

from .config import get_config
from .exchanges.binance import BinanceExchange
from .exchanges.okx import OKXExchange
from .core.symbols import SymbolManager
from .core.quotes import QuoteBus
from .core.detector import ArbitrageDetector
from .core.executor import ArbitrageExecutor
from .core.inventory import InventoryManager
from .core.risk import RiskManager
from .storage.db import Database
from .storage.journal import TradeJournal
from .alerts.telegram import TelegramNotifier
from .backtest.recorder import TickRecorder
from .backtest.replay import TickReplay
from .backtest.sim import BacktestSimulator
from .core.session import SessionManager


class CrossExchangeArbBot:
    """Cross-exchange arbitrage bot."""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = get_config(config_path)
        self.exchanges: Dict[str, Any] = {}
        self.symbol_manager = SymbolManager(self.config)
        self.quote_bus = QuoteBus(self.config)
        self.detector = ArbitrageDetector(self.config)
        self.executor = ArbitrageExecutor(self.config, self.exchanges, "live")  # Live trading mode
        self.risk_manager = RiskManager(self.config)
        self.session_manager = SessionManager(self.config)  # New session manager
        self.storage = Database(self.config.storage.db_path)
        self.alerts = TelegramNotifier(self.config.alerts) if self.config.alerts else None
        
        # Initialize missing attributes
        self.running = False
        self.mode = "live"  # Default to live trading
        self.notifier = self.alerts  # Use alerts as notifier
        
        # Initialize exchanges
        self.exchanges = self._init_exchanges()
        
        logger.info("Cross-Exchange Arbitrage Bot initialized")
        logger.info(f"Mode: {self.mode.upper()} CEX ARBITRAGE")
        logger.info(f"Capital: $100 total ($25 per exchange, $25 per leg)")
        logger.info(f"Session duration: {self.config.session.duration_hours}h")
        logger.info(f"Max trades per session: {self.config.risk.max_trades_per_session}")
        logger.info(f"Position size limit: ${self.config.detector.max_notional_usdt}")
        logger.info(f"Target pairs: {self.config.session.target_pairs}")
        logger.info(f"Risk profile: {self.config.risk.max_daily_loss}% max daily loss")

    def _init_exchanges(self) -> Dict[str, Any]:
        """Initialize exchange connections."""
        exchanges = {}
        
        # Initialize Binance
        try:
            exchanges['binance'] = BinanceExchange(self.config)
            logger.info("Binance exchange initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Binance: {e}")
        
        # Initialize OKX
        try:
            exchanges['okx'] = OKXExchange(self.config)
            logger.info("OKX exchange initialized")
        except Exception as e:
            logger.error(f"Failed to initialize OKX: {e}")
        
        return exchanges

    async def start(self):
        """Start the bot."""
        if self.running:
            return
        
        logger.info(f"Starting Cross-Exchange Arbitrage Bot in {self.mode} mode")
        logger.info(f"Left exchange: {self.config.exchanges.left}")
        logger.info(f"Right exchange: {self.config.exchanges.right}")
        logger.info(f"Min edge: {self.config.detector.min_edge_bps} bps")
        logger.info(f"Max notional: ${self.config.detector.max_notional_usdt:,.2f}")
        
        try:
            # Connect to exchanges
            for name, exchange in self.exchanges.items():
                try:
                    await exchange.connect()
                    logger.info(f"Connected to {name}")
                except Exception as e:
                    logger.error(f"Failed to connect to {name}: {e}")
            
            # Build symbol universe
            universe = await self.symbol_manager.build_universe(self.exchanges)
            logger.info(f"Symbol universe: {universe.intersection_symbols} intersection symbols")
            
            # Add exchanges to quote bus
            for name, exchange in self.exchanges.items():
                self.quote_bus.add_exchange(name, exchange)
            
            # Connect to database
            await self.storage.connect()
            
            # Test alerts
            if self.alerts:
                await self.alerts.test_connection()
            
            # Start quote monitoring
            symbols = universe.intersection_symbols
            await self.quote_bus.start(symbols)
            
            self.running = True
            
            # Main trading loop
            await self._trading_loop()
            
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            await self.notifier.notify_error(str(e), "Bot startup")
            raise
        finally:
            await self.stop()

    async def stop(self):
        """Stop the bot."""
        if not self.running:
            return
        
        logger.info("Stopping Cross-Exchange Arbitrage Bot")
        self.running = False
        
        try:
            await self.quote_bus.stop()
            for exchange in self.exchanges.values():
                await exchange.disconnect()
            await self.storage.disconnect()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(self.stop())

    async def _trading_loop(self):
        """Main trading loop."""
        logger.info("Entering main trading loop")
        
        while self.running:
            try:
                # Check if session should continue
                if not self.session_manager.should_continue_session():
                    logger.info("Session ended, stopping trading loop")
                    break
                
                # Get latest quotes
                quotes = self.quote_bus.get_fresh_quotes()
                
                # Detect opportunities
                opportunities = self.detector.detect_opportunities(quotes)
                
                if opportunities:
                    logger.info(f"Detected {len(opportunities)} arbitrage opportunities")
                    
                    # Process each opportunity
                    for opportunity in opportunities:
                        await self._process_opportunity(opportunity)
                        
                        # Check if we should stop after this trade
                        if not self.session_manager.should_continue_session():
                            break
                
                # Log session status every 5 minutes
                # if int(time.time()) % 300 == 0: # This line was removed as per new_code
                #     self.session_manager.log_session_status() # This line was removed as per new_code
                
                # Wait before next iteration
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                await self.notifier.notify_error(str(e), "Trading loop")
                await asyncio.sleep(5)  # Wait before retrying

    async def _process_opportunity(self, opportunity):
        """Process a detected arbitrage opportunity."""
        try:
            # Record opportunity in session
            self.session_manager.record_opportunity(opportunity)
            
            # Check if session should continue
            if not self.session_manager.should_continue_session():
                logger.info("Session limits reached, skipping opportunity")
                return
            
            # Check risk limits before execution
            if self.risk_manager.should_stop_trading():
                logger.warning("Risk limits exceeded, skipping opportunity")
                return
            
            # Execute arbitrage
            execution_result = await self.executor.execute_arbitrage(opportunity)
            
            # Record trade in session
            self.session_manager.record_trade(execution_result)
            
            # Update risk metrics
            self.risk_manager.update_risk_metrics(execution_result)
            
            # Journal execution
            await self.storage.journal_execution(execution_result)
            
            # Send notifications
            if self.alerts:
                await self.alerts.notify_execution(execution_result)
            
            logger.info(f"Opportunity executed: {opportunity.symbol} {opportunity.direction.value}, PnL: ${execution_result.realized_pnl:.4f}")
            
        except Exception as e:
            logger.error(f"Error processing opportunity: {e}")

    async def run_recording_mode(self, symbols: List[str], outfile: str):
        """Run in recording mode to save ticks to parquet."""
        logger.info(f"Starting recording mode for {len(symbols)} symbols")
        
        try:
            # Connect to exchanges
            for name, exchange in self.exchanges.items():
                await exchange.connect()
            
            # Start recording
            await self.recorder.start_recording(symbols, outfile, self.exchanges)
            
        except Exception as e:
            logger.error(f"Recording failed: {e}")
            raise
        finally:
            await self.stop()

    async def run_backtest_mode(self, parquet_file: str):
        """Run in backtest mode using historical data."""
        logger.info(f"Starting backtest mode with {parquet_file}")
        
        try:
            # Run backtest
            results = await self.simulator.run_backtest(parquet_file)
            
            # Print results
            print("\n=== BACKTEST RESULTS ===")
            print(f"Total trades: {results['total_trades']}")
            print(f"Win rate: {results['win_rate']:.2%}")
            print(f"Total PnL: ${results['total_pnl']:.2f}")
            print(f"Average edge: {results['avg_edge_bps']:.2f} bps")
            print(f"Sharpe ratio: {results['sharpe_ratio']:.2f}")
            
        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            raise


@click.group()
def cli():
    """Cross-Exchange Arbitrage Bot CLI."""
    pass


@cli.command()
@click.option('--mode', default='paper', type=click.Choice(['paper', 'live', 'record', 'backtest']),
              help='Bot mode (default: paper)')
@click.option('--config', type=click.Path(exists=True), default='config.yaml',
              help='Path to config file')
@click.option('--symbols', help='Comma-separated symbols for record mode')
@click.option('--outfile', help='Output file for record mode')
@click.option('--parquet-file', help='Parquet file for backtest mode')
def run(mode, config, symbols, outfile, parquet_file):
    """Run the cross-exchange arbitrage bot."""
    
    # Setup logging
    logger.remove()
    logger.add(sys.stderr, level="INFO", 
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
    logger.add("bot.log", level="DEBUG", 
               format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}")
    
    # Use uvloop on Linux for better performance
    if sys.platform != "win32" and UVLOOP_AVAILABLE:
        uvloop.install()
    
    # Create and run bot
    bot = CrossExchangeArbBot(config_path=config)
    
    try:
        if mode == 'record':
            if not symbols or not outfile:
                logger.error("Record mode requires --symbols and --outfile")
                sys.exit(1)
            symbol_list = [s.strip() for s in symbols.split(',')]
            asyncio.run(bot.run_recording_mode(symbol_list, outfile))
        elif mode == 'backtest':
            if not parquet_file:
                logger.error("Backtest mode requires --parquet-file")
                sys.exit(1)
            asyncio.run(bot.run_backtest_mode(parquet_file))
        else:
            asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot failed: {e}")
        sys.exit(1)


@cli.command()
@click.option('--days', default=7, type=int, help='Number of days to report (default: 7)')
def report(days):
    """Generate trading report."""
    async def generate_report():
        # Setup logging
        logger.remove()
        logger.add(sys.stderr, level="WARNING")
        
        # Initialize database
        config = get_config()
        db = Database(config.storage.db_path)
        journal = TradeJournal(db)
        
        try:
            await db.connect()
            report_text = await journal.generate_report(days)
            print(report_text)
        finally:
            await db.disconnect()
    
    asyncio.run(generate_report())


@cli.command()
def status():
    """Show bot status."""
    async def show_status():
        # Setup logging
        logger.remove()
        logger.add(sys.stderr, level="WARNING")
        
        # Initialize components
        config = get_config()
        db = Database(config.storage.db_path)
        journal = TradeJournal(db)
        
        try:
            await db.connect()
            
            # Get recent performance
            performance = await journal.get_performance_summary(1)  # Last day
            summary = performance['summary']
            
            print(f"""
=== BOT STATUS ===
Last 24h Performance:
- Trades: {summary.total_trades}
- Win Rate: {summary.win_rate:.2%}
- PnL: ${summary.total_pnl:.2f}
- Avg Edge: {summary.avg_edge_bps:.2f} bps
- Avg Latency: {summary.avg_latency_ms:.1f} ms
""")
            
        finally:
            await db.disconnect()
    
    asyncio.run(show_status())


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
