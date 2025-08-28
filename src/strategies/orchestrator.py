"""Main strategy orchestrator for running multiple arbitrage strategies."""

import asyncio
from typing import List, Dict, Any
from loguru import logger

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
            
            # Wait for all strategies to complete
            await asyncio.gather(*strategy_tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"Fatal error in orchestrator: {e}")
            await self.stop()
    
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
