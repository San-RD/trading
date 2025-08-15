# 🚀 Live CEX↔CEX Arbitrage Bot

A high-performance, latency-aware cross-exchange arbitrage bot that detects price gaps between **Binance Spot** and **OKX Spot**, executes simultaneous taker orders, and provides comprehensive risk management.

## ⚠️ **IMPORTANT: LIVE TRADING BOT**

**This bot is configured for LIVE TRADING with REAL MONEY.** It includes comprehensive risk management but should be used with caution.

## 🎯 **Key Features**

- **Real-time Arbitrage Detection**: Monitors price differences between exchanges in real-time
- **Multi-Exchange Support**: Currently supports Binance and OKX
- **Live Trading Mode**: Execute real arbitrage trades with risk controls
- **Risk Management**: Comprehensive risk controls with dynamic parameter adjustment
- **Telegram Integration**: Real-time notifications and bot control
- **Inventory Management**: Automatic rebalancing suggestions across exchanges
- **Session Management**: Time-limited trading sessions with auto-stop

## 🏗️ **Architecture**

```
tri_arb_bot/
├── src/
│   ├── exchanges/          # Exchange integrations
│   │   ├── base.py        # Base exchange interface
│   │   ├── binance.py     # Binance implementation
│   │   ├── okx.py         # OKX implementation
│   │   ├── filters.py     # Trading rules & precision
│   │   └── fees.py        # Fee management
│   ├── core/              # Core arbitrage logic
│   │   ├── symbols.py     # Symbol universe management
│   │   ├── quotes.py      # Quote consolidation & WebSocket
│   │   ├── detector.py    # Arbitrage opportunity detection
│   │   ├── executor.py    # Trade execution
│   │   ├── inventory.py   # Balance & rebalancing
│   │   ├── risk.py        # Risk management
│   │   └── session.py     # Session management
│   ├── storage/           # Data persistence
│   │   ├── db.py          # SQLite database
│   │   ├── models.py      # Data models
│   │   └── journal.py     # Trade journaling
│   ├── alerts/            # Notifications
│   │   └── telegram.py    # Telegram bot
│   ├── config.py          # Configuration management
│   └── main.py            # Main entry point & CLI
├── run_live_cex_arbitrage.py  # Live trading runner
├── config.yaml            # Configuration file (create from template)
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## 🚀 **Quick Start**

### **1. Clone the Repository**
```bash
git clone <your-github-repo-url>
cd tri_arb_bot
```

### **2. Install Dependencies**
```bash
pip install -r requirements.txt
```

### **3. Configure the Bot**
```bash
# Copy the template configuration
cp config.template.yaml config.yaml

# Edit config.yaml with your API keys and settings
# ⚠️ NEVER commit config.yaml to git!
```

### **4. Set Up API Keys**
Create a `config.yaml` file with your exchange API credentials:

```yaml
exchanges:
  left: "binance"
  right: "okx"
  accounts:
    binance:
      key: "YOUR_BINANCE_API_KEY"
      secret: "YOUR_BINANCE_SECRET"
      sandbox: false  # Set to true for testing
    okx:
      key: "YOUR_OKX_API_KEY"
      secret: "YOUR_OKX_SECRET"
      password: "YOUR_OKX_PASSPHRASE"
      sandbox: false  # Set to true for testing
```

### **5. Run the Bot**

**Live Trading (REAL MONEY):**
```bash
python run_live_cex_arbitrage.py
```

**Paper Trading (Simulation):**
```bash
py -m src.main run --mode paper
```

## ⚙️ **Configuration**

### **Risk Management**
- **Max Daily Loss**: 1% of total balance
- **Max Per Trade Loss**: 0.3% of position size
- **Position Size**: $25 max per leg
- **Session Duration**: 2 hours maximum
- **Circuit Breakers**: Stop after 2 consecutive losses

### **Trading Parameters**
- **Spread Threshold**: 0.50% gross, ≥0.35% net after fees & slippage
- **Target Pairs**: ETH/USDT only
- **Capital Allocation**: $100 total ($25 per exchange)
- **Rebalancing**: Auto 50% USDC / 50% ETH ratio

## 🛡️ **Safety Features**

- **Sandbox Mode**: Test with paper trading first
- **Risk Limits**: Multiple layers of risk controls
- **Session Limits**: Automatic time-based stopping
- **Position Sizing**: Conservative position limits
- **Circuit Breakers**: Automatic stop on consecutive losses

## 📊 **Monitoring & Alerts**

- **Real-time Logging**: Comprehensive trade and risk logging
- **Telegram Notifications**: Instant alerts for trades and risk events
- **Session Summary**: Detailed performance reports
- **CSV Export**: Complete trade history export

## 🔧 **Development**

### **Running Tests**
```bash
# Test configuration
python -c "from src.config import Config; print('Config OK')"

# Test detector
python -c "from src.core.detector import ArbitrageDetector; print('Detector OK')"
```

### **Adding New Exchanges**
1. Create new exchange class in `src/exchanges/`
2. Inherit from `BaseExchange`
3. Implement required methods
4. Add to configuration

## ⚠️ **Important Notes**

### **Security**
- **NEVER commit `config.yaml`** to git (contains API keys)
- Use environment variables for sensitive data in production
- Regularly rotate API keys
- Monitor API usage and permissions

### **Risk Disclaimer**
- This bot trades with **REAL MONEY**
- Cryptocurrency trading involves significant risk
- Past performance does not guarantee future results
- Use at your own risk and never invest more than you can afford to lose

### **Legal Compliance**
- Ensure compliance with local regulations
- Check exchange terms of service
- Consider tax implications of trading

## 📝 **License**

This project is for educational and personal use. Please ensure compliance with all applicable laws and regulations.

## 🤝 **Contributing**

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📞 **Support**

For issues and questions:
1. Check the logs for error details
2. Review the configuration
3. Test with paper trading first
4. Open an issue on GitHub

## 🚨 **Emergency Stop**

If you need to stop the bot immediately:
- Press `Ctrl+C` in the terminal
- The bot will attempt graceful shutdown
- Check exchange positions manually
- Verify all orders are properly closed

---

**Happy Trading! 🚀📈**

*Remember: This bot uses REAL MONEY. Trade responsibly!*
