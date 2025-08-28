# Spot↔Perp Arbitrage Strategy

This module implements a **Binance spot ↔ Hyperliquid perp** arbitrage strategy that runs **in parallel** to the existing spot↔spot logic.

## 🎯 Strategy Overview

The strategy identifies price differences between:
- **Binance spot markets** (ETH/USDC)
- **Hyperliquid perpetual futures** (ETH-PERP)

When the perp is "rich" (higher than spot), we:
1. Buy ETH on Binance spot
2. Sell ETH-PERP on Hyperliquid

When the perp is "cheap" (lower than spot), we:
1. Sell ETH on Binance spot  
2. Buy ETH-PERP on Hyperliquid

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Binance      │    │   Hyperliquid    │    │   Strategy      │
│   (Spot)       │◄──►│   (Perp)         │◄──►│   Runner        │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Market Data  │    │   Market Data    │    │   Opportunity   │
│   Stream       │    │   Stream         │    │   Detection     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                       │
                                                       ▼
                                              ┌─────────────────┐
                                              │   Execution     │
                                              │   Planning      │
                                              └─────────────────┘
                                                       │
                                                       ▼
                                              ┌─────────────────┐
                                              │   Two-Leg       │
                                              │   IOC Orders    │
                                              └─────────────────┘
```

## 📁 Module Structure

- **`detector.py`** - Identifies arbitrage opportunities using VWAP pricing
- **`planner.py`** - Creates executable trading plans with proper sizing
- **`runner.py`** - Orchestrates the entire strategy execution
- **`__init__.py`** - Module exports

## 🚀 Quick Start

### 1. Configuration

The strategy is configured via `config.yaml`:

```yaml
routes:
  - name: "ETH_binance_spot__hl_perp"
    enabled: true
    left:  { ex: "binance",     type: "spot", symbol: "ETH/USDC" }
    right: { ex: "hyperliquid", type: "perp", symbol: "ETH-PERP" }

perp:
  max_hold_minutes: 10
  funding_cost_bps_per_8h: 0.0

detector:
  min_edge_bps: 30                     # ≥0.30% gross
  max_spread_bps: 300
  min_book_bbo_age_ms: 300

execution:
  type: "IOC"                          # Immediate-or-Cancel
  guard_bps: 2
  max_leg_latency_ms: 150
  per_order_cap_usd: 50
```

### 2. Run the Strategy

```bash
# Run just the spot↔perp strategy
python run_spot_perp_strategy.py

# Or run with the main bot (both strategies)
python run_monitoring_bot.py
```

### 3. Monitor via Telegram

The strategy sends read-only alerts:
- ✅ **Trade fills** with PnL and execution time
- ⚠️ **Partial fills/unwinds** for risk management  
- 🚨 **Risk events** when limits are exceeded
- 📊 **Status updates** via `/status` command

## 🔧 Key Features

### Depth-Aware VWAP Sizing
- Uses L1-L10 order book levels for accurate pricing
- Calculates optimal trade size based on available liquidity
- Applies safety factors to prevent market impact

### Two-Leg IOC Execution
- Sends both legs simultaneously for atomic execution
- Uses Immediate-or-Cancel orders for speed
- Handles partial fills with automatic unwinding

### Risk Management
- Daily notional limits ($400 default)
- Consecutive loss limits (2 max)
- Automatic trading pause on risk events
- Partial fill unwinding to prevent exposure

### Funding Rate Awareness
- Calculates funding costs for expected holding period
- Prefers trades where short leg receives funding
- Configurable funding rate thresholds

## 📊 Performance Metrics

The strategy tracks:
- **Opportunities detected** per session
- **Trades executed** with success rate
- **Realized PnL** in USD
- **Execution latency** per leg
- **Risk guard status** and warnings

## 🧪 Testing

Run the test suite:

```bash
# Install test dependencies
pip install pytest

# Run tests
python -m pytest tests/test_spot_perp_basic.py -v
```

Tests cover:
- Opportunity detection logic
- VWAP calculations
- Execution planning
- Risk management
- Telegram notifications

## 🔒 Safety Features

- **Read-only Telegram** - No configuration changes via bot
- **Feature flags** - Can be enabled/disabled via config
- **Risk guards** - Automatic pause on limit breaches
- **Partial unwind** - Clean exit from failed trades
- **Session limits** - Maximum trades and duration caps

## 🚨 Risk Warnings

- **Perpetual futures** carry funding rate risk
- **Leverage exposure** if positions aren't properly hedged
- **Exchange risk** - Both venues must remain operational
- **Liquidity risk** - Large orders may impact prices
- **Technical risk** - Network issues can cause failed executions

## 🔮 Future Enhancements

- **Live funding rates** from Hyperliquid API
- **Dynamic position sizing** based on volatility
- **Multi-symbol support** (SOL, BTC, etc.)
- **Advanced unwinding** with limit orders
- **Performance analytics** and backtesting

## 📞 Support

For issues or questions:
1. Check the logs for error details
2. Verify exchange connectivity
3. Review risk limit configurations
4. Test with small position sizes first

---

**⚠️ Disclaimer**: This is experimental software. Test thoroughly in paper trading before using real funds. Cryptocurrency trading involves substantial risk of loss.
