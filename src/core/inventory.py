"""Inventory management for cross-exchange arbitrage."""

import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from loguru import logger

from ..exchanges.base import BaseExchange, Balance
from ..config import Config


@dataclass
class RebalancePlan:
    """Plan for rebalancing inventory across exchanges."""
    asset: str
    from_exchange: str
    to_exchange: str
    amount: float
    reason: str
    priority: str  # high, medium, low
    estimated_fee: float
    estimated_time_minutes: int


class InventoryManager:
    """Manages inventory and balances across exchanges."""

    def __init__(self, config: Config, exchanges: Dict[str, BaseExchange]):
        self.config = config
        self.exchanges = exchanges
        self.balances: Dict[str, Dict[str, Balance]] = {}
        self.last_update = 0
        self.rebalance_threshold = config.inventory.rebalance_threshold_pct / 100
        self.rebalance_asset = config.inventory.rebalance_asset

    async def update_balances(self, force: bool = False) -> Dict[str, Dict[str, Balance]]:
        """Update balances from all exchanges."""
        current_time = time.time()
        
        # Update if forced or if balances are stale (>5 minutes)
        if not force and (current_time - self.last_update) < 300:
            return self.balances
        
        logger.info("Updating balances from all exchanges")
        
        for exchange_name, exchange in self.exchanges.items():
            try:
                if exchange.is_connected():
                    balances = await exchange.fetch_balances()
                    self.balances[exchange_name] = balances
                    logger.info(f"Updated {exchange_name} balances: {len(balances)} assets")
                else:
                    logger.warning(f"Exchange {exchange_name} not connected, skipping balance update")
            except Exception as e:
                logger.error(f"Failed to update balances from {exchange_name}: {e}")
        
        self.last_update = current_time
        return self.balances

    def get_balance(self, exchange: str, asset: str) -> Optional[Balance]:
        """Get balance for a specific asset on a specific exchange."""
        if exchange not in self.balances:
            return None
        
        return self.balances[exchange].get(asset)

    def get_total_balance(self, asset: str) -> float:
        """Get total balance for an asset across all exchanges."""
        total = 0.0
        
        for exchange_balances in self.balances.values():
            if asset in exchange_balances:
                total += exchange_balances[asset].total
        
        return total

    def get_free_balance(self, asset: str) -> float:
        """Get total free balance for an asset across all exchanges."""
        total = 0.0
        
        for exchange_balances in self.balances.values():
            if asset in exchange_balances:
                total += exchange_balances[asset].free
        
        return total

    def get_exchange_balance_summary(self) -> Dict[str, Dict[str, float]]:
        """Get balance summary by exchange and asset."""
        summary = {}
        
        for exchange_name, balances in self.balances.items():
            summary[exchange_name] = {}
            for asset, balance in balances.items():
                summary[exchange_name][asset] = {
                    'free': balance.free,
                    'total': balance.total,
                    'locked': balance.total - balance.free
                }
        
        return summary

    def check_rebalancing_needs(self) -> List[RebalancePlan]:
        """Check if rebalancing is needed and create plans."""
        if not self.balances:
            return []
        
        rebalance_plans = []
        
        # Check each asset for imbalances
        all_assets = set()
        for balances in self.balances.values():
            all_assets.update(balances.keys())
        
        for asset in all_assets:
            if asset == self.rebalance_asset:
                continue  # Skip quote asset
            
            # Calculate total balance and distribution
            total_balance = self.get_total_balance(asset)
            if total_balance <= 0:
                continue
            
            # Check distribution across exchanges
            for exchange_name, balances in self.balances.items():
                if asset not in balances:
                    continue
                
                balance = balances[asset]
                balance_pct = balance.total / total_balance
                
                # Check if this exchange has too much of the asset
                if balance_pct > (0.5 + self.rebalance_threshold):
                    # This exchange has too much, plan to move some out
                    excess_amount = balance.total - (total_balance * 0.5)
                    
                    # Find exchange with less of this asset
                    target_exchange = None
                    min_balance_pct = 1.0
                    
                    for other_exchange, other_balances in self.balances.items():
                        if other_exchange == exchange_name:
                            continue
                        
                        if asset in other_balances:
                            other_pct = other_balances[asset].total / total_balance
                            if other_pct < min_balance_pct:
                                min_balance_pct = other_pct
                                target_exchange = other_exchange
                    
                    if target_exchange:
                        plan = RebalancePlan(
                            asset=asset,
                            from_exchange=exchange_name,
                            to_exchange=target_exchange,
                            amount=excess_amount * 0.5,  # Move half of excess
                            reason=f"Imbalanced distribution: {exchange_name} has {balance_pct:.1%}, target has {min_balance_pct:.1%}",
                            priority="medium" if balance_pct > 0.7 else "low",
                            estimated_fee=0.0,  # TODO: implement fee estimation
                            estimated_time_minutes=5
                        )
                        rebalance_plans.append(plan)
        
        # Sort by priority
        priority_order = {"high": 3, "medium": 2, "low": 1}
        rebalance_plans.sort(key=lambda x: priority_order.get(x.priority, 0), reverse=True)
        
        if rebalance_plans:
            logger.info(f"Created {len(rebalance_plans)} rebalancing plans")
        
        return rebalance_plans

    def get_inventory_summary(self) -> Dict[str, Any]:
        """Get inventory summary."""
        if not self.balances:
            return {"error": "No balance data available"}
        
        summary = {
            'total_assets': len(set().union(*[set(b.keys()) for b in self.balances.values()])),
            'exchanges': list(self.balances.keys()),
            'last_update': self.last_update,
            'balances': self.get_exchange_balance_summary(),
            'rebalancing_needed': len(self.check_rebalancing_needs()) > 0
        }
        
        # Add total values for major assets
        major_assets = ['USDT', 'USDC', 'BTC', 'ETH']
        for asset in major_assets:
            total = self.get_total_balance(asset)
            if total > 0:
                summary[f'total_{asset}'] = total
        
        return summary

    def estimate_transfer_fee(self, from_exchange: str, to_exchange: str, 
                            asset: str, amount: float) -> float:
        """Estimate transfer fee between exchanges."""
        # This is a simplified estimation
        # In practice, you'd need to check actual network fees
        
        if from_exchange == to_exchange:
            return 0.0  # Internal transfer
        
        # Estimate based on asset and amount
        if asset in ['USDT', 'USDC']:
            # Stablecoins usually have low fees
            return 1.0
        elif asset in ['BTC', 'ETH']:
            # Major cryptocurrencies
            return 5.0
        else:
            # Other assets
            return 2.0

    def get_rebalancing_recommendations(self) -> List[Dict[str, Any]]:
        """Get rebalancing recommendations."""
        plans = self.check_rebalancing_needs()
        recommendations = []
        
        for plan in plans:
            recommendation = {
                'action': f"Transfer {plan.amount:.4f} {plan.asset} from {plan.from_exchange} to {plan.to_exchange}",
                'reason': plan.reason,
                'priority': plan.priority,
                'estimated_cost': plan.estimated_fee,
                'estimated_time': f"{plan.estimated_time_minutes} minutes"
            }
            recommendations.append(recommendation)
        
        return recommendations
