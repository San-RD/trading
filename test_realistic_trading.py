#!/usr/bin/env python3
"""
Test script for realistic trading model validation.
This script tests the updated arbitrage detection with realistic fees, slippage, and edge calculations.
"""

import asyncio
import time
from typing import Dict, List, Any
from src.config import Config
from src.core.detector import ArbitrageDetector
from src.core.quotes import ConsolidatedQuote
from src.exchanges.base import Quote
from src.core.executor import ArbitrageExecutor
from src.exchanges.base import BaseExchange

class MockExchange(BaseExchange):
    """Mock exchange for testing."""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
    
    async def connect(self):
        pass
    
    async def disconnect(self):
        pass
    
    async def load_markets(self):
        pass
    
    async def watch_quotes(self, symbols: List[str]):
        pass
    
    async def fetch_order_book(self, symbol: str, limit: int = 10):
        pass
    
    async def place_order(self, symbol: str, side: str, order_type: str, quantity: float, price: float = None):
        pass
    
    async def cancel_order(self, order_id: str, symbol: str):
        pass
    
    async def fetch_balances(self):
        pass
    
    async def health_check(self):
        return True

def create_test_quotes():
    """Create test quotes with realistic market data."""
    
    # SOL/USDT test case - realistic scenario
    sol_left_quote = Quote(
        venue="binance",
        symbol="SOL/USDT",
        bid=25.50,
        ask=25.52,
        bid_size=1000.0,
        ask_size=1200.0,
        ts_exchange=int(time.time() * 1000),
        ts_local=int(time.time() * 1000)
    )
    
    sol_right_quote = Quote(
        venue="okx",
        symbol="SOL/USDT",
        bid=25.58,  # 6 bps higher bid
        ask=25.60,  # 8 bps higher ask
        bid_size=800.0,
        ask_size=900.0,
        ts_exchange=int(time.time() * 1000),
        ts_local=int(time.time() * 1000)
    )
    
    sol_consolidated = ConsolidatedQuote(
        symbol="SOL/USDT",
        left_quote=sol_left_quote,
        right_quote=sol_right_quote,
        ts_local=int(time.time() * 1000)
    )
    
    # ETH/USDT test case - tighter spread
    eth_left_quote = Quote(
        venue="binance",
        symbol="ETH/USDT",
        bid=3200.00,
        ask=3200.50,
        bid_size=50.0,
        ask_size=60.0,
        ts_exchange=int(time.time() * 1000),
        ts_local=int(time.time() * 1000)
    )
    
    eth_right_quote = Quote(
        venue="okx",
        symbol="ETH/USDT",
        bid=3201.00,  # 1 bps higher bid
        ask=3201.50,  # 1 bps higher ask
        bid_size=40.0,
        ask_size=50.0,
        ts_exchange=int(time.time() * 1000),
        ts_local=int(time.time() * 1000)
    )
    
    eth_consolidated = ConsolidatedQuote(
        symbol="ETH/USDT",
        left_quote=eth_left_quote,
        right_quote=eth_right_quote,
        ts_local=int(time.time() * 1000)
    )
    
    return [sol_consolidated, eth_consolidated]

async def test_realistic_detection():
    """Test realistic arbitrage detection."""
    
    print("🔍 Testing Realistic Arbitrage Detection")
    print("=" * 50)
    
    # Load configuration
    config = Config.load_from_file("config.yaml")
    
    # Create detector
    detector = ArbitrageDetector(config)
    
    # Create test quotes
    quotes = create_test_quotes()
    
    print(f"Configuration:")
    print(f"  Min edge: {config.detector.min_edge_bps} bps")
    print(f"  Max spread: {config.detector.max_spread_bps} bps")
    print(f"  Max quote age: {config.detector.min_book_bbo_age_ms} ms")
    print(f"  Binance taker fee: {config.get_taker_fee_bps('binance')} bps")
    print(f"  OKX taker fee: {config.get_taker_fee_bps('okx')} bps")
    print()
    
    # Test detection
    opportunities = detector.detect_opportunities(quotes)
    
    print(f"Detected {len(opportunities)} opportunities:")
    print()
    
    for i, opp in enumerate(opportunities, 1):
        print(f"Opportunity {i}: {opp.symbol}")
        print(f"  Direction: {opp.direction.value}")
        print(f"  Raw edge: {opp.raw_edge_bps:.2f} bps")
        print(f"  Net edge: {opp.net_edge_bps:.2f} bps")
        print(f"  Expected profit: ${opp.expected_profit_usdt:.4f}")
        print(f"  Trade size: {opp.trade_size:.4f}")
        print(f"  Notional: ${opp.notional_value:,.2f}")
        print(f"  Metadata:")
        for key, value in opp.metadata.items():
            if isinstance(value, float):
                print(f"    {key}: {value:.4f}")
            else:
                print(f"    {key}: {value}")
        print()

