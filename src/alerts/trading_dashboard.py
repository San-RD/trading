"""Trading dashboard for monitoring arbitrage bot performance."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from src.storage.models import Trade, Opportunity, Order, Fill
from src.storage.db import DatabaseManager


class TradingDashboard:
    """Dashboard for monitoring trading performance and status."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
        self.chat_id = None
        
    def set_chat_id(self, chat_id: str):
        """Set the Telegram chat ID for notifications."""
        self.chat_id = chat_id
        self.logger.info(f"Trading dashboard chat ID set to: {chat_id}")
    
    async def get_current_status(self) -> Dict[str, Any]:
        """Get current trading bot status."""
        try:
            # Try to get real data from database
            trades = await self.db_manager.get_recent_trades(limit=100)
            
            if trades:
                # Calculate real statistics
                total_trades = len(trades)
                total_pnl = sum(trade.get('pnl', 0) for trade in trades)
                profitable_trades = len([t for t in trades if t.get('pnl', 0) > 0])
                win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
                
                # Get last trade time
                last_trade = max(trades, key=lambda x: x.get('timestamp', datetime.min))
                last_trade_time = last_trade.get('timestamp')
                
                # Get session start (first trade time)
                first_trade = min(trades, key=lambda x: x.get('timestamp', datetime.max))
                session_start = first_trade.get('timestamp').strftime('%Y-%m-%d %H:%M:%S') if first_trade.get('timestamp') else 'N/A'
                
                return {
                    'session_active': True,
                    'total_trades': total_trades,
                    'win_rate': win_rate,
                    'total_pnl': total_pnl,
                    'last_trade_time': last_trade_time,
                    'session_start': session_start
                }
            else:
                # No trades yet, return default
                return {
                    'session_active': False,
                    'total_trades': 0,
                    'win_rate': 0.0,
                    'total_pnl': 0.0,
                    'last_trade_time': None,
                    'session_start': 'No trades yet'
                }
            
        except Exception as e:
            self.logger.error(f"Error getting current status: {e}")
            return {}
    
    async def get_daily_summary(self) -> Dict[str, Any]:
        """Get daily trading summary."""
        try:
            # Get today's trades from database
            today = datetime.now().date()
            start_time = datetime.combine(today, datetime.min.time())
            end_time = datetime.combine(today, datetime.max.time())
            
            trades = await self.db_manager.get_trades_in_period(start_time, end_time)
            
            if trades:
                total_trades = len(trades)
                total_pnl = sum(trade.get('pnl', 0) for trade in trades)
                profitable_trades = len([t for t in trades if t.get('pnl', 0) > 0])
                losing_trades = len([t for t in trades if t.get('pnl', 0) < 0])
                win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
                
                return {
                    'date': today.strftime('%Y-%m-%d'),
                    'total_trades': total_trades,
                    'total_pnl': total_pnl,
                    'win_rate': win_rate,
                    'profitable_trades': profitable_trades,
                    'losing_trades': losing_trades
                }
            else:
                return {
                    'date': today.strftime('%Y-%m-%d'),
                    'total_trades': 0,
                    'total_pnl': 0.0,
                    'win_rate': 0.0,
                    'profitable_trades': 0,
                    'losing_trades': 0
                }
            
        except Exception as e:
            self.logger.error(f"Error getting daily summary: {e}")
            return {}
    
    async def get_weekly_summary(self) -> Dict[str, Any]:
        """Get weekly trading summary."""
        try:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=7)
            start_time = datetime.combine(start_date, datetime.min.time())
            end_time = datetime.combine(end_date, datetime.max.time())
            
            trades = await self.db_manager.get_trades_in_period(start_time, end_time)
            
            if trades:
                total_trades = len(trades)
                total_pnl = sum(trade.get('pnl', 0) for trade in trades)
                profitable_trades = len([t for t in trades if t.get('pnl', 0) > 0])
                losing_trades = len([t for t in trades if t.get('pnl', 0) < 0])
                win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
                
                return {
                    'period': f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                    'total_trades': total_trades,
                    'total_pnl': total_pnl,
                    'win_rate': win_rate,
                    'profitable_trades': profitable_trades,
                    'losing_trades': losing_trades
                }
            else:
                return {
                    'period': f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                    'total_trades': 0,
                    'total_pnl': 0.0,
                    'win_rate': 0.0,
                    'profitable_trades': 0,
                    'losing_trades': 0
                }
            
        except Exception as e:
            self.logger.error(f"Error getting weekly summary: {e}")
            return {}
    
    async def get_monthly_summary(self) -> Dict[str, Any]:
        """Get monthly trading summary."""
        try:
            end_date = datetime.now().date()
            start_date = end_date.replace(day=1)  # First day of current month
            start_time = datetime.combine(start_date, datetime.min.time())
            end_time = datetime.combine(end_date, datetime.max.time())
            
            trades = await self.db_manager.get_trades_in_period(start_time, end_time)
            
            if trades:
                total_trades = len(trades)
                total_pnl = sum(trade.get('pnl', 0) for trade in trades)
                profitable_trades = len([t for t in trades if t.get('pnl', 0) > 0])
                losing_trades = len([t for t in trades if t.get('pnl', 0) < 0])
                win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
                
                return {
                    'month': start_date.strftime('%Y-%m'),
                    'total_trades': total_trades,
                    'total_pnl': total_pnl,
                    'win_rate': win_rate,
                    'profitable_trades': profitable_trades,
                    'losing_trades': losing_trades
                }
            else:
                return {
                    'month': start_date.strftime('%Y-%m'),
                    'total_trades': 0,
                    'total_pnl': 0.0,
                    'win_rate': 0.0,
                    'profitable_trades': 0,
                    'losing_trades': 0
                }
            
        except Exception as e:
            self.logger.error(f"Error getting monthly summary: {e}")
            return {}
    
    async def periodic_summary_update(self, interval_minutes: int = 15):
        """Send periodic summary updates."""
        while True:
            try:
                if self.chat_id:
                    status = await self.get_current_status()
                    if status.get('session_active'):
                        # Only send updates when trading is active
                        summary = await self.get_daily_summary()
                        if 'message' not in summary:
                            message = f"""
📊 *Periodic Trading Update*

*Status:* Active
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*Today's Summary:*
• Total Trades: {summary['total_trades']}
• Total P&L: ${summary['total_pnl']:.2f}
• Win Rate: {summary['win_rate']:.1f}%
• Profitable: {summary['profitable_trades']}
• Losing: {summary['losing_trades']}
                            """
                            # For now, just log the message
                            self.logger.info(f"Periodic update: {message}")
                
                await asyncio.sleep(interval_minutes * 60)
                
            except Exception as e:
                self.logger.error(f"Error in periodic summary update: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
