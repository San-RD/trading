"""Basic tests for spot↔perp arbitrage strategy."""

import pytest
import time
from unittest.mock import Mock, AsyncMock
from decimal import Decimal

from src.strategies.spot_perp.detector import SpotPerpDetector, SpotPerpOpportunity, SpotPerpDirection
from src.strategies.spot_perp.planner import SpotPerpPlanner, ExecutionPlan, ExecutionLeg
from src.strategies.spot_perp.runner import SpotPerpRunner, StrategyState
from src.notify.telegram_readonly import TelegramReadOnlyNotifier, TelegramConfig


class MockQuote:
    """Mock quote for testing."""
    def __init__(self, symbol: str, bid: float, ask: float, ts_exchange: int = None):
        self.symbol = symbol
        self.bid = bid
        self.ask = ask
        self.ts_exchange = ts_exchange or int(time.time() * 1000)
        self.bids = [(bid, 1.0)]
        self.asks = [(ask, 1.0)]
        
    @property
    def mid_price(self):
        return (self.bid + self.ask) / 2
        
    @property
    def spread_bps(self):
        return ((self.ask - self.bid) / self.bid) * 10000


class MockConfig:
    """Mock configuration for testing."""
    def __init__(self):
        self.detector = Mock()
        self.detector.min_edge_bps = 30
        self.detector.min_book_bbo_age_ms = 300
        self.detector.max_spread_bps = 300
        self.detector.max_venue_clock_skew_ms = 150
        self.detector.min_notional_usdc = 10
        
        self.realistic_trading = Mock()
        self.realistic_trading.min_net_edge_after_slippage = 20
        
        self.depth_model = Mock()
        self.depth_model.levels = 10
        self.depth_model.max_depth_pct = 0.0015
        self.depth_model.min_liquidity_multiplier = 3.0
        self.depth_model.safety_factor = 0.80
        self.depth_model.slippage_buffer_bps = 5.0
        
        self.perp = Mock()
        self.perp.max_hold_minutes = 10
        self.perp.funding_cost_bps_per_8h = 0.0
        self.perp.require_funding_sign_ok = False
        
        self.fees = Mock()
        self.fees.taker_bps = {'binance': 7.5, 'hyperliquid': 3.0}
        self.fees.maker_bps = {'binance': 7.5, 'hyperliquid': 2.0}
        
        self.execution = Mock()
        self.execution.type = "IOC"
        self.execution.guard_bps = 2
        self.execution.max_leg_latency_ms = 150
        self.execution.partial_fill_threshold = 0.95
        self.execution.per_order_cap_usd = 50
        
        self.risk = Mock()
        self.risk.max_notional_usdc = 25.0
        self.risk.daily_notional_limit = 400
        self.risk.max_consecutive_losses = 2
        self.risk.max_daily_loss_pct = 1.0


