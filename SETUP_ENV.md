# Environment Variables Setup Guide

## 🔐 Setting Up Your Environment Variables

### 1. Create Your .env File

Copy the `env.example` file to `.env`:

```bash
cp env.example .env
```

### 2. Fill In Your API Keys

Edit the `.env` file with your actual credentials:

```bash
# Binance API Keys
BINANCE_API_KEY=your_actual_binance_api_key
BINANCE_SECRET_KEY=your_actual_binance_secret_key

# Kraken API Keys  
KRAKEN_API_KEY=your_actual_kraken_api_key
KRAKEN_SECRET_KEY=your_actual_kraken_secret_key

# Hyperliquid Configuration
HYPERLIQUID_WALLET_ADDRESS=0x0D1F99f16c7D5047e8ECA4D50CC68C682dd53597
HYPERLIQUID_PRIVATE_KEY=0x862fdec89b3bee9c9eddbca0eaceb23162d8787c

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=7778778156:AAEesgvgwttp2K1SHQq3Jp_o8W5NUiVkzvs
TELEGRAM_CHAT_ID=536885403

# Database Configuration
DATABASE_URL=live_cex_arbitrage_2025_08_15.sqlite
```

### 3. Test Your Configuration

Run the test script to verify everything is working:

```bash
python test_config.py
```

You should see:
```
✅ All required environment variables are set
✅ Configuration loaded successfully!
🎉 All tests passed! Configuration is ready to use.
```

### 4. Optional Overrides

You can also override key configuration values:

```bash
# Override minimum edge requirements
MIN_EDGE_BPS=25

# Override maximum trade size
MAX_NOTIONAL_USDT=20

# Change trading mode
TRADING_MODE=paper
```

## 🚨 Security Notes

- **NEVER commit your `.env` file to git**
- The `.env` file is already in `.gitignore`
- Keep your API keys secure and private
- Rotate your API keys regularly

## 🔧 Troubleshooting

### Common Issues:

1. **"Missing environment variables"**
   - Make sure you copied `env.example` to `.env`
   - Check that all variables are filled in

2. **"Configuration loading failed"**
   - Verify your API keys are correct
   - Check that `config.yaml` exists and is valid

3. **"Import errors"**
   - Make sure you're in the project root directory
   - Check that all dependencies are installed

### Getting Help:

If you encounter issues:
1. Run `python test_config.py` and check the output
2. Verify your `.env` file has all required variables
3. Check that `config.yaml` uses environment variable syntax (`${VAR_NAME}`)
