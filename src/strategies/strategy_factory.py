"""Strategy factory for creating different arbitrage strategies."""

from typing import Dict, Any, Optional
from loguru import logger

from .spot_perp.runner import SpotPerpRunner
from src.config import Config, RouteConfig


class StrategyFactory:
    """Factory for creating arbitrage strategies based on route configuration."""
    
    @staticmethod
    def create_strategy(route: RouteConfig, config: Config) -> Optional[Any]:
        """Create a strategy instance based on route configuration."""
        try:
            strategy_type = route.strategy_type.lower()
            
            if strategy_type == "spot_perp":
                logger.info(f"Creating Spot↔Perp strategy for route: {route.name}")
                return SpotPerpRunner(config, route)
            
            elif strategy_type == "spot_spot":
                logger.info(f"Creating Spot↔Spot strategy for route: {route.name}")
                # TODO: Import and return existing spot↔spot strategy
                # from .spot_spot.runner import SpotSpotRunner
                # return SpotSpotRunner(config, route)
                logger.warning("Spot↔Spot strategy not yet implemented in factory")
                return None
            
            elif strategy_type == "perp_perp":
                logger.info(f"Creating Perp↔Perp strategy for route: {route.name}")
                # TODO: Implement perp↔perp strategy
                logger.warning("Perp↔Perp strategy not yet implemented")
                return None
            
            else:
                logger.error(f"Unknown strategy type: {strategy_type}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to create strategy for route {route.name}: {e}")
            return None
    
    @staticmethod
    def get_enabled_routes(config: Config) -> list[RouteConfig]:
        """Get all enabled routes from configuration."""
        if not config.routes:
            return []
        
        enabled_routes = [route for route in config.routes if route.enabled]
        logger.info(f"Found {len(enabled_routes)} enabled routes")
        
        for route in enabled_routes:
            logger.info(f"  - {route.name}: {route.left['ex']} ↔ {route.right['ex']} ({route.strategy_type})")
        
        return enabled_routes