class TestSpotPerpDetector:
    """Test spot↔perp detector functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = MockConfig()
        self.detector = SpotPerpDetector(self.config)
        
        # Mock exchanges
        self.spot_exchange = Mock()
        self.spot_exchange.name = "binance"
        self.perp_exchange = Mock()
        self.perp_exchange.name = "hyperliquid"
        
        self.detector.set_exchanges(self.spot_exchange, self.perp_exchange)

    def test_detect_opportunities_basic(self):
        """Test basic opportunity detection."""
        # Create mock quotes
        spot_quote = MockQuote("ETH/USDC", 2000.0, 2001.0)
        perp_quote = MockQuote("ETH-PERP", 2005.0, 2006.0)
        
        # Detect opportunities
        opportunities = self.detector.detect_opportunities([spot_quote], [perp_quote])
        
        assert len(opportunities) > 0
        assert opportunities[0].symbol == "ETH/USDC"
        assert opportunities[0].gross_edge_bps > 30  # Should meet minimum threshold

    def test_detect_opportunities_invalid_age(self):
        """Test that old quotes are rejected."""
        # Create old quotes
        old_time = int((time.time() - 1) * 1000)  # 1 second ago
        spot_quote = MockQuote("ETH/USDC", 2000.0, 2001.0, old_time)
        perp_quote = MockQuote("ETH-PERP", 2005.0, 2006.0, old_time)
        
        opportunities = self.detector.detect_opportunities([spot_quote], [perp_quote])
        
        assert len(opportunities) == 0

    def test_detect_opportunities_wide_spread(self):
        """Test that wide spreads are rejected."""
        # Create quotes with wide spreads
        spot_quote = MockQuote("ETH/USDC", 2000.0, 2100.0)  # 5% spread
        perp_quote = MockQuote("ETH-PERP", 2005.0, 2006.0)
        
        opportunities = self.detector.detect_opportunities([spot_quote], [perp_quote])
        
        assert len(opportunities) == 0

    def test_calculate_vwap_bid_side(self):
        """Test VWAP calculation for bid side."""
        quote = MockQuote("ETH/USDC", 2000.0, 2001.0)
        
        vwap = self.detector._calculate_vwap(quote, "bid", SpotPerpDirection.SPOT_BUY_PERP_SELL)
        
        assert vwap == 2000.0  # Should use bid price

    def test_calculate_vwap_ask_side(self):
        """Test VWAP calculation for ask side."""
        quote = MockQuote("ETH/USDC", 2000.0, 2001.0)
        
        vwap = self.detector._calculate_vwap(quote, "ask", SpotPerpDirection.SPOT_BUY_PERP_SELL)
        
        assert vwap == 2001.0  # Should use ask price

    def test_calculate_funding_cost(self):
        """Test funding cost calculation."""
        # Test SPOT_BUY_PERP_SELL (short perp, receive funding)
        funding_cost = self.detector._calculate_funding_cost(SpotPerpDirection.SPOT_BUY_PERP_SELL)
        assert funding_cost <= 0  # Should be negative (benefit)
        
        # Test SPOT_SELL_PERP_BUY (long perp, pay funding)
        funding_cost = self.detector._calculate_funding_cost(SpotPerpDirection.SPOT_SELL_PERP_BUY)
        assert funding_cost >= 0  # Should be positive (cost)


class TestSpotPerpPlanner:
    """Test spot↔perp planner functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = MockConfig()
        self.planner = SpotPerpPlanner(self.config)
        
        # Mock exchanges
        self.spot_exchange = Mock()
        self.spot_exchange.name = "binance"
        self.perp_exchange = Mock()
        self.perp_exchange.name = "hyperliquid"
        
        self.planner.set_exchanges(self.spot_exchange, self.perp_exchange)

    def test_create_execution_plan_basic(self):
        """Test basic execution plan creation."""
        # Create mock opportunity
        opportunity = SpotPerpOpportunity(
            symbol="ETH/USDC",
            direction=SpotPerpDirection.SPOT_BUY_PERP_SELL,
            spot_exchange="binance",
            perp_exchange="hyperliquid",
            spot_price=2000.0,
            perp_price=2005.0,
            spot_vwap=2000.5,
            perp_vwap=2004.5,
            trade_size=0.1,
            gross_edge_bps=50.0,
            net_edge_bps=35.0,
            total_fees_bps=10.5,
            funding_cost_bps=-2.0,
            slippage_buffer_bps=5.0
        )
        
        plan = self.planner.create_execution_plan(opportunity)
        
        assert plan is not None
        assert len(plan.legs) == 2
        assert plan.expected_pnl > 0
        assert plan.max_slippage_bps > 0

    def test_create_execution_plan_expired(self):
        """Test that expired opportunities are rejected."""
        # Create expired opportunity
        opportunity = SpotPerpOpportunity(
            symbol="ETH/USDC",
            direction=SpotPerpDirection.SPOT_BUY_PERP_SELL,
            spot_exchange="binance",
            perp_exchange="hyperliquid",
            spot_price=2000.0,
            perp_price=2005.0,
            spot_vwap=2000.5,
            perp_vwap=2004.5,
            trade_size=0.1,
            gross_edge_bps=50.0,
            net_edge_bps=35.0,
            total_fees_bps=10.5,
            funding_cost_bps=-2.0,
            slippage_buffer_bps=5.0,
            expires_at=int((time.time() - 1) * 1000)  # Expired
        )
        
        plan = self.planner.create_execution_plan(opportunity)
        
        assert plan is None

    def test_create_execution_plan_small_notional(self):
        """Test that small notional trades are rejected."""
        # Create opportunity with small trade size
        opportunity = SpotPerpOpportunity(
            symbol="ETH/USDC",
            direction=SpotPerpDirection.SPOT_BUY_PERP_SELL,
            spot_exchange="binance",
            perp_exchange="hyperliquid",
            spot_price=2000.0,
            perp_price=2005.0,
            spot_vwap=2000.5,
            perp_vwap=2004.5,
            trade_size=0.001,  # Very small
            gross_edge_bps=50.0,
            net_edge_bps=35.0,
            total_fees_bps=10.5,
            funding_cost_bps=-2.0,
            slippage_buffer_bps=5.0
        )
        
        plan = self.planner.create_execution_plan(opportunity)
        
        assert plan is None

    def test_create_unwind_plan(self):
        """Test unwind plan creation."""
        # Create mock opportunity
        opportunity = SpotPerpOpportunity(
            symbol="ETH/USDC",
            direction=SpotPerpDirection.SPOT_BUY_PERP_SELL,
            spot_exchange="binance",
            perp_exchange="hyperliquid",
            spot_price=2000.0,
            perp_price=2005.0,
            spot_vwap=2000.5,
            perp_vwap=2004.5,
            trade_size=0.1,
            gross_edge_bps=50.0,
            net_edge_bps=35.0,
            total_fees_bps=10.5,
            funding_cost_bps=-2.0,
            slippage_buffer_bps=5.0
        )
        
        # Create mock filled leg
        filled_leg = ExecutionLeg(
            exchange="binance",
            symbol="ETH/USDC",
            side="buy",
            order_type="IOC",
            amount=0.1,
            price=2000.0
        )
        
        unwind_plan = self.planner.create_unwind_plan(filled_leg, opportunity)
        
        assert unwind_plan is not None
        assert len(unwind_plan.legs) == 1
        assert unwind_plan.legs[0].reduce_only is True
        assert unwind_plan.legs[0].side == "sell"  # Opposite of filled leg


