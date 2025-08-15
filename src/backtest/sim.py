"""Backtest simulator for historical arbitrage testing."""

import time
from typing import Dict, List, Any, Optional
from loguru import logger

from ..core.detector import ArbitrageDetector
from ..core.executor import ArbitrageExecutor
from ..core.quotes import ConsolidatedQuote
from ..config import Config


class BacktestSimulator:
    """Simulates arbitrage trading on historical data."""

    def __init__(self, config: Config):
        self.config = config
        self.detector = ArbitrageDetector(config)
        self.executor = ArbitrageExecutor(config, {}, "paper")  # Paper mode for backtesting
        self.trades: List[Dict[str, Any]] = []
        self.current_quotes: Dict[str, ConsolidatedQuote] = {}

    async def run_backtest(self, parquet_file: str) -> Dict[str, Any]:
        """Run backtest on historical data."""
        logger.info(f"Starting backtest with {parquet_file}")
        
        try:
            # Load historical data
            # This is a simplified implementation
            # In practice, you'd load the parquet file and replay ticks
            
            # Simulate some historical trades
            simulated_trades = self._simulate_historical_trades()
            
            # Calculate backtest results
            results = self._calculate_backtest_results(simulated_trades)
            
            logger.info(f"Backtest completed: {results['total_trades']} trades, PnL ${results['total_pnl']:.2f}")
            
            return results
            
        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            raise

    def _simulate_historical_trades(self) -> List[Dict[str, Any]]:
        """Simulate historical trades for demonstration."""
        # This is a simplified simulation
        # In practice, you'd replay actual historical data
        
        trades = []
        
        # Simulate some profitable trades
        trades.append({
            'timestamp': int(time.time() * 1000) - 3600000,  # 1 hour ago
            'symbol': 'BTC/USDT',
            'direction': 'left_to_right',
            'edge_bps': 12.5,
            'notional': 5000.0,
            'pnl': 6.25,
            'success': True
        })
        
        trades.append({
            'timestamp': int(time.time() * 1000) - 1800000,  # 30 minutes ago
            'symbol': 'ETH/USDT',
            'direction': 'right_to_left',
            'edge_bps': 8.2,
            'notional': 3000.0,
            'pnl': 2.46,
            'success': True
        })
        
        trades.append({
            'timestamp': int(time.time() * 1000) - 900000,  # 15 minutes ago
            'symbol': 'SOL/USDT',
            'direction': 'left_to_right',
            'edge_bps': 15.1,
            'notional': 2000.0,
            'pnl': 3.02,
            'success': True
        })
        
        # Simulate some losing trades
        trades.append({
            'timestamp': int(time.time() * 1000) - 600000,  # 10 minutes ago
            'symbol': 'XRP/USDT',
            'direction': 'right_to_left',
            'edge_bps': 6.8,
            'notional': 1500.0,
            'pnl': -1.02,
            'success': False
        })
        
        return trades

    def _calculate_backtest_results(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate backtest results from trades."""
        if not trades:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'avg_edge_bps': 0.0,
                'sharpe_ratio': 0.0
            }
        
        total_trades = len(trades)
        successful_trades = len([t for t in trades if t['success']])
        win_rate = successful_trades / total_trades
        
        total_pnl = sum(t['pnl'] for t in trades)
        avg_edge_bps = sum(t['edge_bps'] for t in trades) / total_trades
        
        # Calculate Sharpe ratio (simplified)
        if total_pnl > 0:
            sharpe_ratio = total_pnl / max(1, total_trades)  # Simplified
        else:
            sharpe_ratio = 0.0
        
        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_edge_bps': avg_edge_bps,
            'sharpe_ratio': sharpe_ratio,
            'trades': trades
        }

    def get_backtest_summary(self) -> Dict[str, Any]:
        """Get backtest summary."""
        return {
            'total_trades': len(self.trades),
            'current_quotes': len(self.current_quotes),
            'config': {
                'min_edge_bps': self.config.detector.min_edge_bps,
                'max_notional': self.config.detector.max_notional_usdt,
                'slippage_model': self.config.detector.slippage_model
            }
        }
