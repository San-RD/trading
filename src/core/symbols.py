"""Symbol universe management for cross-exchange arbitrage."""

from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass
from loguru import logger

from ..exchanges.base import BaseExchange
from ..config import Config


@dataclass
class SymbolUniverse:
    """Universe of tradable symbols across exchanges."""
    symbols: List[str]
    base_assets: Set[str]
    quote_assets: Set[str]
    exchange_symbols: Dict[str, List[str]]
    intersection_symbols: List[str]


class SymbolManager:
    """Manages symbol universe across exchanges."""

    def __init__(self, config: Config):
        self.config = config
        self.universe: Optional[SymbolUniverse] = None

    async def build_universe(self, exchanges: Dict[str, BaseExchange]) -> SymbolUniverse:
        """Build symbol universe from available exchanges."""
        logger.info("Building symbol universe...")
        
        # Get symbols from each exchange
        exchange_symbols = {}
        all_symbols = set()
        all_base_assets = set()
        all_quote_assets = set()
        
        for exchange_name, exchange in exchanges.items():
            if not exchange.is_connected():
                logger.warning(f"Exchange {exchange_name} not connected, skipping")
                continue
            
            # Get symbols from exchange
            try:
                markets = await exchange.load_markets()
                exchange_symbols[exchange_name] = list(markets.keys())
                all_symbols.update(markets.keys())
                
                # Extract base and quote assets
                for symbol in markets.keys():
                    if '/' in symbol:
                        base, quote = symbol.split('/', 1)
                        all_base_assets.add(base)
                        all_quote_assets.add(quote)
                
                logger.info(f"Exchange {exchange_name}: {len(markets)} symbols")
                
            except Exception as e:
                logger.error(f"Failed to load markets from {exchange_name}: {e}")
                exchange_symbols[exchange_name] = []
        
        # Filter symbols based on configuration
        filtered_symbols = self._filter_symbols(all_symbols)
        
        # Find intersection symbols (available on both exchanges)
        left_exchange = self.config.exchanges.left
        right_exchange = self.config.exchanges.right
        
        left_symbols = set(exchange_symbols.get(left_exchange, []))
        right_symbols = set(exchange_symbols.get(right_exchange, []))
        
        intersection_symbols = list(left_symbols.intersection(right_symbols))
        intersection_symbols = [s for s in intersection_symbols if s in filtered_symbols]
        
        logger.info(f"Symbol intersection: {len(intersection_symbols)} symbols")
        
        # Create universe
        self.universe = SymbolUniverse(
            symbols=list(filtered_symbols),
            base_assets=all_base_assets,
            quote_assets=all_quote_assets,
            exchange_symbols=exchange_symbols,
            intersection_symbols=intersection_symbols
        )
        
        return self.universe

    def _filter_symbols(self, symbols: Set[str]) -> Set[str]:
        """Filter symbols based on configuration."""
        filtered = set()
        
        for symbol in symbols:
            if not self._is_valid_symbol(symbol):
                continue
            
            filtered.add(symbol)
        
        logger.info(f"Filtered symbols: {len(filtered)} out of {len(symbols)}")
        return filtered

    def _is_valid_symbol(self, symbol: str) -> bool:
        """Check if a symbol is valid according to configuration."""
        if '/' not in symbol:
            return False
        
        base, quote = symbol.split('/', 1)
        
        # Check quote assets
        if quote not in self.config.symbols.quote_assets:
            return False
        
        # Check whitelist
        if self.config.symbols.whitelist and base not in self.config.symbols.whitelist:
            return False
        
        # Check blacklist
        if base in self.config.symbols.blacklist:
            return False
        
        return True

    def get_trading_pairs(self, base_asset: str) -> List[str]:
        """Get all trading pairs for a base asset."""
        if not self.universe:
            return []
        
        pairs = []
        for symbol in self.universe.intersection_symbols:
            if symbol.startswith(f"{base_asset}/"):
                pairs.append(symbol)
        
        return pairs

    def get_quote_assets(self, base_asset: str) -> List[str]:
        """Get all quote assets for a base asset."""
        pairs = self.get_trading_pairs(base_asset)
        return [pair.split('/')[1] for pair in pairs]

    def get_intersection_symbols(self) -> List[str]:
        """Get symbols available on both exchanges."""
        if not self.universe:
            return []
        return self.universe.intersection_symbols

    def get_exchange_symbols(self, exchange: str) -> List[str]:
        """Get symbols available on a specific exchange."""
        if not self.universe:
            return []
        return self.universe.exchange_symbols.get(exchange, [])

    def is_symbol_available(self, symbol: str, exchange: str) -> bool:
        """Check if a symbol is available on a specific exchange."""
        if not self.universe:
            return False
        return symbol in self.universe.exchange_symbols.get(exchange, [])

    def get_preferred_quote_asset(self, base_asset: str) -> Optional[str]:
        """Get the preferred quote asset for a base asset."""
        available_quotes = self.get_quote_assets(base_asset)
        
        # Prefer USDT if available
        if self.config.symbols.prefer_stable in available_quotes:
            return self.config.symbols.prefer_stable
        
        # Return first available quote asset
        return available_quotes[0] if available_quotes else None

    def get_symbol_summary(self) -> Dict[str, Any]:
        """Get summary of symbol universe."""
        if not self.universe:
            return {}
        
        return {
            'total_symbols': len(self.universe.symbols),
            'intersection_symbols': len(self.universe.intersection_symbols),
            'base_assets': len(self.universe.base_assets),
            'quote_assets': len(self.universe.quote_assets),
            'exchanges': list(self.universe.exchange_symbols.keys()),
            'top_base_assets': sorted(list(self.universe.base_assets))[:10],
            'quote_assets_list': sorted(list(self.universe.quote_assets))
        }
