"""Portfolio management for balances and position sizing."""

from typing import Dict, Optional
from decimal import Decimal
from loguru import logger

from ..exchange.binance import BinanceClient, Balance
from ..config import get_config


class Portfolio:
    """Manages account portfolio and position sizing."""
    
    def __init__(self, exchange_client: BinanceClient):
        self.exchange = exchange_client
        self.config = get_config()
        self.balances: Dict[str, Balance] = {}
        self.last_update = 0.0
        self.update_interval = 30.0  # seconds
    
    async def update_balances(self, force: bool = False) -> Dict[str, Balance]:
        """Update account balances."""
        current_time = self.exchange.get_last_ws_update()
        
        if not force and current_time - self.last_update < self.update_interval:
            return self.balances
        
        try:
            self.balances = await self.exchange.fetch_balances()
            self.last_update = current_time
            logger.debug(f"Updated balances for {len(self.balances)} assets")
        except Exception as e:
            logger.error(f"Failed to update balances: {e}")
        
        return self.balances
    
    def get_balance(self, asset: str) -> Optional[Balance]:
        """Get balance for a specific asset."""
        return self.balances.get(asset)
    
    def get_free_balance(self, asset: str) -> float:
        """Get free balance for a specific asset."""
        balance = self.get_balance(asset)
        return balance.free if balance else 0.0
    
    def get_total_balance(self, asset: str) -> float:
        """Get total balance for a specific asset."""
        balance = self.get_balance(asset)
        return balance.total if balance else 0.0
    
    def get_usdt_equivalent(self, asset: str, price_usdt: float) -> float:
        """Get USDT equivalent value of an asset."""
        total_balance = self.get_total_balance(asset)
        return total_balance * price_usdt
    
    def calculate_available_notional(self, quote_asset: str = "USDT") -> float:
        """Calculate available notional for trading."""
        free_balance = self.get_free_balance(quote_asset)
        
        if quote_asset == "USDT":
            # Apply safety margin
            available = free_balance * 0.95
            return min(available, self.config.risk.max_notional_usdt)
        else:
            # For non-USDT quote assets, convert to USDT equivalent
            # This is simplified - in practice you'd need current market prices
            return min(free_balance, self.config.risk.max_notional_usdt)
    
    def has_sufficient_balance(self, asset: str, required_amount: float) -> bool:
        """Check if there's sufficient balance for an asset."""
        free_balance = self.get_free_balance(asset)
        return free_balance >= required_amount
    
    def get_portfolio_summary(self) -> Dict:
        """Get portfolio summary."""
        total_usdt_value = 0.0
        asset_breakdown = {}
        
        for asset, balance in self.balances.items():
            if balance.total > 0:
                # For now, assume 1:1 for non-USDT assets
                # In practice, you'd fetch current market prices
                if asset == "USDT":
                    usdt_value = balance.total
                else:
                    usdt_value = balance.total  # Placeholder
                
                total_usdt_value += usdt_value
                asset_breakdown[asset] = {
                    'free': balance.free,
                    'total': balance.total,
                    'usdt_value': usdt_value
                }
        
        return {
            'total_usdt_value': total_usdt_value,
            'assets': asset_breakdown,
            'last_update': self.last_update,
            'available_notional': self.calculate_available_notional()
        }
    
    def check_balance_thresholds(self) -> Dict[str, bool]:
        """Check if balance thresholds are met."""
        usdt_balance = self.get_free_balance("USDT")
        stop_threshold = self.config.risk.stop_if_balance_usdt_below
        
        return {
            'above_stop_threshold': usdt_balance >= stop_threshold,
            'sufficient_for_trading': usdt_balance >= self.config.risk.max_notional_usdt
        }
    
    def simulate_trade_impact(self, opportunity, notional: float) -> Dict:
        """Simulate the impact of a trade on portfolio."""
        # This is a simplified simulation
        # In practice, you'd need to track asset flows more carefully
        
        current_balances = self.balances.copy()
        
        # Simulate executing the opportunity
        # This is placeholder logic - actual implementation would be more complex
        simulated_pnl = opportunity.expected_profit
        
        return {
            'current_balances': current_balances,
            'simulated_pnl': simulated_pnl,
            'risk_acceptable': simulated_pnl > 0
        }
