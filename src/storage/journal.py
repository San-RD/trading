"""Trade journaling for cross-exchange arbitrage bot."""

from typing import Dict, List, Any, Optional
from loguru import logger

from .db import Database


class TradeJournal:
    """Handles trade journaling and reporting."""

    def __init__(self, database: Database):
        self.database = database

    async def journal_opportunity(self, opportunity) -> bool:
        """Journal a detected arbitrage opportunity."""
        try:
            await self.database.insert_opportunity(opportunity)
            logger.info(f"Journaled opportunity: {opportunity.symbol} {opportunity.direction.value}")
            return True
        except Exception as e:
            logger.error(f"Failed to journal opportunity: {e}")
            return False

    async def journal_execution(self, execution_result) -> bool:
        """Journal an execution result with enhanced metrics."""
        try:
            # Extract enhanced metrics for detailed journaling
            enhanced_metrics = {
                'raw_edge_bps': getattr(execution_result, 'raw_edge_bps', 0),
                'fees_bps': getattr(execution_result, 'fees_bps', 0),
                'slippage_bps': getattr(execution_result, 'slippage_bps', 0),
                'realized_bps': getattr(execution_result, 'realized_bps', 0),
                'leg_fill_rates': getattr(execution_result, 'leg_fill_rates', {}),
                'leg_latencies': getattr(execution_result, 'leg_latencies', {}),
                'venue_clock_skew_ms': getattr(execution_result, 'venue_clock_skew_ms', 0),
                'partial_fill_handling': getattr(execution_result, 'partial_fill_handling', 'none'),
                'adverse_selection_bps': getattr(execution_result, 'adverse_selection_bps', 0),
                'rebalance_cost_bps': getattr(execution_result, 'rebalance_cost_bps', 0)
            }
            
            # Log detailed execution metrics
            logger.info(f"Execution metrics for {execution_result.opportunity.symbol}:")
            logger.info(f"  Raw edge: {enhanced_metrics['raw_edge_bps']:.2f} bps")
            logger.info(f"  Fees: {enhanced_metrics['fees_bps']:.2f} bps")
            logger.info(f"  Slippage: {enhanced_metrics['slippage_bps']:.2f} bps")
            logger.info(f"  Realized: {enhanced_metrics['realized_bps']:.2f} bps")
            logger.info(f"  Venue skew: {enhanced_metrics['venue_clock_skew_ms']:.1f} ms")
            
            # Log per-leg details
            for leg_name, fill_rate in enhanced_metrics['leg_fill_rates'].items():
                latency = enhanced_metrics['leg_latencies'].get(leg_name, 0)
                logger.info(f"  {leg_name}: {fill_rate:.1%} fill, {latency:.1f} ms")
            
            # Store enhanced metrics in database
            await self.database.insert_execution(execution_result, enhanced_metrics)
            logger.info(f"Journaled execution with enhanced metrics: {execution_result.opportunity.symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to journal execution: {e}")
            return False

    async def generate_report(self, days: int) -> str:
        """Generate trading report for last N days."""
        try:
            performance = await self.database.get_performance_summary(days)
            opportunities = await self.database.get_recent_opportunities(50)
            
            report = f"""
=== TRADING REPORT (Last {days} days) ===
Performance Summary:
- Total Trades: {performance.get('summary', {}).get('total_trades', 0)}
- Win Rate: {performance.get('summary', {}).get('win_rate', 0):.2%}
- Total PnL: ${performance.get('summary', {}).get('total_pnl', 0):.2f}
- Average Edge: {performance.get('summary', {}).get('avg_edge_bps', 0):.2f} bps
- Average Latency: {performance.get('summary', {}).get('avg_latency_ms', 0):.1f} ms

Recent Opportunities:
"""
            
            for opp in opportunities[:10]:  # Show top 10
                report += f"- {opp['symbol']}: {opp['direction']} @ {opp['edge_bps']:.2f} bps\n"
            
            return report
            
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            return f"Error generating report: {e}"

    async def get_performance_summary(self, days: int) -> Dict[str, Any]:
        """Get performance summary for last N days."""
        return await self.database.get_performance_summary(days)
