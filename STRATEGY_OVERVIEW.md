# 🚀 Arbitrage Bot Strategy Overview

## 📁 **File Structure & Purpose**

### 🎯 **Main Entry Points (Choose One):**

#### **1. `run_arbitrage_bot.py` - NEW RECOMMENDED**
- **Purpose**: Runs ALL enabled strategies simultaneously using the orchestrator
- **Use Case**: Production deployment, running multiple strategies
- **Command**: `py run_arbitrage_bot.py`
- **Features**: 
  - Runs ETH/USDC and BTC/USDC spot↔perp strategies in parallel
  - Automatic strategy management
  - Route-based configuration

#### **2. `run_spot_perp_strategy.py` - ORIGINAL**
- **Purpose**: Runs only the single spot↔perp strategy
- **Use Case**: Testing single strategy, development
- **Command**: `py run_spot_perp_strategy.py`
- **Features**: 
  - Single strategy execution
  - Direct control over one strategy

#### **3. `run_monitoring_bot.py` - ORIGINAL**
- **Purpose**: Your existing monitoring bot
- **Use Case**: Legacy monitoring functionality
- **Command**: `py run_monitoring_bot.py`

### 🏗️ **Strategy Architecture Files:**

#### **`src/strategies/orchestrator.py`**
- **Purpose**: Manages multiple strategies running in parallel
- **Key Features**:
  - Starts/stops all enabled strategies
  - Concurrent execution
  - Error handling and recovery
  - Status monitoring

#### **`src/strategies/strategy_factory.py`**
- **Purpose**: Creates different strategy types based on route configuration
- **Supported Types**:
  - `spot_perp`: Binance spot ↔ Hyperliquid perp
  - `spot_spot`: Binance spot ↔ Kraken spot (future)
  - `perp_perp`: Perp ↔ Perp (future)

#### **`src/strategies/spot_perp/runner.py`**
- **Purpose**: Main execution engine for spot↔perp strategy
- **Features**:
  - Market data streaming
  - Opportunity detection
  - Trade execution
  - Risk management
  - Route-aware configuration

### 🔌 **Exchange Adapters:**

#### **`src/exchanges/binance.py`**
- **Purpose**: Binance spot trading integration
- **Features**: REST + WebSocket, order management, balance tracking

#### **`src/exchanges/hyperliquid.py`**
- **Purpose**: Hyperliquid perpetual futures trading
- **Features**: REST + WebSocket, perp order types, position management

#### **`src/exchanges/kraken.py`**
- **Purpose**: Kraken spot trading (for future spot↔spot strategy)

### 📱 **Notification Systems:**

#### **`src/notify/telegram_readonly.py` - NEW**
- **Purpose**: Read-only Telegram alerts for the new strategy
- **Features**: Trade notifications, risk alerts, status updates

#### **`src/alerts/telegram.py` - ORIGINAL**
- **Purpose**: Your existing Telegram integration

## 🎯 **How to Use:**

### **Option 1: Run All Strategies (Recommended)**
```bash
py run_arbitrage_bot.py
```
This will:
- Load route configuration from `config.yaml`
- Start ETH/USDC spot↔perp strategy
- Start BTC/USDC spot↔perp strategy
- Run both simultaneously

### **Option 2: Run Single Strategy**
```bash
py run_spot_perp_strategy.py
```
This will:
- Run only the spot↔perp strategy
- Use hardcoded symbol configuration

### **Option 3: Custom Route Configuration**
Edit `config.yaml` to:
- Enable/disable specific routes
- Change strategy types
- Modify trading parameters

## ⚙️ **Configuration:**

### **Routes in `config.yaml`:**
```yaml
routes:
  - name: "ETH_binance_spot__hl_perp"
    enabled: true
    strategy_type: "spot_perp"
    left:  { ex: "binance", type: "spot", symbol: "ETH/USDC" }
    right: { ex: "hyperliquid", type: "perp", symbol: "ETH-PERP" }
  
  - name: "BTC_binance_spot__hl_perp"
    enabled: true
    strategy_type: "spot_perp"
    left:  { ex: "binance", type: "spot", symbol: "BTC/USDC" }
    right: { ex: "hyperliquid", type: "perp", symbol: "BTC-PERP" }
```

### **Environment Variables:**
Copy `env.example` to `.env` and fill in your credentials:
```bash
cp env.example .env
# Edit .env with your actual API keys
```

## 🔒 **Security:**
- **NEVER commit `.env` to git**
- **Rotate API keys regularly**
- **Use environment variables for sensitive data**
- **Monitor API usage and limits**

## 🚀 **Next Steps:**
1. **Copy `env.example` to `.env`**
2. **Fill in your actual API credentials**
3. **Test with `py run_arbitrage_bot.py`**
4. **Monitor Telegram notifications**
5. **Adjust risk parameters as needed**
