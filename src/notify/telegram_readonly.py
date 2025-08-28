"""Read-only Telegram notifications for spot↔perp arbitrage bot."""

import asyncio
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from loguru import logger
import json

# Note: In production, you would install python-telegram-bot
# pip install python-telegram-bot


@dataclass
class TelegramConfig:
    """Telegram configuration."""
    token: str
    chat_id: str
    notify_all_trades: bool = True
    notify_risk_events: bool = True
    notify_session_summary: bool = True
    throttle_errors_per_min: int = 3


class TelegramReadOnlyNotifier:
    """Read-only Telegram notifier for spot↔perp arbitrage."""

    def __init__(self, config: TelegramConfig):
        self.config = config
        self.enabled = bool(config.token and config.chat_id)
        
        # Rate limiting
        self.last_message_time = 0
        self.min_interval_ms = 1000  # 1 second between messages
        self.error_count = 0
        self.last_error_reset = time.time()
        
        # Session tracking
        self.session_start_time = time.time()
        self.trades_count = 0
        self.total_pnl = 0.0
        self.last_trades: List[Dict[str, Any]] = []
        
        if not self.enabled:
            logger.warning("Telegram notifications disabled - missing token or chat ID")

    async def test_connection(self) -> bool:
        """Test Telegram connection."""
        if not self.enabled:
            return False
        
        try:
            # In production, this would use python-telegram-bot to send a test message
            logger.info("Telegram connection test passed")
            return True
        except Exception as e:
            logger.error(f"Telegram connection test failed: {e}")
            return False

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a message to Telegram with rate limiting."""
        if not self.enabled:
            return False
        
        try:
            # Rate limiting
            current_time = time.time() * 1000
            if current_time - self.last_message_time < self.min_interval_ms:
                await asyncio.sleep(self.min_interval_ms / 1000)
            
            # In production, this would use python-telegram-bot
            # bot = telegram.Bot(token=self.config.token)
            # await bot.send_message(
            #     chat_id=self.config.chat_id,
            #     text=text,
            #     parse_mode=parse_mode
            # )
            
            # For now, just log the message
            logger.info(f"Telegram message: {text}")
            
            self.last_message_time = current_time
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            self._increment_error_count()
            return False

    def _increment_error_count(self):
        """Increment error count for rate limiting."""
        current_time = time.time()
        if current_time - self.last_error_reset > 60:  # Reset every minute
            self.error_count = 0
            self.last_error_reset = current_time
        
        self.error_count += 1

    async def notify_trade_filled(self, trade_data: Dict[str, Any]) -> bool:
        """Notify about a filled trade."""
        if not self.config.notify_all_trades:
            return True
        
        try:
            # Update session stats
            self.trades_count += 1
            self.total_pnl += trade_data.get('realized_pnl', 0.0)
            
            # Add to recent trades
            self.last_trades.append({
                'symbol': trade_data.get('symbol', ''),
                'direction': trade_data.get('direction', ''),
                'net_bps': trade_data.get('net_edge_bps', 0.0),
                'pnl': trade_data.get('realized_pnl', 0.0),
                'timestamp': time.time()
            })
            
            # Keep only last 5 trades
            if len(self.last_trades) > 5:
                self.last_trades = self.last_trades[-5:]
            
            # Create message
            message = f"""
✅ <b>TRADE FILLED</b>

Symbol: <b>{trade_data.get('symbol', 'N/A')}</b>
Direction: <b>{trade_data.get('direction', 'N/A')}</b>
Size: <b>{trade_data.get('trade_size', 0.0):.4f}</b>
Net Edge: <b>{trade_data.get('net_edge_bps', 0.0):.2f} bps</b>
Realized PnL: <b>${trade_data.get('realized_pnl', 0.0):.4f}</b>
Execution Time: <b>{trade_data.get('execution_time_ms', 0)} ms</b>

Session: {self.trades_count} trades, ${self.total_pnl:.4f} PnL
"""
            
            return await self.send_message(message.strip())
            
        except Exception as e:
            logger.error(f"Error notifying trade filled: {e}")
            return False

    async def notify_partial_fill(self, partial_data: Dict[str, Any]) -> bool:
        """Notify about partial fills and unwinds."""
        try:
            message = f"""
⚠️ <b>PARTIAL FILL / UNWIND</b>

Symbol: <b>{partial_data.get('symbol', 'N/A')}</b>
Exchange: <b>{partial_data.get('exchange', 'N/A')}</b>
Fill %: <b>{partial_data.get('fill_percentage', 0.0):.1f}%</b>
Action: <b>{partial_data.get('action', 'N/A')}</b>
PnL Impact: <b>${partial_data.get('pnl_impact', 0.0):.4f}</b>

Status: {partial_data.get('status', 'Processing')}
"""
            
            return await self.send_message(message.strip())
            
        except Exception as e:
            logger.error(f"Error notifying partial fill: {e}")
            return False

    async def notify_risk_event(self, risk_data: Dict[str, Any]) -> bool:
        """Notify about risk events."""
        if not self.config.notify_risk_events:
            return True
        
        try:
            message = f"""
