"""Configuration management for the cross-exchange arbitrage bot."""

import os
from pathlib import Path
from typing import Dict, List, Optional
import yaml
from pydantic import BaseModel, Field


class ExchangeAccount(BaseModel):
    """Exchange account configuration."""
    key: str
    secret: str
    password: Optional[str] = None
    sandbox: bool = True  # Default to sandbox for safety


class ExchangeConfig(BaseModel):
    """Exchange configuration."""
    left: str
    right: str
    accounts: Dict[str, ExchangeAccount]


class FeeConfig(BaseModel):
    """Fee configuration."""
    taker_bps: Dict[str, float] = Field(default_factory=lambda: {"default": 10.0})
    maker_bps: Dict[str, float] = Field(default_factory=lambda: {"default": 8.0})


class SymbolConfig(BaseModel):
    """Symbol configuration."""
    quote_assets: List[str] = ["USDC"]
    whitelist: List[str] = ["BTC", "ETH", "SOL", "XRP", "ARB", "OP"]
    blacklist: List[str] = []
    prefer_stable: str = "USDC"


class DetectorConfig(BaseModel):
    """Arbitrage detection configuration."""
    min_edge_bps: float = 28.0  # Updated to realistic threshold
    min_book_bbo_age_ms: int = 300  # Reduced for faster detection
    max_spread_bps: float = 15.0  # Tighter spreads
    max_notional_usdc: float = 25.0
    min_notional_usdc: float = 10.0  # Minimum trade size
    prefer_stable: str = "USDC"
    slippage_model: str = "depth_aware"  # Updated to depth-aware
    max_venue_clock_skew_ms: int = 200  # New: max time difference between exchanges
    # Dynamic trade sizing parameters
    liquidity_multiplier: float = 1.5  # Require 1.5x target size in liquidity
    safety_factor: float = 0.8  # Use 80% of available liquidity
    max_depth_pct: float = 0.20  # Max 0.20% from midprice for aggregation


class ExecutionConfig(BaseModel):
    """Execution configuration."""
    type: str = "IOC"
    guard_bps: float = 3.0
    max_leg_latency_ms: int = 150  # Reduced for faster execution
    hedge: Dict[str, bool] = Field(default_factory=lambda: {"atomic": True, "cancel_on_partial": True})
    partial_fill_threshold: float = 0.95  # New: threshold for partial fill handling
    per_order_cap_usd: float = 15.0  # Maximum USD per order


class InventoryConfig(BaseModel):
    """Inventory management configuration."""
    min_free_usdc: float = 2.0
    size_pct_of_side_liquidity: float = 0.15  # 15% of available liquidity
    rebalance_asset: str = "USDC"
    rebalance_threshold_pct: float = 15.0  # Rebalance at 15% deviation
    max_inventory_deviation_pct: float = 10.0  # Max 10% deviation
    target_stable_ratio: float = 0.5  # 50% stablecoin / 50% crypto


class RiskConfig(BaseModel):
    """Risk management configuration."""
    max_daily_notional: float = 1000.0
    max_notional_usdc: float = 25.0  # Max position size per leg
    max_daily_loss: float = -50.0
    max_consecutive_losses: int = 2
    max_drawdown_pct: float = 5.0
    emergency_stop_pnl: float = -30.0
    max_trades_per_day: int = 10
    max_trades_per_session: int = 5
    max_loss_per_trade_pct: float = 0.3
    max_session_loss_pct: float = 1.0
    
    # Aliases for config.yaml compatibility
    @property
    def daily_notional_limit(self) -> float:
        """Alias for max_daily_notional from config.yaml."""
        return self.max_daily_notional
    
    @property
    def max_daily_loss_pct(self) -> float:
        """Alias for max_daily_loss_pct from config.yaml."""
        return abs(self.max_daily_loss) if self.max_daily_loss < 0 else 0.0


class DepthModelConfig(BaseModel):
    """Depth model configuration."""
    enabled: bool = True
    levels: int = 10  # L10 order book depth
    update_interval_ms: int = 500  # Update every 500ms
    max_level_age_ms: int = 1000  # Discard stale depth data
    slippage_buffer_bps: float = 3.0  # 3 bps slippage buffer
    min_liquidity_multiplier: float = 3.0  # Require 3x position size in liquidity
    # Order book aggregation parameters
    max_depth_pct: float = 0.20  # Max 0.20% from midprice for aggregation
    vwap_calculation_levels: int = 10  # Use L1-L10 for VWAP calculation
    per_order_cap_usdc: float = 1000.0  # Split orders larger than $1k
    safety_factor: float = 0.80  # Use 80% of available liquidity for safety


