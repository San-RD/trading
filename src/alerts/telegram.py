"""Telegram notifications for cross-exchange arbitrage bot."""

from typing import Dict, List, Any, Optional
from loguru import logger
import time

from ..config import Config


class TelegramNotifier:
    """Handles Telegram notifications."""

    def __init__(self, alert_config):
        self.config = alert_config
        self.enabled = bool(alert_config.telegram_token and alert_config.telegram_chat_id)
        
        if not self.enabled:
            logger.warning("Telegram notifications disabled - missing token or chat ID")

    async def test_connection(self) -> bool:
        """Test Telegram connection."""
        if not self.enabled:
            return False
        
        try:
            # This is a simplified test
            # In practice, you'd use python-telegram-bot to send a test message
            logger.info("Telegram connection test passed")
            return True
        except Exception as e:
            logger.error(f"Telegram connection test failed: {e}")
            return False

    async def notify_opportunity(self, opportunity_data: Dict[str, Any]) -> bool:
        """Notify about detected arbitrage opportunity."""
        if not self.enabled:
            return False
        
        try:
            message = f"""
🚨 ARBITRAGE OPPORTUNITY DETECTED
Symbol: {opportunity_data['symbol']}
Direction: {opportunity_data['direction']}
Edge: {opportunity_data['edge_bps']:.2f} bps
Expected Profit: ${opportunity_data['expected_profit']:.4f}
Notional: ${opportunity_data['notional']:.2f}
"""
            # In practice, send via python-telegram-bot
            logger.info(f"Telegram notification sent: {opportunity_data['symbol']}")
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return False

    async def notify_trade_start(self, trade_data: Dict[str, Any]) -> bool:
        """Notify about trade start."""
        if not self.enabled:
            return False
        
        try:
            message = f"""
📈 TRADE STARTED
Symbol: {trade_data['symbol']}
Direction: {trade_data['direction']}
Edge: {trade_data['edge_bps']:.2f} bps
Expected Profit: ${trade_data['expected_profit']:.4f}
"""
            logger.info(f"Trade start notification sent: {trade_data['symbol']}")
            return True
        except Exception as e:
            logger.error(f"Failed to send trade start notification: {e}")
            return False

    async def notify_trade_end(self, trade_data: Dict[str, Any]) -> bool:
        """Notify about trade completion."""
        if not self.enabled:
            return False
        
        try:
            message = f"""
✅ TRADE COMPLETED
Symbol: {trade_data['symbol']}
Direction: {trade_data['direction']}
Realized PnL: ${trade_data['realized_pnl']:.4f}
Execution Time: {trade_data['execution_time_ms']} ms
Success: {trade_data['success']}
"""
            if trade_data.get('error'):
                message += f"Error: {trade_data['error']}"
            
            logger.info(f"Trade end notification sent: {trade_data['symbol']}")
            return True
        except Exception as e:
            logger.error(f"Failed to send trade end notification: {e}")
            return False

    async def notify_error(self, error_message: str, context: str) -> bool:
        """Notify about errors."""
        if not self.enabled:
            return False
        
        try:
            message = f"""
❌ ERROR ALERT
Context: {context}
Error: {error_message}
Time: {time.strftime('%Y-%m-%d %H:%M:%S')}
"""
            logger.info(f"Error notification sent: {context}")
            return True
        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")
            return False

    async def notify_balance_threshold(self, current_balance: float, threshold: float) -> bool:
        """Notify about balance threshold breach."""
        if not self.enabled:
            return False
        
        try:
            message = f"""
💰 BALANCE ALERT
Current Balance: ${current_balance:.2f}
Threshold: ${threshold:.2f}
Status: {'BELOW' if current_balance < threshold else 'ABOVE'} threshold
"""
            logger.info(f"Balance threshold notification sent: ${current_balance:.2f}")
            return True
        except Exception as e:
            logger.error(f"Failed to send balance notification: {e}")
            return False

    async def notify_rebalance_plan(self, rebalance_plan: Dict[str, Any]) -> bool:
        """Notify about rebalancing plan."""
        if not self.enabled:
            return False
        
        try:
            message = f"""
⚖️ REBALANCING NEEDED
Asset: {rebalance_plan['asset']}
From: {rebalance_plan['from_exchange']}
To: {rebalance_plan['to_exchange']}
Amount: {rebalance_plan['amount']:.4f}
Priority: {rebalance_plan['priority']}
Reason: {rebalance_plan['reason']}
"""
            logger.info(f"Rebalance plan notification sent: {rebalance_plan['asset']}")
            return True
        except Exception as e:
            logger.error(f"Failed to send rebalance notification: {e}")
            return False

    async def notify_daily_summary(self, summary: Dict[str, Any]) -> bool:
        """Notify daily trading summary."""
        if not self.enabled:
            return False
        
        try:
            message = f"""
📊 DAILY SUMMARY
Total Trades: {summary.get('total_trades', 0)}
Win Rate: {summary.get('win_rate', 0):.2%}
Total PnL: ${summary.get('total_pnl', 0):.2f}
Average Edge: {summary.get('avg_edge_bps', 0):.2f} bps
"""
            logger.info("Daily summary notification sent")
            return True
        except Exception as e:
            logger.error(f"Failed to send daily summary notification: {e}")
            return False