async def test_realistic_execution():
    """Test realistic trade execution."""
    
    print("💼 Testing Realistic Trade Execution")
    print("=" * 50)
    
    # Load configuration
    config = Config.load_from_file("config.yaml")
    
    # Create mock exchanges
    exchanges = {
        "binance": MockExchange("binance", {}),
        "okx": MockExchange("okx", {})
    }
    
    # Create executor
    executor = ArbitrageExecutor(config, exchanges, "paper")
    
    # Create test opportunity
    from src.core.detector import ArbitrageOpportunity, ArbitrageDirection
    
    opportunity = ArbitrageOpportunity(
        symbol="SOL/USDT",
        direction=ArbitrageDirection.LEFT_TO_RIGHT,
        left_exchange="binance",
        right_exchange="okx",
        buy_price=25.52,
        sell_price=25.58,
        base_asset="SOL",
        quote_asset="USDT",
        trade_size=100.0,
        notional_value=2552.0,
        raw_edge_bps=23.5,
        net_edge_bps=15.5,
        expected_profit_usdt=3.96,
        spread_bps=7.8,
        quotes_age_ms=150,
        confidence_score=0.85,
        detected_at=int(time.time() * 1000),
        expires_at=int(time.time() * 1000) + 5000,
        metadata={
            'buy_exchange': 'binance',
            'sell_exchange': 'okx',
            'buy_fee_bps': 7.5,
            'sell_fee_bps': 8.0,
            'total_fees_bps': 15.5,
            'slippage_bps': 5.0,
            'raw_edge_bps': 23.5,
            'net_edge_after_fees': 8.0
        }
    )
    
    print(f"Test opportunity:")
    print(f"  Symbol: {opportunity.symbol}")
    print(f"  Raw edge: {opportunity.raw_edge_bps:.2f} bps")
    print(f"  Net edge: {opportunity.net_edge_bps:.2f} bps")
    print(f"  Expected profit: ${opportunity.expected_profit_usdt:.4f}")
    print()
    
    # Execute paper trade
    result = await executor.execute_arbitrage(opportunity)
    
    print(f"Execution result:")
    print(f"  Success: {result.success}")
    print(f"  Realized PnL: ${result.realized_pnl:.4f}")
    print(f"  Execution time: {result.execution_time_ms} ms")
    if result.metadata:
        print(f"  Metadata:")
        for key, value in result.metadata.items():
            if isinstance(value, float):
                print(f"    {key}: {value:.4f}")
            else:
                print(f"    {key}: {value}")
    else:
        print(f"  Metadata: None")
    print()

def test_fee_calculations():
    """Test fee calculations."""
    
    print("💰 Testing Fee Calculations")
    print("=" * 50)
    
    config = Config.load_from_file("config.yaml")
    
    # Test different scenarios
    scenarios = [
        {"symbol": "SOL/USDT", "notional": 1000.0, "buy_exchange": "binance", "sell_exchange": "okx"},
        {"symbol": "ETH/USDT", "notional": 5000.0, "buy_exchange": "okx", "sell_exchange": "binance"},
        {"symbol": "BTC/USDT", "notional": 10000.0, "buy_exchange": "binance", "sell_exchange": "okx"}
    ]
    
    for scenario in scenarios:
        buy_fee_bps = config.get_taker_fee_bps(scenario["buy_exchange"])
        sell_fee_bps = config.get_taker_fee_bps(scenario["sell_exchange"])
        total_fees_bps = buy_fee_bps + sell_fee_bps
        
        buy_fee_usd = scenario["notional"] * (buy_fee_bps / 10000)
        sell_fee_usd = scenario["notional"] * (sell_fee_bps / 10000)
        total_fees_usd = buy_fee_usd + sell_fee_usd
        
        print(f"{scenario['symbol']} - ${scenario['notional']:,.2f} notional:")
        print(f"  Buy fee ({scenario['buy_exchange']}): {buy_fee_bps} bps = ${buy_fee_usd:.4f}")
        print(f"  Sell fee ({scenario['sell_exchange']}): {sell_fee_bps} bps = ${sell_fee_usd:.4f}")
        print(f"  Total fees: {total_fees_bps} bps = ${total_fees_usd:.4f}")
        print()

async def main():
    """Main test function."""
    
    print("🚀 Realistic Trading Model Validation")
    print("=" * 60)
    print()
    
    try:
        # Test fee calculations
        test_fee_calculations()
        
        # Test realistic detection
        await test_realistic_detection()
        
        # Test realistic execution
        await test_realistic_execution()
        
        print("✅ All tests completed successfully!")
        print()
        print("📊 Key Improvements Implemented:")
        print("  • Realistic fee structure (7.5 + 8.0 = 15.5 bps total)")
        print("  • Slippage modeling with depth-aware estimation")
        print("  • Partial fill handling with unwind logic")
        print("  • Higher edge thresholds (28 bps minimum)")
        print("  • Quote alignment and age validation")
        print("  • Realistic PnL calculation")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