class RealisticTradingConfig(BaseModel):
    """Realistic trading parameters."""
    min_net_edge_after_slippage: float = 35.0  # 35 bps = 0.35% minimum edge after fees + slippage
    slippage_estimation_method: str = "linear_slope"  # linear | exponential | none
    partial_fill_handling: str = "unwind"  # unwind | retry | accept
    rebalance_cost_accounting: bool = True  # Track rebalance costs
    adverse_selection_tracking: bool = True  # Track mid-price movement


class SessionConfig(BaseModel):
    """Session management configuration."""
    duration_hours: int = 3
    auto_stop: bool = True
    export_results: bool = True
    # Focused on top 10 most liquid pairs available on both Kraken and Binance
    target_pairs: List[str] = [
        "BTC/USDC",    # Bitcoin - highest volume
        "ETH/USDC",    # Ethereum - highest volume  
        "XRP/USDC",    # Ripple - high volume
        "BNB/USDC",    # Binance Coin - high volume
        "SOL/USDC",    # Solana - high volume
        "DOGE/USDC",   # Dogecoin - high volume
        "TRX/USDT",    # Tron - high volume
        "ADA/USDC",    # Cardano - high volume
        "LINK/USDC",   # Chainlink - high volume
        "HYPE/USDC"    # Hype - high volume
    ]


class BacktestConfig(BaseModel):
    """Backtesting configuration."""
    parquet_path: str = "data/recordings/btc_eth_sol_2025-08-15.parquet"
    start_ts: Optional[int] = None
    end_ts: Optional[int] = None


class PerpConfig(BaseModel):
    """Perpetual futures configuration."""
    max_hold_minutes: int = 10
    funding_cost_bps_per_8h: float = 0.0
    require_funding_sign_ok: bool = False

class AlertConfig(BaseModel):
    """Alert configuration."""
    telegram_token: str
    telegram_chat_id: str
    notify_all_trades: bool = True
    notify_risk_events: bool = True
    notify_session_summary: bool = True
    enable_interactive_bot: bool = False


class StorageConfig(BaseModel):
    """Storage configuration."""
    db_path: str = "arb.sqlite"


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = "INFO"
    json: bool = True
    log_trades: bool = True
    log_quotes: bool = False
    log_execution_details: bool = True


class ServerConfig(BaseModel):
    """HTTP server configuration."""
    enable_status_http: bool = True
    port: int = 8080


class HyperliquidConfig(BaseModel):
    """Hyperliquid exchange configuration."""
    wallet_address: str
    private_key: str
    chain: str = "arbitrum"
    initial_capital_usdc: float = 50.0

class RouteConfig(BaseModel):
    """Route configuration for arbitrage strategies."""
    name: str
    enabled: bool = True
    left: Dict[str, str]
    right: Dict[str, str]

class Config(BaseModel):
    """Main configuration model."""
    exchanges: ExchangeConfig
    fees: FeeConfig
    symbols: SymbolConfig
    detector: DetectorConfig
    execution: ExecutionConfig
    inventory: InventoryConfig
    risk: RiskConfig
    depth_model: DepthModelConfig
    realistic_trading: RealisticTradingConfig
    session: SessionConfig
    hyperliquid: HyperliquidConfig
    perp: PerpConfig = Field(default_factory=PerpConfig)
    alerts: Optional[AlertConfig] = None
    storage: StorageConfig = Field(default_factory=StorageConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    routes: Optional[List[RouteConfig]] = None

    def get_taker_fee_bps(self, exchange: str) -> float:
        """Get taker fee in basis points for an exchange."""
        return self.fees.taker_bps.get(exchange, self.fees.taker_bps.get("default", 10.0))

    def get_maker_fee_bps(self, exchange: str) -> float:
        """Get maker fee in basis points for an exchange."""
        return self.fees.maker_bps.get(exchange, self.fees.maker_bps.get("default", 8.0))

    @classmethod
    def load_from_file(cls, config_path: str = "config.yaml") -> "Config":
        """Load configuration from YAML file with environment variable substitution."""
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r") as f:
            config_data = yaml.safe_load(f)

        # Substitute environment variables
        config_str = yaml.dump(config_data)
        for key, value in os.environ.items():
            config_str = config_str.replace(f"${{{key}}}", value)

        config_data = yaml.safe_load(config_str)
        return cls(**config_data)


def get_config(config_path: str = "config.yaml") -> Config:
    """Get configuration instance."""
    return Config.load_from_file(config_path)
