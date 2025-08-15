"""Risk management for cross-exchange arbitrage."""

import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from loguru import logger

from .detector import ArbitrageOpportunity
from .executor import ExecutionResult
from ..config import Config


class RiskLimitExceeded(Exception):
    """Raised when risk limits are exceeded."""
    pass


@dataclass
class RiskMetrics:
    """Risk management metrics."""
    total_trades: int
    successful_trades: int
    total_pnl: float
    consecutive_losses: int
    max_drawdown: float
    daily_pnl: float
    daily_notional: float
    last_trade_time: int
    risk_score: float


class RiskManager:
    """Manages risk controls and monitoring."""

    def __init__(self, config: Config):
        self.config = config
        self.metrics = RiskMetrics(
            total_trades=0,
            successful_trades=0,
            total_pnl=0.0,
            consecutive_losses=0,
            max_drawdown=0.0,
            daily_pnl=0.0,
            daily_notional=0.0,
            last_trade_time=0,
            risk_score=0.0
        )
        self.daily_reset_time = int(time.time())
        self.max_consecutive_losses = config.risk.max_consecutive_losses
        self.max_daily_loss = config.risk.max_daily_loss
        self.max_daily_notional = config.risk.max_daily_notional
        
        # Initialize additional attributes for backward compatibility
        self.total_trades = 0
        self.current_pnl = 0.0
        self.daily_trades = 0
        self.session_trades = 0
        self.max_pnl = 0.0
        self.initial_balance = 100.0  # Default starting balance

    def check_execution_risk(self, opportunity: ArbitrageOpportunity) -> tuple[bool, Optional[str]]:
        """Check if execution is safe from a risk perspective."""
        current_time = int(time.time() * 1000)
        
        # Check if opportunity has expired
        if current_time > opportunity.expires_at:
            return False, "Opportunity expired"
        
        # Check quotes age
        if opportunity.quotes_age_ms > self.config.detector.min_book_bbo_age_ms:
            return False, "Quotes too old"
        
        # Check notional limits
        if opportunity.notional_value > self.config.detector.max_notional_usdt:
            return False, f"Notional value {opportunity.notional_value} exceeds limit {self.config.detector.max_notional_usdt}"
        
        # Check daily notional limit
        if self.metrics.daily_notional + opportunity.notional_value > self.max_daily_notional:
            return False, f"Daily notional limit exceeded"
        
        # Check consecutive losses
        if self.metrics.consecutive_losses >= self.max_consecutive_losses:
            return False, f"Too many consecutive losses: {self.metrics.consecutive_losses}"
        
        # Check daily PnL limit
        if self.metrics.daily_pnl < self.max_daily_loss:
            return False, f"Daily loss limit exceeded: {self.metrics.daily_pnl}"
        
        # Check risk score
        if self.metrics.risk_score > 0.8:  # High risk
            return False, f"Risk score too high: {self.metrics.risk_score:.2f}"
        
        return True, None

    def update_risk_metrics(self, execution_result: ExecutionResult):
        """Update risk metrics after execution."""
        current_time = int(time.time())
        
        # Update trade counts
        self.metrics.total_trades += 1
        if execution_result.success:
            self.metrics.successful_trades += 1
            self.metrics.consecutive_losses = 0
        else:
            self.metrics.consecutive_losses += 1
        
        # Update PnL
        self.metrics.total_pnl += execution_result.realized_pnl
        self.metrics.daily_pnl += execution_result.realized_pnl
        
        # Update notional
        if execution_result.opportunity:
            self.metrics.daily_notional += execution_result.opportunity.notional_value
        
        # Update drawdown
        if execution_result.realized_pnl < 0:
            current_drawdown = abs(execution_result.realized_pnl)
            if current_drawdown > self.metrics.max_drawdown:
                self.metrics.max_drawdown = current_drawdown
        
        # Update last trade time
        self.metrics.last_trade_time = current_time
        
        # Calculate risk score
        self._calculate_risk_score()
        
        # Check if we need to reset daily metrics
        if current_time - self.daily_reset_time > 86400:  # 24 hours
            self._reset_daily_metrics()
        
        logger.info(f"Risk metrics updated: trades={self.metrics.total_trades}, "
                   f"pnl=${self.metrics.total_pnl:.2f}, consecutive_losses={self.metrics.consecutive_losses}")

    def _calculate_risk_score(self):
        """Calculate current risk score (0.0 = low risk, 1.0 = high risk)."""
        risk_score = 0.0
        
        # Consecutive losses factor
        loss_factor = min(1.0, self.metrics.consecutive_losses / self.max_consecutive_losses)
        risk_score += loss_factor * 0.3
        
        # Daily PnL factor
        if self.metrics.daily_pnl < 0:
            pnl_factor = min(1.0, abs(self.metrics.daily_pnl) / abs(self.max_daily_loss))
            risk_score += pnl_factor * 0.3
        
        # Drawdown factor
        drawdown_factor = min(1.0, self.metrics.max_drawdown / 1000.0)  # Normalize to $1000
        risk_score += drawdown_factor * 0.2
        
        # Success rate factor
        if self.metrics.total_trades > 0:
            success_rate = self.metrics.successful_trades / self.metrics.total_trades
            success_factor = 1.0 - success_rate
            risk_score += success_factor * 0.2
        
        self.metrics.risk_score = min(1.0, risk_score)

    def _reset_daily_metrics(self):
        """Reset daily metrics."""
        self.metrics.daily_pnl = 0.0
        self.metrics.daily_notional = 0.0
        self.daily_reset_time = int(time.time())
        logger.info("Daily risk metrics reset")

    def should_stop_trading(self, execution_result: Optional[ExecutionResult] = None) -> bool:
        """Check if trading should be stopped based on risk limits."""
        # Check consecutive losses
        if self.metrics.consecutive_losses >= self.config.risk.max_consecutive_losses:
            logger.warning(f"Stopping trading due to {self.metrics.consecutive_losses} consecutive losses")
            return True
        
        # Check daily loss limit
        if self.metrics.daily_pnl < self.config.risk.max_daily_loss:
            logger.warning(f"Stopping trading due to daily loss limit: ${self.metrics.daily_pnl:.2f}")
            return True
        
        # Check drawdown
        if self.max_pnl > 0:
            current_drawdown = (self.current_pnl - self.max_pnl) / self.max_pnl * 100
            if current_drawdown < -self.config.risk.max_drawdown_pct:
                logger.warning(f"Stopping trading due to drawdown: {current_drawdown:.2f}%")
                return True
        
        # Check emergency stop PnL
        if self.current_pnl < self.config.risk.emergency_stop_pnl:
            logger.warning(f"Stopping trading due to emergency stop PnL: ${self.current_pnl:.2f}")
            return True
        
        # Check daily trade count
        if self.daily_trades >= self.config.risk.max_trades_per_day:
            logger.warning(f"Stopping trading due to daily trade limit: {self.daily_trades}")
            return True
        
        # Check session trade count
        if self.session_trades >= self.config.risk.max_trades_per_session:
            logger.warning(f"Stopping trading due to session trade limit: {self.session_trades}")
            return True
        
        # Check per-trade loss limit if we have execution result
        if execution_result and execution_result.realized_pnl < 0:
            trade_loss_pct = abs(execution_result.realized_pnl) / execution_result.opportunity.notional_value * 100
            if trade_loss_pct > self.config.risk.max_loss_per_trade_pct:
                logger.warning(f"Stopping trading due to per-trade loss limit: {trade_loss_pct:.2f}%")
                return True
        
        # Check session loss limit
        if self.current_pnl < 0:
            session_loss_pct = abs(self.current_pnl) / self.initial_balance * 100
            if session_loss_pct > self.config.risk.max_session_loss_pct:
                logger.warning(f"Stopping trading due to session loss limit: {session_loss_pct:.2f}%")
                return True
        
        return False

    def update_risk_metrics(self, execution_result: ExecutionResult) -> None:
        """Update risk metrics after trade execution."""
        # Update trade counts
        self.daily_trades += 1
        self.session_trades += 1
        self.total_trades += 1
        
        # Update PnL
        self.current_pnl += execution_result.realized_pnl
        self.metrics.daily_pnl += execution_result.realized_pnl
        self.metrics.total_pnl += execution_result.realized_pnl
        
        # Update max PnL
        if self.current_pnl > self.max_pnl:
            self.max_pnl = self.current_pnl
        
        # Update consecutive losses/wins
        if execution_result.realized_pnl > 0:
            self.metrics.consecutive_losses = 0
        else:
            self.metrics.consecutive_losses += 1
        
        # Log risk metrics
        logger.info(f"Risk metrics updated: trades={self.metrics.total_trades}, pnl=${self.metrics.total_pnl:.2f}, consecutive_losses={self.metrics.consecutive_losses}")
        
        # Check if we should stop trading
        if self.should_stop_trading(execution_result):
            logger.critical("Risk limits exceeded, trading stopped")
            raise RiskLimitExceeded("Risk limits exceeded")

    def get_risk_summary(self) -> Dict[str, Any]:
        """Get risk management summary."""
        return {
            'total_trades': self.metrics.total_trades,
            'successful_trades': self.metrics.successful_trades,
            'success_rate': self.metrics.successful_trades / max(1, self.metrics.total_trades),
            'total_pnl': self.metrics.total_pnl,
            'daily_pnl': self.metrics.daily_pnl,
            'daily_notional': self.metrics.daily_notional,
            'consecutive_losses': self.metrics.consecutive_losses,
            'max_drawdown': self.metrics.max_drawdown,
            'risk_score': self.metrics.risk_score,
            'last_trade_time': self.metrics.last_trade_time,
            'trading_allowed': not self.should_stop_trading(),
            'limits': {
                'max_consecutive_losses': self.max_consecutive_losses,
                'max_daily_loss': self.max_daily_loss,
                'max_daily_notional': self.max_daily_notional
            }
        }

    def adjust_risk_parameters(self, market_conditions: Dict[str, Any]):
        """Dynamically adjust risk parameters based on market conditions."""
        # This is a simplified implementation
        # In practice, you'd want more sophisticated logic
        
        volatility = market_conditions.get('volatility', 0.0)
        spread_avg = market_conditions.get('spread_avg', 0.0)
        
        # Adjust based on market volatility
        if volatility > 0.05:  # High volatility
            self.max_consecutive_losses = max(3, self.max_consecutive_losses - 1)
            logger.info(f"Reduced max consecutive losses to {self.max_consecutive_losses} due to high volatility")
        
        # Adjust based on spread conditions
        if spread_avg > 0.002:  # High spreads
            self.max_daily_notional = max(50000, self.max_daily_notional * 0.8)
            logger.info(f"Reduced daily notional limit to {self.max_daily_notional} due to high spreads")

    def get_risk_alerts(self) -> List[Dict[str, Any]]:
        """Get current risk alerts."""
        alerts = []
        
        if self.metrics.consecutive_losses >= 3:
            alerts.append({
                'level': 'warning',
                'message': f"Consecutive losses: {self.metrics.consecutive_losses}",
                'action': 'Consider reducing position sizes'
            })
        
        if self.metrics.daily_pnl < -500:
            alerts.append({
                'level': 'warning',
                'message': f"Daily loss: ${self.metrics.daily_pnl:.2f}",
                'action': 'Monitor closely, consider stopping if trend continues'
            })
        
        if self.metrics.risk_score > 0.7:
            alerts.append({
                'level': 'high',
                'message': f"High risk score: {self.metrics.risk_score:.2f}",
                'action': 'Consider stopping trading temporarily'
            })
        
        return alerts