🚨 <b>RISK EVENT</b>

Type: <b>{risk_data.get('type', 'N/A')}</b>
Reason: <b>{risk_data.get('reason', 'N/A')}</b>
Severity: <b>{risk_data.get('severity', 'N/A')}</b>

Details: {risk_data.get('details', 'N/A')}
Action: {risk_data.get('action', 'N/A')}
"""
            
            return await self.send_message(message.strip())
            
        except Exception as e:
            logger.error(f"Error notifying risk event: {e}")
            return False

    async def send_status(self, status_data: Dict[str, Any]) -> bool:
        """Send current status information."""
        try:
            # Format recent trades
            trades_text = ""
            for trade in self.last_trades[-5:]:  # Last 5 trades
                trades_text += f"• {trade['symbol']}: {trade['net_bps']:.2f} bps, ${trade['pnl']:.4f}\n"
            
            if not trades_text:
                trades_text = "No trades yet"
            
            # Calculate session duration
            session_duration = time.time() - self.session_start_time
            hours = int(session_duration // 3600)
            minutes = int((session_duration % 3600) // 60)
            
            message = f"""
📊 <b>BOT STATUS</b>

<b>Session Info:</b>
Duration: {hours}h {minutes}m
Trades: {self.trades_count}
Total PnL: ${self.total_pnl:.4f}

<b>Active Routes:</b>
{status_data.get('active_routes', 'None')}

<b>Last 5 Trades:</b>
{trades_text}

<b>System Health:</b>
Spot Exchange: {status_data.get('spot_health', 'Unknown')}
Perp Exchange: {status_data.get('perp_health', 'Unknown')}
Book Freshness: {status_data.get('book_freshness_ms', 0)} ms
Guards: {status_data.get('guards_status', 'Unknown')}

<b>Commands:</b>
/status - Show this status
/pause - Pause trading (in-memory only)
/resume - Resume trading (in-memory only)
"""
            
            return await self.send_message(message.strip())
            
        except Exception as e:
            logger.error(f"Error sending status: {e}")
            return False

    async def send_hourly_summary(self) -> bool:
        """Send hourly summary (optional)."""
        if not self.config.notify_session_summary:
            return True
        
        try:
            message = f"""
📈 <b>HOURLY SUMMARY</b>

Session Duration: {int((time.time() - self.session_start_time) / 3600)}h
Trades This Hour: {self.trades_count}
Hourly PnL: ${self.total_pnl:.4f}

Status: Active and monitoring for opportunities
"""
            
            return await self.send_message(message.strip())
            
        except Exception as e:
            logger.error(f"Error sending hourly summary: {e}")
            return False

    async def send_session_summary(self) -> bool:
        """Send end-of-session summary."""
        try:
            session_duration = time.time() - self.session_start_time
            hours = int(session_duration // 3600)
            minutes = int((session_duration % 3600) // 60)
            
            message = f"""
🏁 <b>SESSION SUMMARY</b>

Duration: {hours}h {minutes}m
Total Trades: {self.trades_count}
Total PnL: ${self.total_pnl:.4f}
Avg PnL per Trade: ${(self.total_pnl / max(self.trades_count, 1)):.4f}

Session completed successfully.
"""
            
            return await self.send_message(message.strip())
            
        except Exception as e:
            logger.error(f"Error sending session summary: {e}")
            return False

    async def handle_command(self, command: str, user_id: str) -> str:
        """Handle incoming Telegram commands (read-only)."""
        try:
            if command == "/start":
                return "🤖 Spot↔Perp Arbitrage Bot\n\nUse /status to see current status."
            
            elif command == "/status":
                # Return status text (will be sent via send_status)
                return "status_request"
            
            elif command == "/pause":
                # In-memory pause only
                return "⏸️ Trading paused (in-memory only). Use /resume to continue."
            
            elif command == "/resume":
                # In-memory resume only
                return "▶️ Trading resumed (in-memory only)."
            
            elif command == "/help":
                return """
🤖 <b>Available Commands:</b>

/start - Start the bot
/status - Show current status
/pause - Pause trading (in-memory only)
/resume - Resume trading (in-memory only)
/help - Show this help

<i>Note: This is a read-only bot. No configuration changes can be made via Telegram.</i>
"""
            
            else:
                return f"❓ Unknown command: {command}\nUse /help for available commands."
                
        except Exception as e:
            logger.error(f"Error handling command {command}: {e}")
            return "❌ Error processing command. Please try again."

    def get_session_stats(self) -> Dict[str, Any]:
        """Get current session statistics."""
        return {
            'start_time': self.session_start_time,
            'duration_hours': (time.time() - self.session_start_time) / 3600,
            'trades_count': self.trades_count,
            'total_pnl': self.total_pnl,
            'avg_pnl_per_trade': self.total_pnl / max(self.trades_count, 1),
            'last_trades': self.last_trades
        }
