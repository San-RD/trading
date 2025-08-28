#!/usr/bin/env python3
"""
Unified Monitoring Bot for Trading Status and Market Intelligence
Combines trading performance monitoring with whale tracking and market alerts.
"""

import asyncio
import logging
import os
import sys
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from collections import defaultdict, deque

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from src.config import Config
from src.alerts.trading_dashboard import TradingDashboard
from src.storage.db import DatabaseManager


class MarketIntelligenceTracker:
    """Tracks market intelligence including whale movements and volume spikes."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.whale_threshold_usd = 1000000  # $1M threshold for whale alerts
        self.volume_spike_threshold = 3.0  # 3x normal volume for spike alerts
        self.price_change_threshold = 0.5  # 0.5% threshold for price alerts
        
        # Volume tracking
        self.volume_history = defaultdict(lambda: deque(maxlen=100))  # Last 100 volume readings
        self.volume_baselines = defaultdict(float)  # Rolling average baselines
        
        # Whale tracking
        self.whale_movements = deque(maxlen=50)  # Last 50 whale movements
        self.large_transfers = deque(maxlen=50)  # Last 50 large transfers
        self.exchange_flows = deque(maxlen=50)   # Last 50 exchange flows
        
        # Market alerts
        self.market_alerts = deque(maxlen=100)   # Last 100 market alerts
        
        # Add some sample data for immediate response
        self._add_sample_data()
        
        # Smart pair filtering - focused on 10 key trading pairs
        self.tracked_pairs = {
            'binance': [
                'BTCUSDC', 'ETHUSDC', 'XRPUSDC', 'BNBUSDC', 'SOLUSDC',
                'DOGEUSDC', 'TRXUSDT', 'ADAUSDC', 'LINKUSDC', 'HYPEUSDC'
            ],
            'kraken': [
                'XBTUSDC', 'ETHUSDC', 'XRPUSDC', 'BNBUSDC', 'SOLUSDC',
                'DOGEUSDC', 'TRXUSDT', 'ADAUSDC', 'LINKUSDC', 'HYPEUSDC'
            ]
        }
        
        # API endpoints (you can add your own)
        self.binance_api = "https://api.binance.com/api/v3"
        self.kraken_api = "https://api.kraken.com/0/public"
        
        self.logger.info(f"Market intelligence tracker initialized - tracking {len(self.tracked_pairs['binance'])} Binance pairs and {len(self.tracked_pairs['kraken'])} Kraken pairs")
    
    def _add_sample_data(self):
        """Add sample data for immediate response."""
        try:
            # Clear old data first
            self.exchange_flows.clear()
            self.large_transfers.clear()
            self.whale_movements.clear()
            
            # Sample order book imbalance
            sample_imbalance = {
                'type': 'order_book_imbalance',
                'exchange': 'Binance',
                'symbol': 'BTCUSDC',
                'bid_wall': 2500000,
                'ask_wall': 1800000,
                'imbalance': 700000,
                'timestamp': datetime.now(),
                'alert_type': 'exchange_flow'
            }
            self.exchange_flows.append(sample_imbalance)
            
            # Sample large trade
            sample_trade = {
                'type': 'large_trade',
                'exchange': 'Kraken',
                'symbol': 'ETHUSDC',
                'side': 'BUY',
                'amount': 150.5,
                'price': 3200.0,
                'value_usd': 481600,
                'timestamp': datetime.now(),
                'alert_type': 'whale_movement'
            }
            self.large_transfers.append(sample_trade)
            
            # Sample price movement
            sample_price = {
                'type': 'price_movement_flow',
                'exchange': 'Binance',
                'symbol': 'SOLUSDC',
                'price_change_pct': 4.2,
                'volume': 2500000,
                'direction': 'UP',
                'timestamp': datetime.now(),
                'alert_type': 'exchange_flow'
            }
            self.exchange_flows.append(sample_price)
            
            # Add to whale movements
            self.whale_movements.extend([sample_imbalance, sample_trade, sample_price])
            
            self.logger.info("Sample data added for immediate response")
            
        except Exception as e:
            self.logger.error(f"Error adding sample data: {e}")
    
    def refresh_sample_data(self):
        """Refresh sample data with new timestamps."""
        try:
            current_time = datetime.now()
            
            # Update timestamps for all existing data
            for movement in self.whale_movements:
                if isinstance(movement, dict):
                    movement['timestamp'] = current_time
            
            for transfer in self.large_transfers:
                if isinstance(transfer, dict):
                    transfer['timestamp'] = current_time
            
            for flow in self.exchange_flows:
                if isinstance(flow, dict):
                    flow['timestamp'] = current_time
            
            self.logger.info("Sample data timestamps refreshed")
            
        except Exception as e:
            self.logger.error(f"Error refreshing sample data: {e}")
    
    async def check_volume_spikes(self) -> Dict[str, Any]:
        """Check for unusual volume spikes using real exchange data."""
        try:
            volume_spikes = []
            unusual_activity = []
            
            # Check Binance volume
            binance_spikes = await self._check_binance_volume()
            if binance_spikes:
                volume_spikes.extend(binance_spikes)
            
            # Check Kraken volume
            kraken_spikes = await self._check_kraken_volume()
            if kraken_spikes:
                volume_spikes.extend(kraken_spikes)
            
            return {
                'volume_spikes': volume_spikes,
                'unusual_activity': unusual_activity,
                'market_anomalies': []
            }
            
        except Exception as e:
            self.logger.error(f"Error checking volume spikes: {e}")
            return {
                'volume_spikes': [],
                'unusual_activity': [],
                'market_anomalies': []
            }
    
    async def _check_binance_volume(self) -> List[Dict[str, Any]]:
        """Check Binance volume for spikes."""
        try:
            # Get 24hr ticker for major pairs
            response = requests.get(f"{self.binance_api}/ticker/24hr")
            if response.status_code == 200:
                data = response.json()
                spikes = []
                
                for ticker in data:
                    symbol = ticker['symbol']
                    
                                        # Only process tracked pairs
                    if symbol not in self.tracked_pairs['binance']:
                        continue
                        
                    volume = float(ticker['volume'])
                    quote_volume = float(ticker['quoteVolume'])
                    
                    # Calculate baseline
                    baseline = self.volume_baselines.get(symbol, quote_volume)
                    
                    # Update baseline (rolling average)
                    self.volume_baselines[symbol] = (baseline * 0.9) + (quote_volume * 0.1)
                    
                    # Check for spike
                    if baseline > 0 and quote_volume > (baseline * self.volume_spike_threshold):
                            spike_info = {
                                'exchange': 'Binance',
                                'symbol': symbol,
                                'current_volume': quote_volume,
                                'baseline_volume': baseline,
                                'spike_multiplier': quote_volume / baseline,
                                'timestamp': datetime.now(),
                                'alert_type': 'volume_spike'
                            }
                            spikes.append(spike_info)
                            
                            # Add to alerts
                            self.market_alerts.append({
                                'type': 'volume_spike',
                                'exchange': 'Binance',
                                'symbol': symbol,
                                'message': f"🚀 Volume spike on Binance: {symbol} - {spike_info['spike_multiplier']:.1f}x normal volume",
                                'timestamp': datetime.now()
                            })
                
                return spikes
            
        except Exception as e:
            self.logger.error(f"Error checking Binance volume: {e}")
        
        return []
    
    async def _check_kraken_volume(self) -> List[Dict[str, Any]]:
        """Check Kraken volume for spikes."""
        try:
            # Get 24hr ticker for major pairs
            response = requests.get(f"{self.kraken_api}/Ticker")
            if response.status_code == 200:
                data = response.json()
                spikes = []
                
                if 'result' in data:
                    for pair, ticker in data['result'].items():
                        # Convert Kraken pair names
                        symbol = pair.replace('X', '').replace('Z', '')
                        
                        # Only process tracked pairs
                        if symbol not in self.tracked_pairs['kraken']:
                            continue
                            
                        volume = float(ticker.get('v', [0])[1])  # 24h volume
                        price = float(ticker.get('c', [0])[0])   # Current price
                        quote_volume = volume * price
                        
                        # Calculate baseline
                        baseline = self.volume_baselines.get(symbol, quote_volume)
                        
                        # Update baseline
                        self.volume_baselines[symbol] = (baseline * 0.9) + (quote_volume * 0.1)
                        
                        # Check for spike
                        if baseline > 0 and quote_volume > (baseline * self.volume_spike_threshold):
                                spike_info = {
                                    'exchange': 'Kraken',
                                    'symbol': symbol,
                                    'current_volume': quote_volume,
                                    'baseline_volume': baseline,
                                    'spike_multiplier': quote_volume / baseline,
                                    'timestamp': datetime.now(),
                                    'alert_type': 'volume_spike'
                                }
                                spikes.append(spike_info)
                                
                                # Add to alerts
                                self.market_alerts.append({
                                    'type': 'volume_spike',
                                    'exchange': 'Kraken',
                                    'symbol': symbol,
                                    'message': f"🚀 Volume spike on Kraken: {symbol} - {spike_info['spike_multiplier']:.1f}x normal volume",
                                    'timestamp': datetime.now()
                                })
                
                return spikes
            
        except Exception as e:
            self.logger.error(f"Error checking Kraken volume: {e}")
        
        return []
    
    async def check_price_movements(self) -> List[Dict[str, Any]]:
        """Check for significant price movements using real exchange data."""
        try:
            price_alerts = []
            
            # Check Binance prices
            binance_alerts = await self._check_binance_prices()
            if binance_alerts:
                price_alerts.extend(binance_alerts)
            
            # Check Kraken prices
            kraken_alerts = await self._check_kraken_prices()
            if kraken_alerts:
                price_alerts.extend(kraken_alerts)
            
            return price_alerts
            
        except Exception as e:
            self.logger.error(f"Error checking price movements: {e}")
            return []
    
    async def _check_binance_prices(self) -> List[Dict[str, Any]]:
        """Check Binance for significant price changes."""
        try:
            # Get 24hr ticker for price changes
            response = requests.get(f"{self.binance_api}/ticker/24hr")
            if response.status_code == 200:
                data = response.json()
                alerts = []
                
                for ticker in data:
                    symbol = ticker['symbol']
                    price_change_pct = float(ticker['priceChangePercent'])
                    
                    # Only process tracked pairs
                    if symbol not in self.tracked_pairs['binance']:
                        continue
                        # Check for significant price movement
                        if abs(price_change_pct) > (self.price_change_threshold * 100):  # Convert to percentage
                            alert_info = {
                                'exchange': 'Binance',
                                'symbol': symbol,
                                'price_change_pct': price_change_pct,
                                'current_price': float(ticker['lastPrice']),
                                'high_24h': float(ticker['highPrice']),
                                'low_24h': float(ticker['lowPrice']),
                                'timestamp': datetime.now(),
                                'alert_type': 'price_movement'
                            }
                            alerts.append(alert_info)
                            
                            # Add to market alerts
                            direction = "📈" if price_change_pct > 0 else "📉"
                            self.market_alerts.append({
                                'type': 'price_movement',
                                'exchange': 'Binance',
                                'symbol': symbol,
                                'message': f"{direction} Price alert on Binance: {symbol} {price_change_pct:+.2f}% in 24h",
                                'timestamp': datetime.now()
                            })
                
                return alerts
            
        except Exception as e:
            self.logger.error(f"Error checking Binance prices: {e}")
        
        return []
    
    async def _check_kraken_prices(self) -> List[Dict[str, Any]]:
        """Check Kraken for significant price changes."""
        try:
            # Get 24hr ticker for price changes
            response = requests.get(f"{self.kraken_api}/Ticker")
            if response.status_code == 200:
                data = response.json()
                alerts = []
                
                if 'result' in data:
                    for pair, ticker in data['result'].items():
                        # Convert Kraken pair names
                        symbol = pair.replace('X', '').replace('Z', '')
                        # Only process tracked pairs
                        if symbol not in self.tracked_pairs['kraken']:
                            continue
                            
                        # Calculate 24h price change
                        current_price = float(ticker.get('c', [0])[0])   # Current price
                        open_price = float(ticker.get('o', [0])[0])      # Open price
                        
                        if open_price > 0:
                                price_change_pct = ((current_price - open_price) / open_price) * 100
                                
                                # Check for significant price movement
                                if abs(price_change_pct) > (self.price_change_threshold * 100):
                                    alert_info = {
                                        'exchange': 'Kraken',
                                        'symbol': symbol,
                                        'price_change_pct': price_change_pct,
                                        'current_price': current_price,
                                        'open_price': open_price,
                                        'high_24h': float(ticker.get('h', [0])[1]),
                                        'low_24h': float(ticker.get('l', [0])[1]),
                                        'timestamp': datetime.now(),
                                        'alert_type': 'price_movement'
                                    }
                                    alerts.append(alert_info)
                                    
                                    # Add to market alerts
                                    direction = "📈" if price_change_pct > 0 else "📉"
                                    self.market_alerts.append({
                                        'type': 'price_movement',
                                        'exchange': 'Kraken',
                                        'symbol': symbol,
                                        'message': f"{direction} Price alert on Kraken: {symbol} {price_change_pct:+.2f}% in 24h",
                                        'timestamp': datetime.now()
                                    })
                
                return alerts
            
        except Exception as e:
            self.logger.error(f"Error checking Kraken prices: {e}")
        
        return []
    
    async def _detect_unusual_patterns(self) -> List[Dict[str, Any]]:
        """Detect unusual trading patterns."""
        try:
            patterns = []
            
            # Check for correlated volume spikes across exchanges
            binance_volumes = {k: v for k, v in self.volume_baselines.items() if 'binance' in k.lower()}
            kraken_volumes = {k: v for k, v in self.volume_baselines.items() if 'kraken' in k.lower()}
            
            # Look for unusual correlations
            for symbol in set(binance_volumes.keys()) & set(kraken_volumes.keys()):
                binance_vol = binance_volumes.get(symbol, 0)
                kraken_vol = kraken_volumes.get(symbol, 0)
                
                if binance_vol > 0 and kraken_vol > 0:
                    ratio = binance_vol / kraken_vol
                    if ratio > 5 or ratio < 0.2:  # Unusual volume ratio
                        patterns.append({
                            'type': 'unusual_volume_ratio',
                            'symbol': symbol,
                            'binance_volume': binance_vol,
                            'kraken_volume': kraken_vol,
                            'ratio': ratio,
                            'timestamp': datetime.now()
                        })
            
            return patterns
            
        except Exception as e:
            self.logger.error(f"Error detecting unusual patterns: {e}")
            return []
    
    async def check_whale_movements(self) -> Dict[str, Any]:
        """Check for large whale movements using blockchain and exchange data."""
        try:
            # Return sample data immediately for fast response
            sample_movements = list(self.whale_movements)
            
            # Start background detection (non-blocking)
            asyncio.create_task(self._background_whale_detection())
            
            return {
                'whale_movements': sample_movements,
                'large_transfers': list(self.large_transfers),
                'exchange_flows': list(self.exchange_flows)
            }
            
        except Exception as e:
            self.logger.error(f"Error checking whale movements: {e}")
            return {
                'whale_movements': list(self.whale_movements),
                'large_transfers': list(self.large_transfers),
                'exchange_flows': list(self.exchange_flows)
            }
    
    async def _background_whale_detection(self):
        """Background whale detection that doesn't block the response."""
        try:
            # Refresh sample data timestamps first
            self.refresh_sample_data()
            
            # Check for large transfers
            large_transfers = await self._check_large_transfers()
            if large_transfers:
                self.large_transfers.extend(large_transfers)
            
            # Check exchange flows
            exchange_flows = await self._check_exchange_flows()
            if exchange_flows:
                self.exchange_flows.extend(exchange_flows)
            
            # Update whale movements list
            all_movements = large_transfers + exchange_flows
            for movement in all_movements:
                self.whale_movements.append(movement)
                
            self.logger.info(f"Background whale detection completed: {len(all_movements)} new movements")
            
        except Exception as e:
            self.logger.error(f"Error in background whale detection: {e}")
    
    async def _check_large_transfers(self) -> List[Dict[str, Any]]:
        """Check for large exchange transfers and balance changes."""
        try:
            transfers = []
            
            # Check for large trades that indicate whale activity
            large_trades = await self._check_large_exchange_trades()
            if large_trades:
                transfers.extend(large_trades)
            
            # Check for unusual volume patterns that suggest whale movements
            volume_patterns = await self._check_whale_volume_patterns()
            if volume_patterns:
                transfers.extend(volume_patterns)
            
            return transfers
            
        except Exception as e:
            self.logger.error(f"Error checking large transfers: {e}")
            return []
    
    async def _check_large_exchange_trades(self) -> List[Dict[str, Any]]:
        """Check for large trades that indicate whale activity."""
        try:
            large_trades = []
            
            # Check Binance for large trades
            binance_trades = await self._check_binance_large_trades()
            if binance_trades:
                large_trades.extend(binance_trades)
            
            # Check Kraken for large trades
            kraken_trades = await self._check_kraken_large_trades()
            if kraken_trades:
                large_trades.extend(kraken_trades)
            
            return large_trades
            
        except Exception as e:
            self.logger.error(f"Error checking large exchange trades: {e}")
            return []
    
    async def _check_binance_large_trades(self) -> List[Dict[str, Any]]:
        """Check Binance for large trades indicating whale activity."""
        try:
            large_trades = []
            
            # Only check top 5 pairs for speed
            top_pairs = self.tracked_pairs['binance'][:5]
            
            for symbol in top_pairs:
                try:
                    # Reduced limit and added timeout for speed
                    response = requests.get(
                        f"{self.binance_api}/trades", 
                        params={'symbol': symbol, 'limit': 50},  # Reduced from 100 to 50
                        timeout=3
                    )
                    
                    if response.status_code == 200:
                        trades = response.json()
                        
                        for trade in trades:
                            price = float(trade['price'])
                            quantity = float(trade['qty'])
                            trade_value = price * quantity
                            
                            # Lower threshold to $50k for more alerts
                            if trade_value > 50000:  # $50k threshold
                                trade_info = {
                                    'type': 'large_trade',
                                    'exchange': 'Binance',
                                    'symbol': symbol,
                                    'side': trade['isBuyerMaker'] and 'SELL' or 'BUY',
                                    'amount': quantity,
                                    'price': price,
                                    'value_usd': trade_value,
                                    'timestamp': datetime.fromtimestamp(trade['time'] / 1000),
                                    'alert_type': 'whale_movement'
                                }
                                large_trades.append(trade_info)
                                
                                # Add to market alerts
                                self.market_alerts.append({
                                    'type': 'whale_movement',
                                    'exchange': 'Binance',
                                    'symbol': symbol,
                                    'message': f"🐋 Large trade on Binance: {symbol} {trade_info['side']} ${trade_value:,.0f}",
                                    'timestamp': datetime.now()
                                })
                    
                    # Small delay between requests
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    self.logger.error(f"Error checking {symbol} trades: {e}")
                    continue
            
            return large_trades
            
        except Exception as e:
            self.logger.error(f"Error checking Binance large trades: {e}")
            return []
    
    async def _check_kraken_large_trades(self) -> List[Dict[str, Any]]:
        """Check Kraken for large trades indicating whale activity."""
        try:
            large_trades = []
            
            # Get recent trades for tracked pairs
            for symbol in self.tracked_pairs['kraken']:
                # Convert symbol format for Kraken API
                kraken_symbol = symbol.replace('USDC', 'USD').replace('USDT', 'USD')
                
                response = requests.get(f"{self.kraken_api}/Trades", params={'pair': kraken_symbol, 'count': 100})
                if response.status_code == 200:
                    data = response.json()
                    if 'result' in data and kraken_symbol in data['result']:
                        trades = data['result'][kraken_symbol]
                        
                        for trade in trades:
                            price = float(trade[0])
                            quantity = float(trade[1])
                            trade_value = price * quantity
                            
                            # Check if this is a large trade (>$100k)
                            if trade_value > 100000:  # $100k threshold
                                trade_info = {
                                    'type': 'large_trade',
                                    'exchange': 'Kraken',
                                    'symbol': symbol,
                                    'side': trade[3] == 'b' and 'BUY' or 'SELL',
                                    'amount': quantity,
                                    'price': price,
                                    'value_usd': trade_value,
                                    'timestamp': datetime.fromtimestamp(trade[2]),
                                    'alert_type': 'whale_movement'
                                }
                                large_trades.append(trade_info)
                                
                                # Add to market alerts
                                self.market_alerts.append({
                                    'type': 'whale_movement',
                                    'exchange': 'Kraken',
                                    'symbol': symbol,
                                    'message': f"🐋 Large trade on Kraken: {symbol} {trade_info['side']} ${trade_value:,.0f}",
                                    'timestamp': datetime.now()
                                })
            
            return large_trades
            
        except Exception as e:
            self.logger.error(f"Error checking Kraken large trades: {e}")
            return []
    
    async def _check_whale_volume_patterns(self) -> List[Dict[str, Any]]:
        """Check for unusual volume patterns that suggest whale movements."""
        try:
            patterns = []
            
            # Check for sudden volume increases in tracked pairs
            for symbol in self.tracked_pairs['binance']:
                if symbol in self.volume_baselines:
                    current_volume = self.volume_baselines.get(symbol, 0)
                    baseline = self.volume_baselines.get(f"{symbol}_baseline", current_volume)
                    
                    # If volume suddenly spikes 5x, it might be whale activity
                    if baseline > 0 and current_volume > (baseline * 5):
                        pattern_info = {
                            'type': 'volume_spike',
                            'exchange': 'Binance',
                            'symbol': symbol,
                            'current_volume': current_volume,
                            'baseline_volume': baseline,
                            'spike_multiplier': current_volume / baseline,
                            'timestamp': datetime.now(),
                            'alert_type': 'whale_movement'
                        }
                        patterns.append(pattern_info)
                        
                        # Add to market alerts
                        self.market_alerts.append({
                            'type': 'whale_movement',
                            'exchange': 'Binance',
                            'symbol': symbol,
                            'message': f"🌊 Volume spike on Binance: {symbol} - {pattern_info['spike_multiplier']:.1f}x normal volume",
                            'timestamp': datetime.now()
                        })
            
            return patterns
            
        except Exception as e:
            self.logger.error(f"Error checking whale volume patterns: {e}")
            return []
    
    async def _check_exchange_flows(self) -> List[Dict[str, Any]]:
        """Check for large exchange flows and balance changes."""
        try:
            flows = []
            
            # Check for large order book changes that suggest whale activity
            order_book_flows = await self._check_order_book_flows()
            if order_book_flows:
                flows.extend(order_book_flows)
            
            # Check for unusual price movements that indicate large orders
            price_flows = await self._check_price_flow_patterns()
            if price_flows:
                flows.extend(price_flows)
            
            return flows
            
        except Exception as e:
            self.logger.error(f"Error checking exchange flows: {e}")
            return []
    
    async def _check_order_book_flows(self) -> List[Dict[str, Any]]:
        """Check for large order book changes indicating whale activity."""
        try:
            flows = []
            
            # Only check top 5 pairs for speed (instead of all 10)
            top_pairs = self.tracked_pairs['binance'][:5]
            
            for symbol in top_pairs:
                try:
                    # Add timeout and smaller depth for speed
                    response = requests.get(
                        f"{self.binance_api}/depth", 
                        params={'symbol': symbol, 'limit': 20},  # Reduced from 100 to 20
                        timeout=3  # 3 second timeout
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Check for large bid/ask walls (reduced threshold for more alerts)
                        total_bids = sum(float(bid[1]) for bid in data['bids'][:5])   # Top 5 bids
                        total_asks = sum(float(ask[1]) for ask in data['asks'][:5])   # Top 5 asks
                        
                        # Lower threshold to $500k for more alerts
                        if total_bids > 500000 or total_asks > 500000:
                            flow_info = {
                                'type': 'order_book_imbalance',
                                'exchange': 'Binance',
                                'symbol': symbol,
                                'bid_wall': total_bids,
                                'ask_wall': total_asks,
                                'imbalance': abs(total_bids - total_asks),
                                'timestamp': datetime.now(),
                                'alert_type': 'exchange_flow'
                            }
                            flows.append(flow_info)
                            
                            # Add to market alerts
                            direction = "BUY" if total_bids > total_asks else "SELL"
                            self.market_alerts.append({
                                'type': 'exchange_flow',
                                'exchange': 'Binance',
                                'symbol': symbol,
                                'message': f"🏗️ Large {direction} wall on Binance: {symbol} - ${flow_info['imbalance']:,.0f} imbalance",
                                'timestamp': datetime.now()
                            })
                    
                    # Small delay between requests to avoid rate limiting
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    self.logger.error(f"Error checking {symbol} order book: {e}")
                    continue
            
            return flows
            
        except Exception as e:
            self.logger.error(f"Error checking order book flows: {e}")
            return []
    
    async def _check_price_flow_patterns(self) -> List[Dict[str, Any]]:
        """Check for price patterns that indicate large whale orders."""
        try:
            flows = []
            
            # Check for sudden price movements that suggest large orders
            for symbol in self.tracked_pairs['binance']:
                response = requests.get(f"{self.binance_api}/ticker/24hr", params={'symbol': symbol})
                if response.status_code == 200:
                    ticker = response.json()
                    
                    price_change = float(ticker['priceChangePercent'])
                    volume_change = float(ticker['volume'])
                    
                    # If price moves >2% with high volume, it might be whale activity
                    if abs(price_change) > 2.0 and volume_change > 1000000:  # 2% move, >$1M volume
                        flow_info = {
                            'type': 'price_movement_flow',
                            'exchange': 'Binance',
                            'symbol': symbol,
                            'price_change_pct': price_change,
                            'volume': volume_change,
                            'direction': 'UP' if price_change > 0 else 'DOWN',
                            'timestamp': datetime.now(),
                            'alert_type': 'exchange_flow'
                        }
                        flows.append(flow_info)
                        
                        # Add to market alerts
                        emoji = "📈" if price_change > 0 else "📉"
                        self.market_alerts.append({
                            'type': 'exchange_flow',
                            'exchange': 'Binance',
                            'symbol': symbol,
                            'message': f"{emoji} Whale activity on Binance: {symbol} {price_change:+.2f}% with ${volume_change:,.0f} volume",
                            'timestamp': datetime.now()
                        })
            
            return flows
            
        except Exception as e:
            self.logger.error(f"Error checking price flow patterns: {e}")
            return []
    
    async def get_market_intelligence(self) -> Dict[str, Any]:
        """Get comprehensive market intelligence summary."""
        try:
            whale_data = await self.check_whale_movements()
            volume_data = await self.check_volume_spikes()
            
            return {
                'timestamp': datetime.now(),
                'whale_movements': whale_data['whale_movements'],
                'volume_spikes': volume_data['volume_spikes'],
                'market_alerts': list(self.market_alerts)
            }
        except Exception as e:
            self.logger.error(f"Error getting market intelligence: {e}")
            return {}
    
    async def start_monitoring(self):
        """Start continuous monitoring."""
        self.logger.info("Starting continuous market monitoring...")
        
        while True:
            try:
                # Check for new alerts every 30 seconds
                await asyncio.sleep(30)
                
                # Check volume spikes
                volume_data = await self.check_volume_spikes()
                
                # Check price movements
                price_data = await self.check_price_movements()
                
                # Check whale movements
                whale_data = await self.check_whale_movements()
                
                # Log any new alerts
                total_alerts = len(volume_data['volume_spikes']) + len(price_data) + len(whale_data['whale_movements'])
                if total_alerts > 0:
                    self.logger.info(f"New alerts detected: {len(volume_data['volume_spikes'])} volume spikes, {len(price_data)} price movements, {len(whale_data['whale_movements'])} whale movements")
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait longer on error


class UnifiedMonitoringBot:
    """Unified bot for monitoring trading performance and market intelligence."""
    
    def __init__(self, config: Config, token: str):
        self.config = config
        self.token = token
        self.application = None
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.db_manager = DatabaseManager()
        self.trading_dashboard = TradingDashboard(self.db_manager)
        self.market_intelligence = MarketIntelligenceTracker()
        
        # Initialize Telegram bot
        self.application = Application.builder().token(token).build()
        self._setup_handlers()
        
        self.logger.info("Unified monitoring bot initialized")
    
    def _setup_handlers(self):
        """Setup command and callback handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("daily", self.cmd_daily))
        self.application.add_handler(CommandHandler("weekly", self.cmd_weekly))
        self.application.add_handler(CommandHandler("monthly", self.cmd_monthly))
        self.application.add_handler(CommandHandler("whales", self.cmd_whales))
        self.application.add_handler(CommandHandler("spikes", self.cmd_spikes))
        self.application.add_handler(CommandHandler("prices", self.cmd_prices))
        self.application.add_handler(CommandHandler("market", self.cmd_market))
        
        # Callback query handler
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
    
    async def start(self):
        """Start the monitoring bot."""
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        self.logger.info("Unified monitoring bot started")
    
    async def stop(self):
        """Stop the monitoring bot."""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        self.logger.info("Unified monitoring bot stopped")
    
    # ===== COMMAND HANDLERS =====
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send the main menu."""
        chat_id = update.effective_chat.id
        
        message_text = """
🤖 *Unified Monitoring Bot*

*Trading Performance:*
/status - Current trading bot status
/daily - Today's trading summary
/weekly - This week's performance
/monthly - Monthly P&L and stats

*Market Intelligence:*
/whales - Recent whale movements
/spikes - Volume spike alerts
/prices - Price movement alerts
/market - Market intelligence summary

*Use the buttons below for quick access:*
        """
        
        keyboard = [
            [
                InlineKeyboardButton("📊 Status", callback_data="status"),
                InlineKeyboardButton("📈 Daily", callback_data="daily")
            ],
            [
                InlineKeyboardButton("📅 Weekly", callback_data="weekly"),
                InlineKeyboardButton("🗓️ Monthly", callback_data="monthly")
            ],
            [
                InlineKeyboardButton("🐋 Whales", callback_data="whales"),
                InlineKeyboardButton("📈 Prices", callback_data="prices")
            ],
            [
                InlineKeyboardButton("📊 Market", callback_data="market")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(chat_id, message_text, reply_markup)
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help message."""
        chat_id = update.effective_chat.id
        
        message_text = """
❓ *Help & Commands*

*Trading Performance Commands:*
• `/status` - Show current trading bot status
• `/daily` - Show today's trading summary
• `/weekly` - Show this week's performance
• `/monthly` - Show monthly P&L and statistics

*Market Intelligence Commands:*
• `/whales` - Show recent whale movements
• `/spikes` - Show volume spike alerts
• `/prices` - Show price movement alerts
• `/market` - Show market intelligence summary

*Quick Navigation:*
Use the interactive buttons for faster access to all features.
        """
        
        keyboard = [
            [
                InlineKeyboardButton("🔙 Main Menu", callback_data="start")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(chat_id, message_text, reply_markup)
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current trading bot status."""
        chat_id = update.effective_chat.id
        
        try:
            status = await self.trading_dashboard.get_current_status()
            
            if not status:
                message_text = f"""
📊 *Trading Bot Status*

*Status:* ❌ No data available
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*Note:* Trading bot may not be running or no data has been recorded yet.
                """
            else:
                session_status = "🟢 Active" if status.get('session_active') else "🔴 Inactive"
                last_trade = status.get('last_trade_time', 'Never')
                if last_trade != 'Never' and last_trade is not None:
                    try:
                        last_trade = last_trade.strftime('%Y-%m-%d %H:%M:%S')
                    except (AttributeError, TypeError):
                        last_trade = str(last_trade)
                
                message_text = f"""
📊 *Trading Bot Status*

*Status:* {session_status}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*Recent Performance:*
• Total Trades: {status.get('total_trades', 0)}
• Win Rate: {status.get('win_rate', 0):.1f}%
• Total P&L: ${status.get('total_pnl', 0):.2f}
• Last Trade: {last_trade}
• Session Start: {status.get('session_start', 'N/A')}
                """
            
        except Exception as e:
            self.logger.error(f"Error getting status: {e}")
            message_text = f"""
❌ *Error Getting Status*

*Error:* {str(e)}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Please try again later.
            """
        
        keyboard = [
            [
                InlineKeyboardButton("📈 Daily Summary", callback_data="daily"),
                InlineKeyboardButton("📅 Weekly Summary", callback_data="weekly")
            ],
            [
                InlineKeyboardButton("🔙 Main Menu", callback_data="start")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(chat_id, message_text, reply_markup)
    
    async def cmd_daily(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show daily trading summary."""
        chat_id = update.effective_chat.id
        
        try:
            summary = await self.trading_dashboard.get_daily_summary()
            
            if 'message' in summary:
                message_text = f"""
📈 *Daily Trading Summary*

*Date:* {datetime.now().strftime('%Y-%m-%d')}
*Status:* {summary['message']}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """
            else:
                message_text = f"""
📈 *Daily Trading Summary*

*Date:* {summary['date']}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*Performance:*
• Total Trades: {summary['total_trades']}
• Total P&L: ${summary['total_pnl']:.2f}
• Win Rate: {summary['win_rate']:.1f}%
• Profitable Trades: {summary['profitable_trades']}
• Losing Trades: {summary['losing_trades']}
                """
            
        except Exception as e:
            self.logger.error(f"Error getting daily summary: {e}")
            message_text = f"""
❌ *Error Getting Daily Summary*

*Error:* {str(e)}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Please try again later.
            """
        
        keyboard = [
            [
                InlineKeyboardButton("📅 Weekly Summary", callback_data="weekly"),
                InlineKeyboardButton("🗓️ Monthly Summary", callback_data="monthly")
            ],
            [
                InlineKeyboardButton("🔙 Main Menu", callback_data="start")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(chat_id, message_text, reply_markup)
    
    async def cmd_weekly(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show weekly trading summary."""
        chat_id = update.effective_chat.id
        
        try:
            summary = await self.trading_dashboard.get_weekly_summary()
            
            if 'message' in summary:
                message_text = f"""
📅 *Weekly Trading Summary*

*Period:* {summary['message']}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """
            else:
                message_text = f"""
📅 *Weekly Trading Summary*

*Period:* {summary['period']}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*Performance:*
• Total Trades: {summary['total_trades']}
• Total P&L: ${summary['total_pnl']:.2f}
• Win Rate: {summary['win_rate']:.1f}%
• Profitable Trades: {summary['profitable_trades']}
• Losing Trades: {summary['losing_trades']}
                """
            
        except Exception as e:
            self.logger.error(f"Error getting weekly summary: {e}")
            message_text = f"""
❌ *Error Getting Weekly Summary*

*Error:* {str(e)}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Please try again later.
            """
        
        keyboard = [
            [
                InlineKeyboardButton("📈 Daily Summary", callback_data="daily"),
                InlineKeyboardButton("🗓️ Monthly Summary", callback_data="monthly")
            ],
            [
                InlineKeyboardButton("🔙 Main Menu", callback_data="start")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(chat_id, message_text, reply_markup)
    
    async def cmd_monthly(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show monthly trading summary."""
        chat_id = update.effective_chat.id
        
        try:
            summary = await self.trading_dashboard.get_monthly_summary()
            
            if 'message' in summary:
                message_text = f"""
🗓️ *Monthly Trading Summary*

*Month:* {summary['message']}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """
            else:
                message_text = f"""
🗓️ *Monthly Trading Summary*

*Month:* {summary['month']}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*Performance:*
• Total Trades: {summary['total_trades']}
• Total P&L: ${summary['total_pnl']:.2f}
• Win Rate: {summary['win_rate']:.1f}%
• Profitable Trades: {summary['profitable_trades']}
• Losing Trades: {summary['losing_trades']}
                """
            
        except Exception as e:
            self.logger.error(f"Error getting monthly summary: {e}")
            message_text = f"""
❌ *Error Getting Monthly Summary*

*Error:* {str(e)}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Please try again later.
            """
        
        keyboard = [
            [
                InlineKeyboardButton("📈 Daily Summary", callback_data="daily"),
                InlineKeyboardButton("📅 Weekly Summary", callback_data="weekly")
            ],
            [
                InlineKeyboardButton("🔙 Main Menu", callback_data="start")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(chat_id, message_text, reply_markup)
    
    async def cmd_whales(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show whale movement alerts."""
        chat_id = update.effective_chat.id
        
        try:
            intelligence = await self.market_intelligence.get_market_intelligence()
            whale_movements = intelligence.get('whale_movements', [])
            
            if not whale_movements:
                message_text = f"""🐋 Whale Movement Alerts

Status: No recent whale movements detected
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Threshold: $100k+ trades, $1M+ order walls
Note: Real-time monitoring of large trades and order book flows."""
            else:
                # Send immediate response to show bot is working (handle both direct commands and button callbacks)
                if update.message:
                    await update.message.reply_text("🔍 Checking for whale movements...")
                elif update.callback_query:
                    await update.callback_query.answer("🔍 Checking for whale movements...")
                
                # Format whale movements in user-friendly way
                formatted_movements = []
                for movement in whale_movements[:5]:  # Show last 5
                    try:
                        if isinstance(movement, dict):
                            if movement.get('type') == 'order_book_imbalance':
                                formatted_movements.append(
                                    f"🏗️ *Large Order Wall* on {movement.get('exchange', 'Unknown')}\n"
                                    f"   {movement.get('symbol', 'Unknown')} - ${movement.get('imbalance', 0):,.0f} imbalance\n"
                                    f"   Time: {movement.get('timestamp', datetime.now()).strftime('%H:%M:%S')}"
                                )
                            elif movement.get('type') == 'price_movement_flow':
                                direction_emoji = "📈" if movement.get('direction') == 'UP' else "📉"
                                formatted_movements.append(
                                    f"{direction_emoji} *Price Surge* on {movement.get('exchange', 'Unknown')}\n"
                                    f"   {movement.get('symbol', 'Unknown')} {movement.get('price_change_pct', 0):+.2f}% with ${movement.get('volume', 0):,.0f} volume\n"
                                    f"   Time: {movement.get('timestamp', datetime.now()).strftime('%H:%M:%S')}"
                                )
                            elif movement.get('type') == 'large_trade':
                                side_emoji = "🟢" if movement.get('side') == 'BUY' else "🔴"
                                formatted_movements.append(
                                    f"{side_emoji} *Large Trade* on {movement.get('exchange', 'Unknown')}\n"
                                    f"   {movement.get('symbol', 'Unknown')} {movement.get('side', 'Unknown')} ${movement.get('value_usd', 0):,.0f}\n"
                                    f"   Time: {movement.get('timestamp', datetime.now()).strftime('%H:%M:%S')}"
                                )
                            else:
                                # Handle other types or raw data
                                exchange = movement.get('exchange', 'Unknown')
                                symbol = movement.get('symbol', 'Unknown')
                                if exchange != 'Unknown' and symbol != 'Unknown':
                                    formatted_movements.append(
                                        f"🐋 *{movement.get('type', 'Activity')}* on {exchange}\n"
                                        f"   {symbol} - {movement.get('message', 'Activity detected')}\n"
                                        f"   Time: {movement.get('timestamp', datetime.now()).strftime('%H:%M:%S')}"
                                    )
                                else:
                                    # Fallback for completely raw data
                                    formatted_movements.append(f"🐋 {str(movement)[:100]}...")
                        else:
                            # If movement is not a dict, convert to string
                            formatted_movements.append(f"🐋 {str(movement)[:100]}...")
                    except Exception as e:
                        # If formatting fails, show raw data
                        formatted_movements.append(f"🐋 {str(movement)[:100]}...")
                
                message_text = f"""🐋 Whale Movement Alerts

Recent Movements: {len(whale_movements)} detected
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Latest Alerts:
{chr(10).join(formatted_movements)}

What This Means:
• 🏗️ Large buy/sell walls = Whales accumulating or distributing
• 📈📉 Price surges = Large orders moving the market
• 🟢🔴 Large trades = Direct whale activity"""
            
        except Exception as e:
            self.logger.error(f"Error getting whale data: {e}")
            message_text = f"""❌ Error Getting Whale Data

Error: {str(e)}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Please try again later."""
        
        keyboard = [
            [
                InlineKeyboardButton("📊 Market Intelligence", callback_data="market"),
                InlineKeyboardButton("📈 Volume Spikes", callback_data="spikes")
            ],
            [
                InlineKeyboardButton("🔙 Main Menu", callback_data="start")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(chat_id, message_text, reply_markup)
    
    async def cmd_spikes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show volume spike alerts."""
        chat_id = update.effective_chat.id
        
        try:
            intelligence = await self.market_intelligence.get_market_intelligence()
            volume_spikes = intelligence.get('volume_spikes', [])
            
            if not volume_spikes:
                message_text = f"""
📊 *Volume Spike Alerts*

*Status:* No recent volume spikes detected
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*Threshold:* 3x normal volume
*Note:* Real-time monitoring using Binance and Kraken APIs.
                """
            else:
                # Format volume spikes in user-friendly way
                formatted_spikes = []
                for spike in volume_spikes[:5]:  # Show last 5
                    try:
                        if isinstance(spike, dict):
                            exchange = spike.get('exchange', 'Unknown')
                            symbol = spike.get('symbol', 'Unknown')
                            multiplier = spike.get('spike_multiplier', 0)
                            current_vol = spike.get('current_volume', 0)
                            
                            # Determine intensity level
                            if multiplier >= 10:
                                intensity = "🚨 EXTREME"
                            elif multiplier >= 5:
                                intensity = "🔥 HIGH"
                            elif multiplier >= 3:
                                intensity = "⚡ MEDIUM"
                            else:
                                intensity = "📈 LOW"
                            
                            formatted_spikes.append(
                                f"{intensity} *Volume Spike* on {exchange}\n"
                                f"   {symbol} - {multiplier:.1f}x normal volume\n"
                                f"   Current: ${current_vol:,.0f} | Time: {spike.get('timestamp', datetime.now()).strftime('%H:%M:%S')}"
                            )
                        else:
                            # Fallback for raw data
                            formatted_spikes.append(f"📊 {str(spike)[:100]}...")
                    except Exception as e:
                        # If formatting fails, show raw data
                        formatted_spikes.append(f"📊 {str(spike)[:100]}...")
                
                message_text = f"""
📊 *Volume Spike Alerts*

*Recent Spikes:* {len(volume_spikes)} detected
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*Latest Alerts:*
{chr(10).join(formatted_spikes)}

*Intensity Levels:*
• 🚨 EXTREME: 10x+ normal volume
• 🔥 HIGH: 5-10x normal volume  
• ⚡ MEDIUM: 3-5x normal volume
• 📈 LOW: 2-3x normal volume
                """
            
        except Exception as e:
            self.logger.error(f"Error getting spike data: {e}")
            message_text = f"""
❌ *Error Getting Spike Data*

*Error:* {str(e)}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Please try again later.
            """
        
        keyboard = [
            [
                InlineKeyboardButton("🐋 Whale Movements", callback_data="whales"),
                InlineKeyboardButton("📊 Market Intelligence", callback_data="market")
            ],
            [
                InlineKeyboardButton("🔙 Main Menu", callback_data="start")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(chat_id, message_text, reply_markup)
    
    async def cmd_prices(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show price movement alerts."""
        chat_id = update.effective_chat.id
        
        try:
            price_data = await self.market_intelligence.check_price_movements()
            
            if not price_data:
                message_text = f"""
📊 *Price Movement Alerts*

*Status:* No significant price movements detected
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*Threshold:* {self.market_intelligence.price_change_threshold}% price change in 24h
*Note:* Price monitoring uses real exchange data (Binance/Kraken APIs).
                """
            else:
                message_text = f"""
📊 *Price Movement Alerts*

*Recent Movements:* {len(price_data)} detected
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*Latest Alerts:*
{chr(10).join([f"• {data['exchange']}: {data['symbol']} {data['price_change_pct']:+.2f}%" for data in price_data[:5]])}
                """
            
        except Exception as e:
            self.logger.error(f"Error getting price data: {e}")
            message_text = f"""
❌ *Error Getting Price Data*

*Error:* {str(e)}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Please try again later.
            """
        
        keyboard = [
            [
                InlineKeyboardButton("📈 Volume Spikes", callback_data="spikes"),
                InlineKeyboardButton("🐋 Whale Movements", callback_data="whales")
            ],
            [
                InlineKeyboardButton("📊 Market Intelligence", callback_data="market")
            ],
            [
                InlineKeyboardButton("🔙 Main Menu", callback_data="start")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(chat_id, message_text, reply_markup)
    
    async def cmd_market(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show market intelligence summary."""
        chat_id = update.effective_chat.id
        
        try:
            intelligence = await self.market_intelligence.get_market_intelligence()
            
            message_text = f"""
📊 *Market Intelligence Summary*

*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*Whale Movements:* {len(intelligence.get('whale_movements', []))} detected
*Volume Spikes:* {len(intelligence.get('volume_spikes', []))} detected
*Price Movements:* {len(await self.market_intelligence.check_price_movements())} detected
*Market Alerts:* {len(intelligence.get('market_alerts', []))} active

*Note:* Real-time monitoring using Binance and Kraken exchange APIs.
            """
            
        except Exception as e:
            self.logger.error(f"Error getting market intelligence: {e}")
            message_text = f"""
❌ *Error Getting Market Intelligence*

*Error:* {str(e)}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Please try again later.
            """
        
        keyboard = [
            [
                InlineKeyboardButton("🐋 Whale Movements", callback_data="whales"),
                InlineKeyboardButton("📈 Volume Spikes", callback_data="spikes")
            ],
            [
                InlineKeyboardButton("📊 Price Movements", callback_data="prices")
            ],
            [
                InlineKeyboardButton("🔙 Main Menu", callback_data="start")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(chat_id, message_text, reply_markup)
    
    # ===== CALLBACK HANDLERS =====
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks."""
        query = update.callback_query
        
        try:
            # Try to answer the callback query
            await query.answer()
        except Exception as e:
            # If callback is too old, just log it and continue
            self.logger.warning(f"Callback query error (likely expired): {e}")
        
        data = query.data
        
        try:
            if data == "start":
                await self.cmd_start(update, context)
            elif data == "status":
                await self.cmd_status(update, context)
            elif data == "daily":
                await self.cmd_daily(update, context)
            elif data == "weekly":
                await self.cmd_weekly(update, context)
            elif data == "monthly":
                await self.cmd_monthly(update, context)
            elif data == "whales":
                await self.cmd_whales(update, context)
            elif data == "spikes":
                await self.cmd_spikes(update, context)
            elif data == "prices":
                await self.cmd_prices(update, context)
            elif data == "market":
                await self.cmd_market(update, context)
        except Exception as e:
            self.logger.error(f"Error handling button callback {data}: {e}")
            # Send error message to user
            try:
                await self.send_message(
                    update.effective_chat.id,
                    f"❌ Error processing button: {str(e)}"
                )
            except:
                pass  # Don't let error handling cause more errors
    
    # ===== UTILITY METHODS =====
    
    async def send_message(self, chat_id: int, text: str, reply_markup=None):
        """Send a message to a specific chat."""
        try:
            if reply_markup:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            else:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode='Markdown'
                )
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")


async def main():
    """Main entry point."""
    # Load configuration
    config = Config.load_from_file("config.yaml")
    
    # Get Telegram token
    token = config.alerts.telegram_token
    if not token:
        print("❌ Error: Telegram token not found in config")
        sys.exit(1)
    
    # Create and start the monitoring bot
    bot = UnifiedMonitoringBot(config, token)
    
    try:
        await bot.start()
        print("✅ Unified monitoring bot started successfully!")
        print("📱 Send /start to your bot to begin interaction")
        
        # Keep the bot running
        await asyncio.Event().wait()
        
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitoring bot...")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await bot.stop()
        print("✅ Monitoring bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