class TestTelegramReadOnlyNotifier:
    """Test read-only Telegram notifier functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = TelegramConfig(
            token="test_token",
            chat_id="test_chat_id",
            notify_all_trades=True,
            notify_risk_events=True,
            notify_session_summary=True
        )
        self.notifier = TelegramReadOnlyNotifier(self.config)

    def test_initialization(self):
        """Test notifier initialization."""
        assert self.notifier.enabled is True
        assert self.notifier.config.token == "test_token"
        assert self.notifier.config.chat_id == "test_chat_id"

    def test_initialization_disabled(self):
        """Test notifier initialization with missing credentials."""
        config = TelegramConfig(token="", chat_id="")
        notifier = TelegramReadOnlyNotifier(config)
        
        assert notifier.enabled is False

    def test_handle_command_start(self):
        """Test /start command handling."""
        response = self.notifier.handle_command("/start", "user123")
        
        assert "Spot↔Perp Arbitrage Bot" in response

    def test_handle_command_status(self):
        """Test /status command handling."""
        response = self.notifier.handle_command("/status", "user123")
        
        assert response == "status_request"

    def test_handle_command_pause(self):
        """Test /pause command handling."""
        response = self.notifier.handle_command("/pause", "user123")
        
        assert "Trading paused" in response

    def test_handle_command_resume(self):
        """Test /resume command handling."""
        response = self.notifier.handle_command("/resume", "user123")
        
        assert "Trading resumed" in response

    def test_handle_command_help(self):
        """Test /help command handling."""
        response = self.notifier.handle_command("/help", "user123")
        
        assert "Available Commands" in response
        assert "read-only bot" in response

    def test_handle_command_unknown(self):
        """Test unknown command handling."""
        response = self.notifier.handle_command("/unknown", "user123")
        
        assert "Unknown command" in response
        assert "/help" in response

    def test_get_session_stats(self):
        """Test session statistics retrieval."""
        stats = self.notifier.get_session_stats()
        
        assert 'start_time' in stats
        assert 'trades_count' in stats
        assert 'total_pnl' in stats
        assert 'avg_pnl_per_trade' in stats


class TestStrategyState:
    """Test strategy state functionality."""
    
    def test_initial_state(self):
        """Test initial state values."""
        state = StrategyState()
        
        assert state.is_running is False
        assert state.is_paused is False
        assert state.opportunities_detected == 0
        assert state.trades_executed == 0
        assert state.total_pnl == 0.0

    def test_state_modification(self):
        """Test state modification."""
        state = StrategyState()
        
        state.is_running = True
        state.opportunities_detected = 5
        state.trades_executed = 2
        state.total_pnl = 10.5
        
        assert state.is_running is True
        assert state.opportunities_detected == 5
        assert state.trades_executed == 2
        assert state.total_pnl == 10.5


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
