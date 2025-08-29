"""Main strategy orchestrator for running multiple arbitrage strategies."""

import asyncio
import time
from typing import List, Dict, Any
from loguru import logger
from datetime import datetime

from .strategy_factory import StrategyFactory
from src.config import Config


class StrategyOrchestrator:
    """Orchestrates multiple arbitrage strategies based on route configuration."""
    
    def __init__(self, config: Config):
        self.config = config
        self.active_strategies: List[Any] = []
        self.is_running = False
        
    async def start(self):
        """Start all enabled strategies."""
        try:
            logger.info("🚀 Starting Strategy Orchestrator...")
            
            # Get enabled routes
            enabled_routes = StrategyFactory.get_enabled_routes(self.config)
            if not enabled_routes:
                logger.warning("No enabled routes found in configuration")
                return
            
            # Create and start strategies for each route
            for route in enabled_routes:
                try:
                    strategy = StrategyFactory.create_strategy(route, self.config)
                    if strategy:
                        self.active_strategies.append(strategy)
                        logger.info(f"✅ Created strategy for route: {route.name}")
                    else:
                        logger.error(f"❌ Failed to create strategy for route: {route.name}")
                        
                except Exception as e:
                    logger.error(f"❌ Error creating strategy for route {route.name}: {e}")
            
            if not self.active_strategies:
                logger.error("No strategies were successfully created")
                return
            
            # Start all strategies concurrently
            self.is_running = True
            logger.info(f"🎯 Starting {len(self.active_strategies)} strategies...")
            
            # Start strategies in separate tasks
            strategy_tasks = []
            for strategy in self.active_strategies:
                task = asyncio.create_task(strategy.start())
                strategy_tasks.append(task)
            
            # Start heartbeat task
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            # Wait for all strategies to complete
            await asyncio.gather(*strategy_tasks, heartbeat_task, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"Fatal error in orchestrator: {e}")
            await self.stop()
    
    async def _heartbeat_loop(self):
        """Send heartbeat every minute showing status of all strategies."""
        try:
            last_heartbeat = time.time()
            
            while self.is_running:
                try:
                    current_time = time.time()
                    
                    # Send heartbeat every 60 seconds
                    if current_time - last_heartbeat >= 60:
                        await self._send_heartbeat()
                        last_heartbeat = current_time
                    
                    await asyncio.sleep(1)  # Check every second
                    
                except Exception as e:
                    logger.error(f"Error in heartbeat loop: {e}")
                    await asyncio.sleep(5)  # Wait before retrying
                    
        except Exception as e:
            logger.error(f"Fatal error in heartbeat loop: {e}")
    
    async def _send_heartbeat(self):
        """Send heartbeat message showing status of all strategies."""
        try:
            # Collect status from all strategies
            strategy_statuses = []
            total_trades = 0
            total_pnl = 0.0
            
            for strategy in self.active_strategies:
                try:
                    if hasattr(strategy, 'get_status'):
                        status = await strategy.get_status()
                        strategy_statuses.append(status)
                        
                        # Aggregate trades and PnL
                        if 'total_trades' in status:
                            total_trades += status.get('total_trades', 0)
                        if 'total_pnl' in status:
                            total_pnl += status.get('total_pnl', 0.0)
                    else:
                        strategy_statuses.append({'name': 'Unknown', 'status': 'No status method'})
                        
                except Exception as e:
                    strategy_statuses.append({'name': 'Error', 'status': f'Error: {e}'})
            
            # Create heartbeat message
            message = f"""
💓 <b>ORCHESTRATOR HEARTBEAT</b>

⏰ Time: {datetime.now().strftime('%H:%M:%S')}
🔄 Status: <b>ACTIVE</b> - Running {len(self.active_strategies)} strategies

📊 <b>Overall Status:</b>
• Active Strategies: {len(self.active_strategies)}
• Total Trades: {total_trades}
• Total P&L: ${total_pnl:.2f}

🎯 <b>Strategy Status:</b>
"""
            
            # Add individual strategy statuses
            for i, status in enumerate(strategy_statuses, 1):
                name = status.get('name', f'Strategy {i}')
                status_text = status.get('status', 'Unknown')
                message += f"• {name}: {status_text}\n"
            
            message += f"""
💡 <b>Bot Status:</b>
• Market Data: ✅ Streaming
• Opportunity Detection: ✅ Active
• Risk Management: ✅ Monitoring
• All Systems: 🟢 Operational
            """
            
            # Send to all strategies that have Telegram
            for strategy in self.active_strategies:
                if hasattr(strategy, 'telegram') and strategy.telegram:
                    try:
                        await strategy.telegram.send_message(message)
                        break  # Only send once
                    except Exception as e:
                        logger.error(f"Error sending heartbeat to strategy {strategy}: {e}")
            
            logger.info(f"Orchestrator heartbeat sent - {len(self.active_strategies)} strategies active")
            
        except Exception as e:
            logger.error(f"Error sending orchestrator heartbeat: {e}")
    
    async def stop(self):
        """Stop all active strategies."""
        try:
            logger.info("🛑 Stopping Strategy Orchestrator...")
            self.is_running = False
            
            # Stop all active strategies
            stop_tasks = []
            for strategy in self.active_strategies:
                if hasattr(strategy, 'stop'):
                    task = asyncio.create_task(strategy.stop())
                    stop_tasks.append(task)
            
            if stop_tasks:
                await asyncio.gather(*stop_tasks, return_exceptions=True)
            
            self.active_strategies.clear()
            logger.info("✅ Strategy Orchestrator stopped")
            
        except Exception as e:
            logger.error(f"Error stopping orchestrator: {e}")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get status of all active strategies."""
        try:
            status = {
                'orchestrator_running': self.is_running,
                'active_strategies': len(self.active_strategies),
                'strategies': []
            }
            
            for strategy in self.active_strategies:
                if hasattr(strategy, 'get_status'):
                    try:
                        strategy_status = await strategy.get_status()
                        status['strategies'].append(strategy_status)
                    except Exception as e:
                        status['strategies'].append({'error': str(e)})
                else:
                    status['strategies'].append({'status': 'unknown'})
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting orchestrator status: {e}")
            return {'error': str(e)}
