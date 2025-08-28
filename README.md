# Cross-Exchange Arbitrage Bot

A high-performance, low-latency arbitrage bot for cryptocurrency exchanges with real-time monitoring and market intelligence.

## 🚀 Features

### Core Trading Bot
- **Ultra-low latency** arbitrage detection and execution
- **Multi-exchange support** (Binance, Kraken)
- **Real-time order book** monitoring
- **Risk management** with configurable limits
- **Depth-aware** trade sizing and execution

### Monitoring & Intelligence
- **Telegram monitoring bot** for real-time status (runs 24/7)
- **Performance analytics** (daily/weekly/monthly summaries)
- **Market intelligence** tracking (whale movements, volume spikes)
- **Database logging** for performance analysis

## 📁 Project Structure

```
tri_arb_bot/
├── src/                          # Core bot source code
│   ├── core/                     # Core arbitrage logic
│   ├── exchanges/                # Exchange integrations
│   ├── storage/                  # Database and data models
│   └── alerts/                   # Monitoring and alerts
├── run_live_cex_arbitrage.py    # Main trading bot (start when needed)
├── run_monitoring_bot.py         # Telegram monitoring bot (runs 24/7)
├── start_monitoring.py           # Startup script for monitoring bot
├── config.yaml                   # Configuration file
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

## 🛠️ Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Exchanges
Copy `env.example` to `.env` and fill in your API keys:
```bash
cp env.example .env
```

### 3. Configure Bot
Edit `config.yaml` with your trading parameters:
- Risk limits
- Trading pairs
- Fee structures
- Execution settings

### 4. Start Monitoring Bot (24/7)
The monitoring bot runs continuously to track performance:
```bash
python start_monitoring.py
```

### 5. Start Trading Bot (When Needed)
Start the live trading bot only when you want to trade:
```bash
python run_live_cex_arbitrage.py
```

## 📊 Configuration

### Key Parameters
- **`min_edge_bps`**: Minimum arbitrage edge (basis points)
- **`max_daily_notional`**: Maximum daily trading volume
- **`max_trades_per_day`**: Maximum trades per day
- **`guard_bps`**: Slippage protection buffer

### Risk Management
- **Daily loss limits**
- **Position size caps**
- **Consecutive loss protection**
- **Drawdown monitoring**

## 🔧 Architecture

### Performance Optimizations
- **WebSocket connections** for real-time data
- **Async/await** for non-blocking operations
- **Database indexing** for fast queries
- **Memory-efficient** data structures

### Monitoring System
- **Real-time status** updates
- **Performance metrics** tracking
- **Market intelligence** alerts
- **Telegram integration** for mobile access

## 📈 Usage

### Monitoring Bot (24/7)
The monitoring bot runs continuously and provides:
- Real-time trading bot status
- Performance summaries
- Market intelligence alerts
- Telegram notifications

### Trading Bot (On-Demand)
The live trading bot:
- Runs only when you start it
- Monitors for arbitrage opportunities
- Executes trades automatically
- Stops when you close it

### Monitoring Bot Commands
- `/start` - Main menu
- `/status` - Current trading status
- `/daily` - Daily performance summary
- `/weekly` - Weekly performance summary
- `/monthly` - Monthly performance summary
- `/whales` - Whale movement alerts
- `/market` - Market intelligence summary

## 🚨 Important Notes

- **Monitoring bot runs 24/7** - Always available for status updates
- **Trading bot starts on-demand** - Only runs when you need it
- **Monitor risk limits** carefully
- **Keep API keys secure**
- **Regular performance review** recommended

## 📞 Support

For issues or questions:
1. Check the logs in the `logs/` directory
2. Review configuration in `config.yaml`
3. Monitor bot status via Telegram

## 📄 License

This project is for educational and personal use. Use at your own risk.
