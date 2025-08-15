"""Utility functions for the trading bot."""

from typing import Dict, List, Optional
from decimal import Decimal
import time


def format_bps(bps: float) -> str:
    """Format basis points with appropriate precision."""
    if bps >= 100:
        return f"{bps:.0f} bps"
    elif bps >= 10:
        return f"{bps:.1f} bps"
    else:
        return f"{bps:.2f} bps"


def calculate_notional(price: float, quantity: float) -> float:
    """Calculate notional value."""
    return price * quantity


def format_usdt(amount: float) -> str:
    """Format USDT amount with appropriate precision."""
    if abs(amount) >= 1000:
        return f"${amount:.0f}"
    elif abs(amount) >= 100:
        return f"${amount:.1f}"
    elif abs(amount) >= 10:
        return f"${amount:.2f}"
    else:
        return f"${amount:.4f}"


def format_percentage(value: float) -> str:
    """Format percentage value."""
    return f"{value:.2%}"


def calculate_roi(initial: float, final: float) -> float:
    """Calculate return on investment."""
    if initial == 0:
        return 0.0
    return (final - initial) / initial


def calculate_annualized_roi(initial: float, final: float, days: float) -> float:
    """Calculate annualized ROI."""
    if days <= 0 or initial == 0:
        return 0.0
    
    roi = calculate_roi(initial, final)
    annualized = (1 + roi) ** (365 / days) - 1
    return annualized


def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.02) -> float:
    """Calculate Sharpe ratio."""
    if not returns:
        return 0.0
    
    avg_return = sum(returns) / len(returns)
    variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
    std_dev = variance ** 0.5
    
    if std_dev == 0:
        return 0.0
    
    return (avg_return - risk_free_rate) / std_dev


def calculate_max_drawdown(values: List[float]) -> float:
    """Calculate maximum drawdown."""
    if not values:
        return 0.0
    
    peak = values[0]
    max_dd = 0.0
    
    for value in values:
        if value > peak:
            peak = value
        else:
            dd = (peak - value) / peak
            max_dd = max(max_dd, dd)
    
    return max_dd


def calculate_win_rate(trades: List[Dict]) -> float:
    """Calculate win rate from trades."""
    if not trades:
        return 0.0
    
    winning_trades = sum(1 for trade in trades if trade.get('pnl', 0) > 0)
    return winning_trades / len(trades)


def calculate_profit_factor(trades: List[Dict]) -> float:
    """Calculate profit factor (gross profit / gross loss)."""
    gross_profit = sum(trade.get('pnl', 0) for trade in trades if trade.get('pnl', 0) > 0)
    gross_loss = abs(sum(trade.get('pnl', 0) for trade in trades if trade.get('pnl', 0) < 0))
    
    if gross_loss == 0:
        return float('inf') if gross_profit > 0 else 1.0
    
    return gross_profit / gross_loss


def format_timestamp(timestamp: float) -> str:
    """Format timestamp for display."""
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))


def format_duration(seconds: float) -> str:
    """Format duration in human readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, returning default if denominator is zero."""
    if denominator == 0:
        return default
    return numerator / denominator


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max."""
    return max(min_val, min(value, max_val))


def is_stale_timestamp(timestamp: float, max_age_seconds: float) -> bool:
    """Check if a timestamp is stale."""
    return time.time() - timestamp > max_age_seconds
