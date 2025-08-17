"""Session management for live trading tests."""

import asyncio
import time
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
from loguru import logger

from ..config import Config
from ..core.executor import ExecutionResult
from ..core.detector import ArbitrageOpportunity


class SessionManager:
    """Manages live trading session with time limits and result export."""
    
    def __init__(self, config: Config):
        self.config = config
        self.session_start = time.time()
        self.session_duration_hours = config.session.duration_hours
        self.max_trades = config.risk.max_trades_per_session
        self.target_pairs = config.session.target_pairs
        self.auto_stop = config.session.auto_stop
        self.export_results = config.session.export_results
        
        # Session tracking
        self.trades_executed: List[Dict[str, Any]] = []
        self.opportunities_detected: List[ArbitrageOpportunity] = []
        self.session_pnl = 0.0
        self.session_trades = 0
        
        logger.info(f"Session initialized: {self.session_duration_hours}h duration, max {self.max_trades} trades")
    
    def should_continue_session(self) -> bool:
        """Check if session should continue."""
        # Check time limit (0 = no time limit)
        if self.session_duration_hours > 0:
            elapsed_hours = (time.time() - self.session_start) / 3600
            if elapsed_hours >= self.session_duration_hours:
                logger.info(f"Session time limit reached: {elapsed_hours:.1f}h elapsed")
                return False
        
        # Check trade count limit (0 = no trade limit)
        if self.max_trades > 0 and self.session_trades >= self.max_trades:
            logger.info(f"Session trade limit reached: {self.session_trades} trades")
            return False
        
        return True
    
    def record_opportunity(self, opportunity: ArbitrageOpportunity) -> None:
        """Record detected opportunity."""
        self.opportunities_detected.append(opportunity)
    
    def record_trade(self, execution_result: ExecutionResult) -> None:
        """Record executed trade."""
        trade_record = {
            'timestamp': datetime.now().isoformat(),
            'symbol': execution_result.opportunity.symbol,
            'direction': execution_result.opportunity.direction.value,
            'buy_exchange': execution_result.opportunity.left_exchange,
            'sell_exchange': execution_result.opportunity.right_exchange,
            'spread_bps': execution_result.opportunity.spread_bps,
            'net_edge_bps': execution_result.opportunity.net_edge_bps,
            'trade_size_usdt': execution_result.opportunity.trade_size * execution_result.opportunity.buy_price,
            'fees_usdt': execution_result.metadata.get('total_fees', 0) if execution_result.metadata else 0,
            'slippage_bps': execution_result.metadata.get('left_slippage_bps', 0) + execution_result.metadata.get('right_slippage_bps', 0) if execution_result.metadata else 0,
            'realized_pnl': execution_result.realized_pnl,
            'execution_time_ms': execution_result.execution_time_ms,
            'success': execution_result.success
        }
        
        self.trades_executed.append(trade_record)
        self.session_pnl += execution_result.realized_pnl
        self.session_trades += 1
        
        logger.info(f"Trade recorded: {trade_record['symbol']} {trade_record['direction']}, PnL: ${trade_record['realized_pnl']:.4f}")
    
    def get_session_summary(self) -> Dict[str, Any]:
        """Get session summary statistics."""
        elapsed_hours = (time.time() - self.session_start) / 3600
        
        # Calculate success rate
        successful_trades = sum(1 for trade in self.trades_executed if trade['success'])
        success_rate = (successful_trades / len(self.trades_executed) * 100) if self.trades_executed else 0
        
        # Calculate average metrics
        avg_spread = sum(trade['spread_bps'] for trade in self.trades_executed) / len(self.trades_executed) if self.trades_executed else 0
        avg_pnl = sum(trade['realized_pnl'] for trade in self.trades_executed) / len(self.trades_executed) if self.trades_executed else 0
        
        # Handle unlimited sessions
        duration_display = "Unlimited" if self.session_duration_hours == 0 else f"{elapsed_hours:.1f}h"
        
        return {
            'session_duration_hours': duration_display,
            'total_opportunities': len(self.opportunities_detected),
            'total_trades': self.session_trades,
            'successful_trades': successful_trades,
            'success_rate_pct': success_rate,
            'total_pnl': self.session_pnl,
            'avg_pnl_per_trade': avg_pnl,
            'avg_spread_bps': avg_spread,
            'target_pairs': self.target_pairs,
            'session_start': datetime.fromtimestamp(self.session_start).isoformat(),
            'session_end': datetime.now().isoformat()
        }
    
    async def export_results_csv(self, filename: Optional[str] = None) -> str:
        """Export session results to CSV."""
        if not self.export_results:
            return ""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"live_test_results_{timestamp}.csv"
        
        filepath = Path(filename)
        
        # Export trades
        if self.trades_executed:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = self.trades_executed[0].keys()
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.trades_executed)
        
        # Export summary
        summary_filepath = filepath.with_name(f"{filepath.stem}_summary.csv")
        summary = self.get_session_summary()
        
        with open(summary_filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            for key, value in summary.items():
                writer.writerow([key, value])
        
        logger.info(f"Session results exported to {filepath} and {summary_filepath}")
        return str(filepath)
    
    def log_session_status(self) -> None:
        """Log current session status."""
        elapsed_hours = (time.time() - self.session_start) / 3600
        remaining_hours = self.session_duration_hours - elapsed_hours
        remaining_trades = self.max_trades - self.session_trades
        
        logger.info(f"Session Status: {elapsed_hours:.1f}h elapsed, {remaining_hours:.1f}h remaining")
        logger.info(f"Trades: {self.session_trades}/{self.max_trades} executed, PnL: ${self.session_pnl:.4f}")
        logger.info(f"Opportunities detected: {len(self.opportunities_detected)}")
        
        if remaining_trades <= 0:
            logger.warning("Session trade limit reached")
        if remaining_hours <= 0:
            logger.warning("Session time limit reached")
    
    async def wait_for_session_end(self) -> None:
        """Wait for session to end naturally."""
        while self.should_continue_session():
            await asyncio.sleep(60)  # Check every minute
            self.log_session_status()
        
        logger.info("Session ended naturally")
        await self.export_results_csv()
