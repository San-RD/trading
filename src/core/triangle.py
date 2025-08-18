"""Triangle arbitrage detection and calculation."""

from typing import Dict, List, Tuple, Optional
from decimal import Decimal
import asyncio
from loguru import logger

from ..exchanges.depth_model import DepthModel
from ..exchanges.base import Quote, OrderBook
from .utils import calculate_spread_bps, calculate_edge_bps


class Triangle:
    """Represents a triangular arbitrage opportunity."""
    
    def __init__(self, asset_a: str, asset_b: str, asset_c: str, 
                 pair_ab: str, pair_bc: str, pair_ca: str):
        self.asset_a = asset_a
        self.asset_b = asset_b
        self.asset_c = asset_c
        self.pair_ab = pair_ab
        self.pair_bc = pair_bc
        self.pair_ca = pair_ca
        
        # Trading path: A -> B -> C -> A
        self.path_abc = [pair_ab, pair_bc, pair_ca]
        
        # Reverse path: A -> C -> B -> A
        self.path_acb = [pair_ca, pair_bc, pair_ab]
    
    def __repr__(self) -> str:
        return f"Triangle({self.asset_a}->{self.asset_b}->{self.asset_c}->{self.asset_a})"
    
    def get_pairs(self) -> List[str]:
        """Get all pairs in this triangle."""
        return [self.pair_ab, self.pair_bc, self.pair_ca]
    
    def get_assets(self) -> List[str]:
        """Get all assets in this triangle."""
        return [self.asset_a, self.asset_b, self.asset_c]


def find_triangles(symbol_rules: Dict[str, SymbolRule], 
                  quote_assets: List[str],
                  exclude_assets: List[str] = None,
                  include_only: List[str] = None) -> List[Triangle]:
    """Find all valid triangles from symbol rules."""
    if exclude_assets is None:
        exclude_assets = []
    if include_only is None:
        include_only = []
    
    # Build directed graph
    G = nx.DiGraph()
    
    # Add nodes for all assets
    all_assets = set()
    for rule in symbol_rules.values():
        if rule.is_active():
            all_assets.add(rule.base_asset)
            all_assets.add(rule.quote_asset)
    
    # Filter assets
    if include_only:
        all_assets = all_assets.intersection(set(include_only))
    
    all_assets = all_assets - set(exclude_assets)
    G.add_nodes_from(all_assets)
    
    # Add edges for trading pairs
    for symbol, rule in symbol_rules.items():
        if rule.is_active():
            base = rule.base_asset
            quote = rule.quote_asset
            
            if base in all_assets and quote in all_assets:
                G.add_edge(base, quote, pair=symbol, side='buy')
                G.add_edge(quote, base, pair=symbol, side='sell')
    
    # Find triangles
    triangles = []
    
    for asset_a in all_assets:
        if asset_a not in quote_assets:
            continue
            
        for asset_b in all_assets:
            if asset_b == asset_a:
                continue
                
            for asset_c in all_assets:
                if asset_c in [asset_a, asset_b]:
                    continue
                
                # Check if we can form a triangle
                if (G.has_edge(asset_a, asset_b) and 
                    G.has_edge(asset_b, asset_c) and 
                    G.has_edge(asset_c, asset_a)):
                    
                    # Get pair names
                    pair_ab = G[asset_a][asset_b]['pair']
                    pair_bc = G[asset_b][asset_c]['pair']
                    pair_ca = G[asset_c][asset_a]['pair']
                    
                    triangle = Triangle(asset_a, asset_b, asset_c, pair_ab, pair_bc, pair_ca)
                    triangles.append(triangle)
    
    logger.info(f"Found {len(triangles)} valid triangles")
    return triangles


def calculate_triangle_edge(triangle: Triangle, quotes: Dict[str, Dict], 
                           start_notional: float, symbol_rules: Dict[str, SymbolRule],
                           depth_model: Optional[DepthModel] = None) -> Tuple[float, float, Dict]:
    """Calculate arbitrage edge for a triangle."""
    
    # Calculate edge for both directions
    edge_abc, profit_abc, legs_abc = _calculate_path_edge(
        triangle.path_abc, quotes, start_notional, symbol_rules, depth_model, "ABC"
    )
    
    edge_acb, profit_acb, legs_acb = _calculate_path_edge(
        triangle.path_acb, quotes, start_notional, symbol_rules, depth_model, "ACB"
    )
    
    # Return the better direction
    if edge_abc > edge_acb:
        return edge_abc, profit_abc, {
            'direction': 'ABC',
            'path': triangle.path_abc,
            'legs': legs_abc
        }
    else:
        return edge_acb, profit_acb, {
            'direction': 'ACB',
            'path': triangle.path_acb,
            'legs': legs_acb
        }


def _calculate_path_edge(path: List[str], quotes: Dict[str, Dict], 
                        start_notional: float, symbol_rules: Dict[str, SymbolRule],
                        depth_model: Optional[DepthModel], direction: str) -> Tuple[float, float, List[Dict]]:
    """Calculate edge for a specific path."""
    
    current_notional = start_notional
    legs = []
    
    for i, pair in enumerate(path):
        if pair not in quotes:
            return 0.0, 0.0, []
        
        quote = quotes[pair]
        rule = symbol_rules.get(pair)
        
        if not rule:
            return 0.0, 0.0, []
        
        # Determine side based on position in path
        if i == 0:  # First leg: buy
            side = 'buy'
            price = quote['ask']
        elif i == len(path) - 1:  # Last leg: sell
            side = 'sell'
            price = quote['bid']
        else:  # Middle leg: depends on asset flow
            # This is simplified - in practice you'd track asset flow
            side = 'buy'  # Placeholder
            price = quote['ask']
        
        # Apply depth model if available
        if depth_model and depth_model.enabled:
            effective_price = depth_model.get_effective_price(pair, side, current_notional / price)
            if effective_price:
                price = effective_price
        
        # Calculate quantity
        quantity = current_notional / price
        
        # Round quantity according to rules
        quantity = float(rule.round_qty(quantity))
        
        # Calculate notional for next leg
        current_notional = quantity * price
        
        # Calculate fees
        fee_rate = get_taker_fee_rate(pair)
        fee_amount = current_notional * fee_rate
        current_notional -= fee_amount
        
        # Store leg details
        legs.append({
            'pair': pair,
            'side': side,
            'price': price,
            'quantity': quantity,
            'notional': current_notional,
            'fee': fee_amount
        })
    
    # Calculate final edge
    final_notional = current_notional
    edge_bps = ((final_notional - start_notional) / start_notional) * 10000
    profit = final_notional - start_notional
    
    logger.debug(f"Path {direction}: start={start_notional:.4f}, end={final_notional:.4f}, "
                f"edge={edge_bps:.2f} bps, profit={profit:.4f}")
    
    return edge_bps, profit, legs


def validate_triangle_execution(triangle: Triangle, quotes: Dict[str, Dict], 
                               symbol_rules: Dict[str, SymbolRule]) -> Tuple[bool, str]:
    """Validate if a triangle can be executed."""
    
    for pair in triangle.get_pairs():
        if pair not in quotes:
            return False, f"Missing quotes for {pair}"
        
        if pair not in symbol_rules:
            return False, f"Missing rules for {pair}"
        
        rule = symbol_rules[pair]
        if not rule.is_active():
            return False, f"Symbol {pair} is not active"
    
    return True, "OK"
